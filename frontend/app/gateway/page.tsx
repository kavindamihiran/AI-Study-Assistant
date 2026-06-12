"use client";

import { Check, Clock3, Play, ShieldCheck, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell, PageHeading } from "@/components/app-shell";
import {
  GatewayResponse,
  ModelProfile,
  getActiveProfile,
  getProfiles,
  switchProfile,
  testProfile,
} from "@/lib/api";

export default function GatewayPage() {
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [active, setActive] = useState<ModelProfile | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [prompt, setPrompt] = useState("Reply with exactly: gateway online");
  const [result, setResult] = useState<GatewayResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void Promise.all([getProfiles(), getActiveProfile()])
      .then(([allProfiles, activeProfile]) => {
        setProfiles(allProfiles);
        setActive(activeProfile);
        setSelectedId(activeProfile.profile_id);
      })
      .catch((loadError) =>
        setError(loadError instanceof Error ? loadError.message : "Gateway unavailable"),
      );
  }, []);

  const selected = useMemo(
    () => profiles.find((profile) => profile.profile_id === selectedId) ?? null,
    [profiles, selectedId],
  );

  async function activate() {
    if (!selected || selected.profile_id === active?.profile_id) return;
    setBusy(true);
    setError("");
    try {
      setActive(await switchProfile(selected.profile_id));
    } catch (activationError) {
      setError(
        activationError instanceof Error ? activationError.message : "Switch failed",
      );
    } finally {
      setBusy(false);
    }
  }

  async function runTest() {
    if (!selected || !prompt.trim()) return;
    setBusy(true);
    setResult(null);
    setError("");
    try {
      setResult(await testProfile(selected.profile_id, prompt.trim()));
    } catch (testError) {
      setError(testError instanceof Error ? testError.message : "Test failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <PageHeading
        section="Model gateway"
        title="One contract, many models"
        description="Inspect, activate, and test every configured NVIDIA NIM model profile."
        action={
          <div className="flex items-center gap-2 rounded-full border border-[#cce6d6] bg-[#edf9f1] px-3 py-1.5 text-xs font-medium text-[#247447]">
            <span className="size-2 rounded-full bg-[#35a961]" />
            Gateway online
          </div>
        }
      />
      <div className="mt-7 grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <section className="rounded-3xl border border-[#dfe5e1] bg-white p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">Model profiles</h2>
              <p className="mt-1 text-xs text-[#7c8982]">{profiles.length} configured profiles</p>
            </div>
            <ShieldCheck size={20} className="text-[#56843f]" />
          </div>
          <div className="mt-5 space-y-3">
            {profiles.map((profile) => {
              const isSelected = profile.profile_id === selectedId;
              const isActive = profile.profile_id === active?.profile_id;
              return (
                <button
                  key={profile.profile_id}
                  onClick={() => {
                    setSelectedId(profile.profile_id);
                    setResult(null);
                    setError("");
                  }}
                  className={`flex w-full items-center gap-4 rounded-2xl border p-4 text-left ${
                    isSelected ? "border-[#82a874] bg-[#f4faef]" : "border-[#e2e7e4]"
                  }`}
                >
                  <div className="grid size-10 place-items-center rounded-xl bg-[#e8f0ff] text-sm font-bold text-[#3767bd]">
                    {profile.display_name.charAt(0)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-semibold">{profile.display_name}</p>
                      {isActive && (
                        <span className="rounded-full bg-[#dff3d7] px-2 py-0.5 text-[9px] font-bold uppercase text-[#3e732c]">
                          Active
                        </span>
                      )}
                    </div>
                    <p className="mt-1 truncate font-mono text-[10px] text-[#89948e]">
                      {profile.model_id}
                    </p>
                  </div>
                  <div className={`grid size-5 place-items-center rounded-full border ${isSelected ? "border-[#709b61] bg-[#709b61] text-white" : "border-[#ccd4cf]"}`}>
                    {isSelected && <Check size={12} />}
                  </div>
                </button>
              );
            })}
          </div>
          <button
            onClick={() => void activate()}
            disabled={busy || !selected || selected.profile_id === active?.profile_id}
            className="mt-5 rounded-xl bg-[#173a29] px-4 py-3 text-xs font-semibold text-white disabled:opacity-40"
          >
            Set as active
          </button>
        </section>

        <section className="rounded-3xl border border-[#dfe5e1] bg-white p-6">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-xl bg-[#173a29] text-[#c8f169]">
              <Zap size={18} />
            </div>
            <div>
              <h2 className="text-sm font-semibold">Live playground</h2>
              <p className="mt-0.5 text-[10px] text-[#87928c]">Test the selected profile</p>
            </div>
          </div>
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            className="mt-5 min-h-32 w-full resize-y rounded-2xl border border-[#dce3de] bg-[#fafbfa] p-4 text-sm outline-none focus:border-[#91ad85]"
          />
          <button
            onClick={() => void runTest()}
            disabled={busy || !selected || !prompt.trim()}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-[#c8f169] px-4 py-3 text-sm font-semibold text-[#17321f] disabled:opacity-40"
          >
            {busy ? (
              <span className="size-4 animate-spin rounded-full border-2 border-[#17321f]/20 border-t-[#17321f]" />
            ) : (
              <Play size={16} fill="currentColor" />
            )}
            Run gateway test
          </button>
          {(result || error) && (
            <div className={`mt-5 rounded-2xl border p-4 ${error ? "border-red-200 bg-red-50 text-red-800" : "border-[#dce9d6] bg-[#f5faf2]"}`}>
              <p className="whitespace-pre-wrap text-sm leading-6">{error || result?.text}</p>
              {result && (
                <div className="mt-4 flex items-center gap-2 border-t border-[#dce6d7] pt-3 text-[10px] text-[#7f8c85]">
                  <Clock3 size={13} />
                  {(result.latency_ms / 1000).toFixed(1)}s · {result.usage.total_tokens ?? "—"} tokens · {result.retry_count} retries
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}

