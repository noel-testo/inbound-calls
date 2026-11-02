"""Post-call pipeline for a verified `post_call_transcription` webhook (SPEC §8, §11).

Order: ingest into Neon → score → Notion "Call transcripts" row → Notion "Cody leads" row → Apollo
(qualified callers only) → lead row updated with the Apollo links → Slack alert (qualified only).

Idempotent: the verified payload is stored on the `calls` row before anything else, every external
id is written back to Neon as soon as it exists, and each step skips work whose id is already
recorded. Apollo call records also upsert on `call_identifier` (the ElevenLabs conversation id).
A claim column stops two deliveries of the same conversation running at once. A failed step is
logged to `events` and leaves `processed_at` null, so `scripts/replay_post_call.py` can finish it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from agent import extraction as extraction_mod
from agent import log
from agent.notion import client as n
from agent.phone import is_mobile, to_e164
from agent.scoring import is_qualified
from agent.slack import qualified_call_text

ROOT = Path(__file__).resolve().parents[1]
APOLLO_APP = "https://app.apollo.io/#"
RELATIONSHIP = {"existing_customer": "customer", "supplier_or_sales": "supplier", "other": "other"}


@dataclass
class Services:
    store: object
    settings: object
    notion: object | None = None
    apollo: object | None = None
    slack: object | None = None


@dataclass
class Facts:
    conversation_id: str
    caller_e164: str | None
    called_number: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_s: int | None
    turns: list[tuple[str, str, datetime]] = field(default_factory=list)
    summary: str | None = None
    termination_reason: str = ""
    extraction: dict = field(default_factory=dict)


def parse(payload: dict) -> Facts:
    data = payload.get("data") or {}
    meta = data.get("metadata") or {}
    phone_call = meta.get("phone_call") or {}
    dyn = (data.get("conversation_initiation_client_data") or {}).get("dynamic_variables") or {}

    start_unix = meta.get("start_time_unix_secs")
    started = datetime.fromtimestamp(start_unix, UTC) if start_unix else None
    duration = meta.get("call_duration_secs")
    ended = started + timedelta(seconds=duration) if started and duration is not None else None

    turns = []
    base = started or datetime.now(UTC)
    for t in data.get("transcript") or []:
        text = (t.get("message") or "").strip()
        if not text:
            continue
        role = "agent" if t.get("role") == "agent" else "caller"
        turns.append((role, text, base + timedelta(seconds=t.get("time_in_call_secs") or 0)))

    analysis = data.get("analysis") or {}
    return Facts(
        conversation_id=data["conversation_id"],
        caller_e164=to_e164(phone_call.get("external_number") or dyn.get("system__caller_id")),
        called_number=to_e164(phone_call.get("agent_number") or dyn.get("system__called_number")),
        started_at=started,
        ended_at=ended,
        duration_s=duration,
        turns=turns,
        summary=(analysis.get("transcript_summary") or "").strip() or None,
        termination_reason=str(meta.get("termination_reason") or ""),
        extraction=extraction_mod.parse(analysis.get("data_collection_results")),
    )


def outcome_for(call: dict, facts: Facts, qualified: bool, messages: list[dict]) -> str:
    if call.get("booking_id"):
        return "discovery_booked"
    if "max" in facts.termination_reason.lower() and "duration" in facts.termination_reason.lower():
        return "max_duration"
    if qualified:
        return "qualified_not_booked"
    categories = {m["category"] for m in messages}
    if "support" in categories:
        return "support_message"
    if "supplier" in categories:
        return "supplier_logged"
    if categories:
        return "message_taken"
    if not any(role == "caller" for role, _, _ in facts.turns):
        return "abandoned"
    return "no_action"


async def _scoring_config(store) -> dict:
    cfg = await store.load_config("scoring")
    return cfg or yaml.safe_load((ROOT / "config" / "scoring.yaml").read_text())


def notion_url(page_id: str | None) -> str | None:
    return f"https://www.notion.so/{page_id.replace('-', '')}" if page_id else None


def apollo_url(kind: str, object_id: str | None) -> str | None:
    return f"{APOLLO_APP}/{kind}/{object_id}" if object_id else None


@dataclass
class Run:
    svc: Services
    facts: Facts
    call: dict
    caller: dict | None
    points: int
    qualified: bool
    outcome: str
    failures: list[str] = field(default_factory=list)

    @property
    def x(self) -> dict:
        return self.facts.extraction

    @property
    def cid(self) -> str:
        return self.facts.conversation_id

    @property
    def name(self) -> str | None:
        return self.x.get("caller_name") or (self.caller or {}).get("name")

    @property
    def organisation(self) -> str | None:
        return self.x.get("organisation") or (self.caller or {}).get("organisation")

    @property
    def email(self) -> str | None:
        return self.x.get("contact_email") or (self.caller or {}).get("email")

    @property
    def known_caller(self) -> bool:
        """True if Cody had this number on record before this call started."""
        seen, start = (self.caller or {}).get("first_seen_at"), self.facts.started_at
        return bool(seen and start and seen < start)

    def local_time(self) -> datetime:
        when = self.facts.started_at or datetime.now(UTC)
        return when.astimezone(ZoneInfo(self.svc.settings.business_tz))

    async def save(self, **cols) -> None:
        await self.svc.store.update_call(self.cid, **cols)
        self.call.update(cols)

    async def step(self, name: str, fn) -> None:
        try:
            await fn()
        except Exception as e:
            self.failures.append(name)
            log.event("post_call_step_failed", call_id=self.cid, step=name, error=str(e))
            await self.svc.store.log_event(
                self.call["id"], "post_call_step_failed", {"step": name, "error": str(e)}
            )

    # ---- Notion ----

    def _transcript_blocks(self) -> list[dict]:
        start = self.facts.started_at
        blocks = []
        for role, text, ts in self.facts.turns:
            offset = int((ts - start).total_seconds()) if start else 0
            who = "Cody" if role == "agent" else "Caller"
            blocks.append(n.paragraph(f"[{offset // 60:02d}:{offset % 60:02d}] {who}: {text}"))
        return blocks

    async def notion_transcript(self) -> None:
        settings, notion = self.svc.settings, self.svc.notion
        if not (notion and settings.notion_transcripts_db_id) or self.call.get(
            "notion_transcript_page_id"
        ):
            return
        db = settings.notion_transcripts_db_id
        page_id = await notion.find_by_conversation(db, self.cid)
        if not page_id:
            props = {
                "Name": n.title(
                    f"{self.local_time():%d %b %Y %H:%M} — {self.name or 'Unknown caller'}"
                ),
                "Conversation ID": n.rich(self.cid),
                "Call time": n.date(
                    self.facts.started_at.isoformat() if self.facts.started_at else None
                ),
                "Caller": n.rich(self.name),
                "Company": n.rich(self.organisation),
                "Outcome": n.select(self.outcome),
                "Summary": n.rich(self.facts.summary),
            }
            page_id = (await notion.create_page(db, props, self._transcript_blocks()))["id"]
        await self.save(notion_transcript_page_id=page_id)

    def _lead_properties(self) -> dict:
        x = self.x
        return {
            "Name": n.title(self.name or "Unknown caller"),
            "Conversation ID": n.rich(self.cid),
            "Call time": n.date(
                self.facts.started_at.isoformat() if self.facts.started_at else None
            ),
            "Phone": n.phone(self.facts.caller_e164),
            "Email": n.email(self.email),
            "Organisation": n.rich(self.organisation),
            "Role": n.select(x.get("caller_role")),
            "Intent": n.select(x.get("intent")),
            "Outcome": n.select(self.outcome),
            "Lead score": n.number(self.points),
            "Qualified": n.checkbox(self.qualified),
            "Known caller": n.checkbox(self.known_caller),
            "Assets": n.multi(x.get("asset_type")),
            "Estate size": n.number(x.get("estate_size")),
            "Estate unit": n.select(x.get("estate_size_unit") if x.get("estate_size") else None),
            "Connectivity": n.select(x.get("current_connectivity")),
            "Driver": n.select(x.get("driver")),
            "Timeline": n.select(x.get("timeline")),
            "Decision authority": n.select(x.get("decision_authority")),
            "Duration (s)": n.number(self.facts.duration_s),
            "Summary": n.rich(self.facts.summary),
            "Apollo contact": n.url(apollo_url("contacts", self.call.get("apollo_contact_id"))),
            "Apollo account": n.url(apollo_url("accounts", self.call.get("apollo_account_id"))),
            "Apollo deal": n.url(apollo_url("opportunities", self.call.get("apollo_deal_id"))),
            "Transcript": n.url(notion_url(self.call.get("notion_transcript_page_id"))),
        }

    async def notion_lead(self) -> None:
        settings, notion = self.svc.settings, self.svc.notion
        if not (notion and settings.notion_leads_db_id):
            return
        db = settings.notion_leads_db_id
        props = self._lead_properties()
        page_id = self.call.get("notion_lead_page_id") or await notion.find_by_conversation(
            db, self.cid
        )
        if page_id:
            await notion.update_page(page_id, props)
        else:
            props["Review"] = n.select("To review")
            page_id = (await notion.create_page(db, props))["id"]
        if page_id != self.call.get("notion_lead_page_id"):
            await self.save(notion_lead_page_id=page_id)

    # ---- Apollo (qualified callers only) ----

    def _contact_fields(self, account_id: str | None) -> dict:
        first, _, last = (self.name or "").partition(" ")
        phone = self.facts.caller_e164
        fields = {
            "first_name": first or None,
            "last_name": last or None,
            "email": self.email,
            "organization_name": self.organisation,
            "account_id": account_id,
        }
        if phone:
            fields["mobile_phone" if is_mobile(phone) else "direct_phone"] = phone
        return {k: v for k, v in fields.items() if v}

    def _note(self) -> str:
        lines = [
            f"Inbound call answered by Cody (AI receptionist), {self.local_time():%d %b %Y %H:%M}.",
            f"Outcome: {self.outcome.replace('_', ' ')}. Lead score: {self.points}.",
        ]
        if self.facts.summary:
            lines += ["", self.facts.summary]
        lead_url = notion_url(self.call.get("notion_lead_page_id"))
        if lead_url:
            lines += ["", f"Review in Notion: {lead_url}"]
        lines += ["", f"ElevenLabs conversation: {self.cid}"]
        return "\n".join(lines)

    async def _remember(self, **ids) -> None:
        await self.save(**ids)
        if self.caller:
            await self.svc.store.update_caller(self.caller["id"], **ids)
            self.caller.update(ids)

    async def apollo(self) -> None:
        apollo, settings, store = self.svc.apollo, self.svc.settings, self.svc.store
        if not (apollo and self.qualified):
            return
        caller = self.caller or {}

        account_id = self.call.get("apollo_account_id") or caller.get("apollo_account_id")
        if not account_id and self.organisation:
            account = await apollo.find_account(self.organisation)
            account = account or await apollo.create_account(self.organisation)
            account_id = account["id"]
        if account_id and account_id != self.call.get("apollo_account_id"):
            await self._remember(apollo_account_id=account_id)

        fields = self._contact_fields(account_id)
        contact_id = self.call.get("apollo_contact_id") or caller.get("apollo_contact_id")
        if contact_id:
            await apollo.update_contact(contact_id, fields)
        else:
            existing = await apollo.find_contact_by_email(self.email) if self.email else None
            if existing:
                contact_id = (await apollo.update_contact(existing["id"], fields))["id"]
            else:
                contact_id = (await apollo.create_contact(fields))["id"]
        if contact_id != self.call.get("apollo_contact_id"):
            await self._remember(apollo_contact_id=contact_id)

        record = await apollo.log_call(
            call_identifier=self.cid,
            contact_id=contact_id,
            account_id=account_id,
            from_number=self.facts.caller_e164,
            to_number=self.facts.called_number or settings.did,
            start_time=self.facts.started_at.isoformat() if self.facts.started_at else None,
            end_time=self.facts.ended_at.isoformat() if self.facts.ended_at else None,
            duration=self.facts.duration_s,
            note=self._note(),
            user_id=settings.apollo_user_id,
        )
        if record.get("id") != self.call.get("apollo_call_id"):
            await self.save(apollo_call_id=record.get("id"))

        if settings.apollo_create_deals and not self.call.get("apollo_deal_id"):
            if account_id:
                deal = await apollo.create_deal(
                    name=f"{self.organisation} — inbound call {self.local_time():%d %b %Y}",
                    account_id=account_id,
                    owner_id=settings.apollo_user_id,
                    stage_id=settings.apollo_deal_stage_id,
                )
                await self.save(apollo_deal_id=deal["id"])
            else:
                await store.log_event(
                    self.call["id"], "apollo_deal_skipped", {"reason": "no organisation"}
                )

        if not self.call.get("apollo_task_id"):
            if settings.apollo_user_id:
                due = datetime.now(UTC) + timedelta(hours=settings.apollo_task_due_hours)
                who = self.name or "the caller"
                if self.organisation:
                    who = f"{who} ({self.organisation})"
                task = await apollo.create_task(
                    user_id=settings.apollo_user_id,
                    contact_id=contact_id,
                    due_at=due.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    title=f"Follow up Cody call: {who}",
                    note=self._note(),
                )
                await self.save(apollo_task_id=task["id"])
            else:
                await store.log_event(
                    self.call["id"], "apollo_task_skipped", {"reason": "APOLLO_USER_ID unset"}
                )

    # ---- Slack (qualified callers only) ----

    async def slack(self) -> None:
        if not (self.svc.slack and self.qualified) or self.call.get("slack_alerted_at"):
            return
        await self.svc.slack.post(
            qualified_call_text(
                name=self.name,
                organisation=self.organisation,
                phone=self.facts.caller_e164,
                email=self.email,
                score=self.points,
                outcome=self.outcome,
                summary=self.facts.summary,
                notion_url=notion_url(self.call.get("notion_lead_page_id")),
                apollo_contact_url=apollo_url("contacts", self.call.get("apollo_contact_id")),
            )
        )
        await self.save(slack_alerted_at=datetime.now(UTC))


async def process(svc: Services, conversation_id: str) -> str:
    """Run (or finish) the pipeline for one stored conversation. Returns a short status."""
    store = svc.store
    call = await store.get_call(conversation_id)
    if not call or not call.get("post_call_payload"):
        return "missing"
    if call.get("processed_at"):
        return "already_processed"
    if not await store.claim(conversation_id):
        return "in_progress"
    try:
        facts = parse(call["post_call_payload"])
        call = await store.ingest(
            conversation_id,
            caller_e164=facts.caller_e164,
            called_number=facts.called_number,
            started_at=facts.started_at,
            ended_at=facts.ended_at,
            duration_s=facts.duration_s,
            turns=facts.turns,
        )
        x = facts.extraction
        points, qualified = is_qualified(x, await _scoring_config(store))
        messages = await store.messages_for(call["id"])
        outcome = outcome_for(call, facts, qualified, messages)

        caller = None
        if facts.caller_e164:
            caller = await store.upsert_caller(
                facts.caller_e164,
                name=x.get("caller_name"),
                email=x.get("contact_email"),
                organisation=x.get("organisation"),
                relationship=RELATIONSHIP.get(x.get("intent"), "lead"),
                last_call_at=facts.started_at,
            )
            await store.link_caller(conversation_id, caller["id"])

        run = Run(svc, facts, call, caller, points, qualified, outcome)
        await run.save(
            intent=x.get("intent") or "unknown",
            extraction=x,
            lead_score=points,
            high_value=qualified,
            outcome=outcome,
            summary=facts.summary,
        )
        await run.step("notion_transcript", run.notion_transcript)
        await run.step("notion_lead", run.notion_lead)
        await run.step("apollo", run.apollo)
        if qualified and svc.apollo:
            await run.step("notion_lead_apollo_links", run.notion_lead)
        await run.step("slack", run.slack)

        if run.failures:
            log.event("post_call_incomplete", call_id=conversation_id, failed=run.failures)
            return "incomplete"
        await run.save(processed_at=datetime.now(UTC))
        log.event("post_call_done", call_id=conversation_id, outcome=outcome, qualified=qualified)
        return "processed"
    finally:
        await store.release(conversation_id)
