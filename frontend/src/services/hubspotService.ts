/**
 * HubSpot Integration Service (Frontend)
 *
 * Communicates with backend integration endpoints to fetch real-time
 * HubSpot connection health, scope availability, synchronization metrics,
 * and execute read-only syncs.
 */

export interface HubSpotScopeInfo {
  readable: boolean;
  status: "active" | "missing_scope" | "error";
  scope_required: string;
  message?: string;
}

export interface HubSpotLastSyncInfo {
  run_id: string;
  status: "completed" | "partial" | "failed";
  started_at: string;
  completed_at?: string;
  contacts_count: number;
  companies_count: number;
  deals_count: number;
  permission_errors?: Record<string, string>;
}

export interface HubSpotStatusResponse {
  configured: boolean;
  connected: boolean;
  portal_id?: string;
  account_type?: string;
  ui_domain?: string;
  last_sync?: HubSpotLastSyncInfo | null;
  scopes: {
    contacts?: HubSpotScopeInfo;
    companies?: HubSpotScopeInfo;
    deals?: HubSpotScopeInfo;
  };
  message: string;
}

export interface ObjectSyncResult {
  status: "synced" | "empty" | "missing_scope" | "error" | "skipped";
  imported: number;
  updated: number;
  total_in_hubspot: number;
  error?: string;
  scope_required?: string;
}

export interface HubSpotSyncSummary {
  run_id: string;
  portal_id?: string;
  status: "completed" | "partial" | "failed";
  started_at: string;
  completed_at: string;
  contacts: ObjectSyncResult;
  companies: ObjectSyncResult;
  deals: ObjectSyncResult;
  permission_errors: Record<string, string>;
  message: string;
}

export async function getHubSpotStatus(): Promise<HubSpotStatusResponse> {
  try {
    const resp = await fetch("/api/integrations/hubspot/status", {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
      cache: "no-store",
      signal: AbortSignal.timeout(25000),
    });

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      throw new Error(errData.error || errData.detail || `Failed to fetch HubSpot status: HTTP ${resp.status}`);
    }

    return await resp.json();
  } catch (err: any) {
    if (err.name === "TimeoutError") {
      throw new Error("HubSpot connection check timed out. Live API verification is taking longer than expected. Please retry.");
    }
    throw err;
  }
}

export async function triggerHubSpotSync(): Promise<HubSpotSyncSummary> {
  try {
    const resp = await fetch("/api/integrations/hubspot/sync", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      cache: "no-store",
      signal: AbortSignal.timeout(60000),
    });

    if (!resp.ok) {
      const errorData = await resp.json().catch(() => ({}));
      throw new Error(errorData.error || errorData.detail || `Failed to trigger HubSpot sync: HTTP ${resp.status}`);
    }

    return await resp.json();
  } catch (err: any) {
    if (err.name === "TimeoutError") {
      throw new Error("HubSpot synchronization request timed out after 60s.");
    }
    throw err;
  }
}
