/**
 * Company / Account Service for Agile Sales & Marketing.
 * Fetches genuine company accounts directly from the backend PostgreSQL database.
 * 
 * Strict Data Integrity:
 * - REAL DATA -> REAL STATE
 * - NO DATA -> NEUTRAL EMPTY STATE (0 companies)
 * - NEVER INVENT OR FABRICATE DEMO COMPANIES
 */

export type CompanyStatus = "NEW" | "ACTIVE" | "INACTIVE";

export interface CompanyContact {
  id: string;
  fullName: string;
  jobTitle: string;
  email: string;
  phone?: string;
  seniority?: string;
}

export interface CompanyLeadRef {
  id: string;
  name: string;
  jobTitle: string;
  score: number | null;
  temperature: "HOT" | "WARM" | "COLD" | "UNASSESSED";
  status: string;
}

export interface CompanyActivityItem {
  id: string;
  type: "email" | "voice_call" | "reply" | "campaign" | "status";
  title: string;
  description: string;
  timestamp: string;
}

export interface CompanyAccount {
  id: string;
  name: string;
  domain: string;
  industry: string;
  employeeCountRange: string;
  city: string;
  country: string;
  location: string;
  website: string;
  status: CompanyStatus;
  leadsCount: number;
  contactsCount: number;
  lastActivityAt: string;
  lastActivityLabel: string;
  createdAt: string;
  contacts: CompanyContact[];
  leads: CompanyLeadRef[];
  campaigns: string[];
  activities: CompanyActivityItem[];
}

export interface CompanyFilterOptions {
  searchQuery?: string;
  industry?: string;
  companySize?: string;
  location?: string;
  status?: string;
  sortBy?: "newest" | "leads_desc" | "name_asc";
}

export interface CreateCompanyPayload {
  name: string;
  domain?: string;
  industry?: string;
  employee_count_range?: string;
  city?: string;
  country?: string;
  website?: string;
}

/**
 * Maps raw backend company response to strong CompanyAccount.
 */
function mapBackendCompanyToAccount(raw: any): CompanyAccount {
  const city = raw.city || "";
  const country = raw.country || "";
  const location = [city, country].filter(Boolean).join(", ") || "—";
  const domain = raw.domain || (raw.website ? raw.website.replace(/^https?:\/\//i, "").split("/")[0] : "—");
  const website = raw.website || (raw.domain ? `https://${raw.domain}` : "#");

  return {
    id: raw.id,
    name: raw.name,
    domain,
    industry: raw.industry || "General Business",
    employeeCountRange: raw.employee_count_range || "—",
    city,
    country,
    location,
    website,
    status: (raw.status || "NEW") as CompanyStatus,
    leadsCount: raw.leads_count || 0,
    contactsCount: raw.contacts_count || 0,
    lastActivityAt: raw.updated_at || raw.created_at || new Date().toISOString(),
    lastActivityLabel: "—",
    createdAt: raw.created_at || new Date().toISOString(),
    contacts: [],
    leads: [],
    campaigns: [],
    activities: [],
  };
}

export interface FetchCompaniesOptions {
  search?: string;
  industry?: string;
  page?: number;
  limit?: number;
  skip?: number;
}

export interface FetchCompaniesResult {
  items: CompanyAccount[];
  total: number;
}

/**
 * Fetches genuine company accounts from the backend API.
 * Never falls back to fabricated demo companies.
 */
export async function fetchCompanies(
  options?: FetchCompaniesOptions
): Promise<FetchCompaniesResult> {
  const params = new URLSearchParams();
  if (options?.search && options.search.trim()) {
    params.set("search", options.search.trim());
  }
  if (options?.industry && options.industry !== "ALL") {
    params.set("industry", options.industry);
  }
  if (options?.page) {
    params.set("page", options.page.toString());
  }
  if (options?.limit) {
    params.set("limit", options.limit.toString());
  }
  if (options?.skip !== undefined) {
    params.set("skip", options.skip.toString());
  }

  const queryStr = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`/api/companies${queryStr}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch companies from backend (HTTP ${res.status})`);
  }

  const headerTotal = res.headers.get("X-Total-Count") || res.headers.get("x-total-count");
  const data = await res.json();
  const rawItems = Array.isArray(data) ? data : [];
  const items = rawItems.map(mapBackendCompanyToAccount);
  const total = headerTotal ? parseInt(headerTotal, 10) : items.length;

  return {
    items,
    total: isNaN(total) ? items.length : total,
  };
}

/**
 * Creates a new company account persisted in the backend database.
 */
export async function createBackendCompany(
  payload: CreateCompanyPayload
): Promise<CompanyAccount> {
  const res = await fetch("/api/companies", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to create company: ${errorText || res.statusText}`);
  }

  const created = await res.json();
  return mapBackendCompanyToAccount(created);
}

/**
 * Filter and sort company accounts according to options.
 */
export function filterCompanies(
  companies: CompanyAccount[],
  criteria: CompanyFilterOptions
): CompanyAccount[] {
  const result = companies.filter((c) => {
    // Search query
    if (criteria.searchQuery && criteria.searchQuery.trim()) {
      const q = criteria.searchQuery.toLowerCase().trim();
      const matchText = `${c.name} ${c.domain} ${c.industry} ${c.location} ${c.city}`.toLowerCase();
      if (!matchText.includes(q)) return false;
    }

    // Industry filter
    if (criteria.industry && criteria.industry !== "ALL") {
      if (c.industry.toLowerCase() !== criteria.industry.toLowerCase()) {
        return false;
      }
    }

    // Company Size filter
    if (criteria.companySize && criteria.companySize !== "ALL") {
      if (c.employeeCountRange !== criteria.companySize) {
        return false;
      }
    }

    // Location filter
    if (criteria.location && criteria.location !== "ALL") {
      if (!c.location.toLowerCase().includes(criteria.location.toLowerCase())) {
        return false;
      }
    }

    // Status filter
    if (criteria.status && criteria.status !== "ALL") {
      if (c.status !== criteria.status) return false;
    }

    return true;
  });

  // Sorting
  if (criteria.sortBy === "leads_desc") {
    result.sort((a, b) => b.leadsCount - a.leadsCount);
  } else if (criteria.sortBy === "name_asc") {
    result.sort((a, b) => a.name.localeCompare(b.name));
  } else {
    // Default newest
    result.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  }

  return result;
}
