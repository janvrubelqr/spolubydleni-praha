"use client";

import dynamic from "next/dynamic";
import { ExternalLink, Filter, RefreshCcw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getSupabase } from "@/lib/supabase";
import { isSharedHousing } from "@/lib/sharedHousing";
import type { Listing } from "@/lib/types";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

type Filters = {
  query: string;
  housingType: string;
  source: string;
  rooms: string;
  maxPrice: string;
  minSize: string;
};

const initialFilters: Filters = {
  query: "",
  housingType: "all",
  source: "all",
  rooms: "all",
  maxPrice: "",
  minSize: "",
};

function formatPrice(price: number | null) {
  if (!price) return "-";
  return new Intl.NumberFormat("cs-CZ", {
    style: "currency",
    currency: "CZK",
    maximumFractionDigits: 0,
  }).format(price);
}

function formatNumber(value: number | null) {
  if (value === null || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("cs-CZ", { maximumFractionDigits: 0 }).format(value);
}

export default function Home() {
  const [listings, setListings] = useState<Listing[]>([]);
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadListings() {
    setLoading(true);
    setError(null);

    let supabase;
    try {
      supabase = getSupabase();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Missing Supabase configuration");
      setLoading(false);
      return;
    }

    const { data, error } = await supabase
      .from("v_active_listings")
      .select(
        "id,source,source_id,url,title,price_czk,price_per_m2,size_m2,rooms,district,address,lat,lon,days_on_market,first_seen_at,last_seen_at,raw",
      )
      .order("first_seen_at", { ascending: false })
      .limit(500);

    if (error) {
      setError(error.message);
      setListings([]);
    } else {
      setListings((data ?? []) as Listing[]);
    }

    setLoading(false);
  }

  useEffect(() => {
    loadListings();
  }, []);

  const options = useMemo(() => {
    return {
      sources: Array.from(new Set(listings.map((item) => item.source))).sort(),
      rooms: Array.from(new Set(listings.map((item) => item.rooms).filter(Boolean))).sort() as string[],
    };
  }, [listings]);

  const filteredListings = useMemo(() => {
    const query = filters.query.trim().toLowerCase();
    const maxPrice = filters.maxPrice ? Number(filters.maxPrice) : null;
    const minSize = filters.minSize ? Number(filters.minSize) : null;

    return listings.filter((listing) => {
      const sharedHousing = isSharedHousing(listing);
      if (filters.housingType === "shared" && !sharedHousing) return false;
      if (filters.housingType === "whole" && sharedHousing) return false;
      if (filters.source !== "all" && listing.source !== filters.source) return false;
      if (filters.rooms !== "all" && listing.rooms !== filters.rooms) return false;
      if (maxPrice && (!listing.price_czk || listing.price_czk > maxPrice)) return false;
      if (minSize && (!listing.size_m2 || listing.size_m2 < minSize)) return false;
      if (!query) return true;

      return [listing.title, listing.address, listing.district, listing.source]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query);
    });
  }, [filters, listings]);

  const stats = useMemo(() => {
    const priced = filteredListings.filter((listing) => listing.price_czk);
    const priceAvg = priced.length
      ? Math.round(priced.reduce((sum, listing) => sum + (listing.price_czk ?? 0), 0) / priced.length)
      : null;
    const priceM2 = filteredListings.filter((listing) => listing.price_per_m2);
    const priceM2Avg = priceM2.length
      ? Math.round(priceM2.reduce((sum, listing) => sum + (listing.price_per_m2 ?? 0), 0) / priceM2.length)
      : null;

    return {
      count: filteredListings.length,
      priceAvg,
      priceM2Avg,
      mapped: filteredListings.filter((listing) => listing.lat && listing.lon).length,
    };
  }, [filteredListings]);

  const selectedListing = filteredListings.find((listing) => listing.id === selectedId) ?? filteredListings[0];

  return (
    <main>
      <header className="topbar">
        <div>
          <h1>Spolubydleni Praha</h1>
          <p>Pronajmy, pokoje a nabidky vhodne pro spolubydleni</p>
        </div>
        <button className="icon-button" onClick={loadListings} aria-label="Obnovit data">
          <RefreshCcw size={18} />
        </button>
      </header>

      <section className="stats-grid">
        <div>
          <span>Inzeratu</span>
          <strong>{formatNumber(stats.count)}</strong>
        </div>
        <div>
          <span>Prumerna cena</span>
          <strong>{formatPrice(stats.priceAvg)}</strong>
        </div>
        <div>
          <span>Cena / m2</span>
          <strong>{stats.priceM2Avg ? `${formatNumber(stats.priceM2Avg)} Kc` : "-"}</strong>
        </div>
        <div>
          <span>Na mape</span>
          <strong>{formatNumber(stats.mapped)}</strong>
        </div>
      </section>

      <section className="filters" aria-label="Filtry">
        <label className="search-field">
          <Search size={18} />
          <input
            value={filters.query}
            onChange={(event) => setFilters({ ...filters, query: event.target.value })}
            placeholder="Hledat adresu, cast nebo zdroj"
          />
        </label>
        <label>
          <Filter size={16} />
          <select
            value={filters.housingType}
            onChange={(event) => setFilters({ ...filters, housingType: event.target.value })}
          >
            <option value="all">Vsechny moznosti</option>
            <option value="shared">Spolubydleni</option>
            <option value="whole">Cele byty</option>
          </select>
        </label>
        <label>
          <span>Zdroj</span>
          <select
            value={filters.source}
            onChange={(event) => setFilters({ ...filters, source: event.target.value })}
          >
            <option value="all">Vsechny zdroje</option>
            {options.sources.map((source) => (
              <option key={source} value={source}>
                {source}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Typ</span>
          <select value={filters.rooms} onChange={(event) => setFilters({ ...filters, rooms: event.target.value })}>
            <option value="all">Vsechny dispozice</option>
            {options.rooms.map((rooms) => (
              <option key={rooms} value={rooms}>
                {rooms}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Max Kc</span>
          <input
            type="number"
            min="0"
            value={filters.maxPrice}
            onChange={(event) => setFilters({ ...filters, maxPrice: event.target.value })}
          />
        </label>
        <label>
          <span>Min m2</span>
          <input
            type="number"
            min="0"
            value={filters.minSize}
            onChange={(event) => setFilters({ ...filters, minSize: event.target.value })}
          />
        </label>
      </section>

      {error ? <div className="error">{error}</div> : null}

      <section className="workspace">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Cena</th>
                <th>Dispozice</th>
                <th>m2</th>
                <th>Lokalita</th>
                <th>Zdroj</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6}>Nacitam data...</td>
                </tr>
              ) : (
                filteredListings.length ? filteredListings.map((listing) => (
                  <tr
                    key={listing.id}
                    className={selectedListing?.id === listing.id ? "selected" : ""}
                    onClick={() => setSelectedId(listing.id)}
                  >
                    <td>{formatPrice(listing.price_czk)}</td>
                    <td>{listing.rooms ?? "-"}</td>
                    <td>{listing.size_m2 ?? "-"}</td>
                    <td>
                      <strong>{listing.district ?? listing.address ?? "-"}</strong>
                      <span>{listing.address ?? listing.title}</span>
                    </td>
                    <td>{listing.source}</td>
                    <td>
                      <a href={listing.url} target="_blank" rel="noreferrer" aria-label="Otevrit inzerat">
                        <ExternalLink size={16} />
                      </a>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={6}>Zadne nabidky pro aktualni filtr.</td>
                  </tr>
                )
              )}
            </tbody>
          </table>
        </div>
        <MapView listings={filteredListings} selectedId={selectedListing?.id ?? null} onSelect={setSelectedId} />
      </section>
    </main>
  );
}
