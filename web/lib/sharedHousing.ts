import type { Listing } from "@/lib/types";

const POSITIVE_TERMS = [
  "spolubyd",
  "spolubydleni",
  "spolubydleni",
  "pokoj",
  "pokoje",
  "room",
  "rooms",
  "shared",
  "share",
  "student",
  "studenti",
  "studentka",
  "studentky",
];

const NEGATIVE_TERMS = [
  "neni vhodne pro spolubydleni",
  "není vhodné pro spolubydlení",
  "bez spolubydleni",
  "bez spolubydlení",
  "neni spolubydleni",
  "není spolubydlení",
];

function normalize(value: unknown) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

export function isSharedHousing(listing: Listing) {
  const text = normalize([
    listing.title,
    listing.address,
    listing.district,
    listing.url,
    listing.raw ? JSON.stringify(listing.raw) : "",
  ].join(" "));

  if (NEGATIVE_TERMS.some((term) => text.includes(normalize(term)))) {
    return false;
  }

  return POSITIVE_TERMS.some((term) => text.includes(normalize(term)));
}
