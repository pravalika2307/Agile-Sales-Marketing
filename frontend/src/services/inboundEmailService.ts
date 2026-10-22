/**
 * Client service for Inbound Email and Microsoft Graph support mailbox integration.
 */

export interface MatchedEntityInfo {
  contact_id?: string | null;
  contact_name?: string | null;
  contact_job_title?: string | null;
  contact_lead_status?: string | null;

  lead_id?: string | null;
  lead_score?: number | null;
  lead_temperature?: string | null;
  lead_company_name?: string | null;

  company_id?: string | null;
  company_name?: string | null;
  company_domain?: string | null;
}

export interface InboundEmailItem {
  id: string;
  organization_id: string;
  graph_message_id: string;
  graph_conversation_id?: string | null;
  internet_message_id?: string | null;
  sender_email: string;
  sender_name?: string | null;
  recipient_email: string;
  subject?: string | null;
  body_preview?: string | null;
  received_at: string;
  is_read: boolean;
  has_attachments: boolean;
  sync_status: "matched" | "unmatched" | string;
  manual_review_status: "pending" | "reviewed" | "dismissed" | "archived" | string;
  matched_contact_id?: string | null;
  matched_lead_id?: string | null;
  matched_company_id?: string | null;
  matched_entity?: MatchedEntityInfo | null;
  created_at: string;
}

export interface InboundEmailDetail extends InboundEmailItem {
  body_content?: string | null;
  body_content_type: string;
  review_notes?: string | null;
  raw_metadata?: Record<string, unknown> | null;
  is_untrusted_content: boolean;
}

export interface InboundEmailListResponse {
  items: InboundEmailItem[];
  total: number;
  unmatched_count: number;
  unread_count: number;
  page: number;
  limit: number;
}

export interface GraphSyncResultResponse {
  sync_run_id: string;
  organization_id: string;
  mailbox: string;
  status: "completed" | "failed" | "blocked_by_safety_guard" | string;
  messages_fetched: number;
  messages_imported: number;
  messages_matched: number;
  messages_unmatched: number;
  messages_skipped: number;
  error_message?: string | null;
  started_at: string;
  completed_at?: string | null;
}

export interface GraphConfigStatusResponse {
  configured: boolean;
  enabled: boolean;
  auto_sync_enabled: boolean;
  sync_interval_minutes: number;
  support_mailbox: string;
  auth_flow: string;
  approved_mailbox_only: boolean;
  permissions_required: string[];
  mode: "active" | "safety_disabled" | "unconfigured" | string;
  message: string;
}

export interface GraphCheckpointStatusResponse {
  mailbox: string;
  has_checkpoint: boolean;
  is_syncing: boolean;
  last_sync_status: string;
  last_successful_sync_at?: string | null;
  sync_started_at?: string | null;
  total_imported: number;
  error_message?: string | null;
}

export interface ManualReviewPayload {
  status: "reviewed" | "dismissed" | "archived" | "pending";
  review_notes?: string;
}

export interface InboundEmailQueryParams {
  status?: string;
  review_status?: string;
  search?: string;
  page?: number;
  limit?: number;
}

/**
 * Fetch paginated inbound emails with optional status and review filters.
 */
export async function getInboundEmails(
  params: InboundEmailQueryParams = {}
): Promise<InboundEmailListResponse> {
  const query = new URLSearchParams();
  if (params.status && params.status !== "all") query.set("status", params.status);
  if (params.review_status && params.review_status !== "all") query.set("review_status", params.review_status);
  if (params.search && params.search.trim()) query.set("search", params.search.trim());
  if (params.page) query.set("page", params.page.toString());
  if (params.limit) query.set("limit", params.limit.toString());

  const qs = query.toString();
  const url = `/api/inbound-emails${qs ? `?${qs}` : ""}`;

  const response = await fetch(url, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.error || `Failed to fetch inbound emails (${response.status})`);
  }

  return response.json();
}

/**
 * Fetch full message detail for a specific inbound email.
 */
export async function getInboundEmailDetail(id: string): Promise<InboundEmailDetail> {
  const response = await fetch(`/api/inbound-emails/${id}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.error || `Failed to fetch email detail (${response.status})`);
  }

  return response.json();
}

/**
 * Update manual review status and triage notes for an inbound email.
 */
export async function updateManualReview(
  id: string,
  payload: ManualReviewPayload
): Promise<InboundEmailDetail> {
  const response = await fetch(`/api/inbound-emails/${id}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.error || `Failed to update review status (${response.status})`);
  }

  return response.json();
}

/**
 * Trigger manual mailbox sync from Microsoft Graph.
 */
export async function triggerMailboxSync(params?: {
  max_messages?: number;
  folder?: string;
}): Promise<GraphSyncResultResponse> {
  const response = await fetch("/api/inbound-emails/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params || {}),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.error || `Failed to initiate mailbox sync (${response.status})`);
  }

  return response.json();
}

/**
 * Inspect Microsoft Graph integration and safety status.
 */
export async function getGraphConfigStatus(): Promise<GraphConfigStatusResponse> {
  const response = await fetch("/api/inbound-emails/config-status", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.error || `Failed to get Graph status (${response.status})`);
  }

  return response.json();
}

/**
 * List recent synchronization runs for audit inspection.
 */
export async function getGraphSyncRuns(limit = 10): Promise<GraphSyncResultResponse[]> {
  const response = await fetch(`/api/inbound-emails/sync-runs?limit=${limit}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.error || `Failed to fetch sync runs (${response.status})`);
  }

  return response.json();
}

/**
 * Fetch incremental checkpoint status and concurrency lock state.
 */
export async function getCheckpointStatus(): Promise<GraphCheckpointStatusResponse> {
  const response = await fetch("/api/inbound-emails/checkpoint-status", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.error || `Failed to fetch checkpoint status (${response.status})`);
  }

  return response.json();
}
