import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "StudyOS | Model Gateway",
  description: "AI Study Assistant model gateway control center",
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

