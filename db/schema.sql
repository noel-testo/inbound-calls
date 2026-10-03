-- Inbound Calls — Neon database `receptionist`
-- Applied idempotently by db/migrate.py. Keep every statement re-runnable.

create extension if not exists pgcrypto;

do $$ begin
  create type call_intent as enum ('new_enquiry','existing_customer','supplier_or_sales','other','unknown');
exception when duplicate_object then null; end $$;

do $$ begin
  create type call_outcome as enum (
    'discovery_booked','qualified_not_booked','message_taken','support_message',
    'supplier_logged','no_action','abandoned','max_duration','error'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type transcript_role as enum ('agent','caller','system');
exception when duplicate_object then null; end $$;

create table if not exists calls (
  id                 uuid primary key default gen_random_uuid(),
  livekit_room       text unique,
  started_at         timestamptz not null default now(),
  ended_at           timestamptz,
  duration_s         integer,
  caller_e164        text,
  cli_present        boolean not null default true,
  intent             call_intent not null default 'unknown',
  outcome            call_outcome,
  lead_score         integer,
  high_value         boolean,
  extraction         jsonb,                 -- authoritative post-call extraction (§6)
  extraction_draft   jsonb,                 -- the agent's in-call draft
  hubspot_contact_id text,
  hubspot_company_id text,
  hubspot_deal_id    text,
  hubspot_meeting_id text,
  hubspot_call_id    text,
  recording_path     text,
  model_versions     jsonb,                 -- {stt, llm, tts, turn_detector}
  processed_at       timestamptz,           -- set by Windmill post_call finalise
  created_at         timestamptz not null default now()
);
create index if not exists calls_started_at_idx on calls (started_at desc);
create index if not exists calls_caller_idx on calls (caller_e164);

create table if not exists transcripts (
  call_id    uuid not null references calls(id) on delete cascade,
  seq        integer not null,
  role       transcript_role not null,
  text       text not null,
  ts         timestamptz not null,
  primary key (call_id, seq)
);

create table if not exists events (
  id        bigserial primary key,
  call_id   uuid references calls(id) on delete cascade,
  ts        timestamptz not null default now(),
  type      text not null,                  -- tool_call, tool_error, turn_latency, guardrail, post_call_undelivered, ...
  payload   jsonb not null default '{}'::jsonb
);
create index if not exists events_call_idx on events (call_id, ts);
create index if not exists events_type_idx on events (type, ts desc);

create table if not exists messages (
  id              uuid primary key default gen_random_uuid(),
  call_id         uuid not null references calls(id) on delete cascade,
  category        text not null,            -- enquiry, support, supplier, other
  summary         text not null,
  callback_number text,
  urgency         text not null default 'normal',  -- normal, high
  site            text,
  hubspot_object_id text,                   -- note or task id once delivered
  created_at      timestamptz not null default now()
);

create table if not exists config (
  key        text primary key,              -- prompt, greeting, scoring, business_hours, ...
  value      jsonb not null,
  updated_at timestamptz not null default now()
);

create table if not exists terms (
  term       text primary key,
  category   text not null,                 -- product, standard, staff, client, place
  weight     real not null default 1.0,
  active     boolean not null default true,
  updated_at timestamptz not null default now()
);

create or replace view calls_today as
  select id, started_at, duration_s, caller_e164, intent, outcome, lead_score, high_value, processed_at
  from calls
  where started_at >= (now() at time zone 'Europe/London')::date
  order by started_at desc;
