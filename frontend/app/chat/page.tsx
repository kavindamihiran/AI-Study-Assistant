"use client";

import {
  Bot,
  FileText,
  History,
  RefreshCcw,
  RotateCcw,
  Send,
  Sparkles,
  User,
} from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell, PageHeading } from "@/components/app-shell";
import { useChatWorkspace } from "@/components/chat-provider";
import { MarkdownText } from "@/components/markdown-text";
import { useStudyWorkspace } from "@/components/study-workspace-provider";
import {
  DocumentRecord,
  ChatSessionSummary,
  getChatSession,
  getChatSessions,
  getDocuments,
} from "@/lib/api";

export default function ChatPage() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [input, setInput] = useState("");
  const {
    clearMessages,
    initializeDocumentSelection,
    loadSession,
    messages,
    selectedDocumentIds,
    sessionId,
    sending,
    sendMessage,
    setSelectedDocumentIds,
    sourceSelectionInitialized,
  } = useChatWorkspace();
  const { activeWorkspace } = useStudyWorkspace();

  useEffect(() => {
    if (!activeWorkspace) return;
    void getDocuments(activeWorkspace.id)
      .then((indexedDocuments) => {
        setDocuments(indexedDocuments);
        if (!sourceSelectionInitialized && indexedDocuments.length) {
          initializeDocumentSelection(indexedDocuments.map((document) => document.id));
        }
      })
      .catch(() => {
        setDocuments([]);
      });
  }, [activeWorkspace?.id, initializeDocumentSelection, sourceSelectionInitialized]);

  async function refreshSessions() {
    setLoadingSessions(true);
    try {
      setSessions(await getChatSessions(activeWorkspace?.id));
    } finally {
      setLoadingSessions(false);
    }
  }

  useEffect(() => {
    if (!sending) {
      void refreshSessions();
    }
  }, [activeWorkspace?.id, sending]);

  async function openSavedSession(savedSessionId: string) {
    if (sending) return;
    const saved = await getChatSession(savedSessionId);
    loadSession(saved);
  }

  function toggleDocument(documentId: string) {
    setSelectedDocumentIds(
      selectedDocumentIds.includes(documentId)
        ? selectedDocumentIds.filter((id) => id !== documentId)
        : [...selectedDocumentIds, documentId],
    );
  }

  function handleSendMessage() {
    const prompt = input.trim();
    if (!prompt || sending) return;
    setInput("");
    sendMessage(prompt, selectedDocumentIds, activeWorkspace?.id);
  }

  return (
    <AppShell>
      <PageHeading
        section="Chat with notes"
        title="Ask your uploaded material"
        description={`Questions are matched against documents in ${activeWorkspace?.title ?? "this study session"}.`}
        action={
          <div className="rounded-full border border-[#dfe5e1] bg-white px-3 py-1.5 text-xs text-[#65736c]">
            AI answers ready
          </div>
        }
      />
      <div className="mt-7 grid gap-6 xl:grid-cols-[1fr_320px]">
        <section className="flex min-h-[620px] flex-col overflow-hidden rounded-3xl border border-[#dfe5e1] bg-white shadow-sm">
          <div className="flex-1 space-y-5 overflow-y-auto p-5 md:p-7">
            {messages.map((message, index) => (
              <div
                key={message.id}
                className={`flex gap-3 ${message.role === "user" ? "justify-end" : ""}`}
              >
                {message.role === "assistant" && (
                  <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#173a29] text-[#c8f169]">
                    <Bot size={17} />
                  </div>
                )}
                <div
                  className={`max-w-[82%] rounded-2xl px-4 py-3 text-sm leading-6 ${
                    message.role === "user"
                      ? "bg-[#173a29] text-white"
                      : "border border-[#e2e7e4] bg-[#f8faf8] text-[#304038]"
                  }`}
                >
                  {message.role === "assistant" ? (
                    <>
                      {message.status === "running" && (
                        <span className="mb-2 inline-flex size-4 animate-spin rounded-full border-2 border-[#173a29]/20 border-t-[#173a29]" />
                      )}
                      <MarkdownText text={message.text} />
                    </>
                  ) : (
                    <p className="whitespace-pre-wrap">{message.text}</p>
                  )}
                  {!!message.citations?.length && (
                    <div className="mt-3 space-y-2 border-t border-[#dfe5e1] pt-3">
                      {message.citations.map((citation) => (
                        <div
                          key={citation.chunk_id}
                          className="rounded-xl bg-white p-3 text-[10px] leading-4 text-[#64716a]"
                        >
                          <p className="font-semibold text-[#304038]">
                            {citation.filename}
                            {citation.page_number
                              ? ` · page ${citation.page_number}`
                              : ""}
                          </p>
                          <p className="mt-1 line-clamp-2">
                            {citation.quoted_snippet}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                  {message.meta && (
                    <p className="mt-2 border-t border-[#dfe5e1] pt-2 font-mono text-[9px] text-[#87928c]">
                      {message.meta}
                    </p>
                  )}
                </div>
                {message.role === "user" && (
                  <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#dce8ff] text-[#315baa]">
                    <User size={17} />
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="border-t border-[#e2e7e4] p-4">
            <div className="flex items-end gap-3 rounded-2xl border border-[#dce3de] bg-[#fafbfa] p-2 focus-within:border-[#91ad85] focus-within:ring-4 focus-within:ring-[#91ad85]/10">
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    handleSendMessage();
                  }
                }}
                placeholder={
                  documents.length
                    ? "Ask something from your notes..."
                    : "Upload a document first..."
                }
                disabled={!documents.length}
                className="min-h-12 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none disabled:cursor-not-allowed"
              />
              <button
                onClick={handleSendMessage}
                disabled={
                  !input.trim() ||
                  sending ||
                  !documents.length ||
                  !selectedDocumentIds.length
                }
                className="grid size-11 place-items-center rounded-xl bg-[#c8f169] text-[#17321f] disabled:opacity-40"
                aria-label="Send message"
              >
                <Send size={17} />
              </button>
            </div>
            <div className="mt-3 flex items-center justify-between text-xs text-[#7c8982]">
              <span>
                {sending
                  ? "Processing continues if you visit another page."
                  : "Messages and selected sources persist while you browse."}
              </span>
              <button
                onClick={clearMessages}
                disabled={sending}
                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 font-semibold text-[#56843f] disabled:opacity-40"
              >
                <RotateCcw size={13} />
                Clear chat
              </button>
            </div>
          </div>
        </section>

        <aside className="space-y-4">
          <div className="rounded-2xl border border-[#dfe5e1] bg-white p-5">
            <History size={18} className="text-[#648b47]" />
            <div className="mt-3 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold">Saved sessions</h2>
                <p className="mt-1 text-[11px] leading-5 text-[#849089]">
                  Reopen previous conversations anytime.
                </p>
              </div>
              <button
                onClick={() => void refreshSessions()}
                className="rounded-lg p-2 text-[#65736c] hover:bg-[#f3f6f3]"
                aria-label="Refresh sessions"
              >
                <RefreshCcw
                  size={15}
                  className={loadingSessions ? "animate-spin" : ""}
                />
              </button>
            </div>
            <div className="mt-3 space-y-2">
              {!sessions.length && (
                <p className="rounded-xl bg-[#f7f9f7] p-3 text-xs text-[#89948e]">
                  No saved sessions yet.
                </p>
              )}
              {sessions.slice(0, 8).map((savedSession) => (
                <button
                  key={savedSession.id}
                  onClick={() => void openSavedSession(savedSession.id)}
                  disabled={sending}
                  className={`w-full rounded-xl border p-3 text-left transition disabled:opacity-50 ${
                    savedSession.id === sessionId
                      ? "border-[#9ab68d] bg-[#f2f8ed]"
                      : "border-[#e2e7e4] hover:bg-[#f7f9f7]"
                  }`}
                >
                  <span className="block truncate text-xs font-semibold text-[#263b30]">
                    {savedSession.title}
                  </span>
                  <span className="mt-1 block truncate text-[9px] text-[#89948e]">
                    saved conversation
                  </span>
                </button>
              ))}
            </div>
          </div>
          <div className="rounded-2xl border border-[#dfe5e1] bg-white p-5">
            <FileText size={18} className="text-[#648b47]" />
            <h2 className="mt-3 text-sm font-semibold">Answer sources</h2>
            <p className="mt-1 text-[11px] leading-5 text-[#849089]">
              Select the indexed documents used for retrieval.
            </p>
            <div className="mt-3 space-y-2">
              {!documents.length && (
                <p className="rounded-xl bg-[#f7f9f7] p-3 text-xs text-[#89948e]">
                  No indexed documents yet.
                </p>
              )}
              {documents.map((document) => (
                <label
                  key={document.id}
                  className="flex cursor-pointer items-start gap-3 rounded-xl border border-[#e2e7e4] p-3"
                >
                  <input
                    type="checkbox"
                    checked={selectedDocumentIds.includes(document.id)}
                    onChange={() => toggleDocument(document.id)}
                    className="mt-0.5 accent-[#56843f]"
                  />
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-semibold">
                      {document.filename}
                    </span>
                    <span className="mt-1 block text-[9px] text-[#89948e]">
                      {document.chunk_count} chunks
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </div>
          <div className="rounded-2xl border border-[#dfe5e1] bg-white p-5">
            <Sparkles size={18} className="text-[#648b47]" />
            <h2 className="mt-3 text-sm font-semibold">Retrieval tips</h2>
            <p className="mt-2 text-[11px] leading-5 text-[#849089]">
              Use keywords that appear in your notes. Questions outside indexed
              material return a clear “not found” answer.
            </p>
          </div>
        </aside>
      </div>
    </AppShell>
  );
}
