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
