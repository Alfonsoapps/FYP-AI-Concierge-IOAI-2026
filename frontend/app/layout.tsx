import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "IOAI 2027 AI Concierge",
  description: "AI-powered concierge for IOAI 2027",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="w-full h-screen bg-gray-900">{children}</body>
    </html>
  );
}
