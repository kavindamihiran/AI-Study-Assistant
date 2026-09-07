"use client";

import {
  AlertTriangle,
  Check,
  Cpu,
  Database,
  ExternalLink,
  FileText,
  Info,
  Loader2,
  LockKeyhole,
  RefreshCw,
  Save,
  Trash2,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell, PageHeading } from "@/components/app-shell";
import { MCPConnections } from "@/components/mcp-connections";
import { useStudyWorkspace } from "@/components/study-workspace-provider";
import {
  CustomModelSettings,
  DocumentRecord,
  ModelProviderPreset,
  ModelSettingsResponse,
  SystemStatus,
  deleteModelSettings,
  getDocuments,
  getModelSettings,
  getSystemStatus,
  listProviderModels,
  saveModelSettings,
  testModelSettings,
} from "@/lib/api";

const inputClass =
  "mt-2 w-full rounded-xl border border-[#dce3de] px-4 py-3 text-sm outline-none focus:border-[#6e947a]";
const labelClass =
  "text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7c8982]";

type FormState = {
  presetId: string;
  displayName: string;
  baseUrl: string;
  modelId: string;
  apiKey: string;
  temperature: number;
  topP: number;
  maxTokens: number;
  maxContextTokens: number;
  supportsStreaming: boolean;
  supportsSystemMessage: boolean;
  supportsJsonMode: boolean;
  fallbackToManaged: boolean;
  isEnabled: boolean;
};

const emptyForm: FormState = {
  presetId: "nvidia",
  displayName: "My model",
  baseUrl: "",
  modelId: "",
  apiKey: "",
  temperature: 0.2,
  topP: 0.95,
  maxTokens: 2048,
  maxContextTokens: 32768,
  supportsStreaming: true,
  supportsSystemMessage: true,
  supportsJsonMode: false,
  fallbackToManaged: true,
  isEnabled: true,
};

function formFromSettings(
  custom: CustomModelSettings,
  presets: ModelProviderPreset[],
): FormState {
  if (!custom.configured) return emptyForm;
  const preset =
    presets.find((item) => item.id === custom.provider_name) ??
    presets.find((item) => item.base_url === custom.base_url);
  return {
    presetId: preset?.id ?? "custom",
    displayName: custom.display_name ?? "My model",
    baseUrl: custom.base_url ?? "",
    modelId: custom.model_id ?? "",
    apiKey: "",
    temperature: custom.temperature ?? 0.2,
    topP: custom.top_p ?? 0.95,
    maxTokens: custom.max_tokens ?? 2048,
    maxContextTokens: custom.max_context_tokens ?? 32768,
    supportsStreaming: custom.supports_streaming ?? true,
    supportsSystemMessage: custom.supports_system_message ?? true,
    supportsJsonMode: custom.supports_json_mode ?? false,
    fallbackToManaged: custom.fallback_to_managed ?? true,
    isEnabled: custom.is_enabled,
  };
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-[#e2e7e4] bg-[#f8faf8] p-3">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 size-4 accent-[#173a29]"
      />
      <span className="min-w-0">
        <span className="block text-sm font-medium text-[#213029]">{label}</span>
        <span className="mt-0.5 block text-xs leading-5 text-[#7c8982]">
          {hint}
        </span>
      </span>
    </label>
  );
}

export default function SettingsPage() {
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const { activeWorkspace } = useStudyWorkspace();

  const [settings, setSettings] = useState<ModelSettingsResponse | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"save" | "test" | "models" | "remove" | null>(
    null,
  );
  const [message, setMessage] = useState<{
    tone: "ok" | "error" | "info";
    text: string;
  } | null>(null);
  const [catalog, setCatalog] = useState<string[]>([]);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    void getSystemStatus()
      .then(setSystem)
      .catch(() => setSystem(null));
  }, []);

  useEffect(() => {
    if (!activeWorkspace) return;
    void getDocuments(activeWorkspace.id)
      .then(setDocuments)
      .catch(() => setDocuments([]));
  }, [activeWorkspace?.id]);

  useEffect(() => {
    void getModelSettings()
      .then((response) => {
        setSettings(response);
        setForm(formFromSettings(response.custom, response.presets));
      })
      .catch((error: Error) =>
        setMessage({ tone: "error", text: error.message }),
      )
      .finally(() => setLoading(false));
  }, []);

  const presets = settings?.presets ?? [];
  const activePreset = useMemo(
    () => presets.find((item) => item.id === form.presetId),
    [presets, form.presetId],
  );
  const custom = settings?.custom;
  const usingCustom = Boolean(custom?.configured && custom?.is_enabled);
  const managedConfigured = Boolean(settings?.managed.configured);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setMessage(null);
  }

  function applyPreset(presetId: string) {
    const preset = presets.find((item) => item.id === presetId);
    setCatalog([]);
    setForm((current) => ({
      ...current,
      presetId,
      baseUrl: preset && preset.base_url ? preset.base_url : current.baseUrl,
      displayName:
        preset && preset.id !== "custom" ? preset.label : current.displayName,
    }));
    setMessage(null);
  }

  async function handleSave() {
    setBusy("save");
    setMessage(null);
    try {
      const response = await saveModelSettings({
        display_name: form.displayName || "My model",
        provider_name: form.presetId,
        base_url: form.baseUrl,
        model_id: form.modelId,
        api_key: form.apiKey.trim() || null,
        temperature: form.temperature,
        top_p: form.topP,
        max_tokens: form.maxTokens,
        max_context_tokens: form.maxContextTokens,
        supports_streaming: form.supportsStreaming,
        supports_system_message: form.supportsSystemMessage,
        supports_json_mode: form.supportsJsonMode,
        fallback_to_managed: form.fallbackToManaged,
        is_enabled: form.isEnabled,
      });
      setSettings(response);
      setForm(formFromSettings(response.custom, response.presets));
      setMessage({
        tone: "ok",
        text: "Saved. Chat and study tools will now use this model.",
      });
    } catch (error) {
      setMessage({ tone: "error", text: (error as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function handleTest() {
    setBusy("test");
    setMessage(null);
    try {
      const result = await testModelSettings({
        base_url: form.baseUrl,
        model_id: form.modelId,
        api_key: form.apiKey.trim() || null,
        supports_system_message: form.supportsSystemMessage,
      });
      if (result.ok) {
        setMessage({
          tone: "ok",
          text: `Connection works (${Math.round(result.latency_ms ?? 0)} ms). Reply: ${
            result.text || "(empty)"
          }`,
        });
      } else {
        setMessage({
          tone: "error",
          text: result.error_message || "The provider rejected the request.",
        });
      }
    } catch (error) {
      setMessage({ tone: "error", text: (error as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function handleLoadModels() {
    setBusy("models");
    setMessage(null);
    try {
      const models = await listProviderModels(
        form.baseUrl,
        form.apiKey.trim() || undefined,
      );
      setCatalog(models);
      setMessage(
        models.length
          ? { tone: "info", text: `Found ${models.length} models.` }
          : {
              tone: "info",
              text: "The provider returned no model list. Type the model ID by hand.",
            },
      );
    } catch (error) {
      setMessage({ tone: "error", text: (error as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function handleRemove() {
    setBusy("remove");
    setMessage(null);
    try {
      const response = await deleteModelSettings();
      setSettings(response);
      setForm(emptyForm);
      setCatalog([]);
      setMessage({
        tone: "info",
        text: managedConfigured
          ? "Removed. The shared study assistant will be used again."
          : "Removed. Add a key again to use chat and study tools.",
      });
    } catch (error) {
      setMessage({ tone: "error", text: (error as Error).message });
    } finally {
      setBusy(null);
    }
  }

  const canSubmit =
    form.baseUrl.trim().length > 0 &&
    form.modelId.trim().length > 0 &&
    (form.apiKey.trim().length > 0 || Boolean(custom?.configured));

  return (
    <AppShell>
      <PageHeading
        section="Settings"
        title="Model and workspace settings"
        description="Bring your own OpenAI-compatible API key and choose any model you like."
      />
      <div className="mt-7 grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section className="min-w-0 space-y-6">
          <div className="rounded-3xl border border-[#dfe5e1] bg-white p-5 sm:p-6">
            <div className="flex items-center gap-3">
              <div className="grid size-10 place-items-center rounded-xl bg-[#edf5e6] text-[#56843f]">
                <Cpu size={18} />
              </div>
              <div className="min-w-0">
                <h2 className="text-base font-semibold">Your AI model</h2>
                <p className="mt-1 text-xs text-[#7c8982]">
                  Works with any OpenAI-compatible endpoint: NVIDIA NIM, OpenAI,
                  OpenRouter, Groq, Together, Mistral, DeepSeek, or a local
                  server. Your key is encrypted before it is stored and is never
                  sent back to the browser.
                </p>
              </div>
            </div>

            <div
              className={`mt-5 flex items-start gap-3 rounded-2xl border p-4 text-sm ${
                usingCustom
                  ? "border-[#cfe3cd] bg-[#f2f9ee] text-[#3d5b35]"
                  : managedConfigured
                    ? "border-[#e2e7e4] bg-[#f8faf8] text-[#54615a]"
                    : "border-[#f0ddc2] bg-[#fdf7ec] text-[#7a5a24]"
              }`}
            >
              {usingCustom ? (
                <Zap size={16} className="mt-0.5 shrink-0" />
              ) : managedConfigured ? (
                <Info size={16} className="mt-0.5 shrink-0" />
              ) : (
                <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              )}
              <p className="leading-6">
                {usingCustom
                  ? `Answers are generated with your own model: ${custom?.model_id}.`
                  : managedConfigured
                    ? "Answers currently use the shared study assistant configured by the server. Add your own key below to use your own model."
                    : "No shared model is configured on this server, so chat and study tools need your own API key below."}
                {custom?.configured && !custom.is_enabled
                  ? " Your saved model is turned off."
                  : ""}
              </p>
            </div>

            {custom?.last_error ? (
              <p className="mt-3 rounded-xl border border-[#f2d3d3] bg-[#fdf3f3] px-4 py-3 text-xs leading-5 text-[#95463f]">
                Last error from your provider: {custom.last_error}
              </p>
            ) : null}

            {loading ? (
              <p className="mt-6 flex items-center gap-2 text-sm text-[#7c8982]">
                <Loader2 size={16} className="animate-spin" /> Loading model
                settings...
              </p>
            ) : (
              <div className="mt-6 space-y-5">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className={labelClass} htmlFor="provider">
                      Provider
                    </label>
                    <select
                      id="provider"
                      value={form.presetId}
                      onChange={(event) => applyPreset(event.target.value)}
                      className={inputClass}
                    >
                      {presets.map((preset) => (
                        <option key={preset.id} value={preset.id}>
                          {preset.label}
                        </option>
                      ))}
                    </select>
                    {activePreset?.api_key_url ? (
                      <a
                        href={activePreset.api_key_url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-[#3f6b4d] hover:underline"
                      >
                        Get an API key <ExternalLink size={12} />
                      </a>
                    ) : null}
                  </div>
                  <div>
                    <label className={labelClass} htmlFor="display-name">
                      Label
                    </label>
                    <input
                      id="display-name"
                      value={form.displayName}
                      maxLength={120}
                      onChange={(event) =>
                        update("displayName", event.target.value)
                      }
                      className={inputClass}
                      placeholder="My model"
                    />
                  </div>
                </div>

                <div>
                  <label className={labelClass} htmlFor="base-url">
                    Base URL
                  </label>
                  <input
                    id="base-url"
                    value={form.baseUrl}
                    maxLength={512}
                    onChange={(event) => update("baseUrl", event.target.value)}
                    className={inputClass}
                    placeholder="https://integrate.api.nvidia.com/v1"
                    spellCheck={false}
                  />
                  <p className="mt-2 text-xs text-[#7c8982]">
                    The root that ends in <code>/v1</code>. A pasted{" "}
                    <code>/chat/completions</code> suffix is trimmed for you.
                  </p>
                </div>

                <div>
                  <label className={labelClass} htmlFor="api-key">
                    API key
                  </label>
                  <input
                    id="api-key"
                    type="password"
                    value={form.apiKey}
                    maxLength={512}
                    onChange={(event) => update("apiKey", event.target.value)}
                    className={inputClass}
                    placeholder={
                      custom?.api_key_hint
                        ? `Saved: ${custom.api_key_hint} — leave blank to keep it`
                        : "nvapi-..."
                    }
                    autoComplete="off"
                    spellCheck={false}
                  />
                </div>

                <div>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <label className={labelClass} htmlFor="model-id">
                      Model ID
                    </label>
                    <button
                      type="button"
                      onClick={handleLoadModels}
                      disabled={busy !== null || !form.baseUrl}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-[#dce3de] px-3 py-1.5 text-xs font-medium text-[#3f6b4d] disabled:opacity-50"
                    >
                      {busy === "models" ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <RefreshCw size={12} />
                      )}
                      Load available models
                    </button>
                  </div>
                  <input
                    id="model-id"
                    value={form.modelId}
                    maxLength={255}
                    list="provider-model-catalog"
                    onChange={(event) => update("modelId", event.target.value)}
                    className={inputClass}
                    placeholder={
                      activePreset?.example_model_id ||
                      "meta/llama-3.3-70b-instruct"
                    }
                    spellCheck={false}
                  />
                  <datalist id="provider-model-catalog">
                    {catalog.map((model) => (
                      <option key={model} value={model} />
                    ))}
                  </datalist>
                  <p className="mt-2 text-xs text-[#7c8982]">
                    Any model the provider serves. If it rejects the request,
                    the shared assistant answers instead when fallback is on.
                  </p>
                </div>

                <button
                  type="button"
                  onClick={() => setShowAdvanced((value) => !value)}
                  className="text-xs font-semibold text-[#3f6b4d] hover:underline"
                >
                  {showAdvanced ? "Hide advanced options" : "Show advanced options"}
                </button>

                {showAdvanced ? (
                  <div className="space-y-4 rounded-2xl border border-[#e2e7e4] bg-[#f8faf8] p-4">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <label className={labelClass} htmlFor="temperature">
                          Temperature
                        </label>
                        <input
                          id="temperature"
                          type="number"
                          min={0}
                          max={2}
                          step={0.05}
                          value={form.temperature}
                          onChange={(event) =>
                            update("temperature", Number(event.target.value))
                          }
                          className={inputClass}
                        />
                      </div>
                      <div>
                        <label className={labelClass} htmlFor="top-p">
                          Top P
                        </label>
                        <input
                          id="top-p"
                          type="number"
                          min={0.01}
                          max={1}
                          step={0.01}
                          value={form.topP}
                          onChange={(event) =>
                            update("topP", Number(event.target.value))
                          }
                          className={inputClass}
                        />
                      </div>
                      <div>
                        <label className={labelClass} htmlFor="max-tokens">
                          Max output tokens
                        </label>
                        <input
                          id="max-tokens"
                          type="number"
                          min={64}
                          max={32000}
                          step={64}
                          value={form.maxTokens}
                          onChange={(event) =>
                            update("maxTokens", Number(event.target.value))
                          }
                          className={inputClass}
                        />
                      </div>
                      <div>
                        <label className={labelClass} htmlFor="max-context">
                          Context window
                        </label>
                        <input
                          id="max-context"
                          type="number"
                          min={1024}
                          step={1024}
                          value={form.maxContextTokens}
                          onChange={(event) =>
                            update("maxContextTokens", Number(event.target.value))
                          }
                          className={inputClass}
                        />
                      </div>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Toggle
                        label="Streaming"
                        hint="Turn off if the provider does not support streamed replies."
                        checked={form.supportsStreaming}
                        onChange={(value) => update("supportsStreaming", value)}
                      />
                      <Toggle
                        label="System messages"
                        hint="Turn off for models with no system role; instructions are merged into the first user message."
                        checked={form.supportsSystemMessage}
                        onChange={(value) =>
                          update("supportsSystemMessage", value)
                        }
                      />
                      <Toggle
                        label="JSON mode"
                        hint="Enable only if the model accepts response_format json_object."
                        checked={form.supportsJsonMode}
                        onChange={(value) => update("supportsJsonMode", value)}
                      />
                      <Toggle
                        label="Fall back to the shared assistant"
                        hint={
                          managedConfigured
                            ? "If your provider fails, retry the request on the server's model."
                            : "No shared model is configured on this server, so this has no effect yet."
                        }
                        checked={form.fallbackToManaged}
                        onChange={(value) => update("fallbackToManaged", value)}
                      />
                      <Toggle
                        label="Use this model"
                        hint="Turn off to keep the settings but go back to the shared assistant."
                        checked={form.isEnabled}
                        onChange={(value) => update("isEnabled", value)}
                      />
                    </div>
                  </div>
                ) : null}

                {message ? (
                  <p
                    className={`rounded-xl border px-4 py-3 text-xs leading-5 ${
                      message.tone === "ok"
                        ? "border-[#cfe3cd] bg-[#f2f9ee] text-[#3d5b35]"
                        : message.tone === "error"
                          ? "border-[#f2d3d3] bg-[#fdf3f3] text-[#95463f]"
                          : "border-[#e2e7e4] bg-[#f8faf8] text-[#54615a]"
                    }`}
                  >
                    {message.text}
                  </p>
                ) : null}

                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={handleSave}
                    disabled={busy !== null || !canSubmit}
                    className="flex items-center gap-2 rounded-xl bg-[#173a29] px-5 py-3 text-sm font-semibold text-white disabled:opacity-50"
                  >
                    {busy === "save" ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <Save size={16} />
                    )}
                    Save model
                  </button>
                  <button
                    type="button"
                    onClick={handleTest}
                    disabled={busy !== null || !canSubmit}
                    className="flex items-center gap-2 rounded-xl border border-[#dce3de] px-5 py-3 text-sm font-semibold text-[#213029] disabled:opacity-50"
                  >
                    {busy === "test" ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <Check size={16} />
                    )}
                    Test connection
                  </button>
                  {custom?.configured ? (
                    <button
                      type="button"
                      onClick={handleRemove}
                      disabled={busy !== null}
                      className="flex items-center gap-2 rounded-xl border border-[#e8d3d3] px-5 py-3 text-sm font-semibold text-[#95463f] disabled:opacity-50"
                    >
                      {busy === "remove" ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Trash2 size={16} />
                      )}
                      Remove
                    </button>
                  ) : null}
                </div>

                {custom?.last_verified_at ? (
                  <p className="text-xs text-[#849089]">
                    Last successful test:{" "}
                    {new Date(custom.last_verified_at).toLocaleString()}
                  </p>
                ) : null}
              </div>
            )}
          </div>

          <div className="rounded-3xl border border-[#dfe5e1] bg-white p-5 sm:p-6">
            <div className="flex items-center gap-3">
              <div className="grid size-10 place-items-center rounded-xl bg-[#edf5e6] text-[#56843f]">
                <LockKeyhole size={18} />
              </div>
              <div>
                <h2 className="text-base font-semibold">Student workspace</h2>
                <p className="mt-1 text-xs text-[#7c8982]">
                  The active subject session for uploads and saved work.
                </p>
              </div>
            </div>

            <div className="mt-6 rounded-2xl border border-[#e2e7e4] bg-[#f8faf8] p-5">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#7c8982]">
                Active session
              </p>
              <h3 className="mt-2 text-lg font-semibold">
                {activeWorkspace?.title ?? "Loading session..."}
              </h3>
              <p className="mt-2 text-sm leading-6 text-[#65736c]">
                Uploads, saved chats, and generated study material are scoped to
                this session.
              </p>
            </div>
          </div>

          <MCPConnections />
        </section>

        <aside className="min-w-0 space-y-4">
          {[
            {
              icon: Cpu,
              title: "Active model",
              text: usingCustom
                ? custom?.model_id ?? "Your model"
                : managedConfigured
                  ? "Shared study assistant"
                  : "Not configured yet",
            },
            {
              icon: Check,
              title: "AI features",
              text:
                usingCustom || managedConfigured
                  ? system?.status === "ready" || usingCustom
                    ? "Ready"
                    : "Checking status"
                  : "Add an API key to enable",
            },
            {
              icon: Database,
              title: "Study data",
              text:
                system?.database === "connected"
                  ? "Connected"
                  : "Checking data store",
            },
            {
              icon: FileText,
              title: "Session documents",
              text: `${documents.length} document${
                documents.length === 1 ? "" : "s"
              } in this session`,
            },
          ].map((item) => (
            <div
              key={item.title}
              className="rounded-2xl border border-[#dfe5e1] bg-white p-5"
            >
              <item.icon size={18} className="text-[#66806f]" />
              <p className="mt-3 text-sm font-semibold">{item.title}</p>
              <p className="mt-1 break-words text-xs text-[#849089]">
                {item.text}
              </p>
            </div>
          ))}
        </aside>
      </div>
    </AppShell>
  );
}
