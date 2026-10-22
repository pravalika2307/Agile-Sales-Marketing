/**
 * Campaign service abstraction for Agile Sales & Marketing.
 * Strictly aligned with backend Campaign, CampaignStep, CampaignContact, and Outreach models.
 *
 * Supported Types: sales_outbound, marketing_social, hybrid
 * Supported Statuses: draft, active, paused, completed
 * Supported Step Types: email (Step 9 backend model)
 * Supported Enrollment Statuses: queued, in_progress, replied, bounced, completed
 *
 * DATA-INTEGRITY RULE:
 * REAL DATA → REAL STATE.
 * NO DATA → NEUTRAL STATE ("—").
 * NO SUCCESS MESSAGE WITHOUT A SUCCESSFUL BACKEND OPERATION.
 * NEVER INVENT BUSINESS DATA.
 */

export type CampaignType = "sales_outbound" | "marketing_social" | "hybrid";
export type CampaignStatus = "draft" | "active" | "paused" | "completed";
export type EnrollmentStatus = "queued" | "in_progress" | "replied" | "bounced" | "completed";

export interface CampaignStepItem {
  id: string;
  stepNumber: number;
  stepType: "email";
  subjectTemplate: string | null;
  bodyTemplate: string | null;
  delayDays: number;
  delayHours: number;
  isActive: boolean;
  createdAt: string;
}

export interface CampaignContactItem {
  id: string;
  contactId: string;
  contactName: string;
  contactEmail: string;
  companyName: string;
  enrollmentStatus: EnrollmentStatus;
  currentStep: number;
  enrolledAt: string;
}

export interface OutreachItem {
  id: string;
  campaignId: string | null;
  contactId: string | null;
  campaignContactId: string | null;
  recipientEmail: string;
  contactName: string | null;
  companyName: string | null;
  channel: string;
  status: "draft" | "scheduled" | "sending" | "sent" | "failed" | "cancelled";
  subject: string | null;
  body: string | null;
  provider: string | null;
  providerMessageId: string | null;
  scheduledAt: string | null;
  sentAt: string | null;
  firstDeliveredAt?: string | null;
  createdAt: string;
  error?: string | null;
}

export interface WorkflowNode {
  id: string;
  type: "start" | "email" | "wait" | "voice" | "sms" | "condition";
  title: string;
  config: Record<string, any>;
  position?: { x: number; y: number };
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  label?: string | null;
}

export interface WorkflowConfig {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

export interface WorkflowValidationResult {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  supported_step_types: string[];
  unavailable_step_types: string[];
}

export interface WorkflowSaveResponse {
  campaign_id: string;
  workflow_config: WorkflowConfig;
  validation: WorkflowValidationResult;
  description?: string | null;
}

export interface TemplatePreviewRequest {
  subject_template?: string | null;
  body_template?: string | null;
  contact_id?: string | null;
  sender_name?: string | null;
  sender_company_name?: string | null;
  use_sample?: boolean;
}

export interface TemplatePreviewResponse {
  rendered_subject: string | null;
  rendered_body: string | null;
  rendered_html?: string | null;
  booking_url?: string | null;
  unresolved_placeholders: string[];
  contact_used: Record<string, any> | null;
  validation_errors: string[];
  safe_fallbacks_applied: string[];
  is_sample?: boolean;
}

export interface CampaignItem {
  id: string;
  organizationId: string;
  name: string;
  type: CampaignType;
  status: CampaignStatus;
  description?: string | null;
  scheduleSettings?: Record<string, unknown> | null;
  workflowConfig?: WorkflowConfig | null;
  contactsCount: number;
  stepsCount: number;
  currentStepNumber: number;
  createdAt: string;
  updatedAt: string;
  steps: CampaignStepItem[];
  contacts: CampaignContactItem[];
  outreaches?: OutreachItem[];
  // Performance metrics: Strictly zero or neutral when no activity recorded
  metrics: {
    sent: number;
    delivered: number;
    simulated?: number;
    opened: number;
    replied: number;
    bounced: number;
    conversionRate: string; // "—" when denominator is 0
  };
}

export interface CampaignCreatePayload {
  name: string;
  type: CampaignType;
  description?: string | null;
  first_step_channel?: "email" | "sms" | "voice";
  scheduleSettings?: Record<string, unknown> | null;
  workflow_config?: WorkflowConfig | null;
}

export interface CampaignFilterOptions {
  searchQuery?: string;
  type?: string;
  status?: string;
  sortBy?: "newest" | "name_asc" | "contacts_desc";
}

export const CAMPAIGN_TYPE_LABELS: Record<CampaignType, string> = {
  sales_outbound: "Sales Outbound",
  marketing_social: "Marketing Social",
  hybrid: "Hybrid",
};

export const CAMPAIGN_STATUS_LABELS: Record<CampaignStatus, string> = {
  draft: "Draft",
  active: "Active",
  paused: "Paused",
  completed: "Completed",
};

export const ENROLLMENT_STATUS_LABELS: Record<EnrollmentStatus, string> = {
  queued: "Queued",
  in_progress: "In Progress",
  replied: "Replied",
  bounced: "Bounced",
  completed: "Completed",
};

export interface RawBackendCampaign {
  id: string;
  organization_id: string;
  name: string;
  type: CampaignType;
  status: CampaignStatus;
  description?: string | null;
  schedule_settings?: Record<string, unknown> | null;
  workflow_config?: WorkflowConfig | null;
  contacts_count?: number;
  steps_count?: number;
  created_at: string;
  updated_at: string;
}

export interface RawBackendCampaignContact {
  id: string;
  campaign_id: string;
  contact_id: string;
  enrollment_status: EnrollmentStatus;
  current_step: number;
  enrolled_at: string;
  updated_at: string;
  contact?: {
    id: string;
    email: string;
    first_name: string;
    last_name: string;
    company?: {
      name: string;
    } | null;
  } | null;
}

export interface RawBackendCampaignStep {
  id: string;
  organization_id: string;
  campaign_id: string;
  step_number: number;
  step_type: string;
  subject_template: string | null;
  body_template: string | null;
  delay_days: number;
  delay_hours: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RawBackendOutreach {
  id: string;
  outreach_id?: string;
  recipient?: string;
  recipient_email?: string;
  organization_id: string;
  campaign_id?: string | null;
  contact_id?: string | null;
  campaign_contact_id?: string | null;
  contact_name?: string | null;
  company_name?: string | null;
  channel: string;
  status: "draft" | "scheduled" | "sending" | "sent" | "failed" | "cancelled";
  subject?: string | null;
  body?: string | null;
  provider?: string | null;
  provider_message_id?: string | null;
  scheduled_at?: string | null;
  sent_at?: string | null;
  first_delivered_at?: string | null;
  created_at: string;
  updated_at: string;
  events?: Array<{
    id: string;
    event_type: string;
    event_metadata?: Record<string, unknown>;
  }>;
}

function mapRawContactToItem(raw: RawBackendCampaignContact): CampaignContactItem {
  const firstName = raw.contact?.first_name || "";
  const lastName = raw.contact?.last_name || "";
  const fullName = `${firstName} ${lastName}`.trim() || raw.contact?.email || "—";
  const companyName = raw.contact?.company?.name || "—";

  return {
    id: raw.id,
    contactId: raw.contact_id,
    contactName: fullName,
    contactEmail: raw.contact?.email || "—",
    companyName: companyName,
    enrollmentStatus: raw.enrollment_status || "queued",
    currentStep: raw.current_step ?? 0,
    enrolledAt: raw.enrolled_at,
  };
}

function mapRawStepToItem(raw: RawBackendCampaignStep): CampaignStepItem {
  return {
    id: raw.id,
    stepNumber: raw.step_number,
    stepType: "email",
    subjectTemplate: raw.subject_template,
    bodyTemplate: raw.body_template,
    delayDays: raw.delay_days ?? 0,
    delayHours: raw.delay_hours ?? 0,
    isActive: Boolean(raw.is_active),
    createdAt: raw.created_at,
  };
}

function mapRawOutreachToItem(raw: RawBackendOutreach): OutreachItem {
  let errorMsg: string | null = null;
  if (raw.status === "failed" && raw.events) {
    const failedEvent = raw.events.find((e) => e.event_type === "failed");
    if (failedEvent && failedEvent.event_metadata && failedEvent.event_metadata.error) {
      errorMsg = String(failedEvent.event_metadata.error);
    }
  }

  return {
    id: raw.id || raw.outreach_id || "",
    campaignId: raw.campaign_id || null,
    contactId: raw.contact_id || null,
    campaignContactId: raw.campaign_contact_id || null,
    recipientEmail: raw.recipient_email || raw.recipient || "—",
    contactName: raw.contact_name || null,
    companyName: raw.company_name || null,
    channel: raw.channel,
    status: raw.status,
    subject: raw.subject || null,
    body: raw.body || null,
    provider: raw.provider || null,
    providerMessageId: raw.provider_message_id || null,
    scheduledAt: raw.scheduled_at || null,
    sentAt: raw.sent_at || null,
    firstDeliveredAt: raw.first_delivered_at || null,
    createdAt: raw.created_at,
    error: errorMsg,
  };
}

function mapRawCampaignToItem(
  raw: RawBackendCampaign,
  steps: CampaignStepItem[] = [],
  contacts: CampaignContactItem[] = [],
  outreaches: OutreachItem[] = []
): CampaignItem {
  const liveSentCount = outreaches.filter((o) => o.status === "sent" && o.provider !== "mock").length;
  const simulatedCount = outreaches.filter((o) => o.status === "sent" && o.provider === "mock").length;
  const verifiedDeliveredCount = outreaches.filter((o) => o.status === "sent" && !!o.firstDeliveredAt).length;
  const contactsCount = raw.contacts_count ?? contacts.length;
  const stepsCount = raw.steps_count ?? steps.length;

  return {
    id: raw.id,
    organizationId: raw.organization_id,
    name: raw.name,
    type: raw.type,
    status: raw.status,
    description: raw.description || null,
    scheduleSettings: raw.schedule_settings,
    workflowConfig: raw.workflow_config || null,
    contactsCount,
    stepsCount,
    currentStepNumber: 1,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    steps,
    contacts,
    outreaches,
    metrics: {
      sent: liveSentCount,
      delivered: verifiedDeliveredCount, // Strictly verified delivery events only
      simulated: simulatedCount,
      opened: 0,
      replied: 0,
      bounced: 0,
      conversionRate: "—",
    },
  };
}

/**
 * Fetch all campaigns from backend with optional filters and total count.
 */
export async function fetchCampaigns(options?: {
  searchQuery?: string;
  type?: string;
  status?: string;
  skip?: number;
  limit?: number;
}): Promise<{ campaigns: CampaignItem[]; total: number }> {
  const params = new URLSearchParams();
  if (options?.searchQuery?.trim()) params.append("search", options.searchQuery.trim());
  if (options?.status && options.status !== "ALL") params.append("status", options.status);
  if (options?.type && options.type !== "ALL") params.append("type", options.type);
  if (options?.skip !== undefined) params.append("skip", String(options.skip));
  if (options?.limit !== undefined) params.append("limit", String(options.limit));

  const qs = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`/api/campaigns${qs}`, {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch campaigns (HTTP ${res.status})`);
  }

  const rawList: RawBackendCampaign[] = await res.json();
  const total = Number(res.headers.get("X-Total-Count") || rawList.length);

  const campaigns = rawList.map((raw) => mapRawCampaignToItem(raw));
  return { campaigns, total };
}

/**
 * Fetch a single campaign by ID along with its steps, contacts, and outreach records.
 */
export async function getCampaignDetails(campaignId: string): Promise<CampaignItem> {
  // 1. Fetch base campaign
  const campRes = await fetch(`/api/campaigns/${campaignId}`, { cache: "no-store" });
  if (!campRes.ok) {
    throw new Error(`Failed to fetch campaign ${campaignId} (HTTP ${campRes.status})`);
  }
  const rawCamp: RawBackendCampaign = await campRes.json();

  // 2. Fetch steps, contacts, and outreaches in parallel
  const [stepsRes, contactsRes, outreachRes] = await Promise.all([
    fetch(`/api/campaigns/${campaignId}/steps`, { cache: "no-store" }).catch(() => null),
    fetch(`/api/campaigns/${campaignId}/contacts?limit=100`, { cache: "no-store" }).catch(() => null),
    fetch(`/api/outreach?campaign_id=${campaignId}&limit=100`, { cache: "no-store" }).catch(() => null),
  ]);

  let steps: CampaignStepItem[] = [];
  if (stepsRes && stepsRes.ok) {
    const rawSteps: RawBackendCampaignStep[] = await stepsRes.json();
    steps = rawSteps.map(mapRawStepToItem);
  }

  let contacts: CampaignContactItem[] = [];
  if (contactsRes && contactsRes.ok) {
    const rawContacts: RawBackendCampaignContact[] = await contactsRes.json();
    contacts = rawContacts.map(mapRawContactToItem);
  }

  let outreaches: OutreachItem[] = [];
  if (outreachRes && outreachRes.ok) {
    const rawOutreach: RawBackendOutreach[] = await outreachRes.json();
    outreaches = rawOutreach.map(mapRawOutreachToItem);
  }

  return mapRawCampaignToItem(rawCamp, steps, contacts, outreaches);
}

/**
 * Create a new campaign strictly in backend.
 */
export async function createCampaign(payload: CampaignCreatePayload): Promise<CampaignItem> {
  const res = await fetch("/api/campaigns", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: payload.name.trim(),
      type: payload.type,
      description: payload.description?.trim() || null,
      first_step_channel: payload.first_step_channel || "email",
      schedule_settings: payload.scheduleSettings || null,
      workflow_config: payload.workflow_config || null,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to create campaign (HTTP ${res.status})`);
  }

  const created: RawBackendCampaign = await res.json();
  return mapRawCampaignToItem(created);
}

/**
 * Transition campaign lifecycle: activate.
 */
export async function activateCampaign(campaignId: string): Promise<CampaignItem> {
  const res = await fetch(`/api/campaigns/${campaignId}/activate`, {
    method: "POST",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to activate campaign (HTTP ${res.status})`);
  }

  const updated: RawBackendCampaign = await res.json();
  return mapRawCampaignToItem(updated);
}

/**
 * Transition campaign lifecycle: pause.
 */
export async function pauseCampaign(campaignId: string): Promise<CampaignItem> {
  const res = await fetch(`/api/campaigns/${campaignId}/pause`, {
    method: "POST",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to pause campaign (HTTP ${res.status})`);
  }

  const updated: RawBackendCampaign = await res.json();
  return mapRawCampaignToItem(updated);
}

/**
 * Transition campaign lifecycle: complete.
 */
export async function completeCampaign(campaignId: string): Promise<CampaignItem> {
  const res = await fetch(`/api/campaigns/${campaignId}/complete`, {
    method: "POST",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to complete campaign (HTTP ${res.status})`);
  }

  const updated: RawBackendCampaign = await res.json();
  return mapRawCampaignToItem(updated);
}

/**
 * Bulk enroll contacts into a campaign.
 */
export async function enrollContactsInCampaign(
  campaignId: string,
  contactIds: string[]
): Promise<{
  enrolledContactIds: string[];
  alreadyEnrolledContactIds: string[];
  rejectedContactIds: string[];
}> {
  const res = await fetch(`/api/campaigns/${campaignId}/contacts/bulk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contact_ids: contactIds }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to enroll contacts (HTTP ${res.status})`);
  }

  const data = await res.json();
  return {
    enrolledContactIds: data.enrolled || data.enrolled_contact_ids || [],
    alreadyEnrolledContactIds: data.already_enrolled || data.already_enrolled_contact_ids || [],
    rejectedContactIds: data.rejected || data.rejected_contact_ids || [],
  };
}

/**
 * Fetch campaign enrolled contacts.
 */
export async function getCampaignContacts(campaignId: string): Promise<CampaignContactItem[]> {
  const res = await fetch(`/api/campaigns/${campaignId}/contacts?limit=100`, {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch enrolled contacts (HTTP ${res.status})`);
  }

  const rawContacts: RawBackendCampaignContact[] = await res.json();
  return rawContacts.map(mapRawContactToItem);
}

/**
 * Execute campaign outreach planning (generates draft Outreaches and advances contacts to in_progress).
 * NOTE: This plans outreach according to sequence Step 1; it does NOT send emails.
 */
export async function executeCampaignPlanning(
  campaignId: string,
  senderName?: string
): Promise<{
  campaignId: string;
  plannedOutreachesCount: number;
  createdOutreachIds: string[];
  skippedContactIds: string[];
  rejectedContactIds: string[];
}> {
  const res = await fetch(`/api/campaigns/${campaignId}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sender_name: senderName || undefined }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to execute campaign outreach planning (HTTP ${res.status})`);
  }

  const data = await res.json();
  return {
    campaignId: data.campaign_id,
    plannedOutreachesCount: data.planned_outreaches_count,
    createdOutreachIds: data.created_outreach_ids || [],
    skippedContactIds: data.skipped_contact_ids || [],
    rejectedContactIds: data.rejected_contact_ids || [],
  };
}

/**
 * Fetch outreach messages for a campaign.
 */
export async function getCampaignOutreaches(campaignId: string): Promise<OutreachItem[]> {
  const res = await fetch(`/api/outreach?campaign_id=${campaignId}&limit=100`, {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch campaign outreaches (HTTP ${res.status})`);
  }

  const rawOutreach: RawBackendOutreach[] = await res.json();
  return rawOutreach.map(mapRawOutreachToItem);
}

/**
 * Send an outreach message via email provider.
 * Surfaces provider delivery failure or success explicitly.
 */
export async function sendOutreachMessage(outreachId: string): Promise<OutreachItem> {
  const res = await fetch(`/api/outreach/${outreachId}/send`, {
    method: "POST",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to send outreach (HTTP ${res.status})`);
  }

  const rawOutreach: RawBackendOutreach = await res.json();
  return mapRawOutreachToItem(rawOutreach);
}

/**
 * Filter and sort campaigns client-side (for instant search or fallback).
 */
export function filterCampaigns(
  campaigns: CampaignItem[],
  options: CampaignFilterOptions
): CampaignItem[] {
  const result = campaigns.filter((c) => {
    if (options.searchQuery && options.searchQuery.trim()) {
      const q = options.searchQuery.toLowerCase().trim();
      if (!c.name.toLowerCase().includes(q)) return false;
    }

    if (options.type && options.type !== "ALL") {
      if (c.type !== options.type) return false;
    }

    if (options.status && options.status !== "ALL") {
      if (c.status !== options.status) return false;
    }

    return true;
  });

  if (options.sortBy === "name_asc") {
    result.sort((a, b) => a.name.localeCompare(b.name));
  } else if (options.sortBy === "contacts_desc") {
    result.sort((a, b) => b.contactsCount - a.contactsCount);
  } else {
    result.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  }

  return result;
}

/**
 * Fetch campaign workflow configuration with backward-compatible step recovery.
 */
export async function fetchCampaignWorkflow(campaignId: string): Promise<WorkflowConfig> {
  const res = await fetch(`/api/campaigns/${campaignId}/workflow`, {
    cache: "no-store",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to fetch campaign workflow (HTTP ${res.status})`);
  }

  return res.json();
}

/**
 * Persist visual workflow configuration and sync email sequence steps.
 */
export async function saveCampaignWorkflow(
  campaignId: string,
  workflowConfig: WorkflowConfig,
  description?: string
): Promise<WorkflowSaveResponse> {
  const res = await fetch(`/api/campaigns/${campaignId}/workflow`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workflow_config: workflowConfig,
      description: description || undefined,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to save campaign workflow (HTTP ${res.status})`);
  }

  return res.json();
}

/**
 * Validate visual workflow graph.
 */
export async function validateWorkflow(
  campaignId: string,
  workflowConfig: WorkflowConfig
): Promise<WorkflowValidationResult> {
  const res = await fetch(`/api/campaigns/${campaignId}/workflow/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(workflowConfig),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to validate workflow (HTTP ${res.status})`);
  }

  return res.json();
}

/**
 * Preview template rendering with genuine persisted contact data.
 */
export async function previewStepTemplate(
  campaignId: string,
  payload: TemplatePreviewRequest
): Promise<TemplatePreviewResponse> {
  const res = await fetch(`/api/campaigns/${campaignId}/workflow/preview-template`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to preview template (HTTP ${res.status})`);
  }

  return res.json();
}

/**
 * Remove an individual contact's membership from a specific campaign.
 */
export async function removeContactFromCampaign(
  campaignId: string,
  contactId: string
): Promise<void> {
  const res = await fetch(`/api/campaigns/${campaignId}/contacts/${contactId}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to remove contact from campaign (HTTP ${res.status})`);
  }
}

/**
 * Delete an individual campaign scoped to the tenant organization.
 */
export async function deleteCampaign(campaignId: string): Promise<void> {
  const res = await fetch(`/api/campaigns/${campaignId}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to delete campaign (HTTP ${res.status})`);
  }
}


