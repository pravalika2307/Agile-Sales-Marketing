/**
 * Retell AI Voice Integration Service (Frontend)
 *
 * Communicates with backend endpoints to fetch real-time
 * Retell connection health, agent discovery, and configuration metrics.
 */

export interface VoiceAgentSummary {
  agent_id: string;
  agent_name: string;
  channel: string;
  voice_id?: string | null;
  response_engine_type?: string | null;
  llm_id?: string | null;
  user_modified_timestamp?: number | null;
  is_configured_sdr: boolean;
  is_configured_inbound: boolean;
}

export interface VoiceAgentsResponse {
  configured: boolean;
  connected: boolean;
  count: number;
  items: VoiceAgentSummary[];
  configured_outbound_agent_id?: string | null;
  configured_inbound_agent_id?: string | null;
  error?: string | null;
  message: string;
}

export interface VoiceStatusResponse {
  configured: boolean;
  connected: boolean;
  provider: string;
  base_url: string;
  outbound_agent_id?: string | null;
  inbound_agent_id?: string | null;
  outbound_from_number?: string | null;
  outbound_agent_valid?: boolean | null;
  inbound_agent_valid?: boolean | null;
  agent_count?: number | null;
  error?: string | null;
  message: string;
}

/**
 * Fetch Retell AI connection health and configuration status.
 */
export async function getVoiceStatus(): Promise<VoiceStatusResponse> {
  try {
    const resp = await fetch("/api/voice/status", {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      throw new Error(errData.detail || errData.error || `Failed to fetch Voice status: HTTP ${resp.status}`);
    }

    return await resp.json();
  } catch (err: any) {
    if (err.name === "TimeoutError") {
      throw new Error("Voice status check timed out after 15s.");
    }
    throw err;
  }
}

/**
 * Fetch discovered Retell voice agents.
 */
export async function getVoiceAgents(): Promise<VoiceAgentsResponse> {
  try {
    const resp = await fetch("/api/voice/agents", {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      throw new Error(errData.detail || errData.error || `Failed to fetch Voice agents: HTTP ${resp.status}`);
    }

    return await resp.json();
  } catch (err: any) {
    if (err.name === "TimeoutError") {
      throw new Error("Voice agent discovery timed out after 15s.");
    }
    throw err;
  }
}

export interface SimulateMockCallCompletionRequest {
  outreach_id?: string;
  call_id?: string;
  outcome?: string;
  meeting_requested?: boolean;
  callback_requested?: boolean;
  qualification_score?: number;
  call_summary?: string;
  disconnection_reason?: string;
}

export interface SimulateMockCallCompletionResponse {
  status: string;
  call_id: string;
  outreach_id?: string | null;
  call_status: string;
  outreach_status: string;
  call_outcome: string;
  simulated: boolean;
  duplicate: boolean;
  followup_email_created: boolean;
  followup_email_id?: string | null;
  followup_status?: string | null;
  followup_reason?: string | null;
  message: string;
}

/**
 * Deterministically complete a simulated mock voice call in test mode.
 */
export async function simulateMockCallCompletion(
  payload: SimulateMockCallCompletionRequest
): Promise<SimulateMockCallCompletionResponse> {
  try {
    const resp = await fetch("/api/voice/simulate-mock-completion", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      throw new Error(
        errData.detail || errData.error || `Failed to complete simulated call: HTTP ${resp.status}`
      );
    }

    return await resp.json();
  } catch (err: any) {
    if (err.name === "TimeoutError") {
      throw new Error("Simulate call completion request timed out after 15s.");
    }
    throw err;
  }
}
