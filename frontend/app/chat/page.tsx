"use client";

import { Bot, Send, Sparkles, User } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell, PageHeading } from "@/components/app-shell";
import { GatewayResponse, ModelProfile, getActiveProfile, testProfile } from "@/lib/api";

type Message = { role: "assistant" | "user"; text: string; meta?: string };

export default function ChatPage() {
  const [profile, setProfile] = useState<ModelProfile | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "Welcome. Ask a study question and I will route it through the active model profile.",
    },
  ]);

  useEffect(() => {
    void getActiveProfile().then(setProfile).catch(() => setProfile(null));
  }, []);

  async function sendMessage() {
    const prompt = input.trim();
    if (!prompt || sending || !profile) return;
    setInput("");
    setSending(true);
    setMessages((current) => [...current, { role: "user", text: prompt }]);
    try {
      const response: GatewayResponse = await testProfile(profile.profile_id, prompt);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: response.text,
          meta: `${response.model_id} · ${(response.latency_ms / 1000).toFixed(1)}s`,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: error instanceof Error ? error.message : "The request failed.",
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <AppShell>
      <PageHeading
        section="Chat with notes"
        title="Ask, understand, remember"
        description="Chat through the same model-safe gateway that will later receive retrieved context and citations from your documents."
        action={
          <div className="rounded-full border border-[#dfe5e1] bg-white px-3 py-1.5 text-xs text-[#65736c]">
            {profile?.display_name ?? "Loading active model..."}
          </div>
        }
      />
      <div className="mt-7 grid gap-6 xl:grid-cols-[1fr_300px]">
        <section className="flex min-h-[620px] flex-col overflow-hidden rounded-3xl border border-[#dfe5e1] bg-white shadow-sm">
          <div className="flex-1 space-y-5 overflow-y-auto p-5 md:p-7">
            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`flex gap-3 ${message.role === "user" ? "justify-end" : ""}`}
              >
                {message.role === "assistant" && (
                  <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#173a29] text-[#c8f169]">
                    <Bot size={17} />
                  </div>
                )}
                <div
                  className={`max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-6 ${
                    message.role === "user"
                      ? "bg-[#173a29] text-white"
                      : "border border-[#e2e7e4] bg-[#f8faf8] text-[#304038]"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{message.text}</p>
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
            {sending && (
              <div className="flex items-center gap-3 text-xs text-[#7c8982]">
                <span className="size-4 animate-spin rounded-full border-2 border-[#173a29]/20 border-t-[#173a29]" />
                Thinking through the gateway...
              </div>
            )}
          </div>
          <div className="border-t border-[#e2e7e4] p-4">
            <div className="flex items-end gap-3 rounded-2xl border border-[#dce3de] bg-[#fafbfa] p-2 focus-within:border-[#91ad85] focus-within:ring-4 focus-within:ring-[#91ad85]/10">
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void sendMessage();
                  }
                }}
                placeholder="Ask a study question..."
                className="min-h-12 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none"
              />
              <button
                onClick={() => void sendMessage()}
                disabled={!input.trim() || sending || !profile}
                className="grid size-11 place-items-center rounded-xl bg-[#c8f169] text-[#17321f] disabled:opacity-40"
                aria-label="Send message"
              >
                <Send size={17} />
              </button>
            </div>
          </div>
        </section>
        <aside className="space-y-4">
          <div className="rounded-2xl border border-[#dfe5e1] bg-white p-5">
            <Sparkles size={18} className="text-[#648b47]" />
            <h2 className="mt-3 text-sm font-semibold">Try asking</h2>
            <div className="mt-3 space-y-2">
              {[
                "Explain B-tree indexes simply.",
                "Create a five-step revision plan.",
                "Quiz me on database normalization.",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setInput(suggestion)}
                  className="w-full rounded-xl border border-[#e2e7e4] p-3 text-left text-xs leading-5 text-[#65736c] hover:bg-[#f7faf6]"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </AppShell>
  );
}

