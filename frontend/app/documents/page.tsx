"use client";

import { File, FileText, Plus, UploadCloud, X } from "lucide-react";
import { useRef, useState } from "react";
import { AppShell, PageHeading } from "@/components/app-shell";

type LocalDocument = { name: string; size: number; type: string };

export default function DocumentsPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [documents, setDocuments] = useState<LocalDocument[]>([]);

  function addFiles(files: FileList | null) {
    if (!files) return;
    setDocuments((current) => [
      ...current,
      ...Array.from(files).map((file) => ({
        name: file.name,
        size: file.size,
        type: file.type || "Unknown",
      })),
    ]);
  }

  return (
    <AppShell>
      <PageHeading
        section="Documents"
        title="Build your study library"
        description="Choose PDFs, text files, or notes now. Backend ingestion and vector indexing will connect to this library in the next implementation phase."
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
        onChange={(event) => addFiles(event.target.files)}
      />
      <button
        onClick={() => inputRef.current?.click()}
        onDrop={(event) => {
          event.preventDefault();
          addFiles(event.dataTransfer.files);
        }}
        onDragOver={(event) => event.preventDefault()}
        className="mt-7 flex min-h-64 w-full flex-col items-center justify-center rounded-3xl border-2 border-dashed border-[#cbd6cf] bg-white p-8 text-center transition hover:border-[#84a177] hover:bg-[#fbfdf9]"
      >
        <div className="grid size-14 place-items-center rounded-2xl bg-[#edf5e6] text-[#56843f]">
          <UploadCloud size={24} />
        </div>
        <h2 className="mt-4 text-base font-semibold">Drop study material here</h2>
        <p className="mt-2 text-xs text-[#7c8982]">PDF, TXT, Markdown, or DOCX</p>
      </button>

      <section className="mt-6 rounded-3xl border border-[#dfe5e1] bg-white p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Selected documents</h2>
            <p className="mt-1 text-xs text-[#7c8982]">
              {documents.length} file{documents.length === 1 ? "" : "s"} waiting
            </p>
          </div>
          <FileText size={19} className="text-[#66806f]" />
        </div>
        <div className="mt-5 space-y-3">
          {!documents.length && (
            <div className="rounded-2xl bg-[#f7f9f7] p-8 text-center text-sm text-[#8a958f]">
              Your selected files will appear here.
            </div>
          )}
          {documents.map((document, index) => (
            <div
              key={`${document.name}-${index}`}
              className="flex items-center gap-4 rounded-2xl border border-[#e2e7e4] p-4"
            >
              <div className="grid size-10 place-items-center rounded-xl bg-[#e8f0ff] text-[#3767bd]">
                <File size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{document.name}</p>
                <p className="mt-1 text-[10px] text-[#89948e]">
                  {(document.size / 1024).toFixed(1)} KB · Ready for ingestion
                </p>
              </div>
              <button
                onClick={() =>
                  setDocuments((current) =>
                    current.filter((_, itemIndex) => itemIndex !== index),
                  )
                }
                className="rounded-lg p-2 text-[#89948e] hover:bg-red-50 hover:text-red-600"
                aria-label={`Remove ${document.name}`}
              >
                <X size={16} />
              </button>
            </div>
          ))}
        </div>
      </section>
    </AppShell>
  );
}

