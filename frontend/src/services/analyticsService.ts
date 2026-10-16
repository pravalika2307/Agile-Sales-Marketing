/**
 * Analytics service for Agile Sales & Marketing.
 * Fetches real, tenant-scoped operational metrics from PostgreSQL backend.
 */

export interface LeadMetrics {
  total_leads: number;
  qualified_leads: number;
  status_breakdown: Record<string, number>;
  temperature_breakdown: Record<string, number>;
}

export interface CampaignMetricsOverview {
  total_campaigns: number;
  active_campaigns: number;
  draft_campaigns: number;
  paused_campaigns: number;
  completed_campaigns: number;
  enrolled_contacts: number;
}

export interface OutreachMetricsOverview {
  total_outreach: number;
  draft: number;
  scheduled: number;
  sent: number;
  delivered: number;
  opened: number;
  clicked: number;
  replied: number;
  bounced: number;
  failed: number;
  channel_breakdown: Record<string, number>;
}

export interface VoiceCallMetricsOverview {
  total_calls: number;
  completed_calls: number;
  average_duration_seconds: number | null;
  outcome_breakdown: Record<string, number>;
}

export interface PipelineMetricsOverview {
  total_deals: number;
  open_deals: number;
  won_deals: number;
  lost_deals: number;
  total_pipeline_value: number;
  won_pipeline_value: number;
}

export interface CampaignPerformanceSummary {
  id: string;
  name: string;
  type: string;
  status: string;
  enrolled_contacts_count: number;
  outreach_count: number;
  sent_count: number;
  delivered_count: number;
  opened_count: number;
  replied_count: number;
  bounced_count: number;
}

export interface FunnelStageMetrics {
  stage_id: string;
  stage_name: string;
  count: number;
  conversion_rate_from_previous?: number | null;
  conversion_rate_from_top?: number | null;
  channel_breakdown: Record<string, number>;
  description: string;
  formula?: string | null;
  denominator_name?: string | null;
}

export interface FunnelMetrics {
  stages: FunnelStageMetrics[];
  total_leads: number;
  qualified_prospects: number;
  contacted_prospects: number;
  engaged_prospects: number;
  pipeline_opportunities: number;
  closed_won: number;
  contacted_records?: number;
  engaged_records?: number;
  contacted_breakdown?: Record<string, number>;
  engaged_breakdown?: Record<string, number>;
  contacted_activities?: Record<string, number>;
  engaged_activities?: Record<string, number>;
  meetings_requested?: number;
  confirmed_bookings?: number;
}

export interface PositiveProspectResponse {
  id: string;
  lead_id?: string | null;
  contact_id?: string | null;
  contact_name?: string | null;
  company_name?: string | null;
  email?: string | null;
  phone?: string | null;
  channel: "voice" | "email" | "qualification" | string;
  response_type: "meeting_requested" | "email_replied" | "qualified_lead" | "qualified_call" | string;
  response_preview?: string | null;
  occurred_at?: string | null;
  deal_id?: string | null;
  deal_name?: string | null;
  deal_amount?: number | null;
  deal_status?: "open" | "won" | "lost" | string | null;
  pipeline_stage_id?: string | null;
  pipeline_stage_name?: string | null;
}

export interface AnalyticsOverviewResponse {
  leads: LeadMetrics;
  campaigns: CampaignMetricsOverview;
  outreach: OutreachMetricsOverview;
  voice: VoiceCallMetricsOverview;
  pipeline: PipelineMetricsOverview;
  campaign_performance: CampaignPerformanceSummary[];
  funnel?: FunnelMetrics | null;
  positive_responses?: PositiveProspectResponse[];
}

export async function fetchAnalyticsOverview(): Promise<AnalyticsOverviewResponse> {
  const response = await fetch("/api/analytics", {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Failed to load analytics: HTTP ${response.status} - ${errorText || response.statusText}`
    );
  }

  return response.json();
}

export interface EmailActivityDetails {
  status: string;
  subject?: string | null;
  body_preview?: string | null;
  provider?: string | null;
  sent_at?: string | null;
  delivered_at?: string | null;
  opened_at?: string | null;
  clicked_at?: string | null;
  replied_at?: string | null;
  bounced_at?: string | null;
  is_delivered: boolean;
  is_replied: boolean;
  is_bounced: boolean;
}

export interface VoiceActivityDetails {
  call_id: string;
  direction: "inbound" | "outbound" | string;
  call_status: string;
  call_outcome?: string | null;
  duration_seconds?: number | null;
  caller_phone?: string | null;
  to_phone?: string | null;
  is_connected: boolean;
  disconnection_reason?: string | null;
  summary?: string | null;
  transcript_snippet?: string | null;
}

export interface UnifiedActivityItem {
  id: string;
  channel: "email" | "voice" | string;
  activity_type: string;
  title: string;
  description?: string | null;
  occurred_at: string;
  lead_id?: string | null;
  contact_id?: string | null;
  campaign_id?: string | null;
  campaign_name?: string | null;
  contact_name?: string | null;
  company_name?: string | null;
  email_details?: EmailActivityDetails | null;
  voice_details?: VoiceActivityDetails | null;
  provenance?: Record<string, unknown>;
}

export interface UnifiedActivityResponse {
  items: UnifiedActivityItem[];
  total: number;
  skip: number;
  limit: number;
}

export interface FetchUnifiedActivitiesParams {
  lead_id?: string;
  contact_id?: string;
  campaign_id?: string;
  list_id?: string;
  channel?: "email" | "voice" | string;
  skip?: number;
  limit?: number;
}

export async function fetchUnifiedActivities(
  params: FetchUnifiedActivitiesParams = {}
): Promise<UnifiedActivityResponse> {
  const query = new URLSearchParams();
  if (params.lead_id) query.set("lead_id", params.lead_id);
  if (params.contact_id) query.set("contact_id", params.contact_id);
  if (params.campaign_id) query.set("campaign_id", params.campaign_id);
  if (params.list_id) query.set("list_id", params.list_id);
  if (params.channel) query.set("channel", params.channel);
  if (params.skip !== undefined) query.set("skip", params.skip.toString());
  if (params.limit !== undefined) query.set("limit", params.limit.toString());

  const queryString = query.toString() ? `?${query.toString()}` : "";
  const response = await fetch(`/api/analytics/activities${queryString}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Failed to load activities: HTTP ${response.status} - ${errorText || response.statusText}`
    );
  }

  return response.json();
}
