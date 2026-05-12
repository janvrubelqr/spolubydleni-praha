import "leaflet/dist/leaflet.css";
import "./styles.css";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Spolubydlení Praha",
  description: "Analytický dashboard pražských pronájmů",
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
