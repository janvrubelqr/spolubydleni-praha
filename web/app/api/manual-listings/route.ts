import { createHash } from "node:crypto";

import { createClient } from "@supabase/supabase-js";
import { NextResponse } from "next/server";

type ManualListingPayload = {
  source?: string;
  text?: string;
  url?: string;
};

const SOURCE = "facebook_manual";
const FALLBACK_URL = "https://www.facebook.com/";

function getSupabaseAdmin() {
  const supabaseUrl = process.env.SUPABASE_URL ?? process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_KEY;

  if (!supabaseUrl || !serviceKey) {
    throw new Error("Missing SUPABASE_URL/NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_KEY");
  }

  return createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

function normalizeText(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function parsePrice(text: string) {
  const match = text.match(/(\d[\d\s.]{2,})\s*(?:kc|kč|czk)/i);
  if (!match) return null;
  const value = Number(match[1].replace(/[^\d]/g, ""));
  return Number.isFinite(value) ? value : null;
}

function parseSize(text: string) {
  const match = text.match(/(\d+(?:[,.]\d+)?)\s*(?:m2|m²|metr)/i);
  if (!match) return null;
  const value = Number(match[1].replace(",", "."));
  return Number.isFinite(value) ? value : null;
}

function parseRooms(text: string) {
  const roomMatch = text.match(/\b(\d\+(?:kk|\d))\b/i);
  if (roomMatch) return roomMatch[1].toLowerCase();
  if (/\b(pokoj|spolubydl|room|shared)\b/i.test(text)) return "pokoj";
  return null;
}

function parseDistrict(text: string) {
  const match = text.match(/praha\s*\d+/i);
  if (!match) return null;
  return match[0].replace(/\s+/, " ").replace(/^praha/i, "Praha");
}

function titleFromText(text: string) {
  const firstLine = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean);

  if (!firstLine) return "Facebook nabídka";
  return firstLine.length > 120 ? `${firstLine.slice(0, 117)}...` : firstLine;
}

function sourceIdFor(text: string, url: string) {
  return createHash("sha256")
    .update(`${SOURCE}:${url || text}`)
    .digest("hex")
    .slice(0, 32);
}

export async function POST(request: Request) {
  let payload: ManualListingPayload;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: "Neplatný JSON." }, { status: 400 });
  }

  const text = normalizeText(payload.text);
  const url = normalizeText(payload.url);

  if (!text || text.length < 20) {
    return NextResponse.json({ error: "Vlož delší text příspěvku." }, { status: 400 });
  }

  try {
    const supabase = getSupabaseAdmin();
    const price = parsePrice(text);
    const sourceId = sourceIdFor(text, url);

    const listing = {
      source: SOURCE,
      source_id: sourceId,
      url: url || FALLBACK_URL,
      title: titleFromText(text),
      description: text,
      price_czk: price,
      size_m2: parseSize(text),
      rooms: parseRooms(text),
      district: parseDistrict(text),
      address: parseDistrict(text),
      raw: {
        import_type: "manual",
        original_source: payload.source || "facebook",
        original_text: text,
        original_url: url || null,
      },
    };

    const { data, error } = await supabase
      .from("listings")
      .upsert(listing, { onConflict: "source,source_id" })
      .select("id")
      .single();

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    if (price && data?.id) {
      await supabase.from("price_history").insert({ listing_id: data.id, price_czk: price });
    }

    return NextResponse.json({ ok: true, id: data?.id ?? null });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Import selhal." },
      { status: 500 },
    );
  }
}
