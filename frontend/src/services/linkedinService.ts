/**
 * LinkedIn Integration Service for Agile Sales & Marketing frontend.
 * Provides functions to query connection status, initiate OAuth authorization,
 * and disconnect authorized LinkedIn accounts via Next.js proxy route handlers.
 */

export interface LinkedInStatusResponse {
  configured: boolean;
  connected: boolean;
  status: "connected" | "disconnected" | "expired" | "not_configured";
  member_id?: string | null;
  member_name?: string | null;
  member_email?: string | null;
  profile_picture_url?: string | null;
  connected_at?: string | null;
  expires_at?: string | null;
  scopes?: string[];
  message: string;
}

export interface LinkedInAuthorizeResponse {
  authorization_url: string;
  state: string;
}

export interface LinkedInDisconnectResponse {
  success: boolean;
  message: string;
}

export interface LinkedInCapabilityItem {
  status: "available" | "restricted" | "unsupported";
  scope_required: string;
  scope_granted: boolean;
  description: string;
  assisted_alternative?: string | null;
}

export interface LinkedInCapabilitiesResponse {
  configured: boolean;
  connected: boolean;
  member_id?: string | null;
  member_name?: string | null;
  granted_scopes: string[];
  capabilities: Record<string, LinkedInCapabilityItem>;
  workflow_mode: string;
  booking_url: string;
  connection_note_limit: number;
}

export interface LinkedInAssistedQueueItem {
  campaign_contact_id: string;
  contact_id: string;
  lead_id?: string | null;
  full_name: string;
  first_name: string;
  last_name: string;
  company_name?: string | null;
  job_title?: string | null;
  linkedin_url?: string | null;
  linkedin_profile_url?: string | null;
  has_linkedin_profile_url?: boolean;
  search_url: string;
  connection_note: string;
  followup_message: string;
  booking_url: string;
  outreach_id?: string | null;
  outreach_status: "pending" | "copied" | "sent";
  sent_at?: string | null;
}

export interface LinkedInAssistedQueueResponse {
  campaign_id: string;
  total: number;
  pending_count: number;
  completed_count: number;
  items: LinkedInAssistedQueueItem[];
}

export interface LinkedInConfirmActionRequest {
  campaign_contact_id: string;
  action_type: "connection_request" | "direct_message";
  notes?: string;
}

export interface LinkedInConfirmActionResponse {
  success: boolean;
  outreach_id: string;
  status: string;
  confirmed_at: string;
  message: string;
}

export interface UpdateProspectLinkedInUrlResponse {
  campaign_contact_id: string;
  contact_id: string;
  lead_id?: string | null;
  linkedin_profile_url: string;
  status: string;
}

/**
 * Fetch the current LinkedIn integration status for the active organization.
 */
export async function getLinkedInStatus(): Promise<LinkedInStatusResponse> {
  const res = await fetch("/api/integrations/linkedin/status", {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error || `HTTP ${res.status}: Failed to fetch LinkedIn status`);
  }

  return res.json();
}

/**
 * Request an authorization URL and cryptographically secure state token to begin LinkedIn OAuth.
 */
export async function getLinkedInAuthorizeUrl(): Promise<LinkedInAuthorizeResponse> {
  const res = await fetch("/api/integrations/linkedin/authorize", {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error || `HTTP ${res.status}: Failed to initiate LinkedIn authorization`);
  }

  return res.json();
}

/**
 * Disconnect the active LinkedIn account for the active organization.
 */
export async function disconnectLinkedIn(): Promise<LinkedInDisconnectResponse> {
  const res = await fetch("/api/integrations/linkedin/disconnect", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error || `HTTP ${res.status}: Failed to disconnect LinkedIn account`);
  }

  return res.json();
}

/**
 * Fetch LinkedIn API capability matrix with scopes and assisted workflow details.
 */
export async function getLinkedInCapabilities(): Promise<LinkedInCapabilitiesResponse> {
  const res = await fetch("/api/integrations/linkedin/capabilities", {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error || `HTTP ${res.status}: Failed to fetch LinkedIn capabilities`);
  }

  return res.json();
}

/**
 * Fetch campaign contacts enrolled for assisted LinkedIn outreach with pre-rendered notes and search links.
 */
export async function getLinkedInCampaignQueue(
  campaignId: string
): Promise<LinkedInAssistedQueueResponse> {
  const res = await fetch(`/api/campaigns/${campaignId}/linkedin/queue`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error || `HTTP ${res.status}: Failed to fetch LinkedIn assisted queue`);
  }

  return res.json();
}

/**
 * Record manual confirmation that a LinkedIn outreach step (connection request or message) was executed.
 */
export async function confirmLinkedInAction(
  campaignId: string,
  payload: LinkedInConfirmActionRequest
): Promise<LinkedInConfirmActionResponse> {
  const res = await fetch(`/api/campaigns/${campaignId}/linkedin/confirm`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error || `HTTP ${res.status}: Failed to confirm LinkedIn outreach action`);
  }

  return res.json();
}

/**
 * Update or record a prospect's LinkedIn profile URL directly from the campaign outreach queue.
 */
export async function updateProspectLinkedInUrl(
  campaignId: string,
  campaignContactId: string,
  profileUrl: string
): Promise<UpdateProspectLinkedInUrlResponse> {
  const res = await fetch(
    `/api/campaigns/${campaignId}/linkedin/prospects/${campaignContactId}/linkedin-url`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ linkedin_profile_url: profileUrl }),
      cache: "no-store",
    }
  );

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(
      errorData.detail || errorData.error || `HTTP ${res.status}: Failed to update LinkedIn profile URL`
    );
  }

  return res.json();
}
