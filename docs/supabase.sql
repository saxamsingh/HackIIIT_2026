-- Tables for DB_BACKEND=supabase. Run once in the Supabase SQL editor.
-- Column names match backend/app/db.py (the SQLite schema is the same shape). Row-level security is
-- left off for the hackathon demo: use the service key on the server only and never ship it to the web app.

create table if not exists farmers (
    id text primary key, name text not null, phone text, state text not null, district text not null,
    crops jsonb not null default '[]', land_acres double precision not null,
    category text not null, language text not null, documents jsonb not null default '[]',
    created_at timestamptz not null);

create table if not exists runs (
    id text primary key, kind text not null, status text not null, target text not null,
    streaming_url text, video_url text, result jsonb, error jsonb, steps integer, cost_credits double precision,
    mode text not null, created_at timestamptz not null, updated_at timestamptz not null);

create table if not exists alerts (
    id text primary key, farmer_id text, type text not null, title text not null, detail text not null,
    source_url text not null, evidence jsonb not null default '[]', claim_id text,
    created_at timestamptz not null);

create table if not exists ledger (
    id text primary key, farmer_id text not null, kind text not null, amount_rs double precision not null,
    formula text not null, confirmed boolean not null, created_at timestamptz not null);

create table if not exists tickets (
    id text primary key, farmer_id text, intent text not null, query text not null, reason text not null,
    status text not null, created_at timestamptz not null);


-- Twilio WhatsApp webhook idempotency. MessageSid is the primary key so provider retries are safe.
create table if not exists channel_messages (
    id text primary key, sender text not null, status text not null, reply text, updated_at timestamptz not null);
