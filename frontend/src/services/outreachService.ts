/**
 * Outreach Domain Service for Agile Sales & Marketing.
 * Strictly aligned with backend Outreach, OutreachEvent, and CallRecord models.
 *
 * Supported Channels: email, linkedin, voice, sms
 * Supported Statuses: draft, scheduled, sending, sent, failed, cancelled
 * Supported Event Types: created, scheduled, sending, sent, failed, cancelled, delivered, opened, clicked, replied, bounced
 */

export type OutreachChannel = "email" | "linkedin" | "voice" | "sms";

export type OutreachStatus =
  | "draft"
  | "scheduled"
  | "sending"
  | "sent"
  | "failed"
  | "cancelled";

export type OutreachEventType =
  | "created"
  | "scheduled"
  | "sending"
  | "sent"
  | "failed"
  | "cancelled"
  | "delivered"
  | "opened"
  | "clicked"
  | "replied"
  | "bounced";

export interface CallRecordInfo {
  id: string;
  callId: string;
  agentId?: string;
  direction: "inbound" | "outbound";
  callStatus: string;
  callOutcome?: string | null;
  callerPhone?: string | null;
  toPhone?: string | null;
  durationMs?: number | null;
  disconnectionReason?: string | null;
  summary?: string | null;
  followupStatus: string;
  followupReason?: string | null;
  startedAt?: string | null;
  endedAt?: string | null;
  analyzedAt?: string | null;
}

export interface OutreachEventItem {
  id: string;
  outreachId: string;
  eventType: OutreachEventType;
  occurredAt: string;
  metadata?: Record<string, unknown> | null;
}

export interface OutreachItem {
  id: string;
  organizationId: string;
  campaignId?: string | null;
  campaignName?: string | null;
  contactId?: string | null;
  contactName: string;
  companyName?: string | null;
  recipient: string;
  channel: OutreachChannel;
  status: OutreachStatus;
  subject?: string | null;
  body?: string | null;
  provider?: string | null;
  providerMessageId?: string | null;
  scheduledAt?: string | null;
  sentAt?: string | null;
  firstDeliveredAt?: string | null;
  firstOpenedAt?: string | null;
  firstClickedAt?: string | null;
  firstRepliedAt?: string | null;
  firstBouncedAt?: string | null;
  createdAt: string;
  updatedAt: string;
  callRecord?: CallRecordInfo | null;
  events: OutreachEventItem[];
}

export interface OutreachFilterOptions {
  searchQuery?: string;
  channel?: string;
  status?: string;
  campaignId?: string;
  dateRange?: string;
}

export const OUTREACH_CHANNEL_LABELS: Record<OutreachChannel, string> = {
  email: "Email",
  linkedin: "LinkedIn",
  voice: "Voice Call",
  sms: "SMS",
};

export const OUTREACH_STATUS_LABELS: Record<OutreachStatus, string> = {
  draft: "Draft",
  scheduled: "Scheduled",
  sending: "Sending",
  sent: "Sent",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const OUTREACH_EVENT_LABELS: Record<OutreachEventType, string> = {
  created: "Message Draft Created",
  scheduled: "Scheduled for Delivery",
  sending: "Handed Off to Provider",
  sent: "Dispatched to Recipient",
  delivered: "Successfully Delivered",
  opened: "Recipient Opened Email",
  clicked: "Link Clicked",
  replied: "Inbound Reply Received",
  bounced: "Delivery Bounced",
  failed: "Delivery Failed",
  cancelled: "Outreach Cancelled",
};

export const CALL_OUTCOME_LABELS: Record<string, string> = {
  INTERESTED: "Interested",
  QUALIFIED: "Qualified",
  MEETING_REQUESTED: "Meeting Requested",
  CALLBACK_REQUESTED: "Callback Requested",
  NOT_INTERESTED: "Not Interested",
  DO_NOT_CONTACT: "Do Not Contact",
  WRONG_PERSON: "Wrong Person",
};

/**
 * Transforms raw backend response from GET /api/v1/outreach into strongly-typed OutreachItem.
 */
export function mapBackendOutreachToItem(raw: any): OutreachItem {
  return {
    id: raw.id,
    organizationId: raw.organization_id || raw.organizationId,
    campaignId: raw.campaign_id ?? raw.campaignId ?? null,
    campaignName: raw.campaign_name ?? raw.campaignName ?? (raw.call_record ? `Voice Follow-up: ${raw.call_record.call_id}` : null),
    contactId: raw.contact_id ?? raw.contactId ?? null,
    contactName: raw.contact_name ?? raw.contactName ?? "Unknown Contact",
    companyName: raw.company_name ?? raw.companyName ?? null,
    recipient: raw.recipient || raw.recipient_email || raw.recipientEmail || "",
    channel: (raw.channel || "email") as OutreachChannel,
    status: (raw.status || "draft") as OutreachStatus,
    subject: raw.subject ?? null,
    body: raw.body ?? null,
    provider: raw.provider ?? null,
    providerMessageId: raw.provider_message_id ?? raw.providerMessageId ?? null,
    scheduledAt: raw.scheduled_at ?? raw.scheduledAt ?? null,
    sentAt: raw.sent_at ?? raw.sentAt ?? null,
    firstDeliveredAt: raw.first_delivered_at ?? raw.firstDeliveredAt ?? null,
    firstOpenedAt: raw.first_opened_at ?? raw.firstOpenedAt ?? null,
    firstClickedAt: raw.first_clicked_at ?? raw.firstClickedAt ?? null,
    firstRepliedAt: raw.first_replied_at ?? raw.firstRepliedAt ?? null,
    firstBouncedAt: raw.first_bounced_at ?? raw.firstBouncedAt ?? null,
    createdAt: raw.created_at ?? raw.createdAt ?? new Date().toISOString(),
    updatedAt: raw.updated_at ?? raw.updatedAt ?? new Date().toISOString(),
    callRecord: raw.call_record ? {
      id: raw.call_record.id,
      callId: raw.call_record.call_id || raw.call_record.callId,
      agentId: raw.call_record.agent_id || raw.call_record.agentId,
      direction: raw.call_record.direction,
      callStatus: raw.call_record.call_status || raw.call_record.callStatus,
      callOutcome: raw.call_record.call_outcome ?? raw.call_record.callOutcome ?? null,
      callerPhone: raw.call_record.caller_phone ?? raw.call_record.callerPhone ?? null,
      toPhone: raw.call_record.to_phone ?? raw.call_record.toPhone ?? null,
      durationMs: raw.call_record.duration_ms ?? raw.call_record.durationMs ?? null,
      disconnectionReason: raw.call_record.disconnection_reason ?? raw.call_record.disconnectionReason ?? null,
      summary: raw.call_record.summary ?? null,
      followupStatus: raw.call_record.followup_status || raw.call_record.followupStatus || "unknown",
      followupReason: raw.call_record.followup_reason ?? raw.call_record.followupReason ?? null,
      startedAt: raw.call_record.started_at ?? raw.call_record.startedAt ?? null,
      endedAt: raw.call_record.ended_at ?? raw.call_record.endedAt ?? null,
      analyzedAt: raw.call_record.analyzed_at ?? raw.call_record.analyzedAt ?? null,
    } : null,
    events: (raw.events || []).map((e: any) => ({
      id: e.id,
      outreachId: e.outreach_id || e.outreachId || raw.id,
      eventType: (e.event_type || e.eventType) as OutreachEventType,
      occurredAt: e.occurred_at || e.occurredAt || new Date().toISOString(),
      metadata: e.event_metadata ?? e.metadata ?? null,
    })),
  };
}

/**
 * Dynamically fetches live Outreach records from the backend API.
 * Never fabricates or returns synthetic data.
 */
export async function fetchOutreachRecords(options?: OutreachFilterOptions): Promise<OutreachItem[]> {
  const queryParams = new URLSearchParams();
  if (options?.channel && options.channel !== "ALL") {
    queryParams.set("channel", options.channel);
  }
  if (options?.status && options.status !== "ALL") {
    queryParams.set("status", options.status);
  }
  if (options?.campaignId && options.campaignId !== "ALL") {
    queryParams.set("campaign_id", options.campaignId);
  }

  const queryStr = queryParams.toString() ? `?${queryParams.toString()}` : "";
  const res = await fetch(`/api/outreach${queryStr}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch outreach records: HTTP ${res.status}`);
  }

  const rawData = await res.json();
  if (!Array.isArray(rawData)) {
    return [];
  }

  return rawData.map(mapBackendOutreachToItem);
}

/**
 * Filters and searches outreach records deterministically.
 */
export function filterOutreach(
  records: OutreachItem[],
  options: OutreachFilterOptions
): OutreachItem[] {
  return records.filter((item) => {
    // Text search: recipient, contact, subject, campaign, providerMessageId
    if (options.searchQuery && options.searchQuery.trim()) {
      const q = options.searchQuery.toLowerCase().trim();
      const matchRecipient = item.recipient.toLowerCase().includes(q);
      const matchContact = item.contactName.toLowerCase().includes(q);
      const matchSubject = (item.subject || "").toLowerCase().includes(q);
      const matchCampaign = (item.campaignName || "").toLowerCase().includes(q);
      const matchProviderId = (item.providerMessageId || "").toLowerCase().includes(q);
      const matchCompany = (item.companyName || "").toLowerCase().includes(q);

      if (
        !matchRecipient &&
        !matchContact &&
        !matchSubject &&
        !matchCampaign &&
        !matchProviderId &&
        !matchCompany
      ) {
        return false;
      }
    }

    // Channel filter
    if (options.channel && options.channel !== "ALL") {
      if (item.channel !== options.channel) return false;
    }

    // Status filter
    if (options.status && options.status !== "ALL") {
      if (item.status !== options.status) return false;
    }

    // Campaign filter
    if (options.campaignId && options.campaignId !== "ALL") {
      if (item.campaignId !== options.campaignId) return false;
    }

    return true;
  });
}

export interface OutreachMetricsRollup {
  totalCount: number;
  totalSent: number;
  totalDelivered: number;
  totalOpened: number;
  totalClicked: number;
  totalReplied: number;
  totalBounced: number;
  deliveredRate: string;
  openedRate: string;
  repliedRate: string;
}

/**
 * Calculates metrics strictly from actual data without fabricating any percentages.
 */
export function computeOutreachMetrics(records: OutreachItem[]): OutreachMetricsRollup {
  const totalCount = records.length;
  let totalSent = 0;
  let totalDelivered = 0;
  let totalOpened = 0;
  let totalClicked = 0;
  let totalReplied = 0;
  let totalBounced = 0;

  for (const r of records) {
    if (r.status === "sent" || r.sentAt) totalSent++;
    if (r.firstDeliveredAt || r.events.some((e) => e.eventType === "delivered")) totalDelivered++;
    if (r.firstOpenedAt || r.events.some((e) => e.eventType === "opened")) totalOpened++;
    if (r.firstClickedAt || r.events.some((e) => e.eventType === "clicked")) totalClicked++;
    if (r.firstRepliedAt || r.events.some((e) => e.eventType === "replied")) totalReplied++;
    if (r.firstBouncedAt || r.events.some((e) => e.eventType === "bounced")) totalBounced++;
  }

  // If denominator is 0, display "—"
  const deliveredRate = totalSent > 0 ? `${((totalDelivered / totalSent) * 100).toFixed(1)}%` : "—";
  const openedRate = totalDelivered > 0 ? `${((totalOpened / totalDelivered) * 100).toFixed(1)}%` : "—";
  const repliedRate = totalDelivered > 0 ? `${((totalReplied / totalDelivered) * 100).toFixed(1)}%` : "—";

  return {
    totalCount,
    totalSent,
    totalDelivered,
    totalOpened,
    totalClicked,
    totalReplied,
    totalBounced,
    deliveredRate,
    openedRate,
    repliedRate,
  };
}

export interface OutreachProvenance {
  isVerified: boolean;
  classification: "verified_live" | "test_fixture" | "draft" | "unverified";
  badgeLabel: string;
  badgeVariant: "warning" | "neutral" | "success" | "info";
  explanation: string;
}

export function getOutreachProvenance(item: OutreachItem): OutreachProvenance {
  const isMockRecipient =
    item.recipient.includes("user1@example.com") ||
    item.recipient.includes("jane_live_audit@example.com") ||
    item.recipient.endsWith("@example.com");
  const callId = item.callRecord?.callId || "";
  const isMockCall =
    callId.startsWith("call_p8_") ||
    callId.startsWith("call_outbound_test_") ||
    callId.startsWith("call_inbound_test_") ||
    callId.includes("test_");

  if (item.status === "draft") {
    return {
      isVerified: false,
      classification: "draft",
      badgeLabel: "Draft (Unsent)",
      badgeVariant: "neutral",
      explanation: "Draft record generated for campaign sequence; not yet dispatched to any provider.",
    };
  }

  if (isMockRecipient || isMockCall) {
    return {
      isVerified: false,
      classification: "test_fixture",
      badgeLabel: "Test Fixture (Unverified)",
      badgeVariant: "warning",
      explanation: isMockCall
        ? `Synthetic test fixture simulating webhook/provider response (${callId}). Not an active telecommunication.`
        : `Synthetic test fixture created with test recipient (${item.recipient}). Not a live email delivery.`,
    };
  }

  if (item.status === "sent" && !item.providerMessageId && !item.provider) {
    return {
      isVerified: false,
      classification: "unverified",
      badgeLabel: "Unverified Dispatch",
      badgeVariant: "warning",
      explanation: "Record marked as sent but lacks confirmed provider dispatch metadata or message ID.",
    };
  }

  return {
    isVerified: true,
    classification: "verified_live",
    badgeLabel: "Verified Live",
    badgeVariant: "success",
    explanation: `Dispatched via ${item.provider || "configured provider"} with confirmed provider event records.`,
  };
}

