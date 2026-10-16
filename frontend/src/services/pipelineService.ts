/**
 * Pipeline & Deal Domain Service for Agile Sales & Marketing.
 * Strictly aligned with backend Pipeline, PipelineStage, and Deal models (crm.py).
 *
 * Supported Deal Statuses: open, won, lost
 * Supported Pipeline: Sales Pipeline with ordered stages from PostgreSQL.
 *
 * Strict Data Integrity:
 * - REAL DATABASE DATA -> DISPLAY REAL DATA
 * - NO DATABASE DATA -> ZERO / EMPTY / NEUTRAL STATE
 * - ZERO FABRICATED DEALS OR BUSINESS DATA
 */

export type DealStatus = "open" | "won" | "lost";

export interface PipelineStageItem {
  id: string;
  pipelineId: string;
  name: string;
  orderIndex: number;
  probabilityPct: number;
  createdAt: string;
  updatedAt: string;
}

export interface PipelineItem {
  id: string;
  organizationId: string;
  name: string;
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
  stages: PipelineStageItem[];
}

export interface DealItem {
  id: string;
  organizationId: string;
  pipelineStageId: string;
  contactId?: string | null;
  contactName?: string | null;
  companyId?: string | null;
  companyName?: string | null;
  name: string;
  amount: number;
  expectedCloseDate?: string | null;
  status: DealStatus;
  createdAt: string;
  updatedAt: string;
  stage?: PipelineStageItem | null;
}

export interface DealCreatePayload {
  name: string;
  pipeline_stage_id: string;
  amount?: number;
  contact_id?: string | null;
  company_id?: string | null;
  expected_close_date?: string | null;
  status?: DealStatus;
}

export interface PipelineMetricsRollup {
  totalDeals: number;
  openDeals: number;
  wonDeals: number;
  lostDeals: number;
  totalPipelineValue: number;
  wonRevenue: number;
}

export interface AvailableContact {
  id: string;
  name: string;
  email: string;
}

export const DEAL_STATUS_LABELS: Record<DealStatus, string> = {
  open: "Open",
  won: "Won",
  lost: "Lost",
};

export const INITIAL_REAL_DEALS: DealItem[] = [];

export const REAL_PIPELINE: PipelineItem = {
  id: "",
  organizationId: "",
  name: "Sales Pipeline",
  isDefault: true,
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  stages: [],
};

// ── Adapters for Backend Models ───────────────────────────────────────────────

export function mapBackendPipeline(raw: any): PipelineItem {
  return {
    id: raw.id,
    organizationId: raw.organization_id,
    name: raw.name,
    isDefault: Boolean(raw.is_default),
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    stages: (raw.stages || []).map((s: any) => ({
      id: s.id,
      pipelineId: s.pipeline_id,
      name: s.name,
      orderIndex: s.order_index ?? 0,
      probabilityPct: s.probability_pct ?? 0,
      createdAt: s.created_at,
      updatedAt: s.updated_at,
    })),
  };
}

export function mapBackendDeal(raw: any): DealItem {
  const contactName = raw.contact
    ? `${raw.contact.first_name || ""} ${raw.contact.last_name || ""}`.trim() || raw.contact.email
    : null;
  const companyName = raw.company?.name || null;

  return {
    id: raw.id,
    organizationId: raw.organization_id,
    pipelineStageId: raw.pipeline_stage_id,
    contactId: raw.contact_id || null,
    contactName,
    companyId: raw.company_id || null,
    companyName,
    name: raw.name,
    amount: typeof raw.amount === "number" ? raw.amount : parseFloat(raw.amount || "0"),
    expectedCloseDate: raw.expected_close_date || null,
    status: raw.status as DealStatus,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    stage: raw.stage
      ? {
          id: raw.stage.id,
          pipelineId: raw.stage.pipeline_id,
          name: raw.stage.name,
          orderIndex: raw.stage.order_index ?? 0,
          probabilityPct: raw.stage.probability_pct ?? 0,
          createdAt: raw.stage.created_at,
          updatedAt: raw.stage.updated_at,
        }
      : null,
  };
}

// ── Live Backend API Calls ───────────────────────────────────────────────────

export async function fetchPipelines(): Promise<PipelineItem[]> {
  const res = await fetch("/api/pipelines", { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to fetch pipelines: ${res.statusText}`);
  }
  const data = await res.json();
  if (!Array.isArray(data)) return [];
  return data.map(mapBackendPipeline);
}

export async function fetchDeals(params?: {
  status?: string;
  pipelineId?: string;
  pipelineStageId?: string;
  search?: string;
}): Promise<DealItem[]> {
  const query = new URLSearchParams();
  if (params?.status && params.status !== "ALL") query.append("status", params.status.toLowerCase());
  if (params?.pipelineId) query.append("pipeline_id", params.pipelineId);
  if (params?.pipelineStageId) query.append("pipeline_stage_id", params.pipelineStageId);
  if (params?.search) query.append("search", params.search);
  query.append("limit", "100");

  const qs = query.toString() ? `?${query.toString()}` : "";
  const res = await fetch(`/api/deals${qs}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to fetch deals: ${res.statusText}`);
  }
  const data = await res.json();
  if (!Array.isArray(data)) return [];
  return data.map(mapBackendDeal);
}

export async function createDeal(payload: DealCreatePayload): Promise<DealItem> {
  const res = await fetch("/api/deals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => null);
    throw new Error(errorData?.error || `Failed to create deal (${res.status})`);
  }
  const data = await res.json();
  return mapBackendDeal(data);
}

export async function moveDealStage(dealId: string, targetStageId: string): Promise<DealItem> {
  const res = await fetch(`/api/deals/${dealId}/stage`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pipeline_stage_id: targetStageId }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => null);
    throw new Error(errorData?.error || `Failed to move deal stage (${res.status})`);
  }
  const data = await res.json();
  return mapBackendDeal(data);
}

export async function updateDealStatus(dealId: string, newStatus: DealStatus): Promise<DealItem> {
  const res = await fetch(`/api/deals/${dealId}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: newStatus }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => null);
    throw new Error(errorData?.error || `Failed to update deal status (${res.status})`);
  }
  const data = await res.json();
  return mapBackendDeal(data);
}

export async function deleteDeal(dealId: string): Promise<void> {
  const res = await fetch(`/api/deals/${dealId}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) {
    const errorData = await res.json().catch(() => null);
    throw new Error(errorData?.error || `Failed to delete deal (${res.status})`);
  }
}

export async function fetchAvailableContacts(): Promise<AvailableContact[]> {
  try {
    const res = await fetch("/api/contacts?limit=100", { cache: "no-store" });
    if (!res.ok) return [];
    const data = await res.json();
    if (!Array.isArray(data)) return [];
    return data.map((c: any) => ({
      id: c.id,
      name: `${c.first_name || ""} ${c.last_name || ""}`.trim() || c.email,
      email: c.email,
    }));
  } catch (err) {
    console.error("fetchAvailableContacts error:", err);
    return [];
  }
}

// ── Metrics & Formatting ─────────────────────────────────────────────────────

export function computePipelineMetrics(deals: DealItem[]): PipelineMetricsRollup {
  let openDeals = 0;
  let wonDeals = 0;
  let lostDeals = 0;
  let totalPipelineValue = 0;
  let wonRevenue = 0;

  for (const d of deals) {
    const amt = typeof d.amount === "number" ? d.amount : 0;
    if (d.status === "open") {
      openDeals++;
      totalPipelineValue += amt;
    } else if (d.status === "won") {
      wonDeals++;
      wonRevenue += amt;
    } else if (d.status === "lost") {
      lostDeals++;
    }
  }

  return {
    totalDeals: deals.length,
    openDeals,
    wonDeals,
    lostDeals,
    totalPipelineValue,
    wonRevenue,
  };
}

export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(amount);
}
