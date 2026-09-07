-- Run log (memory): one row per completed run, written once at the end.
-- Separate in purpose from the LangGraph checkpointer tables (created by
-- PostgresSaver.setup()), but living in the same Supabase Postgres.

create table if not exists market_map_runs (
    run_id                          text primary key,
    topic                           text not null,
    confirmed_scope_summary         jsonb not null default '{}'::jsonb,
    num_layers                      integer not null default 0,

    companies_found                 integer not null default 0,
    companies_verified              integer not null default 0,
    companies_under_corroborated    integer not null default 0,
    rejected_failed_corroboration   integer not null default 0,
    rejected_failed_category_fit    integer not null default 0,
    rejected_failed_existence       integer not null default 0,
    layers_reformulated             integer not null default 0,
    layers_over_cap                 integer not null default 0,

    rescope_count                   integer not null default 0,
    cap_hit                         boolean not null default false,
    direct_edit_takeover            boolean not null default false,

    -- backfilled from LangSmith when tracing is on; null in stub mode
    cost_usd                        numeric,
    total_tokens                    integer,
    latency_s                       numeric,

    warnings                        jsonb not null default '[]'::jsonb,
    created_at                      timestamptz not null default now()
);

create index if not exists market_map_runs_created_at_idx
    on market_map_runs (created_at desc);
create index if not exists market_map_runs_topic_idx
    on market_map_runs (topic);
