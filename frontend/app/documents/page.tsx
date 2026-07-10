"use client";

import {
  AlertCircle,
  ArrowRight,
  Brain,
  CheckCircle2,
  File,
  FileText,
  LoaderCircle,
  MessageSquareText,
  Plus,
  RotateCcw,
  Sparkles,
  Trash2,
  UploadCloud,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AppShell, PageHeading } from "@/components/app-shell";
import { StudyFlow } from "@/components/study-flow";
import { useStudyWorkspace } from "@/components/study-workspace-provider";
import {
  DocumentRecord,
  deleteDocument,
  getDocuments,
  reindexDocument,
  uploadDocument,
} from "@/lib/api";

type UploadItem = {
  id: string;
  filename: string;
  status: "uploading" | "failed";
  error?: string;
};

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentsPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [recentDocumentIds, setRecentDocumentIds] = useState<string[]>([]);
  const { activeWorkspace } = useStudyWorkspace();

  async function refreshDocuments() {
    if (!activeWorkspace) return;
    try {
      setDocuments(await getDocuments(activeWorkspace.id));
      setLoadError("");
    } catch (error) {
      setLoadError(
        error instanceof Error ? error.message : "Could not load documents.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    setDocuments([]);
    setRecentDocumentIds([]);
    void refreshDocuments();
  }, [activeWorkspace?.id]);

  async function addFiles(files: FileList | null) {
    if (!files?.length) return;
    const selectedFiles = Array.from(files);
    if (inputRef.current) inputRef.current.value = "";

    for (const file of selectedFiles) {
      const uploadId = crypto.randomUUID();
      setUploads((current) => [
        ...current,
        { id: uploadId, filename: file.name, status: "uploading" },
      ]);
      try {
        const document = await uploadDocument(file, activeWorkspace?.id);
        setDocuments((current) => [
          document,
          ...current.filter((item) => item.id !== document.id),
        ]);
        setRecentDocumentIds((current) =>
          current.includes(document.id) ? current : [...current, document.id],
        );
        setUploads((current) => current.filter((item) => item.id !== uploadId));
      } catch (error) {
        setUploads((current) =>
          current.map((item) =>
            item.id === uploadId
              ? {
                  ...item,
                  status: "failed",
                  error:
                    error instanceof Error ? error.message : "Ingestion failed.",
                }
              : item,
          ),
        );
        await refreshDocuments();
      }
    }
  }

  async function removeDocument(document: DocumentRecord) {
    try {
      await deleteDocument(document.id);
      setDocuments((current) =>
        current.filter((item) => item.id !== document.id),
      );
    } catch (error) {
      setLoadError(
        error instanceof Error ? error.message : "Could not delete document.",
      );
    }
  }

  async function reindex(document: DocumentRecord) {
    setUploads((current) => [
      ...current,
      {
        id: `reindex-${document.id}`,
        filename: document.filename,
        status: "uploading",
      },
    ]);
    try {
      const updated = await reindexDocument(document.id);
      setDocuments((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setUploads((current) =>
        current.filter((item) => item.id !== `reindex-${document.id}`),
      );
    } catch (error) {
      setUploads((current) =>
        current.map((item) =>
          item.id === `reindex-${document.id}`
            ? {
                ...item,
                status: "failed",
                error:
                  error instanceof Error ? error.message : "Reindexing failed.",
              }
            : item,
        ),
      );
      await refreshDocuments();
    }
  }

  return (
    <AppShell>
      <PageHeading
        section="Documents"
        title="Add your study material"
        description={`Start with notes from ${activeWorkspace?.title ?? "this study session"}, then choose exactly how you want to learn from them.`}
        action={
          <button
            onClick={() => inputRef.current?.click()}
            className="flex items-center gap-2 rounded-xl bg-[#173a29] px-4 py-3 text-xs font-semibold text-white"
          >
            <Plus size={16} />
            Add documents
          </button>
        }
      />
      <StudyFlow current="sources" hasSources={documents.length > 0} />
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.txt,.md,.docx"
        className="hidden"
        onChange={(event) => void addFiles(event.target.files)}
      />
      <button
        onClick={() => inputRef.current?.click()}
        onDrop={(event) => {
          event.preventDefault();
          void addFiles(event.dataTransfer.files);
        }}
        onDragOver={(event) => event.preventDefault()}
        className={`mt-5 flex w-full flex-col items-center justify-center border-2 border-dashed border-[#cbd6cf] bg-white text-center transition hover:border-[#84a177] hover:bg-[#fbfdf9] ${
          documents.length
            ? "min-h-40 rounded-2xl p-5 sm:flex-row sm:gap-4 sm:text-left"
            : "min-h-60 rounded-3xl p-8"
        }`}
      >
        <div className="grid size-14 place-items-center rounded-2xl bg-[#edf5e6] text-[#56843f]">
          <UploadCloud size={24} />
        </div>
        <span>
          <h2 className={`${documents.length ? "mt-3 sm:mt-0" : "mt-4"} text-base font-semibold`}>
            {documents.length ? "Add more material" : "Drop study material here"}
          </h2>
          <p className="mt-2 text-xs text-[#7c8982]">
            PDF, TXT, Markdown, or DOCX · Up to 25 MB
          </p>
        </span>
      </button>

      {recentDocumentIds.length > 0 && uploads.every((item) => item.status !== "uploading") && (
        <section className="mt-5 overflow-hidden rounded-3xl bg-[#173a29] text-white shadow-[0_18px_50px_rgba(23,58,41,0.16)]">
          <div className="p-5 sm:p-6">
            <div className="flex items-start gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-[#c8f169] text-[#17321f]">
                <CheckCircle2 size={19} />
              </span>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#c8f169]">
                  Material ready
                </p>
                <h2 className="mt-1 text-xl font-semibold tracking-tight">
                  Great—what do you want to do next?
                </h2>
                <p className="mt-1 text-xs leading-5 text-white/55">
                  Your new {recentDocumentIds.length === 1 ? "document is" : "documents are"} indexed and already selected for the next step.
                </p>
              </div>
            </div>
            <div className="mt-5 grid gap-2 sm:grid-cols-3">
              <NextAction
                href={`/chat?sources=${recentDocumentIds.join(",")}`}
                icon={MessageSquareText}
                title="Ask questions"
                text="Chat with your notes"
                primary
              />
              <NextAction
                href={`/study-tools?tool=summary&sources=${recentDocumentIds.join(",")}`}
                icon={Sparkles}
                title="Make a summary"
                text="Get the key ideas"
              />
              <NextAction
                href={`/study-tools?tool=mcq&sources=${recentDocumentIds.join(",")}`}
                icon={Brain}
                title="Test myself"
                text="Create practice MCQs"
              />
            </div>
          </div>
        </section>
      )}

      <section className="mt-5 rounded-3xl border border-[#dfe5e1] bg-white p-4 sm:p-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Indexed documents</h2>
            <p className="mt-1 text-xs text-[#7c8982]">
              {documents.length} ready · {uploads.length} active upload
              {uploads.length === 1 ? "" : "s"}
            </p>
          </div>
          <FileText size={19} className="text-[#66806f]" />
        </div>

        {loadError && (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            {loadError}
          </div>
        )}

        <div className="mt-5 space-y-3">
          {uploads.map((upload) => (
            <div
              key={upload.id}
              className={`flex items-center gap-3 rounded-2xl border p-3 sm:gap-4 sm:p-4 ${
                upload.status === "failed"
                  ? "border-red-200 bg-red-50"
                  : "border-[#e2e7e4]"
              }`}
            >
              <div className="grid size-10 place-items-center rounded-xl bg-[#fff0e1] text-[#c66b1c]">
                {upload.status === "uploading" ? (
                  <LoaderCircle size={18} className="animate-spin" />
                ) : (
                  <AlertCircle size={18} />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{upload.filename}</p>
                <p className="mt-1 text-[10px] text-[#89948e]">
                  {upload.status === "uploading"
                    ? "Uploading, extracting text, and creating chunks..."
                    : upload.error}
                </p>
              </div>
              {upload.status === "failed" && (
                <button
                  onClick={() =>
                    setUploads((current) =>
                      current.filter((item) => item.id !== upload.id),
                    )
                  }
                  className="text-xs font-semibold text-red-700"
                >
                  Dismiss
                </button>
              )}
            </div>
          ))}

          {loading && (
            <div className="rounded-2xl bg-[#f7f9f7] p-8 text-center text-sm text-[#8a958f]">
              Loading your document library...
            </div>
          )}
          {!loading && !documents.length && !uploads.length && (
            <div className="rounded-2xl bg-[#f7f9f7] p-8 text-center text-sm text-[#8a958f]">
              Upload your first document to make grounded chat available.
            </div>
          )}
          {documents.map((document) => (
            <div
              key={document.id}
              className="flex items-start gap-3 rounded-2xl border border-[#e2e7e4] p-3 sm:items-center sm:gap-4 sm:p-4"
            >
              <div className="grid size-10 place-items-center rounded-xl bg-[#e8f0ff] text-[#3767bd]">
                <File size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-2">
                  <p className="truncate text-sm font-semibold">
                    {document.filename}
                  </p>
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[9px] font-bold uppercase ${
                      document.status === "indexed"
                        ? "bg-[#edf9f1] text-[#247447]"
                        : "bg-red-50 text-red-700"
                    }`}
                  >
                    {document.status === "indexed" ? (
                      <CheckCircle2 size={10} />
                    ) : (
                      <AlertCircle size={10} />
                    )}
                    {document.status}
                  </span>
                </div>
                <p className="mt-1 text-[10px] text-[#89948e]">
                  {formatBytes(document.file_size)} · {document.chunk_count} chunks ·{" "}
                  {document.character_count.toLocaleString()} characters
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {document.status === "failed" && (
                  <button
                    onClick={() => void reindex(document)}
                    className="rounded-lg p-2 text-[#89948e] hover:bg-[#edf5e6] hover:text-[#56843f]"
                    aria-label={`Reindex ${document.filename}`}
                  >
                    <RotateCcw size={16} />
                  </button>
                )}
                <button
                  onClick={() => void removeDocument(document)}
                  className="rounded-lg p-2 text-[#89948e] hover:bg-red-50 hover:text-red-600"
                  aria-label={`Delete ${document.filename}`}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </AppShell>
  );
}

function NextAction({
  href,
  icon: Icon,
  title,
  text,
  primary = false,
}: {
  href: string;
  icon: typeof MessageSquareText;
  title: string;
  text: string;
  primary?: boolean;
}) {
  return (
    <Link
      href={href}
      className={`group flex items-center gap-3 rounded-2xl border p-3.5 transition hover:-translate-y-0.5 ${
        primary
          ? "border-[#c8f169] bg-[#c8f169] text-[#17321f]"
          : "border-white/10 bg-white/[0.07] hover:bg-white/[0.12]"
      }`}
    >
      <span className={`grid size-9 shrink-0 place-items-center rounded-xl ${primary ? "bg-[#173a29] text-[#c8f169]" : "bg-white/10"}`}>
        <Icon size={16} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold">{title}</span>
        <span className={`block text-[10px] ${primary ? "text-[#31533e]" : "text-white/50"}`}>
          {text}
        </span>
      </span>
      <ArrowRight size={15} className="shrink-0 transition group-hover:translate-x-0.5" />
    </Link>
  );
}
