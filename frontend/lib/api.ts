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

  const payload = await response.json();
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

