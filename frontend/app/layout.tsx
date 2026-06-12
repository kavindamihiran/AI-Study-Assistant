import type { Metadata } from "next";
import { ChatProvider } from "@/components/chat-provider";
import { StudyJobProvider } from "@/components/study-job-provider";
import { StudyWorkspaceProvider } from "@/components/study-workspace-provider";
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
        <StudyWorkspaceProvider>
          <ChatProvider>
            <StudyJobProvider>{children}</StudyJobProvider>
          </ChatProvider>
        </StudyWorkspaceProvider>
      </body>
    </html>
  );
}
