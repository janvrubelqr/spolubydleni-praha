export type Listing = {
  id: string;
  source: string;
  source_id: string;
  url: string;
  title: string | null;
  price_czk: number | null;
  price_per_m2: number | null;
  size_m2: number | null;
  rooms: string | null;
  district: string | null;
  address: string | null;
  lat: number | null;
  lon: number | null;
  days_on_market: number | null;
  first_seen_at: string;
  last_seen_at: string;
  raw?: unknown;
};
