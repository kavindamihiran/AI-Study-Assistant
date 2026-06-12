"use client";

import { BookOpenCheck, Brain, CalendarDays, Layers3, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell, PageHeading } from "@/components/app-shell";
import { ModelProfile, getActiveProfile, testProfile } from "@/lib/api";

const tools = [
  { id: "summary", label: "Summary", icon: BookOpenCheck, instruction: "Create a concise study summary of:" },
  { id: "mcq", label: "MCQs", icon: Brain, instruction: "Create 5 multiple-choice questions with answers about:" },
  { id: "flashcards", label: "Flashcards", icon: Layers3, instruction: "Create 8 question-and-answer flashcards about:" },
  { id: "plan", label: "Study plan", icon: CalendarDays, instruction: "Create a practical 7-day study plan for:" },
];

export default function StudyToolsPage() {
  const [activeTool, setActiveTool] = useState(tools[0]);
  const [profile, setProfile] = useState<ModelProfile | null>(null);
  const [topic, setTopic] = useState("Database indexing and query optimization");
  const [output, setOutput] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void getActiveProfile().then(setProfile).catch(() => setProfile(null));
  }, []);

  async function generate() {
    if (!profile || !topic.trim()) return;
    setLoading(true);
    setOutput("");
    try {
      const response = await testProfile(
        profile.profile_id,
        `${activeTool.instruction}\n\n${topic.trim()}`,
      );
      setOutput(response.text);
    } catch (error) {
      setOutput(error instanceof Error ? error.message : "Generation failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell>
      <PageHeading
        section="Study tools"
        title="Turn topics into practice"
        description="Generate reusable study material through the currently active gateway profile."
      />
      <div className="mt-7 grid gap-6 xl:grid-cols-[320px_1fr]">
        <section className="rounded-3xl border border-[#dfe5e1] bg-white p-4">
          <p className="px-2 py-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7c8982]">
            Choose a tool
          </p>
          <div className="mt-2 space-y-2">
            {tools.map((tool) => (
              <button
                key={tool.id}
                onClick={() => {
                  setActiveTool(tool);
                  setOutput("");
                }}
                className={`flex w-full items-center gap-3 rounded-2xl p-4 text-left text-sm font-medium transition ${
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
        <section className="rounded-3xl border border-[#dfe5e1] bg-white p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">{activeTool.label} generator</h2>
              <p className="mt-1 text-xs text-[#7c8982]">
                Powered by {profile?.display_name ?? "the active model"}
              </p>
            </div>
            <activeTool.icon size={22} className="text-[#56843f]" />
          </div>
          <label className="mt-6 block text-[11px] font-semibold uppercase tracking-[0.12em] text-[#65736c]">
            Topic or source text
          </label>
          <textarea
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            className="mt-3 min-h-36 w-full resize-y rounded-2xl border border-[#dce3de] bg-[#fafbfa] p-4 text-sm leading-6 outline-none focus:border-[#91ad85] focus:ring-4 focus:ring-[#91ad85]/10"
          />
          <button
            onClick={() => void generate()}
            disabled={loading || !profile || !topic.trim()}
            className="mt-3 flex items-center gap-2 rounded-xl bg-[#c8f169] px-5 py-3 text-sm font-semibold text-[#17321f] disabled:opacity-40"
          >
            {loading ? (
              <span className="size-4 animate-spin rounded-full border-2 border-[#17321f]/20 border-t-[#17321f]" />
            ) : (
              <Play size={16} fill="currentColor" />
            )}
            {loading ? "Generating..." : `Generate ${activeTool.label}`}
          </button>
          <div className="mt-6 min-h-64 rounded-2xl border border-[#e2e7e4] bg-[#f8faf8] p-5">
            {output ? (
              <p className="whitespace-pre-wrap text-sm leading-7 text-[#304038]">
                {output}
              </p>
            ) : (
              <p className="text-sm text-[#929c96]">
                Your generated {activeTool.label.toLowerCase()} will appear here.
              </p>
            )}
          </div>
        </section>
      </div>
    </AppShell>
  );
}

