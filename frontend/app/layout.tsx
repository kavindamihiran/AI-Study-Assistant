import type { Metadata } from "next";
import { AuthProvider } from "@/components/auth-provider";
import { ChatProvider } from "@/components/chat-provider";
import { StudyJobProvider } from "@/components/study-job-provider";
import { StudyWorkspaceProvider } from "@/components/study-workspace-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "StudyOS | AI Study Assistant",
  description: "Upload notes, ask questions, and generate study practice.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <StudyWorkspaceProvider>
            <ChatProvider>
              <StudyJobProvider>{children}</StudyJobProvider>
            </ChatProvider>
          </StudyWorkspaceProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
