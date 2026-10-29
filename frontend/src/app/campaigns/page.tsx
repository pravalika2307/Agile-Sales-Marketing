"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Pagination } from "@/components/ui/pagination";
import { Modal } from "@/components/ui/modal";
import { CampaignDetailDrawer } from "@/components/campaigns/campaign-detail-drawer";
import { WorkflowBuilder } from "@/components/campaigns/workflow-builder";
import {
  CampaignItem,
  CampaignType,
  CAMPAIGN_TYPE_LABELS,
  CAMPAIGN_STATUS_LABELS,
  fetchCampaigns,
  createCampaign,
  activateCampaign,
  pauseCampaign,
  completeCampaign,
  deleteCampaign,
  filterCampaigns,
  CampaignFilterOptions,
  getCampaignDetails,
  generateAICampaignDraft,
} from "@/services/campaignService";
import {
  Search,
  Plus,
  Send,
  Eye,
  Play,
  Pause,
  RotateCcw,
  Users,
  Mail,
  AlertCircle,
  Clock,
  Layers,
  Calendar,
  RefreshCw,
  GitBranch,
  Trash2,
  X,
  CheckCircle2,
  Sparkles,
  MessageSquare,
  PhoneCall,
  ShieldCheck,
  Share2,
} from "lucide-react";
import { useAppMode } from "@/contexts/AppModeContext";
import MarketingCampaignsPage from "@/app/marketing/campaigns/page";

export function SalesCampaignsContent() {
  const { mode } = useAppMode();
  const isMarketing = mode === "marketing";

  // Real backend campaigns state
  const [campaignsList, setCampaignsList] = React.useState<CampaignItem[]>([]);
  const [totalCampaigns, setTotalCampaigns] = React.useState(0);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [typeFilter, setTypeFilter] = React.useState("ALL");
  const [statusFilter, setStatusFilter] = React.useState("ALL");
  const [sortBy, setSortBy] = React.useState<"newest" | "name_asc" | "contacts_desc">("newest");

  // Delete Campaign State
  const [campaignToDelete, setCampaignToDelete] = React.useState<CampaignItem | null>(null);
  const [isDeletingCampaign, setIsDeletingCampaign] = React.useState(false);
  const [deleteCampaignError, setDeleteCampaignError] = React.useState<string | null>(null);
  const [deleteCampaignSuccess, setDeleteCampaignSuccess] = React.useState<string | null>(null);

  // Drawer & Modal state
  const [inspectedCampaign, setInspectedCampaign] = React.useState<CampaignItem | null>(null);
  const [workflowBuilderCampaign, setWorkflowBuilderCampaign] = React.useState<CampaignItem | null>(null);
  const [isNewCampaignModalOpen, setIsNewCampaignModalOpen] = React.useState(false);
  const [isCreating, setIsCreating] = React.useState(false);

  // AI Campaign Draft Generator State
  const [isAIGeneratorModalOpen, setIsAIGeneratorModalOpen] = React.useState(false);
  const [isGeneratingAI, setIsGeneratingAI] = React.useState(false);
  const [aiGeneratorError, setAiGeneratorError] = React.useState<string | null>(null);
  const [aiForm, setAiForm] = React.useState({
    description: "",
    target_audience: "",
    objective: "",
    channels: ["email"] as string[],
    campaign_duration_days: 14,
    followup_interval_days: 3,
    tone: "consultative",
  });

  // Pagination & Loading
  const [currentPage, setCurrentPage] = React.useState(1);
  const [pageSize] = React.useState(10);
  const [isLoading, setIsLoading] = React.useState(true);
  const [hasError, setHasError] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  // New Campaign Form (strictly aligned with CampaignCreate schema)
  const [newCampaignForm, setNewCampaignForm] = React.useState<{
    name: string;
    type: CampaignType;
    description: string;
    first_step_channel: "email" | "sms" | "voice" | "physical_mail" | "linkedin";
  }>({
    name: "",
    type: "sales_outbound",
    description: "",
    first_step_channel: "email",
  });

  // Load campaigns from real backend API
  const loadCampaigns = React.useCallback(async () => {
    setIsLoading(true);
    setHasError(false);
    setErrorMessage(null);
    try {
      const data = await fetchCampaigns({
        searchQuery: searchQuery || undefined,
        status: statusFilter !== "ALL" ? statusFilter : undefined,
        type: typeFilter !== "ALL" ? typeFilter : undefined,
        skip: (currentPage - 1) * pageSize,
        limit: pageSize,
      });
      setCampaignsList(data.campaigns);
      setTotalCampaigns(data.total);
    } catch (err: unknown) {
      console.error("Failed to load campaigns:", err);
      setHasError(true);
      setErrorMessage(err instanceof Error ? err.message : "Failed to load campaigns from backend.");
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, statusFilter, typeFilter, currentPage, pageSize]);

  React.useEffect(() => {
    let isMounted = true;
    (async () => {
      try {
        const data = await fetchCampaigns({
          searchQuery: searchQuery || undefined,
          status: statusFilter !== "ALL" ? statusFilter : undefined,
          type: typeFilter !== "ALL" ? typeFilter : undefined,
          skip: (currentPage - 1) * pageSize,
          limit: pageSize,
        });
        if (isMounted) {
          setCampaignsList(data.campaigns);
          setTotalCampaigns(data.total);
          setHasError(false);
          setErrorMessage(null);
        }
      } catch (err: unknown) {
        if (isMounted) {
          setHasError(true);
          setErrorMessage(err instanceof Error ? err.message : "Failed to load campaigns from backend.");
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    })();
    return () => {
      isMounted = false;
    };
  }, [searchQuery, statusFilter, typeFilter, currentPage, pageSize]);

  // Client-side sort/filter fallback
  const filteredCampaigns = React.useMemo(() => {
    const criteria: CampaignFilterOptions = {
      searchQuery,
      type: typeFilter !== "ALL" ? typeFilter : undefined,
      status: statusFilter !== "ALL" ? statusFilter : undefined,
      sortBy,
    };
    return filterCampaigns(campaignsList, criteria);
  }, [campaignsList, searchQuery, typeFilter, statusFilter, sortBy]);

  // Reset Filters
  const handleResetFilters = () => {
    setSearchQuery("");
    setTypeFilter("ALL");
    setStatusFilter("ALL");
    setSortBy("newest");
    setCurrentPage(1);
  };

  const handleConfirmDeleteCampaign = async () => {
    if (!campaignToDelete) return;
    setIsDeletingCampaign(true);
    setDeleteCampaignError(null);
    try {
      await deleteCampaign(campaignToDelete.id);
      setDeleteCampaignSuccess(`Campaign "${campaignToDelete.name}" was successfully deleted.`);
      if (inspectedCampaign?.id === campaignToDelete.id) {
        setInspectedCampaign(null);
      }
      setCampaignToDelete(null);
      await loadCampaigns();
    } catch (err: unknown) {
      setDeleteCampaignError(err instanceof Error ? err.message : "Failed to delete campaign.");
    } finally {
      setIsDeletingCampaign(false);
    }
  };


  // Create Campaign Handler (strictly persists via backend API)
  const handleCreateCampaign = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCampaignForm.name.trim()) return;

    setIsCreating(true);
    setErrorMessage(null);
    try {
      const channel = newCampaignForm.first_step_channel;
      const startId = "start-node";
      const stepId = "step-node-1";

      const initialWorkflow = {
        nodes: [
          {
            id: startId,
            type: "start" as const,
            title: "Campaign Trigger",
            config: {},
            position: { x: 250, y: 50 },
          },
          channel === "sms"
            ? {
                id: stepId,
                type: "sms" as const,
                title: "Step 1: SMS Outreach",
                config: {
                  step_number: 1,
                  body: "Hi {contact.first_name}, this is {sender_name} from {sender_company}. Are you available for a brief briefing? Book directly: {booking_link}",
                  delay_days: 0,
                  delay_hours: 0,
                  is_active: true,
                },
                position: { x: 250, y: 180 },
              }
            : channel === "voice"
            ? {
                id: stepId,
                type: "voice" as const,
                title: "Step 1: AI Voice SDR Call",
                config: {
                  step_number: 1,
                  agent_type: "outbound_sdr",
                  phone_required: true,
                  delay_days: 0,
                  delay_hours: 0,
                  is_active: true,
                },
                position: { x: 250, y: 180 },
              }
            : channel === "physical_mail"
            ? {
                id: stepId,
                type: "physical_mail" as const,
                title: "Step 1: Physical Direct Mail",
                config: {
                  step_number: 1,
                  poplar_campaign_id: "",
                  poplar_creative_id: "",
                  delay_days: 0,
                  delay_hours: 0,
                  is_active: true,
                },
                position: { x: 250, y: 180 },
              }
            : channel === "linkedin"
            ? {
                id: stepId,
                type: "linkedin" as const,
                title: "Step 1: LinkedIn Outreach (Assisted)",
                config: {
                  step_number: 1,
                  message_type: "connection_request",
                  template: "Hi {contact.first_name}, would love to connect and share insights on receivables management. Let's chat: {booking_link}",
                  booking_url: "https://cal.com/agilereceivables/30min",
                  max_chars: 300,
                  delay_days: 0,
                  delay_hours: 0,
                  is_active: true,
                },
                position: { x: 250, y: 180 },
              }
            : {
                id: stepId,
                type: "email" as const,
                title: "Step 1: Introduction Email",
                config: {
                  step_number: 1,
                  subject: "Introduction to Agile Sales & Marketing",
                  body: "Hi {contact.first_name},\n\nConnecting from Agile Sales & Marketing.",
                  delay_days: 0,
                  delay_hours: 0,
                  is_active: true,
                },
                position: { x: 250, y: 180 },
              },
        ],
        edges: [
          {
            id: `edge-${startId}-${stepId}`,
            source: startId,
            target: stepId,
            label: "Next",
          },
        ],
      };

      const created = await createCampaign({
        name: newCampaignForm.name.trim(),
        type: newCampaignForm.type,
        description: newCampaignForm.description.trim() || undefined,
        first_step_channel: channel,
        workflow_config: initialWorkflow,
      });

      setIsNewCampaignModalOpen(false);
      setNewCampaignForm({
        name: "",
        type: "sales_outbound",
        description: "",
        first_step_channel: "email",
      });
      // Refresh real campaigns from backend
      await loadCampaigns();
      // Guided workflow builder entry: immediately launch workflow designer with persisted channel
      setWorkflowBuilderCampaign(created);
    } catch (err: unknown) {
      console.error("Error creating campaign:", err);
      setErrorMessage(err instanceof Error ? err.message : "Failed to create campaign in backend.");
    } finally {
      setIsCreating(false);
    }
  };

  // AI-Assisted Campaign Draft Generator Handler
  const handleGenerateAICampaign = async () => {
    if (!aiForm.description.trim() || !aiForm.target_audience.trim() || !aiForm.objective.trim()) {
      return;
    }
    setIsGeneratingAI(true);
    setAiGeneratorError(null);
    try {
      const result = await generateAICampaignDraft({
        description: aiForm.description.trim(),
        target_audience: aiForm.target_audience.trim(),
        objective: aiForm.objective.trim(),
        channels: aiForm.channels,
        campaign_duration_days: aiForm.campaign_duration_days,
        followup_interval_days: aiForm.followup_interval_days,
        tone: aiForm.tone,
        save_as_draft: true,
      });

      setIsAIGeneratorModalOpen(false);
      await loadCampaigns();

      if (result.campaign_id) {
        try {
          const detailed = await getCampaignDetails(result.campaign_id);
          setWorkflowBuilderCampaign(detailed);
        } catch (detailErr) {
          console.warn("Could not fetch detailed campaign immediately:", detailErr);
        }
      }
    } catch (err: unknown) {
      console.error("AI campaign generation failed:", err);
      setAiGeneratorError(err instanceof Error ? err.message : "Failed to generate AI campaign draft.");
    } finally {
      setIsGeneratingAI(false);
    }
  };

  // Lifecycle status transition handler (persisted via real backend API)
  const handleLifecycleTransition = async (
    campaignId: string,
    newStatus: "active" | "paused" | "completed"
  ) => {
    setErrorMessage(null);
    try {
      let updated: CampaignItem;
      if (newStatus === "active") {
        updated = await activateCampaign(campaignId);
      } else if (newStatus === "paused") {
        updated = await pauseCampaign(campaignId);
      } else {
        updated = await completeCampaign(campaignId);
      }

      // Update state strictly after backend confirms
      setCampaignsList((prev) =>
        prev.map((c) => (c.id === campaignId ? { ...c, status: updated.status } : c))
      );
      if (inspectedCampaign && inspectedCampaign.id === campaignId) {
        setInspectedCampaign({
          ...inspectedCampaign,
          status: updated.status,
          updatedAt: updated.updatedAt,
        });
      }
    } catch (err: unknown) {
      console.error("Failed to update campaign lifecycle status:", err);
      const msg = err instanceof Error ? err.message : "Failed to transition campaign status.";
      setErrorMessage(msg);
      throw err; // rethrow so drawer can show it too
    }
  };

  return (
    <AppShell onNewCampaignClick={() => setIsNewCampaignModalOpen(true)}>
      {/* 1. Page Header with Breadcrumbs */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-2 border-b border-slate-200/80">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold text-slate-500">Sales</span>
            <span className="text-slate-300">/</span>
            <span className="text-xs font-semibold text-agile-red">Campaigns</span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-header">
            {isMarketing ? "Marketing Campaigns" : "Campaign Sequences & Cadence"}
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
            {isMarketing
              ? "Create, manage, and monitor your marketing broadcasts and nurture sequences."
              : "Multi-channel outreach sequences, AI voice SDR calling, and CRM contact cadences."}
          </p>
        </div>

        {/* Top-right Primary Action: + New Campaign */}
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={loadCampaigns}
            disabled={isLoading}
            className="text-xs inline-flex items-center gap-1.5"
            title="Refresh campaigns"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-agile-red" : ""}`} />
            <span>Refresh</span>
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => setIsAIGeneratorModalOpen(true)}
            className="text-xs inline-flex items-center gap-1.5 shadow-xs border-slate-200 hover:bg-slate-50 text-header hover:text-agile-red"
            title="Generate multi-touch campaign sequence with AI"
          >
            <Sparkles className="w-3.5 h-3.5 text-agile-red" />
            <span>Generate with AI</span>
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={() => setIsNewCampaignModalOpen(true)}
            className="text-xs inline-flex items-center gap-1.5 shadow-xs"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Campaign</span>
          </Button>
        </div>
      </div>

      {/* Error alert banner */}
      {errorMessage && (
        <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button
            onClick={() => setErrorMessage(null)}
            className="text-rose-500 hover:text-rose-700"
          >
            &times;
          </button>
        </div>
      )}

      {/* Top Pacing Overview & KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Total Campaigns</span>
            <Layers className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-2xl font-bold text-header">{campaignsList.length}</div>
          <p className="text-[11px] text-slate-400 mt-0.5">Configured sequence workflows</p>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">Active Sequences</span>
            <Play className="w-4 h-4 text-emerald-600" />
          </div>
          <div className="text-2xl font-bold text-emerald-700">
            {campaignsList.filter((c) => c.status === "active").length}
          </div>
          <p className="text-[11px] text-slate-400 mt-0.5">Currently dispatching cadences</p>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Enrolled Contacts</span>
            <Users className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-2xl font-bold text-header">
            {campaignsList.reduce((acc, c) => acc + (c.contactsCount || 0), 0)}
          </div>
          <p className="text-[11px] text-slate-400 mt-0.5">Total prospects in pipeline</p>
        </div>

        <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-xs">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Verified Deliveries</span>
            <Send className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-2xl font-bold text-header">
            {campaignsList.reduce((acc, c) => acc + (c.metrics?.sent || 0), 0)}
          </div>
          <p className="text-[11px] text-slate-400 mt-0.5">Dispatched touchpoints</p>
        </div>
      </div>

      {/* 2. Compact CRM Control Area */}
      <Card className="border border-slate-200 shadow-[0_1px_3px_rgba(0,0,0,0.03)] bg-white">
        <CardContent className="p-3.5 sm:p-4 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-2.5">
            {/* Search Input */}
            <div className="sm:col-span-2">
              <Input
                placeholder="Search campaigns by name..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                icon={<Search className="w-4 h-4 text-slate-400" />}
                className="h-9 text-xs bg-white border-slate-200"
              />
            </div>

            {/* Type Filter */}
            <div>
              <Select
                value={typeFilter}
                onChange={(e) => {
                  setTypeFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="h-9 text-xs"
                options={[
                  { value: "ALL", label: "All Types" },
                  { value: "sales_outbound", label: "Sales Outbound" },
                  { value: "marketing_social", label: "Marketing Social" },
                  { value: "hybrid", label: "Hybrid" },
                ]}
              />
            </div>

            {/* Status Filter */}
            <div>
              <Select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="h-9 text-xs"
                options={[
                  { value: "ALL", label: "All Statuses" },
                  { value: "draft", label: "Draft" },
                  { value: "active", label: "Active" },
                  { value: "paused", label: "Paused" },
                  { value: "completed", label: "Completed" },
                ]}
              />
            </div>

            {/* Sort Filter */}
            <div>
              <Select
                value={sortBy}
                onChange={(e) =>
                  setSortBy(e.target.value as "newest" | "name_asc" | "contacts_desc")
                }
                className="h-9 text-xs"
                options={[
                  { value: "newest", label: "Newest First" },
                  { value: "name_asc", label: "Name: A to Z" },
                  { value: "contacts_desc", label: "Contacts: High to Low" },
                ]}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 3. Campaign Summary Header */}
      <div className="flex items-center justify-between pt-1">
        <div className="flex items-center gap-2.5">
          <h2 className="text-base font-bold text-header">
            {isMarketing ? "Marketing Campaigns" : "Outreach Campaigns"}
          </h2>
          <span className="px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600 font-semibold text-xs border border-slate-200">
            {totalCampaigns} campaigns
          </span>
        </div>
      </div>

      {/* Deletion Feedback Banner */}
      {deleteCampaignSuccess && (
        <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center justify-between gap-2 animate-in fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{deleteCampaignSuccess}</span>
          </div>
          <button
            onClick={() => setDeleteCampaignSuccess(null)}
            className="text-emerald-500 hover:text-emerald-700"
            aria-label="Dismiss message"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* 4. Campaigns Table / Empty / Loading / Error State */}
      <div className="space-y-3">
        {hasError ? (
          /* Error State */
          <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-8 text-center flex flex-col items-center justify-center space-y-3">
            <AlertCircle className="w-8 h-8 text-rose-500" />
            <div>
              <h3 className="text-sm font-semibold text-rose-900">
                Unable to load campaigns.
              </h3>
              <p className="text-xs text-rose-700 mt-0.5">
                {errorMessage || "Please check organization authentication and connection."}
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={loadCampaigns}
              className="text-xs bg-white"
            >
              Try again
            </Button>
          </div>
        ) : isLoading ? (
          /* Skeleton Loading State */
          <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-10 bg-slate-100/70 rounded-md animate-pulse"
              />
            ))}
          </div>
        ) : campaignsList.length === 0 ? (
          /* Professional Empty State (Data-Integrity Compliant) */
          <div className="rounded-xl border border-slate-200 bg-white p-12 text-center flex flex-col items-center justify-center space-y-3">
            <div className="w-10 h-10 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-400">
              <Send className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-header">
                No campaigns yet
              </h3>
              <p className="text-xs text-slate-500 mt-1 max-w-sm">
                {isMarketing
                  ? "Create a campaign to start organizing your marketing sequences and social broadcasts."
                  : "Create a campaign to start organizing your sales outreach and sequence cadence."}
              </p>
            </div>
            <div className="flex items-center gap-2 pt-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIsAIGeneratorModalOpen(true)}
                className="text-xs border-slate-200 hover:bg-slate-50 text-header hover:text-agile-red shadow-xs"
              >
                <Sparkles className="w-3.5 h-3.5 mr-1 text-agile-red" />
                Generate with AI
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => setIsNewCampaignModalOpen(true)}
                className="text-xs shadow-xs"
              >
                <Plus className="w-3.5 h-3.5 mr-1" />
                New Campaign
              </Button>
              <Link href="/leads">
                <Button variant="secondary" size="sm" className="text-xs">
                  {isMarketing ? "View Audience" : "View Leads"}
                </Button>
              </Link>
            </div>
          </div>
        ) : (
          /* Main Campaigns Table */
          <div className="space-y-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Campaign Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Contacts</TableHead>
                  <TableHead>Current Step</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Last Modified</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredCampaigns.map((camp) => (
                  <TableRow
                    key={camp.id}
                    onClick={() => setInspectedCampaign(camp)}
                    className="cursor-pointer"
                  >
                    {/* Campaign Name */}
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-semibold text-header text-sm hover:text-agile-red transition-colors flex items-center gap-1.5">
                          <Send className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                          {camp.name}
                        </span>
                        <span className="text-[11px] font-mono text-slate-400">
                          {camp.id.substring(0, 8)}...
                        </span>
                      </div>
                    </TableCell>

                    {/* Campaign Type */}
                    <TableCell className="font-medium text-slate-700 text-xs sm:text-sm">
                      {CAMPAIGN_TYPE_LABELS[camp.type]}
                    </TableCell>

                    {/* Campaign Status */}
                    <TableCell>
                      {camp.status === "active" && (
                        <Badge variant="coral" dot>
                          Active
                        </Badge>
                      )}
                      {camp.status === "draft" && (
                        <Badge variant="neutral">Draft</Badge>
                      )}
                      {camp.status === "paused" && (
                        <Badge variant="warning">Paused</Badge>
                      )}
                      {camp.status === "completed" && (
                        <Badge variant="success">Completed</Badge>
                      )}
                    </TableCell>

                    {/* Enrolled Contacts Count */}
                    <TableCell>
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-xs font-semibold border border-slate-200">
                        <Users className="w-3 h-3 text-slate-400" />
                        {camp.contactsCount}
                      </span>
                    </TableCell>

                    {/* Current Sequence Step */}
                    <TableCell>
                      {(() => {
                        const firstStep = camp.steps?.find((s) => s.stepNumber === 1) || camp.steps?.[0];
                        const wfNodes = camp.workflowConfig?.nodes || [];
                        const firstActionNode = wfNodes.find((n) => n.type !== "start");
                        const channelType = firstStep?.stepType || firstActionNode?.type || "email";
                        const stepNum = camp.currentStepNumber || 1;

                        if (channelType === "voice") {
                          return (
                            <span className="text-xs text-purple-700 font-medium flex items-center gap-1.5">
                              <PhoneCall className="w-3.5 h-3.5 text-purple-600 shrink-0" />
                              <span>Step {stepNum}: Voice SDR</span>
                            </span>
                          );
                        } else if (channelType === "sms") {
                          return (
                            <span className="text-xs text-emerald-700 font-medium flex items-center gap-1.5">
                              <MessageSquare className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                              <span>Step {stepNum}: SMS</span>
                            </span>
                          );
                        } else if (channelType === "physical_mail") {
                          return (
                            <span className="text-xs text-amber-700 font-medium flex items-center gap-1.5">
                              <Send className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                              <span>Step {stepNum}: Direct Mail</span>
                            </span>
                          );
                        } else if (channelType === "linkedin") {
                          return (
                            <span className="text-xs text-[#0077b5] font-medium flex items-center gap-1.5">
                              <Share2 className="w-3.5 h-3.5 text-[#0077b5] shrink-0" />
                              <span>Step {stepNum}: LinkedIn</span>
                            </span>
                          );
                        } else {
                          return (
                            <span className="text-xs text-slate-700 font-medium flex items-center gap-1.5">
                              <Mail className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                              <span>Step {stepNum}: Email</span>
                            </span>
                          );
                        }
                      })()}
                    </TableCell>

                    {/* Created Date */}
                    <TableCell className="text-xs text-slate-500">
                      {new Date(camp.createdAt).toLocaleDateString()}
                    </TableCell>

                    {/* Updated Date */}
                    <TableCell className="text-xs text-slate-500">
                      {new Date(camp.updatedAt).toLocaleDateString()}
                    </TableCell>

                    {/* Actions */}
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setWorkflowBuilderCampaign(camp)}
                          className="h-7 text-xs text-agile-red hover:bg-agile-lightorange hover:text-agile-red border-agile-red/30"
                          title="Open Visual Campaign Workflow Builder"
                        >
                          <GitBranch className="w-3.5 h-3.5 mr-1" />
                          Workflow
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setInspectedCampaign(camp)}
                          className="h-7 text-xs text-slate-600 hover:bg-slate-100"
                        >
                          <Eye className="w-3.5 h-3.5 mr-1" />
                          View
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setDeleteCampaignError(null);
                            setCampaignToDelete(camp);
                          }}
                          className="h-7 w-7 p-0 text-slate-400 hover:text-rose-600 hover:bg-rose-50"
                          title="Delete Campaign"
                          aria-label={`Delete ${camp.name}`}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            <Pagination
              currentPage={currentPage}
              totalPages={Math.ceil(totalCampaigns / pageSize) || 1}
              onPageChange={setCurrentPage}
            />
          </div>
        )}
      </div>

      {/* 5. Campaign Detail Drawer */}
      <CampaignDetailDrawer
        campaign={inspectedCampaign}
        isOpen={inspectedCampaign !== null}
        onClose={() => setInspectedCampaign(null)}
        onStatusChange={handleLifecycleTransition}
        onCampaignUpdated={loadCampaigns}
        onCampaignDeleted={() => {
          setInspectedCampaign(null);
          loadCampaigns();
        }}
        onOpenWorkflowBuilder={(camp) => {
          setInspectedCampaign(null);
          setWorkflowBuilderCampaign(camp);
        }}
      />

      {/* 6. Modal: Create Campaign (Strictly aligned with backend CampaignCreate schema) */}
      <Modal
        isOpen={isNewCampaignModalOpen}
        onClose={() => setIsNewCampaignModalOpen(false)}
        title="Create New Campaign"
        description="Configure outreach sequence properties and design the multi-touch workflow."
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setIsNewCampaignModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={isCreating || !newCampaignForm.name.trim()}
              onClick={handleCreateCampaign}
            >
              {isCreating ? "Creating..." : "Create & Open Workflow Builder"}
            </Button>
          </>
        }
      >
        <form onSubmit={handleCreateCampaign} className="space-y-4">
          <div className="p-3 bg-gradient-to-r from-[#fff6f0] to-slate-50 border border-[#ebad8f]/60 rounded-xl flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-white border border-[#ebad8f]/70 flex items-center justify-center shrink-0 shadow-xs">
                <Sparkles className="w-3.5 h-3.5 text-agile-red" />
              </div>
              <div className="text-xs">
                <span className="font-semibold text-header">Draft with AI Assistant</span>
                <p className="text-slate-600 text-[11px]">Generate a personalized multi-touch workflow in seconds.</p>
              </div>
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => {
                setIsNewCampaignModalOpen(false);
                setIsAIGeneratorModalOpen(true);
              }}
              className="text-xs bg-white text-header border-slate-200 hover:bg-slate-50 hover:text-agile-red shrink-0 font-medium shadow-xs"
            >
              Generate with AI
            </Button>
          </div>
          <Input
            label="Campaign Name *"
            required
            value={newCampaignForm.name}
            onChange={(e) =>
              setNewCampaignForm({ ...newCampaignForm, name: e.target.value })
            }
            placeholder="e.g. Executive Outbound Sequence"
          />

          <Select
            label="Campaign Type"
            value={newCampaignForm.type}
            onChange={(e) =>
              setNewCampaignForm({
                ...newCampaignForm,
                type: e.target.value as CampaignType,
              })
            }
            options={[
              { value: "sales_outbound", label: "Sales Outbound (B2B Lead Cadence)" },
              { value: "marketing_social", label: "Marketing Social" },
              { value: "hybrid", label: "Hybrid (Multi-touch Outreach)" },
            ]}
          />

          <Select
            label="Initial Communication Channel"
            value={newCampaignForm.first_step_channel}
            onChange={(e) =>
              setNewCampaignForm({
                ...newCampaignForm,
                first_step_channel: e.target.value as "email" | "sms" | "voice" | "physical_mail" | "linkedin",
              })
            }
            options={[
              { value: "email", label: "Email Outreach (Standard outbound cadence)" },
              { value: "sms", label: "SMS Outreach (Twilio SMS / MMS text outreach)" },
              { value: "voice", label: "AI Voice Call (Retell AI outbound SDR call)" },
              { value: "physical_mail", label: "Physical Direct Mail (Poplar Postcards / Letters)" },
              { value: "linkedin", label: "LinkedIn Outreach (Assisted connection notes & messaging)" },
            ]}
          />

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">
              Campaign Description (Optional)
            </label>
            <textarea
              value={newCampaignForm.description}
              onChange={(e) =>
                setNewCampaignForm({ ...newCampaignForm, description: e.target.value })
              }
              placeholder="e.g. Multi-touch outbound cadence targeting enterprise sales leaders"
              rows={2}
              className="w-full rounded-md border border-slate-300 p-2 text-xs focus:border-agile-red focus:outline-none"
            />
          </div>

          <div className="rounded-lg bg-slate-50 p-3 border border-slate-200 text-xs text-slate-600">
            <strong>Lifecycle Rule:</strong> New campaigns are initially created in <code>draft</code> status. Once created, you will immediately enter the <strong>Visual Workflow Editor</strong> to configure steps, delays, templates, and condition branches before activation.
          </div>
        </form>
      </Modal>

      {/* 6b. Modal: AI Campaign Draft Generator */}
      <Modal
        isOpen={isAIGeneratorModalOpen}
        onClose={() => {
          if (!isGeneratingAI) setIsAIGeneratorModalOpen(false);
        }}
        title="Generate Campaign Sequence with AI"
        description="Describe your outreach strategy in plain English. Claude Sonnet 4.5 will architect a multi-touch sequence with delays, conditional branches, and personalized templates."
        maxWidth="lg"
        footer={
          <>
            <Button
              variant="secondary"
              disabled={isGeneratingAI}
              onClick={() => setIsAIGeneratorModalOpen(false)}
              className="text-xs h-9"
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={
                isGeneratingAI ||
                !aiForm.description.trim() ||
                !aiForm.target_audience.trim() ||
                !aiForm.objective.trim()
              }
              onClick={handleGenerateAICampaign}
              className="text-xs h-9 gap-1.5 shadow-sm"
            >
              {isGeneratingAI ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Architecting Sequence...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Generate Editable Draft</span>
                </>
              )}
            </Button>
          </>
        }
      >
        <div className="space-y-4 text-xs">
          {aiGeneratorError && (
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
              <span className="leading-snug">{aiGeneratorError}</span>
            </div>
          )}

          <div className="space-y-1.5">
            <label className="block text-xs font-semibold text-slate-700">
              Campaign Description & Strategy <span className="text-agile-red">*</span>
            </label>
            <textarea
              required
              rows={3}
              value={aiForm.description}
              onChange={(e) => setAiForm({ ...aiForm, description: e.target.value })}
              placeholder="e.g. Re-engage cold B2B SaaS leads who dropped off during Q3 by offering an exclusive pipeline audit."
              className="w-full rounded-lg bg-white border border-slate-200 p-2.5 text-xs text-header placeholder:text-slate-400 transition-all outline-none focus:border-agile-red focus:ring-2 focus:ring-agile-red/15 leading-relaxed"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-700">
                Target Audience / Persona <span className="text-agile-red">*</span>
              </label>
              <Input
                required
                value={aiForm.target_audience}
                onChange={(e) => setAiForm({ ...aiForm, target_audience: e.target.value })}
                placeholder="e.g. VP of Sales, Head of RevOps"
                className="text-xs h-9"
              />
            </div>
            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-700">
                Primary Objective / CTA <span className="text-agile-red">*</span>
              </label>
              <Input
                required
                value={aiForm.objective}
                onChange={(e) => setAiForm({ ...aiForm, objective: e.target.value })}
                placeholder="e.g. Book 15-min calendar briefing"
                className="text-xs h-9"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="block text-xs font-semibold text-slate-700">
              Available Channels
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
              {[
                { id: "email", label: "Email", icon: Mail, iconClass: "text-blue-600" },
                { id: "sms", label: "Twilio SMS", icon: MessageSquare, iconClass: "text-emerald-600" },
                { id: "voice", label: "Voice SDR", icon: PhoneCall, iconClass: "text-purple-600" },
                { id: "physical_mail", label: "Poplar Mail", icon: Send, iconClass: "text-amber-600" },
                { id: "linkedin", label: "LinkedIn", icon: Share2, iconClass: "text-[#0077b5]" },
              ].map((ch) => {
                const checked = aiForm.channels.includes(ch.id);
                const Icon = ch.icon;
                return (
                  <label
                    key={ch.id}
                    className={`flex items-center gap-2 p-2.5 rounded-lg border cursor-pointer transition-all select-none ${
                      checked
                        ? "bg-[#fff6f0] border-agile-red/60 text-header font-medium shadow-xs ring-1 ring-agile-red/20"
                        : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50 hover:border-slate-300"
                    } ${ch.id === "email" ? "cursor-default" : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={ch.id === "email"}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setAiForm({ ...aiForm, channels: [...aiForm.channels, ch.id] });
                        } else {
                          setAiForm({
                            ...aiForm,
                            channels: aiForm.channels.filter((c) => c !== ch.id),
                          });
                        }
                      }}
                      className="rounded border-slate-300 text-agile-red focus:ring-agile-red/30 accent-[#d7525a] h-3.5 w-3.5 shrink-0"
                    />
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Icon className={`w-3.5 h-3.5 shrink-0 ${ch.iconClass}`} />
                      <span className="truncate text-xs">{ch.label}</span>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-700">
                Sequence Duration
              </label>
              <Select
                value={String(aiForm.campaign_duration_days)}
                onChange={(e) =>
                  setAiForm({ ...aiForm, campaign_duration_days: Number(e.target.value) })
                }
                className="text-xs h-9"
                options={[
                  { value: "7", label: "7 Days (Sprint)" },
                  { value: "14", label: "14 Days (Standard)" },
                  { value: "21", label: "21 Days (Extended)" },
                  { value: "30", label: "30 Days (Nurture)" },
                ]}
              />
            </div>
            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-700">
                Follow-up Interval
              </label>
              <Select
                value={String(aiForm.followup_interval_days)}
                onChange={(e) =>
                  setAiForm({ ...aiForm, followup_interval_days: Number(e.target.value) })
                }
                className="text-xs h-9"
                options={[
                  { value: "2", label: "2 Days delay" },
                  { value: "3", label: "3 Days delay" },
                  { value: "5", label: "5 Days delay" },
                  { value: "7", label: "7 Days delay" },
                ]}
              />
            </div>
            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-700">
                Copy Tone
              </label>
              <Select
                value={aiForm.tone}
                onChange={(e) => setAiForm({ ...aiForm, tone: e.target.value })}
                className="text-xs h-9"
                options={[
                  { value: "consultative", label: "Consultative" },
                  { value: "professional", label: "Professional" },
                  { value: "conversational", label: "Conversational" },
                  { value: "direct", label: "Direct & Concise" },
                ]}
              />
            </div>
          </div>

          <div className="rounded-lg bg-slate-50 p-3.5 border border-slate-200 text-xs text-slate-700 leading-relaxed space-y-1.5">
            <div className="flex items-center gap-1.5 font-semibold text-header">
              <ShieldCheck className="w-4 h-4 text-agile-red shrink-0" />
              <span>Safety & Entitlement Controls</span>
            </div>
            <ul className="list-disc list-inside space-y-1 text-slate-600 text-[11px] pl-1">
              <li>All generated campaigns are saved strictly in <code className="bg-white px-1 py-0.5 rounded border border-slate-200 font-mono text-slate-800">draft</code> status for your review.</li>
              <li>Voice and SMS steps are only generated if entitled and enabled for your tenant.</li>
              <li>Booking URLs strictly use the canonical <code className="bg-white px-1 py-0.5 rounded border border-slate-200 font-mono text-slate-800">{"{booking_link}"}</code> variable—never hallucinated URLs.</li>
            </ul>
          </div>
        </div>
      </Modal>

      {/* 7. Visual Campaign Workflow Builder Modal */}
      {workflowBuilderCampaign && (
        <WorkflowBuilder
          campaignId={workflowBuilderCampaign.id}
          campaignName={workflowBuilderCampaign.name}
          campaignStatus={workflowBuilderCampaign.status}
          initialWorkflow={workflowBuilderCampaign.workflowConfig}
          initialDescription={workflowBuilderCampaign.description}
          onClose={() => {
            setWorkflowBuilderCampaign(null);
            loadCampaigns();
          }}
          onSaved={() => {
            loadCampaigns();
          }}
        />
      )}

      {/* 8. Modal: Delete Campaign Confirmation */}
      <Modal
        isOpen={campaignToDelete !== null}
        onClose={() => {
          if (!isDeletingCampaign) {
            setCampaignToDelete(null);
            setDeleteCampaignError(null);
          }
        }}
        title={`Delete Campaign: ${campaignToDelete?.name || ""}?`}
        description="This permanently removes the campaign from the active campaign list. Associated enrollment and historical records may be retained where required for audit and data integrity."
        footer={
          <>
            <Button
              variant="secondary"
              disabled={isDeletingCampaign}
              onClick={() => {
                setCampaignToDelete(null);
                setDeleteCampaignError(null);
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={isDeletingCampaign}
              onClick={handleConfirmDeleteCampaign}
              className="bg-rose-600 hover:bg-rose-700 text-white border-rose-600"
            >
              {isDeletingCampaign ? "Deleting Campaign..." : "Delete Campaign"}
            </Button>
          </>
        }
      >
        {campaignToDelete && (
          <div className="space-y-3">
            {deleteCampaignError && (
              <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-rose-500" />
                <span>{deleteCampaignError}</span>
              </div>
            )}
            <div className="rounded-lg bg-slate-50 border border-slate-200 p-3.5 space-y-2 text-xs">
              <div className="flex justify-between items-center">
                <span className="text-slate-500 font-medium">Campaign Name:</span>
                <span className="text-slate-900 font-semibold">{campaignToDelete.name}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-500 font-medium">Type:</span>
                <span className="text-slate-900">{CAMPAIGN_TYPE_LABELS[campaignToDelete.type]}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-500 font-medium">Enrolled Contacts:</span>
                <span className="text-slate-900 font-semibold">{campaignToDelete.contactsCount}</span>
              </div>
            </div>
            <p className="text-xs text-rose-600 font-medium leading-relaxed">
              This action cannot be undone from the UI.
            </p>
          </div>
        )}
      </Modal>
    </AppShell>
  );
}

export default function CampaignsPage() {
  return <SalesCampaignsContent />;
}
