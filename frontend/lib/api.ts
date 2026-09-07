export type DocumentRecord = {
  id: string;
  filename: string;
  file_type: string;
  content_type: string | null;
  file_size: number;
  title: string;
  study_session_id: string | null;
  status: "processing" | "indexed" | "failed";
  chunk_count: number;
  character_count: number;
  created_at: string;
  error: string | null;
};

export type Citation = {
  document_id: string;
  filename: string;
  page_number: number | null;
  chunk_id: string;
  quoted_snippet: string;
  relevance_score: number;
};

export type GroundedChatResponse = {
  session_id: string;
  answer_text: string;
  citations: Citation[];
  latency_ms: number;
};

export type ChatSessionSummary = {
  id: string;
  title: string;
  study_session_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ChatSessionMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  citations: Citation[];
  created_at: string;
};

export type ChatSessionDetail = {
  id: string;
  title: string;
  study_session_id: string | null;
  messages: ChatSessionMessage[];
};

export type StudyWorkspace = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type StudyToolKind = "summary" | "mcq" | "flashcards" | "plan";

export type MCQItem = {
  question: string;
  options: string[];
  answer_index: number;
  explanation: string;
};

export type FlashcardItem = {
  front: string;
  back: string;
};

export type StudyToolResponse = {
  tool: StudyToolKind;
  text: string;
  data: { items: MCQItem[] | FlashcardItem[] } | null;
  citations: Citation[];
  latency_ms: number;
};

export type SystemStatus = {
  status: string;
  ai_ready: boolean;
  data_ready: boolean;
  database: string;
};

export type ModelProviderPreset = {
  id: string;
  label: string;
  base_url: string;
  example_model_id: string;
  api_key_url: string;
};

export type CustomModelSettings = {
  configured: boolean;
  is_enabled: boolean;
  display_name?: string;
  provider_name?: string;
  base_url?: string;
  model_id?: string;
  api_key_hint?: string;
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  max_context_tokens?: number;
  supports_streaming?: boolean;
  supports_system_message?: boolean;
  supports_json_mode?: boolean;
  fallback_to_managed?: boolean;
  last_verified_at?: string | null;
  last_error?: string | null;
};

export type ModelSettingsResponse = {
  managed: { configured: boolean; display_name: string; description: string };
  custom: CustomModelSettings;
  presets: ModelProviderPreset[];
  active_source: "custom" | "managed";
};

export type ModelSettingsInput = {
  display_name: string;
  provider_name: string;
  base_url: string;
  model_id: string;
  api_key?: string | null;
  temperature: number;
  top_p: number;
  max_tokens: number;
  max_context_tokens: number;
  supports_streaming: boolean;
  supports_system_message: boolean;
  supports_json_mode: boolean;
  fallback_to_managed: boolean;
  is_enabled: boolean;
};

export type ModelTestInput = {
  base_url?: string;
  model_id?: string;
  api_key?: string | null;
  supports_system_message?: boolean;
};

export type ModelTestResult = {
  ok: boolean;
  text?: string;
  latency_ms?: number;
  error_type?: string | null;
  error_message?: string | null;
};

export type AuthUser = {
  id: string;
  email: string;
  display_name: string;
};

type AuthResponse = {
  user: AuthUser;
  csrf_token: string;
};

const configuredApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
export const API_BASE_URL = configuredApiBaseUrl
  ? (
      configuredApiBaseUrl.startsWith("http://") ||
      configuredApiBaseUrl.startsWith("https://")
        ? configuredApiBaseUrl
        : `https://${configuredApiBaseUrl}`
    ).replace(/\/$/, "")
  : "http://127.0.0.1:8000";

let csrfToken = "";

export function setCsrfToken(value: string) {
  csrfToken = value;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const mutation = !["GET", "HEAD", "OPTIONS"].includes(method);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(mutation && csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
      ...init?.headers,
    },
  });

  const text = await response.text();
  let payload: any = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text };
    }
  }
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event("studyos-auth-required"));
    }
    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.error_message ?? `Request failed with HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
}

export async function getCurrentUser(): Promise<AuthUser> {
  const response = await request<AuthResponse>("/api/auth/me");
  setCsrfToken(response.csrf_token);
  return response.user;
}

export async function login(
  email: string,
  password: string,
): Promise<AuthUser> {
  const response = await request<AuthResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setCsrfToken(response.csrf_token);
  return response.user;
}

export async function register(
  displayName: string,
  email: string,
  password: string,
): Promise<AuthUser> {
  const response = await request<AuthResponse>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({
      display_name: displayName,
      email,
      password,
    }),
  });
  setCsrfToken(response.csrf_token);
  return response.user;
}

export async function logout(): Promise<void> {
  await request<void>("/api/auth/logout", { method: "POST" });
  setCsrfToken("");
}

export async function getDocuments(
  studySessionId?: string | null,
): Promise<DocumentRecord[]> {
  const query = studySessionId
    ? `?study_session_id=${encodeURIComponent(studySessionId)}`
    : "";
  const response = await request<{ documents: DocumentRecord[] }>(
    `/api/documents${query}`,
  );
  return response.documents;
}

export async function uploadDocument(
  file: File,
  studySessionId?: string | null,
): Promise<DocumentRecord> {
  const form = new FormData();
  form.append("file", file);
  if (studySessionId) {
    form.append("study_session_id", studySessionId);
  }
  const response = await fetch(`${API_BASE_URL}/api/documents/upload`, {
    method: "POST",
    body: form,
    credentials: "include",
    headers: csrfToken ? { "X-CSRF-Token": csrfToken } : {},
  });
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(
      typeof detail === "string" ? detail : `Upload failed with HTTP ${response.status}`,
    );
  }
  return payload as DocumentRecord;
}

export function deleteDocument(documentId: string): Promise<void> {
  return request<void>(`/api/documents/${documentId}`, { method: "DELETE" });
}

export function reindexDocument(documentId: string): Promise<DocumentRecord> {
  return request<DocumentRecord>(`/api/documents/${documentId}/reindex`, {
    method: "POST",
  });
}

export function getSystemStatus(): Promise<SystemStatus> {
  return request<SystemStatus>("/ready");
}

export function chatWithDocuments(
  query: string,
  documentIds?: string[],
  sessionId?: string,
  studySessionId?: string | null,
): Promise<GroundedChatResponse> {
  return request<GroundedChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({
      query,
      document_ids: documentIds?.length ? documentIds : null,
      session_id: sessionId ?? null,
      study_session_id: studySessionId ?? null,
    }),
  });
}

export async function getChatSessions(
  studySessionId?: string | null,
): Promise<ChatSessionSummary[]> {
  const query = studySessionId
    ? `?study_session_id=${encodeURIComponent(studySessionId)}`
    : "";
  const response = await request<{ sessions: ChatSessionSummary[] }>(
    `/api/chat/sessions${query}`,
  );
  return response.sessions;
}

export function getChatSession(sessionId: string): Promise<ChatSessionDetail> {
  return request<ChatSessionDetail>(`/api/chat/sessions/${sessionId}`);
}

export async function getStudyWorkspaces(): Promise<StudyWorkspace[]> {
  const response = await request<{ sessions: StudyWorkspace[] }>(
    "/api/study-sessions",
  );
  return response.sessions;
}

export function createStudyWorkspace(title: string): Promise<StudyWorkspace> {
  return request<StudyWorkspace>("/api/study-sessions", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export function deleteStudyWorkspace(workspaceId: string): Promise<void> {
  return request<void>(`/api/study-sessions/${workspaceId}`, {
    method: "DELETE",
  });
}

export function generateStudyTool(
  tool: StudyToolKind,
  documentIds: string[],
  topic?: string,
): Promise<StudyToolResponse> {
  return request<StudyToolResponse>(`/api/study/${tool}`, {
    method: "POST",
    body: JSON.stringify({
      document_ids: documentIds,
      topic: topic?.trim() || null,
      count: tool === "mcq" ? 5 : 8,
      days: 7,
    }),
  });
}

export function getModelSettings(): Promise<ModelSettingsResponse> {
  return request<ModelSettingsResponse>("/api/settings/model");
}

export function saveModelSettings(
  payload: ModelSettingsInput,
): Promise<ModelSettingsResponse> {
  return request<ModelSettingsResponse>("/api/settings/model", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteModelSettings(): Promise<ModelSettingsResponse> {
  return request<ModelSettingsResponse>("/api/settings/model", {
    method: "DELETE",
  });
}

export function testModelSettings(
  payload: ModelTestInput,
): Promise<ModelTestResult> {
  return request<ModelTestResult>("/api/settings/model/test", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listProviderModels(
  baseUrl: string,
  apiKey?: string,
): Promise<string[]> {
  const response = await request<{ models: string[] }>(
    "/api/settings/model/catalog",
    {
      method: "POST",
      body: JSON.stringify({ base_url: baseUrl, api_key: apiKey || null }),
    },
  );
  return response.models;
}

export type MCPConnection = {
  grant_id: string;
  client_id: string;
  client_name: string;
  scope: string;
  created_at: string;
  expires_at: string;
  last_used_at: string | null;
};

/** The URL a student pastes into Claude or ChatGPT to add StudyOS. */
export const MCP_SERVER_URL = `${API_BASE_URL}/mcp`;

export async function listMcpConnections(): Promise<MCPConnection[]> {
  const response = await request<{ connections: MCPConnection[] }>(
    "/api/mcp/connections",
  );
  return response.connections;
}

export function revokeMcpConnection(grantId: string): Promise<void> {
  return request<void>(`/api/mcp/connections/${grantId}`, {
    method: "DELETE",
  });
}
