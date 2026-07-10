"use client";

import { Check, Database, FileText, LockKeyhole, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell, PageHeading } from "@/components/app-shell";
import { useStudyWorkspace } from "@/components/study-workspace-provider";
import { DocumentRecord, SystemStatus, getDocuments, getSystemStatus } from "@/lib/api";

export default function SettingsPage() {
  const [saved, setSaved] = useState(false);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const { activeWorkspace } = useStudyWorkspace();

  useEffect(() => {
    void getSystemStatus()
      .then(setSystem)
      .catch(() => setSystem(null));
  }, []);

  useEffect(() => {
    if (!activeWorkspace) return;
    void getDocuments(activeWorkspace.id)
      .then(setDocuments)
      .catch(() => setDocuments([]));
  }, [activeWorkspace?.id]);

  function save() {
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  }

  return (
    <AppShell>
      <PageHeading
        section="Settings"
        title="Workspace settings"
        description="Review your current study session and production workspace status."
      />
      <div className="mt-7 grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section className="min-w-0 rounded-3xl border border-[#dfe5e1] bg-white p-5 sm:p-6">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-xl bg-[#edf5e6] text-[#56843f]">
              <LockKeyhole size={18} />
            </div>
            <div>
              <h2 className="text-base font-semibold">Student workspace</h2>
              <p className="mt-1 text-xs text-[#7c8982]">
                Simple controls for the active subject session.
              </p>
            </div>
          </div>

          <div className="mt-6 rounded-2xl border border-[#e2e7e4] bg-[#f8faf8] p-5">
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7c8982]">
              Active session
            </p>
            <h3 className="mt-2 text-lg font-semibold">
              {activeWorkspace?.title ?? "Loading session..."}
            </h3>
            <p className="mt-2 text-sm leading-6 text-[#65736c]">
              Uploads, saved chats, and generated study material are scoped to
              this session.
            </p>
          </div>

          <button
            onClick={save}
            className="mt-6 flex items-center gap-2 rounded-xl bg-[#173a29] px-5 py-3 text-sm font-semibold text-white"
          >
            {saved ? <Check size={16} /> : <Save size={16} />}
            {saved ? "Saved" : "Save settings"}
          </button>
        </section>

        <aside className="min-w-0 space-y-4">
          {[
            {
              icon: Check,
              title: "AI features",
              text: system?.status === "ready" ? "Ready" : "Checking status",
            },
            {
              icon: Database,
              title: "Study data",
              text: system?.database === "connected" ? "Connected" : "Checking data store",
            },
            {
              icon: FileText,
              title: "Session documents",
              text: `${documents.length} document${documents.length === 1 ? "" : "s"} in this session`,
            },
          ].map((item) => (
            <div
              key={item.title}
              className="rounded-2xl border border-[#dfe5e1] bg-white p-5"
            >
              <item.icon size={18} className="text-[#66806f]" />
              <p className="mt-3 text-sm font-semibold">{item.title}</p>
              <p className="mt-1 text-xs text-[#849089]">{item.text}</p>
            </div>
          ))}
        </aside>
      </div>
    </AppShell>
  );
}
