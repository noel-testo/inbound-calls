"""HTTPS webhook service that ElevenLabs calls (SPEC §4.1, §7, §8).

    POST /elevenlabs/conversation-init   caller lookup at call start (X-Cody-Secret)
    POST /tools/check_availability       Cal.com slots (X-Cody-Secret)
    POST /tools/book_meeting             Cal.com booking (X-Cody-Secret)
    POST /tools/take_message             Neon message (X-Cody-Secret)
    POST /elevenlabs/post-call           post_call_transcription (HMAC ElevenLabs-Signature)
    GET  /healthz

The post-call receiver verifies the signature on the raw body, stores the payload in Neon, answers
200 and runs the pipeline in the background, so ElevenLabs never waits on Notion or Apollo.

    uv run uvicorn agent.app:create_app --factory --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from agent import conversation_init, log, post_call, tools
from agent.security import (
    SECRET_HEADER,
    SIGNATURE_HEADER,
    SignatureError,
    secret_ok,
    verify_signature,
)
from agent.settings import Settings


def build_services(settings: Settings, store) -> post_call.Services:
    from agent.apollo import ApolloClient
    from agent.notion import NotionClient
    from agent.slack import SlackNotifier

    return post_call.Services(
        store=store,
        settings=settings,
        notion=NotionClient(settings.notion_api_key) if settings.notion_api_key else None,
        apollo=ApolloClient(settings.apollo_api_key) if settings.apollo_api_key else None,
        slack=SlackNotifier(settings.slack_webhook_url) if settings.slack_webhook_url else None,
    )


def create_app(
    settings: Settings | None = None,
    *,
    store=None,
    calcom=None,
    services: post_call.Services | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    log.configure()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.store is None:
            from agent.store import Store

            if not settings.database_url:
                raise RuntimeError("DATABASE_URL is not set")
            app.state.store = await Store.connect(settings.database_url)
        if app.state.calcom is None:
            from agent.calcom import CalComClient

            app.state.calcom = CalComClient.from_env()
        if app.state.services is None:
            app.state.services = build_services(settings, app.state.store)
        yield
        await app.state.store.close()

    app = FastAPI(title="Cody webhook service", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.store = store
    app.state.calcom = calcom
    app.state.services = services

    def require_secret(request: Request) -> None:
        if not secret_ok(request.headers.get(SECRET_HEADER), settings.tool_secret):
            raise HTTPException(status_code=401, detail="unauthorised")

    async def json_body(request: Request) -> dict:
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise HTTPException(status_code=400, detail="invalid JSON") from e
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="expected a JSON object")
        return body

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.post("/elevenlabs/conversation-init")
    async def conversation_init_hook(request: Request):
        require_secret(request)
        return await conversation_init.handle(app.state.store, settings, await json_body(request))

    @app.post("/tools/check_availability")
    async def check_availability(request: Request):
        require_secret(request)
        body = await json_body(request)
        return await tools.check_availability(app.state.store, app.state.calcom, body)

    @app.post("/tools/book_meeting")
    async def book_meeting(request: Request):
        require_secret(request)
        body = await json_body(request)
        return await tools.book_meeting(app.state.store, app.state.calcom, body)

    @app.post("/tools/take_message")
    async def take_message(request: Request):
        require_secret(request)
        return await tools.take_message(app.state.store, await json_body(request))

    @app.post("/elevenlabs/post-call")
    async def post_call_hook(request: Request, background: BackgroundTasks):
        raw = await request.body()
        try:
            verify_signature(raw, request.headers.get(SIGNATURE_HEADER), settings.webhook_secret)
        except SignatureError as e:
            log.event("post_call_rejected", reason=str(e))
            return JSONResponse({"error": "invalid signature"}, status_code=401)
        payload = json.loads(raw)
        if payload.get("type") != "post_call_transcription":
            log.event("post_call_ignored", type=payload.get("type"))
            return {"received": True, "ignored": payload.get("type")}
        conversation_id = (payload.get("data") or {}).get("conversation_id")
        if not conversation_id:
            return JSONResponse({"error": "missing conversation_id"}, status_code=400)
        call = await app.state.store.record_post_call(conversation_id, payload)
        log.event(
            "post_call_received",
            call_id=conversation_id,
            already_processed=bool(call.get("processed_at")),
        )
        if not call.get("processed_at"):
            background.add_task(_run_pipeline, app.state.services, conversation_id)
        return {"received": True}

    return app


async def _run_pipeline(services: post_call.Services, conversation_id: str) -> None:
    try:
        status = await post_call.process(services, conversation_id)
        log.event("post_call_status", call_id=conversation_id, status=status)
    except Exception as e:
        log.event("post_call_error", call_id=conversation_id, error=str(e))
