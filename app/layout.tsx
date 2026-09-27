import type { Metadata } from "next";
import { IBM_Plex_Sans } from "next/font/google";

import "./globals.css";

const plex = IBM_Plex_Sans({
  variable: "--font-plex",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Market Monitor",
  description: "SPY and QQQ with the NAAIM Exposure Index and the AAII sentiment survey.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${plex.variable} h-full antialiased`}>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
