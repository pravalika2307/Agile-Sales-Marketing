/**
 * CRM Lead Database Service for Agile Sales & Marketing.
 * Live backend data integration strictly adhering to enterprise data-integrity standards.
 * NO fabricated business data, NO hardcoded demo arrays, NO invented activity timelines.
 */

export type CRMLeadStatus =
  | "new"
  | "contacted"
  | "replied"
  | "qualified"
  | "unresponsive"
  | "opted_out"
  | "selected"
  | "enrolled"
  | "converted"
  | "rejected";

export type CRMLeadTemperature = "HOT" | "WARM" | "COLD" | "UNASSESSED";

export interface LeadActivityItem {
  id: string;
  type: "voice_call" | "email_sent" | "reply" | "status_change" | "enrollment";
  title: string;
  description: string;
  timestamp: string;
  meta?: Record<string, string>;
}

export interface BackendLead {
  id: string;
  organization_id: string;
  icp_id?: string | null;
  company_id?: string | null;
  contact_id?: string | null;
  source: string;
  source_external_id?: string | null;
  company_name: string;
  company_domain?: string | null;
  industry?: string | null;
  employee_count_range?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  address_line_1?: string | null;
  address_line_2?: string | null;
  country?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  job_title?: string | null;
  linkedin_profile_url?: string | null;
  qualification_status: string;
  lead_temperature?: string | null;
  lead_score?: number | null;
  is_scored?: boolean;
  qualification_reason?: string | null;
  status: string;
  assigned_to_user_id?: string | null;
  assignee_name?: string | null;
  routing_rule_id?: string | null;
  routed_at?: string | null;
  routing_notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CRMLead {
  id: string;
  firstName: string;
  lastName: string;
  fullName: string;
  email: string;
  phone: string;
  jobTitle: string;
  seniority: string;
  department: string;
  companyName: string;
  companyDomain: string;
  industry: string;
  companySize: string;
  city: string;
  state: string;
  country: string;
  location: string;
  website: string;
  linkedinProfileUrl?: string | null;
  leadScore: number | null;
  isScored: boolean;
  temperature: CRMLeadTemperature;
  status: CRMLeadStatus;
  source: string;
  qualificationStatus: "new" | "qualified" | "disqualified" | "reviewed";
  qualificationReason: string;
  assignedToUserId?: string | null;
  assigneeName?: string | null;
  routingRuleId?: string | null;
  routedAt?: string | null;
  routingNotes?: string | null;
  lastActivityAt: string;
  lastActivityLabel: string;
  campaignName?: string;
  contactId?: string | null;
  createdAt: string;
  activities: LeadActivityItem[];
}

export interface CreateLeadPayload {
  firstName: string;
  lastName?: string;
  email?: string;
  phone?: string;
  companyName: string;
  jobTitle?: string;
  industry?: string;
  linkedinProfileUrl?: string;
  temperature?: CRMLeadTemperature;
}

export interface UpdateLeadPayload {
  firstName?: string;
  lastName?: string;
  email?: string;
  phone?: string;
  companyName?: string;
  companyDomain?: string;
  jobTitle?: string;
  industry?: string;
  employeeCountRange?: string;
  city?: string;
  state?: string;
  postalCode?: string;
  addressLine1?: string;
  addressLine2?: string;
  country?: string;
  linkedinProfileUrl?: string | null;
  temperature?: CRMLeadTemperature;
  qualificationStatus?: "new" | "qualified" | "disqualified" | "reviewed";
  qualificationReason?: string;
  status?: CRMLeadStatus;
}

export interface CRMLeadFilterOptions {
  searchQuery?: string;
  status?: string;
  qualificationStatus?: string;
  temperature?: string;
  source?: string;
  company?: string;
  campaign?: string;
  sortBy?: "newest" | "score_desc" | "activity";
}

function formatRelativeTime(dateString?: string): string {
  if (!dateString) return "—";
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return "—";
    const diffSec = Math.floor((Date.now() - date.getTime()) / 1000);
    if (diffSec < 60) return "Just now";
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    if (diffSec < 172800) return "Yesterday";
    return date.toLocaleDateString();
  } catch {
    return "—";
  }
}

/**
 * Converts a raw backend Lead record to the frontend CRMLead structure.
 * Zero fabricated activities or metrics.
 */
export function mapBackendLeadToCRMLead(lead: BackendLead): CRMLead {
  const firstName = lead.first_name || "";
  const lastName = lead.last_name || "";
  const fullName =
    `${firstName} ${lastName}`.trim() ||
    lead.email ||
    lead.company_name ||
    "Unknown Prospect";

  const rawTemp = (lead.lead_temperature || "").toUpperCase();
  const temperature: CRMLeadTemperature =
    rawTemp === "HOT" ? "HOT" : rawTemp === "WARM" ? "WARM" : rawTemp === "COLD" ? "COLD" : "UNASSESSED";

  const locParts = [lead.city, lead.state, lead.country].filter(Boolean);
  const location = locParts.length > 0 ? locParts.join(", ") : "—";

  // REAL DATA ONLY: Only leads genuinely evaluated via ICP algorithm have leadScore.
  const isScored = Boolean(lead.is_scored ?? (lead.icp_id && lead.qualification_reason));
  const leadScore = isScored && typeof lead.lead_score === "number" ? lead.lead_score : null;

  return {
    id: lead.id,
    firstName,
    lastName,
    fullName,
    email: lead.email || "—",
    phone: lead.phone || "",
    jobTitle: lead.job_title || "—",
    seniority: "—",
    department: "—",
    companyName:
      lead.company_name &&
      lead.company_name !== "HubSpot Contact" &&
      lead.company_name !== "Unknown"
        ? lead.company_name
        : "—",
    companyDomain: lead.company_domain || "",
    industry: lead.industry || "—",
    companySize: lead.employee_count_range || "—",
    city: lead.city || "",
    state: lead.state || "",
    country: lead.country || "",
    location,
    website: lead.company_domain
      ? lead.company_domain.startsWith("http")
        ? lead.company_domain
        : `https://${lead.company_domain}`
      : "",
    linkedinProfileUrl: lead.linkedin_profile_url || null,
    leadScore,
    isScored,
    temperature,
    status: (lead.status as CRMLeadStatus) || "new",
    source: lead.source || "Manual Entry",
    qualificationStatus:
      (lead.qualification_status as "new" | "qualified" | "disqualified" | "reviewed") || "new",
    qualificationReason: lead.qualification_reason || "—",
    assignedToUserId: lead.assigned_to_user_id || null,
    assigneeName: lead.assignee_name || null,
    routingRuleId: lead.routing_rule_id || null,
    routedAt: lead.routed_at || null,
    routingNotes: lead.routing_notes || null,
    lastActivityAt: lead.updated_at || lead.created_at,
    lastActivityLabel: formatRelativeTime(lead.updated_at || lead.created_at),
    contactId: lead.contact_id || null,
    createdAt: lead.created_at,
    // REAL DATA ONLY: Zero fabricated activities. Activities are only populated if backed by actual records.
    activities: [],
  };
}

export interface FetchCRMLeadsOptions {
  page?: number;
  pageSize?: number;
  search?: string;
  status?: string;
  qualificationStatus?: string;
  leadTemperature?: string;
  source?: string;
  industry?: string;
  excludeTest?: boolean;
}

/**
 * Fetches genuine Leads from the backend API.
 * Test artifacts (Retell test calls, mock emails) are excluded by default.
 */
export async function fetchCRMLeads(
  options: FetchCRMLeadsOptions = {}
): Promise<{ items: CRMLead[]; total: number }> {
  try {
    const params = new URLSearchParams();
    if (options.page) params.set("page", options.page.toString());
    if (options.pageSize) params.set("page_size", options.pageSize.toString());
    if (options.search && options.search.trim()) params.set("search", options.search.trim());
    if (options.status && options.status !== "ALL") params.set("status", options.status);
    if (options.qualificationStatus && options.qualificationStatus !== "ALL")
      params.set("qualification_status", options.qualificationStatus);
    if (options.leadTemperature && options.leadTemperature !== "ALL")
      params.set("lead_temperature", options.leadTemperature.toLowerCase());
    if (options.source && options.source !== "ALL") params.set("source", options.source);
    if (options.industry && options.industry !== "ALL") params.set("industry", options.industry);
    params.set("exclude_test", options.excludeTest !== false ? "true" : "false");

    const res = await fetch(`/api/leads?${params.toString()}`, {
      method: "GET",
      cache: "no-store",
    });

    if (!res.ok) {
      const errText = await res.text().catch(() => "");
      console.warn(`[crmLeadService] Backend returned ${res.status}: ${errText}`);
      throw new Error(`Failed to fetch leads (${res.status}): ${errText}`);
    }

    const data = await res.json();
    const rawItems: BackendLead[] = Array.isArray(data.items) ? data.items : [];
    const mapped = rawItems.map(mapBackendLeadToCRMLead);

    return {
      items: mapped,
      total: typeof data.total === "number" ? data.total : mapped.length,
    };
  } catch (err) {
    console.error("[crmLeadService] Failed to fetch CRM leads:", err);
    throw err;
  }
}

/**
 * Fetches an individual lead by ID.
 */
export async function fetchCRMLeadById(leadId: string): Promise<CRMLead> {
  const res = await fetch(`/api/leads/${leadId}`, { cache: "no-store" });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Failed to fetch lead (${res.status}): ${errText}`);
  }
  const raw = await res.json();
  return mapBackendLeadToCRMLead(raw);
}

/**
 * Creates a real Lead record persisted to the backend database.
 * No arbitrary score assignments (HOT=80, WARM=60, etc.).
 */
export async function createBackendLead(payload: CreateLeadPayload): Promise<CRMLead> {
  const backendBody: Record<string, any> = {
    first_name: payload.firstName.trim(),
    last_name: payload.lastName?.trim() || null,
    email: payload.email?.trim() || null,
    phone: payload.phone?.trim() || null,
    job_title: payload.jobTitle?.trim() || null,
    company_name: payload.companyName.trim(),
    company_domain: payload.email?.includes("@") ? payload.email.split("@")[1].trim() : null,
    industry: payload.industry?.trim() || null,
    source: "manual",
  };

  if (payload.linkedinProfileUrl) {
    backendBody.linkedin_profile_url = payload.linkedinProfileUrl.trim();
  }

  // Only assign temperature if explicitly selected by user
  if (payload.temperature && payload.temperature !== "UNASSESSED") {
    backendBody.lead_temperature = payload.temperature.toLowerCase();
  }

  const res = await fetch("/api/leads", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(backendBody),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Failed to create lead (${res.status}): ${errText}`);
  }

  const createdRaw: BackendLead = await res.json();
  return mapBackendLeadToCRMLead(createdRaw);
}

/**
 * Updates an individual lead record in the backend and returns the mapped CRMLead.
 */
export async function updateBackendLead(
  leadId: string,
  payload: UpdateLeadPayload
): Promise<CRMLead> {
  const backendBody: Record<string, any> = {};
  if (payload.firstName !== undefined) backendBody.first_name = payload.firstName;
  if (payload.lastName !== undefined) backendBody.last_name = payload.lastName;
  if (payload.email !== undefined) backendBody.email = payload.email;
  if (payload.phone !== undefined) backendBody.phone = payload.phone;
  if (payload.jobTitle !== undefined) backendBody.job_title = payload.jobTitle;
  if (payload.companyName !== undefined) backendBody.company_name = payload.companyName;
  if (payload.companyDomain !== undefined) backendBody.company_domain = payload.companyDomain;
  if (payload.industry !== undefined) backendBody.industry = payload.industry;
  if (payload.employeeCountRange !== undefined) backendBody.employee_count_range = payload.employeeCountRange;
  if (payload.city !== undefined) backendBody.city = payload.city;
  if (payload.state !== undefined) backendBody.state = payload.state;
  if (payload.postalCode !== undefined) backendBody.postal_code = payload.postalCode;
  if (payload.addressLine1 !== undefined) backendBody.address_line_1 = payload.addressLine1;
  if (payload.addressLine2 !== undefined) backendBody.address_line_2 = payload.addressLine2;
  if (payload.country !== undefined) backendBody.country = payload.country;
  if (payload.linkedinProfileUrl !== undefined) {
    backendBody.linkedin_profile_url = payload.linkedinProfileUrl;
  }
  if (payload.temperature !== undefined) {
    backendBody.lead_temperature = payload.temperature === "UNASSESSED" ? null : payload.temperature.toLowerCase();
  }
  if (payload.qualificationStatus !== undefined) {
    backendBody.qualification_status = payload.qualificationStatus;
  }
  if (payload.qualificationReason !== undefined) {
    backendBody.qualification_reason = payload.qualificationReason;
  }
  if (payload.status !== undefined) {
    backendBody.status = payload.status;
  }

  const res = await fetch(`/api/leads/${leadId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(backendBody),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Failed to update lead (${res.status}): ${errText}`);
  }

  const updatedRaw: BackendLead = await res.json();
  return mapBackendLeadToCRMLead(updatedRaw);
}

/**
 * Bulk updates lifecycle status or qualification status for leads in backend DB.
 */
export async function bulkUpdateLeadStatus(payload: {
  leadIds: string[];
  status?: CRMLeadStatus;
  qualificationStatus?: "new" | "qualified" | "disqualified" | "reviewed";
}): Promise<{ updatedCount: number; updatedIds: string[] }> {
  const res = await fetch("/api/leads", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      lead_ids: payload.leadIds,
      status: payload.status,
      qualification_status: payload.qualificationStatus,
    }),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Failed to update lead status (${res.status}): ${errText}`);
  }

  return await res.json();
}

/**
 * Filter and sort CRM leads according to provided criteria.
 */
export function filterCRMLeads(
  leads: CRMLead[],
  criteria: CRMLeadFilterOptions
): CRMLead[] {
  const result = leads.filter((lead) => {
    // Search query
    if (criteria.searchQuery && criteria.searchQuery.trim()) {
      const q = criteria.searchQuery.toLowerCase().trim();
      const matchString = `${lead.fullName} ${lead.email} ${lead.companyName} ${lead.jobTitle} ${lead.location}`.toLowerCase();
      if (!matchString.includes(q)) return false;
    }

    // Lifecycle status filter
    if (criteria.status && criteria.status !== "ALL") {
      if (lead.status !== criteria.status) return false;
    }

    // Qualification status filter
    if (criteria.qualificationStatus && criteria.qualificationStatus !== "ALL") {
      if (lead.qualificationStatus !== criteria.qualificationStatus) return false;
    }

    // Temperature filter
    if (criteria.temperature && criteria.temperature !== "ALL") {
      if (lead.temperature !== criteria.temperature) return false;
    }

    // Source filter
    if (criteria.source && criteria.source !== "ALL") {
      if (lead.source !== criteria.source) return false;
    }

    // Company filter
    if (criteria.company && criteria.company !== "ALL") {
      if (lead.companyName !== criteria.company) return false;
    }

    // Campaign filter
    if (criteria.campaign && criteria.campaign !== "ALL") {
      if (!lead.campaignName?.includes(criteria.campaign)) return false;
    }

    return true;
  });

  // Sorting
  if (criteria.sortBy === "score_desc") {
    result.sort((a, b) => (b.leadScore ?? -1) - (a.leadScore ?? -1));
  } else if (criteria.sortBy === "newest") {
    result.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  }

  return result;
}

export interface LeadConversionResponse {
  lead_id: string;
  company_id: string;
  contact_id?: string | null;
  company_created: boolean;
  contact_created: boolean;
  status: string;
}

/**
 * Converts a prospect lead to CRM Company and Contact records.
 * Returns linked company_id and contact_id.
 */
export async function convertLeadToCRMContact(leadId: string): Promise<LeadConversionResponse> {
  const res = await fetch(`/api/leads/${leadId}/convert`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Failed to convert lead to CRM contact (${res.status}): ${errText}`);
  }

  return await res.json();
}

export interface LeadImportRow {
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
  job_title?: string;
  company_name?: string;
  industry?: string;
  city?: string;
  country?: string;
  linkedin_profile_url?: string;
}

export interface LeadImportResponse {
  imported_count: number;
  skipped_duplicate_count: number;
  failed_count: number;
  imported_ids: string[];
  errors: string[];
}

/**
 * Ingests a batch of lead rows via the backend CSV import API.
 * Deduplicates in-batch and against existing DB records within the tenant organization.
 */
export async function importLeadsBatch(rows: LeadImportRow[]): Promise<LeadImportResponse> {
  const res = await fetch("/api/leads/import", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ rows }),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Failed to import leads (${res.status}): ${errText}`);
  }

  return await res.json();
}

/**
 * Deletes an individual lead record scoped to the tenant organization.
 */
export async function deleteLead(leadId: string): Promise<void> {
  const res = await fetch(`/api/leads/${leadId}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    throw new Error(`Failed to delete lead (${res.status}): ${errText}`);
  }
}


