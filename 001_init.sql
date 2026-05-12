-- =====================================================================
-- Prague Rentals — initial schema
-- Run in Supabase SQL Editor (or via supabase CLI migration)
-- =====================================================================

-- Extensions
create extension if not exists "uuid-ossp";
create extension if not exists postgis;       -- geo lookups for map
create extension if not exists pg_trgm;       -- fuzzy dedup on title/address

-- =====================================================================
-- listings: kanonický zápis inzerátu (jeden řádek = jedna nabídka na zdroji)
-- =====================================================================
create table if not exists listings (
  id              uuid primary key default uuid_generate_v4(),

  -- původ
  source          text not null,                 -- 'sreality', 'bezrealitky', 'flatio', ...
  source_id       text not null,                 -- ID na původním portálu
  url             text not null,

  -- obsah
  title           text,
  description     text,
  price_czk       int,                           -- měsíčně, vše v CZK (EUR přepočítáme při ingestu)
  price_includes_utilities boolean,
  deposit_czk     int,
  size_m2         numeric(6,1),
  rooms           text,                          -- '1+kk', '2+1', 'studio'
  furnished       boolean,

  -- lokalita
  district        text,                          -- 'Praha 2', 'Praha 7'
  address         text,
  location        geography(point, 4326),        -- PostGIS bod (lon, lat)

  -- časová stopa (důležité pro analýzu trhu)
  scraped_at      timestamptz not null default now(),
  first_seen_at   timestamptz not null default now(),
  last_seen_at    timestamptz not null default now(),
  delisted_at     timestamptz,                   -- nastav až přestane být v nálezech

  -- syrový JSON pro audit + budoucí evoluci schématu
  raw             jsonb not null,

  -- deduplikace přes fingerprint (pHash + cena + velikost) — vyplníme později
  fingerprint     text,

  unique (source, source_id)
);

-- indexy pro typické UI dotazy
create index if not exists idx_listings_price        on listings (price_czk);
create index if not exists idx_listings_size         on listings (size_m2);
create index if not exists idx_listings_district     on listings (district);
create index if not exists idx_listings_first_seen   on listings (first_seen_at desc);
create index if not exists idx_listings_active       on listings (delisted_at) where delisted_at is null;
create index if not exists idx_listings_location     on listings using gist (location);
create index if not exists idx_listings_title_trgm   on listings using gin (title gin_trgm_ops);
create index if not exists idx_listings_raw          on listings using gin (raw);

-- =====================================================================
-- price_history: pro trendy a detekci slev
-- =====================================================================
create table if not exists price_history (
  id          bigserial primary key,
  listing_id  uuid not null references listings(id) on delete cascade,
  price_czk   int not null,
  observed_at timestamptz not null default now()
);

create index if not exists idx_price_history_listing on price_history (listing_id, observed_at desc);

-- =====================================================================
-- scrape_runs: monitoring běhů scraperů
-- =====================================================================
create table if not exists scrape_runs (
  id            bigserial primary key,
  source        text not null,
  started_at    timestamptz not null default now(),
  finished_at   timestamptz,
  status        text not null default 'running', -- 'running' | 'ok' | 'error'
  items_seen    int default 0,
  items_new     int default 0,
  items_updated int default 0,
  error_message text
);

create index if not exists idx_scrape_runs_source_started on scrape_runs (source, started_at desc);

-- =====================================================================
-- View pro UI — aktivní inzeráty se základními agregáty
-- =====================================================================
create or replace view v_active_listings as
select
  l.*,
  case
    when l.size_m2 > 0 then round((l.price_czk / l.size_m2)::numeric, 0)
    else null
  end as price_per_m2,
  st_x(l.location::geometry) as lon,
  st_y(l.location::geometry) as lat,
  extract(epoch from (now() - l.first_seen_at)) / 86400 as days_on_market
from listings l
where l.delisted_at is null;

-- =====================================================================
-- Row Level Security — UI bude číst přes anon klíč
-- =====================================================================
alter table listings enable row level security;
alter table price_history enable row level security;

-- read-only přístup pro anonymní (frontend)
create policy "public read listings"
  on listings for select
  to anon, authenticated
  using (true);

create policy "public read price history"
  on price_history for select
  to anon, authenticated
  using (true);

-- write přístup má jen service_role (scrapery běží přes service key)
-- service_role obchází RLS automaticky, takže žádné policy netřeba

comment on table listings is 'Kanonický seznam nabídek pronájmů, jeden řádek = jeden inzerát na jednom portálu.';
comment on column listings.fingerprint is 'Hash pro cross-source deduplikaci (pHash fotky + cena + plocha).';
