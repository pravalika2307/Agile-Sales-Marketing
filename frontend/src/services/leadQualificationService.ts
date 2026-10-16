/**
 * Lead Qualification, Scoring Breakdown, Routing Rules, and Campaign Eligibility Service.
 * Interfaces with enterprise backend endpoints adhering to strict data-integrity rules.
 * Never fabricates qualification scores or routing states.
 */

export interface CriterionDetail {
  criterion: string;
  points: number;
  max_points: number;
  status: "matched" | "unmatched" | "missing_data" | "not_configured";
  detail: string;
}

export interface LeadQualificationResult {
  lead_id: string;
  icp_id?: string | null;
  icp_name?: string | null;
  score: number;
  temperature: "cold" | "warm" | "hot";
  qualification_status: "new" | "qualified" | "disqualified" | "reviewed";
  is_qualified: boolean;
  is_assessed: boolean;
  qualification_reason: string;
  criteria: CriterionDetail[];
  matched_criteria_count: number;
  missing_criteria_count: number;
  unmatched_criteria_count: number;
}

export interface LeadBatchEvaluateResult {
  total_evaluated: number;
  qualified_count: number;
  disqualified_count: number;
  unassessed_count: number;
  results: LeadQualificationResult[];
}

export interface LeadRouteResult {
  lead_id: string;
  is_routed: boolean;
  matched_rule_id?: string | null;
  matched_rule_name?: string | null;
  assigned_to_user_id?: string | null;
  assignee_name?: string | null;
  assigned_team?: string | null;
  routed_at?: string | null;
  explanation: string;
}

export interface LeadBatchRouteResult {
  total_evaluated: number;
  routed_count: number;
  unassigned_count: number;
  already_assigned_count: number;
  results: LeadRouteResult[];
}

export interface RoutingRule {
  id: string;
  organization_id: string;
  name: string;
  description?: string | null;
  priority: number;
  is_active: boolean;
  industries?: string[] | null;
  company_size_min?: number | null;
  company_size_max?: number | null;
  countries?: string[] | null;
  cities?: string[] | null;
  min_score?: number | null;
  max_score?: number | null;
  qualification_statuses?: string[] | null;
  assigned_to_user_id?: string | null;
  assigned_team?: string | null;
  assignee_name?: string | null;
  assignee_email?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateRoutingRulePayload {
  name: string;
  description?: string;
  priority: number;
  is_active?: boolean;
  industries?: string[];
  company_size_min?: number;
  company_size_max?: number;
  countries?: string[];
  cities?: string[];
  min_score?: number;
  max_score?: number;
  qualification_statuses?: string[];
  assigned_to_user_id?: string;
  assigned_team?: string;
}

export interface CampaignEligibilityResult {
  lead_id: string;
  campaign_id: string;
  campaign_name: string;
  campaign_status: string;
  is_eligible: boolean;
  reasons: string[];
  suppression_reasons: string[];
  contact_id?: string | null;
  already_enrolled: boolean;
}

export interface LeadCampaignEnrollResult {
  lead_id: string;
  campaign_id: string;
  contact_id: string;
  campaign_contact_id?: string | null;
  status: "enrolled" | "already_enrolled" | "rejected";
  message: string;
}

// ── Qualification API Client ─────────────────────────────────────────────────

export async function evaluateLeadQualification(
  leadId: string,
  options: {
    icpId?: string;
    dryRun?: boolean;
    qualificationThreshold?: number;
  } = {}
): Promise<LeadQualificationResult> {
  const res = await fetch(`/api/leads/${leadId}/evaluate-qualification`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      icp_id: options.icpId,
      dry_run: options.dryRun ?? false,
      qualification_threshold: options.qualificationThreshold ?? 50,
    }),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    throw new Error(`Failed to evaluate lead qualification (${res.status}): ${errText}`);
  }

  return res.json();
}

export async function batchEvaluateLeads(
  leadIds: string[],
  options: {
    icpId?: string;
    dryRun?: boolean;
    qualificationThreshold?: number;
  } = {}
): Promise<LeadBatchEvaluateResult> {
  const res = await fetch(`/api/leads/batch-evaluate-qualification`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lead_ids: leadIds,
      icp_id: options.icpId,
      dry_run: options.dryRun ?? false,
      qualification_threshold: options.qualificationThreshold ?? 50,
    }),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    throw new Error(`Failed to batch evaluate leads (${res.status}): ${errText}`);
  }

  return res.json();
}

// ── Routing Rules API Client ─────────────────────────────────────────────────

export async function routeLead(
  leadId: string,
  options: {
    dryRun?: boolean;
    ruleId?: string;
    forceReroute?: boolean;
  } = {}
): Promise<LeadRouteResult> {
  const res = await fetch(`/api/leads/${leadId}/route`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dry_run: options.dryRun ?? false,
      rule_id: options.ruleId,
      force_reroute: options.forceReroute ?? false,
    }),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    throw new Error(`Failed to route lead (${res.status}): ${errText}`);
  }

  return res.json();
}

export async function batchRouteLeads(
  leadIds: string[],
  options: {
    dryRun?: boolean;
    forceReroute?: boolean;
  } = {}
): Promise<LeadBatchRouteResult> {
  const res = await fetch(`/api/leads/batch-route`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lead_ids: leadIds,
      dry_run: options.dryRun ?? false,
      force_reroute: options.forceReroute ?? false,
    }),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    throw new Error(`Failed to batch route leads (${res.status}): ${errText}`);
  }

  return res.json();
}

export async function fetchRoutingRules(): Promise<RoutingRule[]> {
  const res = await fetch(`/api/routing-rules`, {
    method: "GET",
    cache: "no-store",
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    throw new Error(`Failed to fetch routing rules (${res.status}): ${errText}`);
  }

  return res.json();
}

export async function createRoutingRule(
  payload: CreateRoutingRulePayload
): Promise<RoutingRule> {
  const res = await fetch(`/api/routing-rules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    throw new Error(`Failed to create routing rule (${res.status}): ${errText}`);
  }

  return res.json();
}

export async function updateRoutingRule(
  ruleId: string,
  payload: Partial<CreateRoutingRulePayload>
): Promise<RoutingRule> {
  const res = await fetch(`/api/routing-rules/${ruleId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    throw new Error(`Failed to update routing rule (${res.status}): ${errText}`);
  }

  return res.json();
}

export async function deleteRoutingRule(ruleId: string): Promise<void> {
  const res = await fetch(`/api/routing-rules/${ruleId}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    throw new Error(`Failed to delete routing rule (${res.status}): ${errText}`);
  }
}

// ── Campaign Eligibility & Enrollment API Client ─────────────────────────────

export async function checkCampaignEligibility(
  leadId: string,
  campaignId: string
): Promise<CampaignEligibilityResult> {
  const res = await fetch(`/api/leads/${leadId}/campaign-eligibility/${campaignId}`, {
    method: "GET",
    cache: "no-store",
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    throw new Error(`Failed to check campaign eligibility (${res.status}): ${errText}`);
  }

  return res.json();
}

export async function enrollLeadInCampaign(
  leadId: string,
  campaignId: string
): Promise<LeadCampaignEnrollResult> {
  const res = await fetch(`/api/leads/${leadId}/enroll-campaign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ campaign_id: campaignId }),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    throw new Error(`Failed to enroll lead in campaign (${res.status}): ${errText}`);
  }

  return res.json();
}
