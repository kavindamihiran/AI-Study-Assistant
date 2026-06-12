import type { Metadata } from "next";
import { ChatProvider } from "@/components/chat-provider";
import { StudyJobProvider } from "@/components/study-job-provider";
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
      <body>
        <ChatProvider>
          <StudyJobProvider>{children}</StudyJobProvider>
        </ChatProvider>
      </body>
    </html>
  );
}
