import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const _geist = Geist({ subsets: ["latin"] });
const _geistMono = Geist_Mono({ subsets: ["latin"] });

export const metadata: Metadata = {
  alternates: { canonical: "/" },
  applicationName: "Draw.io to TikZ",
  authors: [{ name: "Daiki Okayama", url: "https://github.com/okayama-daiki" }],
  creator: "Daiki Okayama",
  description:
    "Convert your Draw.io diagrams into professional LaTeX TikZ code. Perfect for academic papers and technical documentation.",
  generator: "Next.js",
  icons: {
    apple: "/apple-icon.png",
    icon: [
      {
        media: "(prefers-color-scheme: light)",
        url: "/icon-light-32x32.png",
      },
      {
        media: "(prefers-color-scheme: dark)",
        url: "/icon-dark-32x32.png",
      },
      { type: "image/svg+xml", url: "/icon.svg" },
    ],
  },
  keywords: [
    "Draw.io",
    "TikZ",
    "LaTeX",
    "Converter",
    "Diagram",
    "XML",
    "Next.js",
  ],
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000",
  ),
  openGraph: {
    description:
      "Convert your Draw.io diagrams into professional LaTeX TikZ code.",
    images: [
      {
        alt: "Draw.io to TikZ",
        height: 630,
        url: "/og.png",
        width: 1200,
      },
    ],
    siteName: "Draw.io to TikZ",
    title: "Draw.io to TikZ Converter",
    type: "website",
    url: "/",
  },
  publisher: "Daiki Okayama",
  robots: {
    follow: true,
    googleBot: { follow: true, index: true },
    index: true,
  },
  title: {
    default: "Draw.io to TikZ Converter",
    template: "%s | Draw.io to TikZ",
  },
  twitter: {
    card: "summary_large_image",
    description:
      "Convert your Draw.io diagrams into professional LaTeX TikZ code.",
    images: ["/og.png"],
    title: "Draw.io to TikZ Converter",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`font-sans antialiased`}>{children}</body>
    </html>
  );
}
