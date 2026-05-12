"use client";

import { MapPin } from "lucide-react";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import L from "leaflet";

import type { Listing } from "@/lib/types";

const icon = L.divIcon({
  className: "price-marker",
  html: '<span></span>',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
});

type MapViewProps = {
  listings: Listing[];
  selectedId: string | null;
  onSelect: (id: string) => void;
};

function formatPrice(price: number | null) {
  if (!price) return "Cena neuvedena";
  return new Intl.NumberFormat("cs-CZ", {
    style: "currency",
    currency: "CZK",
    maximumFractionDigits: 0,
  }).format(price);
}

export default function MapView({ listings, selectedId, onSelect }: MapViewProps) {
  const points = listings.filter((listing) => listing.lat && listing.lon);

  return (
    <div className="map-shell">
      {points.length ? (
        <MapContainer center={[50.0833, 14.4167]} zoom={12} scrollWheelZoom className="map">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {points.map((listing) => (
            <Marker
              key={listing.id}
              icon={icon}
              position={[listing.lat as number, listing.lon as number]}
              eventHandlers={{ click: () => onSelect(listing.id) }}
              opacity={!selectedId || selectedId === listing.id ? 1 : 0.58}
            >
              <Popup>
                <strong>{formatPrice(listing.price_czk)}</strong>
                <span>{listing.rooms ?? "Byt"} · {listing.size_m2 ?? "?"} m2</span>
                <a href={listing.url} target="_blank" rel="noreferrer">
                  Otevrit inzerat
                </a>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      ) : (
        <div className="empty-map">
          <MapPin size={24} />
          <span>Zadne souradnice pro aktualni filtr</span>
        </div>
      )}
    </div>
  );
}
