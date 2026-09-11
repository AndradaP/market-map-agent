-- Company registry: persistent, cross-run, cross-topic company identity.
-- Each layer's search->extract->corroborate pipeline runs in isolation per
-- run (see execute.py), so without this the same real company gets
-- re-litigated from scratch by search luck every time it's encountered
-- under a different topic or layer -- seen live: Nscale scored 4 independent
-- sources under one topic, 1 under an adjacent one, same real company.

create table if not exists company_registry (
    canonical_host   text primary key,
    canonical_name   text not null,
    sources          jsonb not null default '[]'::jsonb,  -- [{url, title}]
    topics_seen      text[] not null default '{}',
    times_seen       integer not null default 1,
    first_seen_at    timestamptz not null default now(),
    last_seen_at     timestamptz not null default now()
);

create index if not exists company_registry_last_seen_idx
    on company_registry (last_seen_at desc);
