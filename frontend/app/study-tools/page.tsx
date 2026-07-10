"use client";

import {
  BookOpenCheck,
  Brain,
  CalendarDays,
  Check,
  FileText,
  Layers3,
  Play,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AppShell, PageHeading } from "@/components/app-shell";
import { MarkdownText } from "@/components/markdown-text";
import { StudyFlow } from "@/components/study-flow";
import { useStudyWorkspace } from "@/components/study-workspace-provider";
import {
  DocumentRecord,
  FlashcardItem,
  MCQItem,
  StudyToolKind,
  StudyToolResponse,
  getDocuments,
} from "@/lib/api";
import { StudyJob, useStudyJobs } from "@/components/study-job-provider";

const tools = [
  { id: "summary" as const, label: "Summary", icon: BookOpenCheck },
  { id: "mcq" as const, label: "MCQs", icon: Brain },
  { id: "flashcards" as const, label: "Flashcards", icon: Layers3 },
  { id: "plan" as const, label: "Study plan", icon: CalendarDays },
];

export default function StudyToolsPage() {
  const [activeTool, setActiveTool] = useState(tools[0]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [topic, setTopic] = useState("");
  const [error, setError] = useState("");
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const queryWorkspaceRef = useRef<string | null>(null);
  const { jobs, selectedJob, enqueue, selectJob } = useStudyJobs();
  const { activeWorkspace } = useStudyWorkspace();
  const activeJobs = jobs.filter(
    (job) => job.status === "queued" || job.status === "running",
  );

  useEffect(() => {
    if (!activeWorkspace) return;
    setLoadingDocuments(true);
    void getDocuments(activeWorkspace.id)
      .then((uploadedDocuments) => {
        const indexed = uploadedDocuments.filter(
          (document) => document.status === "indexed",
        );
        setDocuments(indexed);
        const query = new URLSearchParams(window.location.search);
        const requestedIds = (query.get("sources") ?? "")
          .split(",")
          .filter((id) => indexed.some((document) => document.id === id));
        setSelectedIds(
          requestedIds.length
            ? requestedIds
            : indexed.map((document) => document.id),
        );
        const requestedTool = tools.find((tool) => tool.id === query.get("tool"));
        if (requestedTool && queryWorkspaceRef.current !== activeWorkspace.id) {
          setActiveTool(requestedTool);
          selectJob(null);
        }
        queryWorkspaceRef.current = activeWorkspace.id;
      })
      .catch((loadError) => {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Could not load study documents.",
        );
      })
      .finally(() => setLoadingDocuments(false));
  }, [activeWorkspace?.id]);

  useEffect(() => {
    if (!selectedJob) return;
    const tool = tools.find((item) => item.id === selectedJob.tool);
    if (tool) setActiveTool(tool);
  }, [selectedJob]);

  function generate() {
    if (selectedIds.length === 0) return;
    setError("");
    const selectedDocuments = documents.filter((document) =>
      selectedIds.includes(document.id),
    );
    enqueue({
      tool: activeTool.id,
      documentIds: selectedIds,
      sourceNames: selectedDocuments.map((document) => document.filename),
      topic,
    });
  }

  function toggleDocument(documentId: string) {
    setSelectedIds((current) =>
      current.includes(documentId)
        ? current.filter((id) => id !== documentId)
        : [...current, documentId],
    );
    selectJob(null);
  }

  return (
    <AppShell>
      <PageHeading
        section="Study tools"
        title="Choose how you want to study"
        description={`Your sources from ${activeWorkspace?.title ?? "this study session"} are ready. Pick an activity and make it your own.`}
      />
      <StudyFlow current="activity" hasSources={documents.length > 0} />
      <div className="mt-5 grid min-w-0 gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
        <div className="min-w-0 space-y-6">
          <section className="rounded-3xl border border-[#dfe5e1] bg-white p-4">
            <p className="px-2 py-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7c8982]">
              Choose a tool
            </p>
            <div className="mt-2 grid grid-cols-2 gap-2 xl:grid-cols-1">
              {tools.map((tool) => (
                <button
                  key={tool.id}
                  onClick={() => {
                    setActiveTool(tool);
                    selectJob(null);
                    setError("");
                  }}
                  className={`flex w-full items-center gap-2.5 rounded-2xl p-3 text-left text-xs font-medium transition sm:p-4 sm:text-sm ${
                    activeTool.id === tool.id
                      ? "bg-[#173a29] text-white"
                      : "hover:bg-[#f3f6f3]"
                  }`}
                >
                  <tool.icon
                    size={18}
                    className={activeTool.id === tool.id ? "text-[#c8f169]" : ""}
                  />
                  {tool.label}
                </button>
              ))}
            </div>
          </section>
          <section className="rounded-3xl border border-[#dfe5e1] bg-white p-4">
            <div className="flex items-center justify-between px-2 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7c8982]">
                PDF sources
              </p>
              {documents.length > 0 && (
                <button
                  onClick={() =>
                    setSelectedIds(
                      selectedIds.length === documents.length
                        ? []
                        : documents.map((document) => document.id),
                    )
                  }
                  className="text-xs font-semibold text-[#56843f]"
                >
                  {selectedIds.length === documents.length
                    ? "Clear all"
                    : "Select all"}
                </button>
              )}
            </div>
            {loadingDocuments ? (
              <p className="px-2 py-4 text-sm text-[#7c8982]">
                Loading indexed documents...
              </p>
            ) : documents.length === 0 ? (
              <div className="rounded-2xl bg-[#f5f7f5] p-4">
                <p className="text-sm text-[#65736c]">
                  Upload and index a PDF before generating practice material.
                </p>
                <Link
                  href="/documents"
                  className="mt-3 inline-flex text-sm font-semibold text-[#477238]"
                >
                  Go to documents
                </Link>
              </div>
            ) : (
              <div className="mt-2 space-y-2">
                {documents.map((document) => {
                  const selected = selectedIds.includes(document.id);
                  return (
                    <button
                      key={document.id}
                      onClick={() => toggleDocument(document.id)}
                      className={`flex w-full items-center gap-3 rounded-2xl border p-3 text-left transition ${
                        selected
                          ? "border-[#9ab68d] bg-[#f2f8ed]"
                          : "border-transparent bg-[#f7f9f7]"
                      }`}
                    >
                      <span
                        className={`grid size-7 shrink-0 place-items-center rounded-lg ${
                          selected
                            ? "bg-[#173a29] text-white"
                            : "bg-white text-[#7c8982]"
                        }`}
                      >
                        {selected ? <Check size={14} /> : <FileText size={14} />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">
                          {document.filename}
                        </span>
                        <span className="text-xs text-[#7c8982]">
                          {document.chunk_count} indexed chunks
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </section>
          {jobs.length > 0 && (
            <section className="rounded-3xl border border-[#dfe5e1] bg-white p-4">
              <p className="px-2 py-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7c8982]">
                Recent work
              </p>
              <div className="mt-2 space-y-2">
                {jobs.slice(0, 6).map((job) => (
                  <button
                    key={job.id}
                    onClick={() => selectJob(job.id)}
                    className={`w-full rounded-2xl border p-3 text-left transition ${
                      selectedJob?.id === job.id
                        ? "border-[#9ab68d] bg-[#f2f8ed]"
                        : "border-transparent bg-[#f7f9f7] hover:border-[#dce5d8]"
                    }`}
                  >
                    <span className="flex items-center justify-between gap-3">
                      <span className="text-sm font-semibold text-[#263b30]">
                        {toolLabel(job.tool)}
                      </span>
                      <span className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] ${statusClass(job.status)}`}>
                        {job.status}
                      </span>
                    </span>
                    <span className="mt-1 block truncate text-xs text-[#75827b]">
                      {job.sourceNames.join(", ")}
                    </span>
                  </button>
                ))}
              </div>
            </section>
          )}
        </div>
        <section className="min-w-0 max-w-full rounded-3xl border border-[#dfe5e1] bg-white p-4 sm:p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">{activeTool.label} generator</h2>
              <p className="mt-1 text-xs text-[#7c8982]">
                {selectedIds.length} source{selectedIds.length === 1 ? "" : "s"}{" "}
                selected
              </p>
            </div>
            <activeTool.icon size={22} className="text-[#56843f]" />
          </div>
          <label className="mt-6 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[#65736c]">
            Optional focus
          </label>
          <textarea
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            placeholder="Leave blank to cover the entire PDF, or enter a topic to emphasize."
            className="mt-3 min-h-28 w-full resize-y rounded-2xl border border-[#dce3de] bg-[#fafbfa] p-4 text-sm leading-6 outline-none focus:border-[#91ad85] focus:ring-4 focus:ring-[#91ad85]/10"
          />
          <button
            onClick={() => void generate()}
            disabled={selectedIds.length === 0}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-[#c8f169] px-5 py-3.5 text-sm font-semibold text-[#17321f] disabled:opacity-40 sm:w-auto sm:justify-start sm:py-3"
          >
            {activeJobs.length > 0 ? (
              <span className="size-4 animate-spin rounded-full border-2 border-[#17321f]/20 border-t-[#17321f]" />
            ) : (
              <Play size={16} fill="currentColor" />
            )}
            {activeJobs.length > 0
              ? `Add ${activeTool.label} to queue`
              : `Generate ${activeTool.label}`}
          </button>
          <p className="mt-3 text-xs leading-5 text-[#7c8982]">
            You can leave this page after starting work. Queued jobs keep running
            and the result appears here when you return.
          </p>
          {error && (
            <p className="mt-4 rounded-xl bg-[#fff1ed] px-4 py-3 text-sm text-[#9c3e2c]">
              {error}
            </p>
          )}
          <div className="mt-6 min-h-64 min-w-0 max-w-full overflow-hidden rounded-2xl border border-[#e2e7e4] bg-[#f8faf8] p-4 sm:p-5">
            {selectedJob ? (
              <StudyJobOutput job={selectedJob} />
            ) : (
              <p className="text-sm text-[#929c96]">
                Your queued {activeTool.label.toLowerCase()} will appear here.
              </p>
            )}
          </div>
        </section>
      </div>
    </AppShell>
  );
}

function StudyJobOutput({ job }: { job: StudyJob }) {
  if (job.status === "queued" || job.status === "running") {
    return (
      <div className="flex min-h-48 flex-col items-center justify-center text-center">
        <span className="size-10 animate-spin rounded-full border-2 border-[#17321f]/10 border-t-[#56843f]" />
        <h3 className="mt-4 font-semibold text-[#263b30]">
          {job.status === "queued" ? "Waiting in queue" : "Generating now"}
        </h3>
        <p className="mt-2 max-w-md text-sm leading-6 text-[#7c8982]">
          {toolLabel(job.tool)} is being created from {job.sourceNames.join(", ")}.
          You can visit other pages while it finishes.
        </p>
      </div>
    );
  }

  if (job.status === "failed") {
    return (
      <div className="rounded-2xl bg-[#fff1ed] p-5">
        <h3 className="font-semibold text-[#8b3727]">Generation failed</h3>
        <p className="mt-2 text-sm leading-6 text-[#9c3e2c]">
          {job.error ?? "The AI assistant could not complete this job."}
        </p>
      </div>
    );
  }

  if (!job.result) {
    return (
      <p className="text-sm text-[#929c96]">
        This job finished, but no result was returned.
      </p>
    );
  }

  return <StudyOutput output={job.result} tool={job.tool} />;
}

function StudyOutput({
  output,
  tool,
}: {
  output: StudyToolResponse;
  tool: StudyToolKind;
}) {
  const items = output.data?.items ?? [];

  return (
    <div className="min-w-0 max-w-full break-words [overflow-wrap:anywhere]">
      {(tool === "summary" || tool === "plan") && (
        <MarkdownText text={output.text} />
      )}
      {tool === "mcq" && (
        <div className="space-y-4">
          {(items as MCQItem[]).map((item, index) => (
            <article key={`${item.question}-${index}`} className="rounded-2xl bg-white p-5">
              <h3 className="font-semibold text-[#24372d]">
                {index + 1}. {item.question}
              </h3>
              <div className="mt-3 space-y-2">
                {item.options.map((option, optionIndex) => (
                  <p
                    key={`${option}-${optionIndex}`}
                    className={`rounded-xl px-3 py-2 text-sm ${
                      optionIndex === item.answer_index
                        ? "bg-[#edf7df] font-medium text-[#315126]"
                        : "bg-[#f5f7f5] text-[#526159]"
                    }`}
                  >
                    {String.fromCharCode(65 + optionIndex)}. {option}
                  </p>
                ))}
              </div>
              <p className="mt-3 text-sm leading-6 text-[#65736c]">
                <span className="font-semibold text-[#3d5548]">Why:</span>{" "}
                {item.explanation}
              </p>
            </article>
          ))}
        </div>
      )}
      {tool === "flashcards" && (
        <div className="grid gap-4 md:grid-cols-2">
          {(items as FlashcardItem[]).map((item, index) => (
            <article key={`${item.front}-${index}`} className="rounded-2xl bg-white p-5">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#78906d]">
                Card {index + 1}
              </p>
              <h3 className="mt-2 font-semibold leading-6 text-[#24372d]">
                {item.front}
              </h3>
              <div className="my-4 h-px bg-[#e4e9e5]" />
              <p className="text-sm leading-6 text-[#526159]">{item.back}</p>
            </article>
          ))}
        </div>
      )}
      {output.citations.length > 0 && (
        <div className="mt-6 border-t border-[#dfe5e1] pt-5">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7c8982]">
            PDF sources used
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {output.citations.map((citation) => (
              <span
                key={citation.chunk_id}
                title={citation.quoted_snippet}
                className="rounded-full border border-[#dce5d8] bg-white px-3 py-1.5 text-xs text-[#526159]"
              >
                {citation.filename}
                {citation.page_number ? ` · page ${citation.page_number}` : ""}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function toolLabel(tool: StudyToolKind) {
  return {
    summary: "Summary",
    mcq: "MCQs",
    flashcards: "Flashcards",
    plan: "Study plan",
  }[tool];
}

function statusClass(status: StudyJob["status"]) {
  return {
    queued: "bg-[#eef2f0] text-[#65736c]",
    running: "bg-[#edf7df] text-[#3f6f2f]",
    completed: "bg-[#eaf5ff] text-[#315baa]",
    failed: "bg-[#fff1ed] text-[#9c3e2c]",
  }[status];
}
