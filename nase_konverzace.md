# Naše konverzace — Prague Rentals projekt

> Shrnutí konverzace o stavbě automatizovaného agregátoru pronájmů v Praze.
> Datum: 12. května 2026

---

## Zadání

**Cíl:** Automatizované řešení, které projde české i zahraniční portály nabízející pronájem pokojů/bytů v Praze.

**Upřesnění přes elicitaci:**
- Hlavní cíl: **Datová analýza trhu** (ceny, trendy)
- Práce s daty: **Web UI s filtry a mapou**
- Anti-bot strategie: **Headless browser (Playwright) + proxy pool**

---

## Architektura

```
┌─────────────────┐
│  Scraper layer  │  Playwright/HTTP workers (jeden modul per portál)
│  (per-portal)   │  + proxy pool, rotace user-agentů
└────────┬────────┘
         │ raw JSON
         ▼
┌─────────────────┐
│  Normalizer     │  Sjednocení schématu, geocoding,
│  (Python/TS)    │  deduplikace přes fuzzy match
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Supabase       │  Postgres + PostGIS (mapa),
│  (Postgres)     │  pg_cron pro plánování, RLS pro UI
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Next.js UI     │  Filtry, mapa (Mapbox/Leaflet),
│  + Supabase JS  │  charts (ceny v čase)
└─────────────────┘
```

**Analogie:** Továrna na konzervy — scrapery jsou sběrači surovin z různých polí, normalizační vrstva je linka, databáze je sklad a UI je obchod.

---

## Cílové portály

### České — vysoká priorita
- **Sreality.cz** — má veřejné JSON API, stačí HTTP klient
- **Bezrealitky.cz** — GraphQL endpoint, ale agresivní antibot
- **Realingo.cz** — agreguje samo, dobré jako sanity check
- **Ulovdomov.cz** — studenti/spolubydlení
- **HoumerCZ, Idnes Reality, Realcity.cz**

### Mezinárodní
- **Facebook Marketplace** + skupiny "Flats for rent Prague"
- **Spareroom.com, Flatio.com, HousingAnywhere.com**
- **Erasmusu, Uniplaces** (studenti)

---

## Tech stack

| Vrstva | Technologie |
|---|---|
| Scrapers | Python + httpx (jednoduché) / Playwright + stealth (odolné) |
| Modely | Pydantic v2 |
| DB | Supabase Postgres + PostGIS + pg_trgm |
| Orchestrace | GitHub Actions cron (start), později Prefect/Dagster |
| UI | Next.js + Supabase JS + Mapbox/MapLibre |
| Budoucnost | MCP server nad DB pro konverzační dotazy přes Claude |

---

## Fázování

| Fáze | Cíl | Doba |
|---|---|---|
| 1 | DB schema + 2 nejjednodušší portály (Sreality, Realingo) přes HTTP | 1 týden |
| 2 | Normalizace + deduplikace + základní Next.js UI s tabulkou | 1 týden |
| 3 | Mapa + filtry + charts (cena/m², trendy) | 1 týden |
| 4 | Playwright + proxy pro Bezrealitky a další odolné | 1-2 týdny |
| 5 | FB Marketplace, mezinárodní portály | průběžně |

---

## Co je hotové (Fáze 1)

### Struktura projektu
```
prague-rentals/
├── README.md
├── requirements.txt
├── .env.example
├── db/
│   └── 001_init.sql           # Schema + indexy + RLS + view
├── shared/
│   ├── models.py              # Pydantic ListingRecord
│   └── repo.py                # SupabaseRepo (upsert, scrape_runs, delisting)
└── scrapers/
    └── sreality.py            # První scraper přes JSON API
```

### Klíčové vlastnosti
- **Idempotence** — upsert přes `(source, source_id)`, žádné duplicity při opakovaném běhu
- **Time-on-market zdarma** — `first_seen_at` při prvním vidění, `last_seen_at` se aktualizuje
- **Price history** — změna ceny = nový řádek v `price_history`
- **Auto-delisting** — inzerát, co zmizel z výsledků, dostane `delisted_at`
- **PostGIS** — geography(point) pro mapu, GIST index
- **RLS** — anonymní přístup jen read-only, scrapery zapisují přes service_role

### DB schéma (přehled)
- `listings` — kanonický záznam (jeden řádek = inzerát na jednom portálu)
- `price_history` — tracking změn cen
- `scrape_runs` — monitoring běhů scraperů
- `v_active_listings` — view s vypočítaným `price_per_m2` a `days_on_market`

---

## Setup, kterým jsme prošli

1. ✅ Vytvořen Supabase projekt
2. ✅ Spuštěna migrace `db/001_init.sql` v SQL Editoru
3. ✅ Získána Project URL (forma `https://<projekt>.supabase.co` — bez `/rest/v1/` suffixu)
4. ✅ Získán `service_role` klíč
5. ✅ Vytvořen lokální `.env` v rootu projektu
6. ⏳ Spuštění scraperu: `python -m scrapers.sreality`

### Co jsme udělali po prvním běhu
- Vytvořili `shared/` balíček a sdílené modely + repository:
  - `shared/models.py`
  - `shared/repo.py`
- Přesunuli existující Sreality scraper do `scrapers/sreality.py`
- Přidali nový Realingo scraper scaffold v `scrapers/realingo.py`
- Přidali `.env.example` s ukázkou proměnných
- Implementovali automatické načítání `.env` a `.env.local` v `shared/repo.py`
- Aktualizovali `README.md` se správnými příkazy pro `python -m scrapers.sreality` a `python -m scrapers.realingo`
- Spustili jsme Sreality scraper úspěšně a ověřili základní pipeline
- Vytvořili `realingo_debug.ipynb` pro ladění Realingo endpointu

### Důležité poznámky ke konfiguraci
- `.env` patří **lokálně**, ne do cloudu (analogie: klíč od bytu v kapse, ne na vývěsce)
- `SUPABASE_URL` musí být bez `/rest/v1/` suffixu — klient si cesty dopisuje sám
- Pro produkční scheduling později → GitHub Actions secrets (ne `.env`)
- `service_role` klíč **nikdy nedávat do frontendu** ani do gitu

---

## Co bude následovat

Po prvním úspěšném běhu Sreality scraperu jsou na výběr směry:

- **A** — druhý a třetí scraper (Realingo, Ulovdomov)
- **B** — Next.js UI s mapou nad daty co už jsou
- **C** — Bezrealitky přes Playwright + stealth
- **D** — deduplikace cross-source (pHash fotek + cena + plocha)

---

## Legalita & etika

- ToS portálů zakazují scraping
- Pro **osobní analýzu** nízké riziko
- Pro **veřejnou distribuci dat** problém (autorská ochrana databáze §88 autorského zákona)
- Respektovat `robots.txt` aspoň formálně, rate limit
- **Neukládat osobní údaje** (telefony, jména majitelů) → GDPR

---

## Sanity check dotazy po prvním běhu

```sql
-- kolik aktivních inzerátů a průměrná cena/m²
select
  count(*)                    as aktivnich,
  round(avg(price_czk))       as prum_cena,
  round(avg(price_czk / nullif(size_m2, 0)))  as prum_cena_m2
from listings
where delisted_at is null;

-- rozložení podle čtvrtí
select district, count(*), round(avg(price_czk)) as prum_cena
from listings
where delisted_at is null and district is not null
group by district
order by count(*) desc;

-- top 10 nejnovějších
select title, price_czk, size_m2, district, url
from v_active_listings
order by first_seen_at desc
limit 10;
```
