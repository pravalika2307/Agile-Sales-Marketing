/**
 * Service for reusable email templates and AI-assisted email generation.
 * Aligned with backend EmailTemplate model and AWS Bedrock (Claude Sonnet 4.5).
 */

export interface EmailTemplateItem {
  id: string;
  organization_id: string;
  name: string;
  description?: string | null;
  category: string;
  subject_template: string;
  body_template: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EmailTemplateCreatePayload {
  name: string;
  description?: string | null;
  category?: string;
  subject_template: string;
  body_template: string;
  is_active?: boolean;
}

export interface EmailTemplateUpdatePayload {
  name?: string;
  description?: string | null;
  category?: string;
  subject_template?: string;
  body_template?: string;
  is_active?: boolean;
}

export interface AIEmailGeneratePayload {
  campaign_name?: string;
  email_objective: string;
  target_audience?: string;
  tone?: string;
  call_to_action?: string;
}

export interface AIEmailGenerateResult {
  subject: string;
  body: string;
  model_used: string;
  ai_provider: string;
  is_mock?: boolean;
}

export const TEMPLATE_CATEGORIES = [
  { value: "all", label: "All Categories" },
  { value: "outbound", label: "Cold Outbound" },
  { value: "follow_up", label: "Follow-up" },
  { value: "nurture", label: "Nurture / Value" },
  { value: "referral", label: "Referral Request" },
  { value: "announcement", label: "Announcement" },
];

/**
 * Fetch list of reusable email templates with search and category filtering.
 */
export async function fetchEmailTemplates(params?: {
  category?: string;
  search?: string;
  is_active?: boolean;
}): Promise<EmailTemplateItem[]> {
  const query = new URLSearchParams();
  if (params?.category && params.category !== "all") query.set("category", params.category);
  if (params?.search && params.search.trim()) query.set("search", params.search.trim());
  if (params?.is_active !== undefined) query.set("is_active", String(params.is_active));

  const qs = query.toString();
  const res = await fetch(`/api/templates${qs ? `?${qs}` : ""}`, {
    cache: "no-store",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to fetch email templates (HTTP ${res.status})`);
  }

  return res.json();
}

/**
 * Get a specific saved email template by ID.
 */
export async function fetchEmailTemplate(id: string): Promise<EmailTemplateItem> {
  const res = await fetch(`/api/templates/${id}`, { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to fetch template (HTTP ${res.status})`);
  }
  return res.json();
}

/**
 * Save a new reusable email template.
 */
export async function createEmailTemplate(
  payload: EmailTemplateCreatePayload
): Promise<EmailTemplateItem> {
  const res = await fetch("/api/templates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to create email template (HTTP ${res.status})`);
  }

  return res.json();
}

/**
 * Update an existing reusable email template.
 */
export async function updateEmailTemplate(
  id: string,
  payload: EmailTemplateUpdatePayload
): Promise<EmailTemplateItem> {
  const res = await fetch(`/api/templates/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to update email template (HTTP ${res.status})`);
  }

  return res.json();
}

/**
 * Delete a saved email template.
 */
export async function deleteEmailTemplate(id: string): Promise<void> {
  const res = await fetch(`/api/templates/${id}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to delete template (HTTP ${res.status})`);
  }
}

/**
 * Generate email subject and body using AWS Bedrock Claude Sonnet 4.5.
 */
export async function generateAIEmail(
  payload: AIEmailGeneratePayload
): Promise<AIEmailGenerateResult> {
  const res = await fetch("/api/campaigns/templates/generate-ai", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to generate email content with AI (HTTP ${res.status})`);
  }

  return res.json();
}
