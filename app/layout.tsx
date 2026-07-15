import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";

import "./globals.css";
import { Providers } from "@/components/layout/providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Nafi — Voice-First AI Financial Assistant",
    template: "%s · Nafi",
  },
  description:
    "Nafi consolidates your accounts via Open Banking and answers with a voice-first AI advisor.",
};

export const viewport: Viewport = {
  themeColor: "#0d1119",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
