"use client";

import {
  AlertCircle,
  CheckCircle2,
  File,
  FileText,
  LoaderCircle,
  Plus,
  RotateCcw,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AppShell, PageHeading } from "@/components/app-shell";
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
        title="Build this session library"
        description={`Upload material for ${activeWorkspace?.title ?? "this study session"}. Each subject session keeps its own documents.`}
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
        className="mt-7 flex min-h-64 w-full flex-col items-center justify-center rounded-3xl border-2 border-dashed border-[#cbd6cf] bg-white p-8 text-center transition hover:border-[#84a177] hover:bg-[#fbfdf9]"
      >
        <div className="grid size-14 place-items-center rounded-2xl bg-[#edf5e6] text-[#56843f]">
          <UploadCloud size={24} />
        </div>
        <h2 className="mt-4 text-base font-semibold">Drop study material here</h2>
        <p className="mt-2 text-xs text-[#7c8982]">
          PDF, TXT, Markdown, or DOCX · Up to 25 MB
        </p>
      </button>

      <section className="mt-6 rounded-3xl border border-[#dfe5e1] bg-white p-6">
        <div className="flex items-center justify-between">
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
              className={`flex items-center gap-4 rounded-2xl border p-4 ${
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
              className="flex items-center gap-4 rounded-2xl border border-[#e2e7e4] p-4"
            >
              <div className="grid size-10 place-items-center rounded-xl bg-[#e8f0ff] text-[#3767bd]">
                <File size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
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
              <div className="flex items-center gap-1">
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
