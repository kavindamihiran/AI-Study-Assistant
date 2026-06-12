"use client";

import { LoaderCircle, MessageSquareText } from "lucide-react";
import Link from "next/link";
import {
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Citation, chatWithDocuments } from "@/lib/api";

export type ChatMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
  meta?: string;
  citations?: Citation[];
  status?: "running" | "completed" | "failed";
};

type ActiveChatRequest = {
  assistantMessageId: string;
  prompt: string;
  documentIds: string[];
  sessionId?: string;
};

type ChatContextValue = {
  messages: ChatMessage[];
  selectedDocumentIds: string[];
  sessionId?: string;
  sending: boolean;
  sendMessage: (prompt: string, documentIds: string[]) => void;
  setSelectedDocumentIds: (documentIds: string[]) => void;
  clearMessages: () => void;
};

const STORAGE_KEY = "studyos.chat.v1";
const CHAT_PROFILE_ID = "nvidia_nemotron_default";
const ChatContext = createContext<ChatContextValue | null>(null);

const starterMessage: ChatMessage = {
  id: "starter",
  role: "assistant",
  text: "Upload notes, select the sources you want, and ask a grounded question.",
  status: "completed",
};

function createId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<ChatMessage[]>([starterMessage]);
  const [selectedDocumentIds, setSelectedDocumentIdsState] = useState<string[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [activeRequest, setActiveRequest] = useState<ActiveChatRequest | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const processingRef = useRef(false);
  const sending = activeRequest !== null;

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as {
          messages?: ChatMessage[];
          selectedDocumentIds?: string[];
          sessionId?: string;
          activeRequest?: ActiveChatRequest | null;
        };
        setMessages(parsed.messages?.length ? parsed.messages : [starterMessage]);
        setSelectedDocumentIdsState(parsed.selectedDocumentIds ?? []);
        setSessionId(parsed.sessionId);
        setActiveRequest(parsed.activeRequest ?? null);
      }
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    } finally {
      setHydrated(true);
    }
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        messages,
        selectedDocumentIds,
        sessionId,
        activeRequest,
      }),
    );
  }, [activeRequest, hydrated, messages, selectedDocumentIds, sessionId]);

  useEffect(() => {
    if (!hydrated || !activeRequest || processingRef.current) return;
    processingRef.current = true;
    setMessages((current) =>
      current.map((message) =>
        message.id === activeRequest.assistantMessageId
          ? {
              ...message,
              text: "Retrieving note chunks and generating an answer...",
              status: "running",
            }
          : message,
      ),
    );

    void chatWithDocuments(
      activeRequest.prompt,
      activeRequest.documentIds,
      activeRequest.sessionId,
      CHAT_PROFILE_ID,
    )
      .then((response) => {
        setSessionId(response.session_id);
        setMessages((current) =>
          current.map((message) =>
            message.id === activeRequest.assistantMessageId
              ? {
                  ...message,
                  text: response.answer_text,
                  meta: response.model_id
                    ? `${response.model_id} · ${(response.latency_ms / 1000).toFixed(1)}s`
                    : "No matching note chunks",
                  citations: response.citations,
                  status: "completed",
                }
              : message,
          ),
        );
      })
      .catch((error) => {
        setMessages((current) =>
          current.map((message) =>
            message.id === activeRequest.assistantMessageId
              ? {
                  ...message,
                  text:
                    error instanceof Error
                      ? error.message
                      : "The request failed.",
                  status: "failed",
                }
              : message,
          ),
        );
      })
      .finally(() => {
        processingRef.current = false;
        setActiveRequest(null);
      });
  }, [activeRequest, hydrated]);

  const sendMessage = useCallback(
    (prompt: string, documentIds: string[]) => {
      const trimmed = prompt.trim();
      if (!trimmed || activeRequest || !documentIds.length) return;
      const userMessage: ChatMessage = {
        id: createId(),
        role: "user",
        text: trimmed,
        status: "completed",
      };
      const assistantMessage: ChatMessage = {
        id: createId(),
        role: "assistant",
        text: "Retrieving note chunks and generating an answer...",
        status: "running",
      };
      setMessages((current) => [...current, userMessage, assistantMessage]);
      setActiveRequest({
        assistantMessageId: assistantMessage.id,
        prompt: trimmed,
        documentIds,
        sessionId,
      });
    },
    [activeRequest, sessionId],
  );

  const setSelectedDocumentIds = useCallback((documentIds: string[]) => {
    setSelectedDocumentIdsState(documentIds);
  }, []);

  const clearMessages = useCallback(() => {
    if (activeRequest) return;
    setMessages([starterMessage]);
    setSessionId(undefined);
  }, [activeRequest]);

  const value = useMemo(
    () => ({
      messages,
      selectedDocumentIds,
      sessionId,
      sending,
      sendMessage,
      setSelectedDocumentIds,
      clearMessages,
    }),
    [
      clearMessages,
      messages,
      selectedDocumentIds,
      sendMessage,
      sending,
      sessionId,
      setSelectedDocumentIds,
    ],
  );

  return (
    <ChatContext.Provider value={value}>
      {children}
      {sending && <ChatStatusCard />}
    </ChatContext.Provider>
  );
}

function ChatStatusCard() {
  return (
    <Link
      href="/chat"
      className="fixed bottom-24 right-5 z-50 flex max-w-[330px] items-center gap-3 rounded-2xl border border-[#d9e3dc] bg-white px-4 py-3 shadow-[0_16px_45px_rgba(21,43,31,0.18)] transition hover:-translate-y-0.5"
    >
      <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#eef5ea] text-[#477238]">
        <LoaderCircle size={18} className="animate-spin" />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold text-[#263b30]">
          Answering your notes
        </span>
        <span className="block truncate text-xs text-[#75827b]">
          Chat keeps processing while you browse.
        </span>
      </span>
      <MessageSquareText size={16} className="text-[#78906d]" />
    </Link>
  );
}

export function useChatWorkspace() {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error("useChatWorkspace must be used inside ChatProvider");
  }
  return context;
}
