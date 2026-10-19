import type { Metadata } from "next";
import { Bungee, Space_Grotesk, Space_Mono } from "next/font/google";
import "./globals.css";
import { THEME_BOOT } from "@/lib/theme";

const grotesk = Space_Grotesk({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-grotesk" });
const mono = Space_Mono({ subsets: ["latin"], weight: ["400", "700"], variable: "--font-mono" });
const bungee = Bungee({ subsets: ["latin"], weight: "400", variable: "--font-bungee" });

export const metadata: Metadata = {
  title: "Pyxida",
  description: "See what is still unsolved in time series anomaly detection, and who is pushing it.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${grotesk.variable} ${mono.variable} ${bungee.variable}`} suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} /></head>
      <body>{children}</body>
    </html>
  );
}
