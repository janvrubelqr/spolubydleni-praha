import "leaflet/dist/leaflet.css";
import "./styles.css";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Spolubydleni Praha",
  description: "Analyticky dashboard prazskych pronajmu",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="cs">
      <body>{children}</body>
    </html>
  );
}
