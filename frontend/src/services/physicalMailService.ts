/**
 * Poplar Physical Mail Integration Service (Frontend)
 *
 * Provides typed client calls to validate recipient postal addresses,
 * preview personalized creative merge variables, authorize estimated production costs,
 * dispatch mailings in test mode, and synchronize in-flight fulfillment statuses.
 */


export interface MailpieceOptionItem {
  id: string;
  label: string;
  description?: string;
  delivery_time?: string;
  finish?: string;
}

export interface PhysicalMailOptions {
  sizes: MailpieceOptionItem[];
  formats: MailpieceOptionItem[];
  postage_classes: MailpieceOptionItem[];
  paper_types: MailpieceOptionItem[];
  cost_estimates: Record<string, number>;
}

export interface PhysicalMailConfigureRequest {
  workflow_mode?: "connect" | "create";
  poplar_campaign_id?: string;
  new_campaign_name?: string;
  purpose?: string;
  sub_purpose?: string;
  description?: string;
  mailpiece_size: string;
  format_type: string;
  paper_type: string;
  postage_class: string;
  design_url?: string;
  design_name?: string;
  creative_id?: string;
  recipient_ids?: string[];
}

export interface PhysicalMailConfigureResponse {
  campaign_id: string;
  poplar_campaign_id: string | null;
  creative_id?: string | null;
  poplar_status: string;
  poplar_name: string | null;
  mailpiece: {
    size: string;
    format: string;
    paper: string;
    postage: string;
    unit_cost: number;
  };
  design: {
    url?: string | null;
    name?: string | null;
  };
  unit_cost: number;
  estimated_total_cost: number;
  recipient_summary: {
    total: number;
    valid: number;
    invalid: number;
  };
}

export interface PhysicalMailHealth {
  configured: boolean;
  connected: boolean;
  environment: string;
  account_id?: string | null;
  account_name?: string | null;
  mode?: string | null;
  allow_live_sending: boolean;
  message: string;
  error?: string | null;
}

export interface PoplarCampaignItem {
  id: string;
  name: string;
  description?: string | null;
  status?: string | null;
  created_at?: string | null;
}

export interface PoplarCampaignListResponse {
  total: number;
  campaigns: PoplarCampaignItem[];
}

export interface PoplarCreativeItem {
  id: string;
  name: string;
  mail_type?: string | null;
  creative_type?: string | null;
  format?: string | null;
  image_formats?: string | null;
  state?: string | null;
  thumbnail_url?: string | null;
  associated_campaign_id?: string | null;
  associated_campaign_name?: string | null;
}

export interface PoplarCreativeListResponse {
  total: number;
  creatives: PoplarCreativeItem[];
}

export interface CreativeValidateRequest {
  file_name: string;
  file_size_bytes?: number;
  content_type?: string;
  mailpiece_size?: string;
}

export interface CreativeValidateResponse {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  file_name: string;
  spec: Record<string, any>;
}

export interface PhysicalMailConfigDetails {
  campaign_id: string;
  configured: boolean;
  poplar_campaign_id: string | null;
  config: Record<string, any>;
  remote_resource: Record<string, any> | null;
}

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


/**
 * Fetch supported mailpiece options (sizes, formats, postage classes, paper stocks).
 */
export async function getPhysicalMailOptions(): Promise<PhysicalMailOptions> {
  const resp = await fetch("/api/physical-mail/options", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Failed to fetch physical mail options (HTTP ${resp.status})`);
  }
  return resp.json();
}

/**
 * Configure mailpiece options and create/link the campaign resource in Poplar.
 */
export async function configurePhysicalMailCampaign(
  campaignId: string,
  payload: PhysicalMailConfigureRequest
): Promise<PhysicalMailConfigureResponse> {
  const resp = await fetch(`/api/campaigns/${campaignId}/physical-mail/configure`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    const errorObj = new Error(err.detail || err.error || `Failed to configure physical mail campaign (HTTP ${resp.status})`);
    if (err.poplar_campaign_id) {
      (errorObj as any).poplar_campaign_id = err.poplar_campaign_id;
    }
    if (err.code) {
      (errorObj as any).code = err.code;
    }
    throw errorObj;
  }
  return resp.json();
}

/**
 * Retrieve saved physical mail configuration and verify status against Poplar.
 */
export async function getCampaignPhysicalMailConfig(
  campaignId: string
): Promise<PhysicalMailConfigDetails> {
  const resp = await fetch(`/api/campaigns/${campaignId}/physical-mail/config`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Failed to get physical mail config (HTTP ${resp.status})`);
  }
  return resp.json();
}

/**
 * Perform a live Poplar account health check (via GET /v1/me).
 */
export async function getPhysicalMailHealth(): Promise<PhysicalMailHealth> {
  const resp = await fetch("/api/physical-mail/health", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Failed to check Poplar health (HTTP ${resp.status})`);
  }
  return resp.json();
}

/**
 * Retrieve existing Poplar campaigns from Poplar account via read-only GET /v1/campaigns.
 */
export async function getPoplarCampaigns(): Promise<PoplarCampaignListResponse> {
  const resp = await fetch("/api/physical-mail/campaigns", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Failed to fetch Poplar campaigns (HTTP ${resp.status})`);
  }
  return resp.json();
}

/**
 * Retrieve creatives available across Poplar campaigns or for a specific campaign.
 */
export async function getPoplarCreatives(
  campaignId?: string
): Promise<PoplarCreativeListResponse> {
  const url = campaignId
    ? `/api/physical-mail/creatives?campaign_id=${encodeURIComponent(campaignId)}`
    : "/api/physical-mail/creatives";
  const resp = await fetch(url, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Failed to fetch Poplar creatives (HTTP ${resp.status})`);
  }
  return resp.json();
}

/**
 * Validate physical mail creative asset dimensions, size, and file type against USPS and Poplar rules.
 */
export async function validateCreativeAsset(
  payload: CreativeValidateRequest
): Promise<CreativeValidateResponse> {
  const resp = await fetch("/api/physical-mail/validate-creative", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Creative validation failed (HTTP ${resp.status})`);
  }
  return resp.json();
}

/**
 * Get dimensional specifications and bleed requirements for all supported mailpiece sizes.
 */
export async function getPhysicalMailSpecs(): Promise<Record<string, any>> {
  const resp = await fetch("/api/physical-mail/specs", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Failed to fetch physical mail specs (HTTP ${resp.status})`);
  }
  return resp.json();
}
