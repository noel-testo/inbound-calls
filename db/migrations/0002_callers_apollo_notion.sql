-- 0002 — HubSpot removed; Cody's own caller directory; Apollo + Notion ids; ElevenLabs conversation id.
-- Re-runnable: every statement is guarded. Applied by db/migrate.py; never run by hand against production.

-- Cody's caller directory: the conversation-init lookup matches the caller's E.164 number here, because
-- Apollo cannot search by phone. Holds only what the lookup and greeting need, plus the Apollo link ids.
create table if not exists callers (
  id                uuid primary key default gen_random_uuid(),
  phone_e164        text not null unique,
  name              text,
  email             text,
  organisation      text,
  relationship      text not null default 'lead',   -- lead, customer, supplier, other
  apollo_contact_id text,
  apollo_account_id text,
  first_seen_at     timestamptz not null default now(),
  last_call_at      timestamptz,
  updated_at        timestamptz not null default now()
);

-- calls: the ElevenLabs conversation id replaces the LiveKit room name (same unique column, renamed).
do $$ begin
  if exists (select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'calls' and column_name = 'livekit_room') then
    alter table calls rename column livekit_room to conversation_id;
  end if;
  if exists (select 1 from pg_constraint where conname = 'calls_livekit_room_key') then
    alter table calls rename constraint calls_livekit_room_key to calls_conversation_id_key;
  end if;
end $$;

alter table calls drop column if exists hubspot_contact_id;
alter table calls drop column if exists hubspot_company_id;
alter table calls drop column if exists hubspot_deal_id;
alter table calls drop column if exists hubspot_meeting_id;
alter table calls drop column if exists hubspot_call_id;

alter table calls add column if not exists caller_id                 uuid references callers(id);
alter table calls add column if not exists called_number             text;
alter table calls add column if not exists summary                   text;
alter table calls add column if not exists booking_id                text;          -- Cal.com booking uid
alter table calls add column if not exists post_call_payload         jsonb;         -- verified webhook body, for replay
alter table calls add column if not exists post_call_lock_until      timestamptz;   -- claim, so concurrent deliveries don't race
alter table calls add column if not exists apollo_contact_id         text;
alter table calls add column if not exists apollo_account_id         text;
alter table calls add column if not exists apollo_call_id            text;
alter table calls add column if not exists apollo_deal_id            text;
alter table calls add column if not exists apollo_task_id            text;
alter table calls add column if not exists notion_lead_page_id       text;
alter table calls add column if not exists notion_transcript_page_id text;
alter table calls add column if not exists slack_alerted_at          timestamptz;

create index if not exists calls_caller_id_idx on calls (caller_id);
create index if not exists calls_unprocessed_idx on calls (ended_at) where processed_at is null;

alter table messages drop column if exists hubspot_object_id;
