/**
 * Lead discovery service abstraction for Agile Sales & Marketing.
 * 
 * Strict Data Integrity:
 * - REAL DATA -> REAL STATE
 * - NO PROVIDER / NO DATA -> NEUTRAL EMPTY STATE (0 prospects)
 * - NEVER GENERATE FAKE LEADS WHEN A PROVIDER IS UNAVAILABLE
 */

export interface LeadItem {
  id: string;
  name: string;
  firstName?: string;
  lastName?: string;
  jobTitle: string;
  company: string;
  domain?: string;
  location: string;
  city?: string;
  country?: string;
  email: string;
  phone?: string;
  leadScore: number | null;
  temperature: "HOT" | "WARM" | "COLD" | "UNASSESSED";
  industry: string;
  companySize: string;
  department: string;
  seniority: string;
  technologies?: string[];
  status?: string;
}

export interface LeadFilterCriteria {
  naturalQuery?: string;
  industry?: string;
  location?: string;
  companySize?: string;
  jobTitle?: string;
  seniority?: string;
  department?: string;
  technology?: string;
  keywords?: string;
}

export interface LeadSearchResult {
  leads: LeadItem[];
  totalFound: number;
  providerConfigured: boolean;
  message?: string;
}

/**
 * Executes a search for prospects.
 * Never fabricates or generates synthetic leads.
 * Reports clearly when no live provider is connected.
 */
export async function searchProspects(
  criteria: LeadFilterCriteria
): Promise<LeadSearchResult> {
  // Agile Sales & Marketing does not currently have an external B2B provider
  // (e.g. Apollo, ZoomInfo) API key connected in the environment.
  // In accordance with Data Integrity: Return 0 results and indicate provider status honestly.
  return {
    leads: [],
    totalFound: 0,
    providerConfigured: false,
    message:
      "No external B2B lead discovery provider is currently configured (e.g. Apollo, ZoomInfo). Connect a data provider or import leads directly into your CRM database.",
  };
}

/**
 * Filter leads based on structured criteria and natural language search query.
 */
export function filterLeads(
  leads: LeadItem[],
  criteria: LeadFilterCriteria
): LeadItem[] {
  return leads.filter((lead) => {
    // Natural Language Search Match
    if (criteria.naturalQuery && criteria.naturalQuery.trim()) {
      const q = criteria.naturalQuery.toLowerCase().trim();
      const matchText = `${lead.name} ${lead.jobTitle} ${lead.company} ${lead.location} ${lead.industry} ${lead.department} ${lead.technologies?.join(" ") || ""}`.toLowerCase();

      // Multi-word token matching
      const tokens = q.split(/\s+/).filter((t) => t.length > 2);
      const tokenMatch = tokens.every((t) => matchText.includes(t));
      if (!tokenMatch && !matchText.includes(q)) return false;
    }

    // Structured Industry
    if (criteria.industry && criteria.industry !== "ALL") {
      if (lead.industry.toLowerCase() !== criteria.industry.toLowerCase()) {
        return false;
      }
    }

    // Structured Location
    if (criteria.location && criteria.location !== "ALL") {
      if (
        !lead.location.toLowerCase().includes(criteria.location.toLowerCase())
      ) {
        return false;
      }
    }

    // Company Size
    if (criteria.companySize && criteria.companySize !== "ALL") {
      if (lead.companySize !== criteria.companySize) {
        return false;
      }
    }

    // Job Title / Seniority
    if (criteria.seniority && criteria.seniority !== "ALL") {
      if (lead.seniority.toLowerCase() !== criteria.seniority.toLowerCase()) {
        return false;
      }
    }

    // Department
    if (criteria.department && criteria.department !== "ALL") {
      if (
        lead.department.toLowerCase() !== criteria.department.toLowerCase()
      ) {
        return false;
      }
    }

    // Keywords
    if (criteria.keywords && criteria.keywords.trim()) {
      const kw = criteria.keywords.toLowerCase();
      const matchText = `${lead.name} ${lead.jobTitle} ${lead.company}`.toLowerCase();
      if (!matchText.includes(kw)) return false;
    }

    return true;
  });
}
