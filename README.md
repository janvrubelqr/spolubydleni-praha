# Prague Rentals - agregator pronajmu v Praze

Datova pipeline, ktera sbira inzeraty z portalu pronajmu v Praze, normalizuje je
do jednotneho schematu v Supabase Postgres a poskytuje data pro analyticke UI.

## Architektura

```text
scrapers/        Per-portal scrapery (Sreality, Realingo, Bezrealitky, ...)
shared/          Datove modely a Supabase repository
001_init.sql     SQL migrace
```

Tok dat: scraper -> `ListingRecord` (Pydantic) -> `SupabaseRepo.upsert_listing()` -> Postgres

## Setup

### 1. Supabase projekt

1. Vytvor projekt na <https://supabase.com/dashboard>
2. V SQL Editoru pust `001_init.sql`
3. V Settings -> API si vezmi:
   - `Project URL` -> `SUPABASE_URL`
   - `service_role` key -> `SUPABASE_SERVICE_KEY`

`service_role` je silny klic. Nikdy ho nedavej do frontendu ani do gitu.

### 2. Lokalni prostredi

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# vypln .env
```

Na Windows muzes misto `cp` pouzit `copy .env.example .env`. Pokud pouzivas
`.env.local`, nacte se automaticky.

### 3. Spusteni scraperu

```bash
python -m scrapers.sreality
python -m scrapers.realingo
```

Po dobehnuti zkontroluj v Supabase tabulky `listings`, `price_history` a
`scrape_runs`.

## Co je hotove

- [x] Schema s PostGIS, `price_history`, `scrape_runs`
- [x] RLS: UI bude cist pres anon klic, scrapery zapisuji pres service key
- [x] Sreality scraper pres verejne JSON API
- [x] Realingo scraper pres Next.js `__NEXT_DATA__` na prvni strance vysledku
- [x] Idempotentni upsert pres `(source, source_id)`
- [x] Tracking zmen cen v `price_history`
- [x] Auto-detekce delistingu pro zdroje s kompletnim pokrytim

## Stav scraperu

### Sreality

Sreality pouziva verejne JSON API a scraper prochazi strankovani. Po uspesnem
behu oznacuje zmizele inzeraty jako `delisted_at`.

### Realingo

Realingo vraci vysledky server-side v Next.js `__NEXT_DATA__`. Scraper aktualne
bere prvni stranku `https://www.realingo.cz/pronajem_reality/Praha/`, filtruje
jen `purpose=RENT` a `property=FLAT`, a uklada cenu, dispozici, plochu, adresu a
GPS souradnice.

Delisting je pro Realingo zatim vypnuty, protoze jeste neni implementovane
strankovani. Tim se zabrani tomu, aby prvni stranka omylem oznacila starsi
Realingo inzeraty jako zmizele.

## Co nasleduje

**Faze 2 - dalsi portaly:**

- [ ] Dodelat strankovani Realingo
- [ ] Ulovdomov (studenti + spolubydleni)
- [ ] Bezrealitky (Playwright + proxy, GraphQL je za antibotem)
- [ ] Flatio (kratkodobe pronajmy)
- [ ] HousingAnywhere, Spareroom (mezinarodni)

**Faze 3 - deduplikace:**

- [ ] Fingerprint pres pHash hlavni fotky + cena + plocha
- [ ] `cross_source_listings` view, ktere sleduje, kde vsude je stejny byt

**Faze 4 - UI:**

- [ ] Next.js + Supabase JS + Mapbox/MapLibre
- [ ] Filtry: cena, velikost, dispozice, mestska cast, doba na trhu
- [ ] Charts: cena/m2 podle ctvrti v case, distribuce cen

**Faze 5 - automation:**

- [ ] GitHub Actions cron
- [ ] Telegram alert pro nove inzeraty podle filtru
- [ ] MCP server nad DB pro konverzacni dotazovani

## Poznamky k provozu

- Rate limit: Sreality scraper ma 1 req/s, Realingo zatim 1 request na beh.
- Bezrealitky: planuj Playwright a proxy pool.
- Legalita: ToS portalu scraping casto zakazuji. Pro osobni analyzu je riziko
  nizsi, pro verejnou distribuci dat vyssi.
- GDPR: neukladat telefony ani jmena majitelu.
