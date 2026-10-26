/**
 * Client service for SaaS communication channel entitlements and upgrade requests.
 */

export interface ChannelCapability {
  channel: "email" | "sms" | "voice" | "ringless_voicemail" | "physical_mail" | string;
  display_name: string;
  description: string;
  status: "included" | "available" | "upgrade_required" | "upgrade_requested" | "awaiting_approval" | "approved" | "suspended" | string;
  is_unlocked: boolean;
  pricing_model: string;
  provider: string;
  features: string[];
  limits: Record<string, any>;
  allocated_quota?: number | null;
  current_usage: number;
  provider_configured?: boolean;
  provider_status_message?: string | null;
  is_provider_ready?: boolean;
}

export interface ChannelListResponse {
  organization_id: string;
  billing_status: string;
  channels: ChannelCapability[];
}

export interface ChannelUpgradeRequestPayload {
  channel: string;
  estimated_volume?: string;
  justification?: string;
}

export interface ChannelUpgradeRequestResponse {
  request_id?: string;
  organization_id: string;
  channel: string;
  status: string;
  requested_at: string;
  message: string;
}

export interface UpgradeRequestDetail {
  id: string;
  organization_id: string;
  organization_name?: string | null;
  channel: string;
  requesting_user_id?: string | null;
  requesting_user_email?: string | null;
  status: "pending" | "approved" | "rejected" | "cancelled" | string;
  estimated_volume?: string | null;
  business_justification?: string | null;
  reviewing_admin_id?: string | null;
  reviewed_at?: string | null;
  rejection_reason?: string | null;
  admin_notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminUpgradeDecisionPayload {
  action: "approve" | "reject";
  allocated_quota?: number;
  rejection_reason?: string;
  admin_notes?: string;
}

/**
 * Fetch available communication channels and the tenant's entitlement status.
 */
export async function getChannelCapabilities(): Promise<ChannelListResponse> {
  const response = await fetch("/api/entitlements/channels", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.error || `Failed to fetch channel capabilities (${response.status})`);
  }
  return response.json();
}

/**
 * Submit an upgrade request to unlock an advanced channel.
 */
export async function submitUpgradeRequest(
  payload: ChannelUpgradeRequestPayload
): Promise<ChannelUpgradeRequestResponse> {
  const response = await fetch("/api/entitlements/upgrade-request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.error || `Failed to submit upgrade request (${response.status})`);
  }
  return response.json();
}

/**
 * List upgrade requests submitted by the current organization.
 */
export async function getMyUpgradeRequests(statusFilter?: string): Promise<UpgradeRequestDetail[]> {
  const query = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : "";
  const response = await fetch(`/api/entitlements/upgrade-requests${query}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.error || `Failed to fetch upgrade requests (${response.status})`);
  }
  return response.json();
}

/**
 * Platform Admin: Fetch upgrade requests across all subscribing organizations.
 */
export async function getAdminUpgradeRequests(statusFilter?: string): Promise<UpgradeRequestDetail[]> {
  const query = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : "";
  const response = await fetch(`/api/entitlements/admin/upgrade-requests${query}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.error || `Failed to fetch admin upgrade requests (${response.status})`);
  }
  return response.json();
}

/**
 * Platform Admin: Approve or reject a pending channel upgrade request.
 */
export async function submitAdminUpgradeDecision(
  requestId: string,
  payload: AdminUpgradeDecisionPayload
): Promise<UpgradeRequestDetail> {
  const response = await fetch(`/api/entitlements/admin/upgrade-requests/${requestId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.error || `Failed to process upgrade decision (${response.status})`);
  }
  return response.json();
}
