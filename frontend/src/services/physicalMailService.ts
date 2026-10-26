/**
 * Poplar Physical Mail Integration Service (Frontend)
 *
 * Provides typed client calls to validate recipient postal addresses,
 * preview personalized creative merge variables, authorize estimated production costs,
 * dispatch mailings in test mode, and synchronize in-flight fulfillment statuses.
 */

export interface PhysicalMailStatus {
  configured: boolean;
  environment: string;
  allow_live_sending: boolean;
  base_url: string;
  default_campaign_id?: string | null;
  default_creative_id?: string | null;
}

export interface RecipientAuditItem {
  recipient_id: string;
  full_name: string;
  company_name?: string | null;
  address?: {
    address_1: string;
    address_2?: string;
    city: string;
    state: string;
    postal_code: string;
    country?: string;
  };
  errors?: string[];
}

export interface PhysicalMailValidateResponse {
  campaign_id: string;
  total_recipients: number;
  valid_count: number;
  invalid_count: number;
  valid_recipients: RecipientAuditItem[];
  invalid_recipients: RecipientAuditItem[];
}

export interface PhysicalMailPreviewResponse {
  campaign_id: string;
  poplar_campaign_id: string;
  poplar_creative_id?: string | null;
  unit_cost: number;
  total_recipients: number;
  valid_count: number;
  invalid_count: number;
  estimated_total_cost: number;
  sample_preview?: {
    recipient: Record<string, string>;
    merge_tags: Record<string, string>;
    estimated_delivery_days: string;
  } | null;
  invalid_recipients: Array<{
    recipient_id: string;
    full_name: string;
    errors: string[];
  }>;
  approval_required: boolean;
}

export interface SingleMailingOutcome {
  recipient_id: string;
  outreach_id: string;
  success: boolean;
  status: string;
  mailing_id?: string | null;
  proof_url?: string | null;
  error?: string | null;
  simulated: boolean;
}

export interface PhysicalMailSubmissionResponse {
  campaign_id: string;
  total_processed: number;
  total_submitted: number;
  total_failed: number;
  estimated_cost: number;
  outcomes: SingleMailingOutcome[];
}

export interface MailingSyncItem {
  outreach_id: string;
  mailing_id: string;
  previous_status: string;
  new_status: string;
  poplar_status: string;
  updated: boolean;
  error?: string | null;
}

export interface PhysicalMailSyncResponse {
  campaign_id: string;
  total_checked: number;
  total_updated: number;
  total_delivered: number;
  total_failed: number;
  results: MailingSyncItem[];
}

/**
 * Fetch Poplar provider configuration and environment status.
 */
export async function getPhysicalMailStatus(): Promise<PhysicalMailStatus> {
  const resp = await fetch("/api/physical-mail/status", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Failed to fetch physical mail status (HTTP ${resp.status})`);
  }
  return resp.json();
}

/**
 * Run pre-flight address validation on enrolled campaign recipients.
 */
export async function validateCampaignPhysicalMail(
  campaignId: string,
  recipientIds?: string[]
): Promise<PhysicalMailValidateResponse> {
  const resp = await fetch(`/api/campaigns/${campaignId}/physical-mail/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recipient_ids: recipientIds }),
    cache: "no-store",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Address validation failed (HTTP ${resp.status})`);
  }
  return resp.json();
}

/**
 * Preview recipient merge variables, sample envelope/card layout, and cost estimation.
 */
export async function previewCampaignPhysicalMail(
  campaignId: string,
  options?: {
    poplar_campaign_id?: string;
    poplar_creative_id?: string;
    unit_cost?: number;
  }
): Promise<PhysicalMailPreviewResponse> {
  const resp = await fetch(`/api/campaigns/${campaignId}/physical-mail/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options || {}),
    cache: "no-store",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Mail preview generation failed (HTTP ${resp.status})`);
  }
  return resp.json();
}

/**
 * Submit campaign physical mail dispatches with explicit user approval and idempotency token.
 */
export async function approveAndSubmitPhysicalMail(
  campaignId: string,
  payload: {
    approved: boolean;
    approval_token: string;
    poplar_campaign_id?: string;
    poplar_creative_id?: string;
    recipient_ids?: string[];
  }
): Promise<PhysicalMailSubmissionResponse> {
  const resp = await fetch(`/api/campaigns/${campaignId}/physical-mail/approve-and-submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Physical mail submission failed (HTTP ${resp.status})`);
  }
  return resp.json();
}

/**
 * Synchronize fulfillment and USPS delivery progress from Poplar provider.
 */
export async function syncCampaignPhysicalMail(
  campaignId: string
): Promise<PhysicalMailSyncResponse> {
  const resp = await fetch(`/api/campaigns/${campaignId}/physical-mail/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Mail tracking sync failed (HTTP ${resp.status})`);
  }
  return resp.json();
}
