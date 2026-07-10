"use client";

import {
  ArrowRight,
  BookOpen,
  FileText,
  Library,
  MessageSquareText,
  NotebookTabs,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell, PageHeading } from "@/components/app-shell";
import { StudyFlow } from "@/components/study-flow";
import { useStudyWorkspace } from "@/components/study-workspace-provider";
import {
  DocumentRecord,
  getDocuments,
  StudyWorkspace,
  getStudyWorkspaces,
} from "@/lib/api";

const quickActions = [
  {
    title: "Add documents",
    text: "Upload PDFs, notes, and lecture material.",
    href: "/documents",
    icon: Library,
    tone: "bg-[#fff0e1] text-[#c66b1c]",
  },
  {
    title: "Generate study tools",
    text: "Create summaries, MCQs, flashcards, and plans.",
    href: "/study-tools",
    icon: WandSparkles,
    tone: "bg-[#f0eaff] text-[#7650b7]",
  },
  {
    title: "Chat with notes",
    text: "Ask grounded questions using your study material.",
    href: "/chat",
    icon: MessageSquareText,
    tone: "bg-[#e8f0ff] text-[#3767bd]",
  },
];

export default function OverviewPage() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [sessions, setSessions] = useState<StudyWorkspace[]>([]);
  const { activeWorkspace } = useStudyWorkspace();

  useEffect(() => {
    if (!activeWorkspace) return;
    void Promise.all([getDocuments(activeWorkspace?.id), getStudyWorkspaces()])
      .then(([indexedDocuments, studySessions]) => {
        setDocuments(indexedDocuments);
        setSessions(studySessions);
      })
      .catch(() => {
        setDocuments([]);
        setSessions([]);
      });
  }, [activeWorkspace]);

  const totalChunks = documents.reduce(
    (total, document) => total + document.chunk_count,
    0,
  );

  return (
    <AppShell>
      <PageHeading
        section="Overview"
        title="Your AI study command center"
        description="Move from raw course material to clear answers, summaries, practice questions, and focused study plans."
        action={
          <div className="flex w-fit items-center gap-2 rounded-full border border-[#cce6d6] bg-[#edf9f1] px-3 py-1.5 text-xs font-medium text-[#247447]">
            <span className="size-2 rounded-full bg-[#35a961] shadow-[0_0_0_4px_rgba(53,169,97,0.12)]" />
            Workspace online
          </div>
        }
      />

      <StudyFlow
        current={documents.length ? "activity" : "sources"}
        hasSources={documents.length > 0}
      />

      <section className="mt-5 flex flex-col justify-between gap-5 overflow-hidden rounded-3xl bg-[#173a29] p-5 text-white sm:p-6 md:flex-row md:items-center">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#c8f169]">
            {documents.length ? "Continue your flow" : "Start here"}
          </p>
          <h2 className="mt-2 text-xl font-semibold sm:text-2xl">
            {documents.length
              ? `${documents.length} source${documents.length === 1 ? " is" : "s are"} ready to study`
              : "Bring your first notes into StudyOS"}
          </h2>
          <p className="mt-2 max-w-xl text-sm leading-6 text-white/55">
            {documents.length
              ? "Choose a learning activity next. Your indexed material will already be selected."
              : "Upload once, then move naturally into summaries, practice questions, flashcards, or grounded chat."}
          </p>
        </div>
        <Link
          href={documents.length ? "/study-tools" : "/documents"}
          className="inline-flex w-full shrink-0 items-center justify-center gap-2 rounded-xl bg-[#c8f169] px-5 py-3.5 text-sm font-semibold text-[#17321f] transition hover:bg-[#d5f58a] md:w-auto"
        >
          {documents.length ? "Choose an activity" : "Add study material"}
          <ArrowRight size={16} />
        </Link>
      </section>

      <div className="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
        {[
          {
            label: "Documents",
            value: String(documents.length),
            note: documents.length ? "Indexed and searchable" : "Ready for your first upload",
            icon: FileText,
          },
          {
            label: "Indexed chunks",
            value: String(totalChunks),
            note: "Available for grounded chat",
            icon: BookOpen,
          },
          {
            label: "Study sessions",
            value: String(sessions.length),
            note: sessions.length ? "Subjects kept separate" : "Create a subject session",
            icon: NotebookTabs,
          },
          {
            label: "AI assistant",
            value: "Ready",
            note: "Answers, summaries, and practice tools",
            icon: Sparkles,
          },
        ].map((item) => (
            <div
              key={item.label}
              className="rounded-2xl border border-[#dfe5e1] bg-white p-4 shadow-[0_8px_30px_rgba(24,51,37,0.035)] sm:p-5"
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs font-medium text-[#7c8982]">{item.label}</p>
                  <p className="mt-2 text-xl font-semibold tracking-tight">
                    {item.value}
                  </p>
                </div>
                <div className="grid size-9 place-items-center rounded-xl bg-[#eef3ef] text-[#456352]">
                  <item.icon size={17} />
                </div>
              </div>
              <p className="mt-3 text-[11px] text-[#98a29c]">{item.note}</p>
            </div>
          ))}
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.3fr_0.7fr]">
        <section className="rounded-3xl border border-[#dfe5e1] bg-white p-5 shadow-[0_12px_40px_rgba(24,51,37,0.04)] sm:p-6">
          <h2 className="text-lg font-semibold tracking-tight">Start studying</h2>
          <p className="mt-1 text-xs text-[#7c8982]">
            Choose the next step in your study workflow.
          </p>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            {quickActions.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="group rounded-2xl border border-[#e2e7e4] p-4 transition hover:-translate-y-0.5 hover:border-[#a9bcae] hover:shadow-lg"
              >
                <div className={`grid size-10 place-items-center rounded-xl ${item.tone}`}>
                  <item.icon size={18} />
                </div>
                <h3 className="mt-4 text-sm font-semibold">{item.title}</h3>
                <p className="mt-2 text-xs leading-5 text-[#7c8982]">{item.text}</p>
                <ArrowRight
                  size={16}
                  className="mt-4 text-[#64806e] transition group-hover:translate-x-1"
                />
              </Link>
            ))}
          </div>
        </section>

        <section className="rounded-3xl bg-[#173a29] p-5 text-white sm:p-6">
          <div className="grid size-11 place-items-center rounded-2xl bg-[#c8f169] text-[#17321f]">
            <Sparkles size={20} />
          </div>
          <h2 className="mt-5 text-xl font-semibold">Study help is ready</h2>
          <p className="mt-2 text-sm leading-6 text-white/60">
            Upload your material once, then turn it into answers, summaries,
            flashcards, practice questions, and study plans.
          </p>
          <Link
            href="/study-tools"
            className="mt-6 inline-flex items-center gap-2 rounded-xl bg-white/10 px-4 py-3 text-xs font-semibold hover:bg-white/15"
          >
            Open study tools
            <ArrowRight size={15} />
          </Link>
        </section>
      </div>
    </AppShell>
  );
}
