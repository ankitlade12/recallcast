import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RecallCast — Fact-locked safety media",
  description:
    "Generate multilingual recall media and prove every critical fact survived.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
