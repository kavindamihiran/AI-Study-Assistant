export type ModelCapabilities = {
  streaming: boolean;
  json_mode: boolean;
  tool_calling: boolean;
  reasoning_mode: boolean;
  vision: boolean;
  system_message: boolean;
  structured_output: boolean;
};

export type ModelProfile = {
  profile_id: string;
  display_name: string;
  provider_name: string;
  model_id: string;
  max_context_tokens: number;
  capabilities: ModelCapabilities;
  defaults: {
    temperature: number;
    top_p: number;
    max_tokens: number;
  };
  prompt_style: string;
  enabled: boolean;
  configured: boolean;
};

export type GatewayResponse = {
  text: string;
  parsed_json: unknown;
  tool_calls: unknown[];
  content_blocks: unknown[];
  usage: {
    input_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
  };
  model_id: string | null;
  profile_id: string | null;
  finish_reason: string | null;
  error_type: string | null;
  error_message: string | null;
  retry_count: number;
  latency_ms: number;
};

export type DocumentRecord = {
  id: string;
  filename: string;
  file_type: string;
  content_type: string | null;
  file_size: number;
  title: string;
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
  model_id: string | null;
  profile_id: string;
  latency_ms: number;
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
  model_id: string | null;
  profile_id: string;
  latency_ms: number;
};

export type SystemStatus = {
  status: string;
  active_profile_id: string;
  model_configured: boolean;
  database: string;
  database_backend: string;
  vector_store: string;
  vector_store_ready: boolean;
  embedding_model: string;
  embedding_dimension: number;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
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
    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.error_message ?? `Request failed with HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
}

export async function getProfiles(): Promise<ModelProfile[]> {
  const response = await request<{ profiles: ModelProfile[] }>(
    "/api/models/profiles",
  );
  return response.profiles;
}

export function getActiveProfile(): Promise<ModelProfile> {
  return request<ModelProfile>("/api/models/active");
}

export function switchProfile(profileId: string): Promise<ModelProfile> {
  return request<ModelProfile>("/api/models/switch", {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export function testProfile(
  profileId: string,
  prompt: string,
): Promise<GatewayResponse> {
  return request<GatewayResponse>("/api/models/test", {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId, prompt }),
  });
}

export async function getDocuments(): Promise<DocumentRecord[]> {
  const response = await request<{ documents: DocumentRecord[] }>(
    "/api/documents",
  );
  return response.documents;
}

export async function uploadDocument(file: File): Promise<DocumentRecord> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/documents/upload`, {
    method: "POST",
    body: form,
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
  profileId?: string,
): Promise<GroundedChatResponse> {
  return request<GroundedChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({
      query,
      document_ids: documentIds?.length ? documentIds : null,
      session_id: sessionId ?? null,
      profile_id: profileId ?? null,
    }),
  });
}

export function generateStudyTool(
  tool: StudyToolKind,
  documentIds: string[],
  topic?: string,
  profileId?: string,
): Promise<StudyToolResponse> {
  return request<StudyToolResponse>(`/api/study/${tool}`, {
    method: "POST",
    body: JSON.stringify({
      document_ids: documentIds,
      topic: topic?.trim() || null,
      profile_id: profileId ?? null,
      count: tool === "mcq" ? 5 : 8,
      days: 7,
    }),
  });
}
