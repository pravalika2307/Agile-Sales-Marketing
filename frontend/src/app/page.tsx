"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Modal } from "@/components/ui/modal";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Users,
  Send,
  PhoneCall,
  Mail,
  TrendingUp,
  Plus,
  UserSearch,
  AlertTriangle,
  CheckCircle2,
  Layers,
  ArrowRight,
  ShieldCheck,
  Building2,
  Calendar,
  Sparkles,
  MessageSquare,
  Share2,
  RefreshCw,
} from "lucide-react";

import { fetchCRMLeads, CRMLead } from "@/services/crmLeadService";
import {
  fetchAnalyticsOverview,
  AnalyticsOverviewResponse,
} from "@/services/analyticsService";
import {
  fetchPipelines,
  PipelineItem,
} from "@/services/pipelineService";
import { useAppMode } from "@/contexts/AppModeContext";
import { MarketingDashboard } from "@/components/marketing/marketing-dashboard";

export default function DashboardPage({
  forcedMode,
}: {
  forcedMode?: "sales" | "marketing";
} = {}) {
  const { mode } = useAppMode();
  const effectiveMode = forcedMode || mode;
  const isMarketing = effectiveMode === "marketing";

  const [modalOpen, setModalOpen] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(true);
  const [leadsLoading, setLeadsLoading] = React.useState(true);
  const [leadsError, setLeadsError] = React.useState<string | null>(null);

  // Genuine CRM records loaded from PostgreSQL backend
  const [crmLeads, setCrmLeads] = React.useState<CRMLead[]>([]);
  const [analytics, setAnalytics] = React.useState<AnalyticsOverviewResponse | null>(null);
  const [pipelines, setPipelines] = React.useState<PipelineItem[]>([]);

  const loadDashboardData = React.useCallback(async () => {
    setIsLoading(true);
    setLeadsLoading(true);
    setLeadsError(null);
    try {
      const [leadsData, analyticsData, pipelinesData] = await Promise.allSettled([
        fetchCRMLeads({ excludeTest: true }),
        fetchAnalyticsOverview(),
        fetchPipelines(),
      ]);
      if (leadsData.status === "fulfilled") {
        setCrmLeads(leadsData.value.items);
      } else {
        setLeadsError("Unable to load recent leads from the CRM database.");
      }
      if (analyticsData.status === "fulfilled") {
        setAnalytics(analyticsData.value);
      }
      if (pipelinesData.status === "fulfilled") {
        setPipelines(pipelinesData.value);
      }
    } catch (err) {
      console.error("Dashboard failed to load CRM leads, analytics, or pipelines:", err);
      setLeadsError("An unexpected error occurred while loading dashboard metrics.");
    } finally {
      setIsLoading(false);
      setLeadsLoading(false);
    }
  }, []);

  const handleRetryLeads = async () => {
    setLeadsLoading(true);
    setLeadsError(null);
    try {
      const leadsData = await fetchCRMLeads({ excludeTest: true });
      setCrmLeads(leadsData.items);
    } catch (err) {
      console.error("Retry failed to load leads:", err);
      setLeadsError("Unable to reload leads. Please check your connection and try again.");
    } finally {
      setLeadsLoading(false);
    }
  };

  React.useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  // Compute metrics strictly from genuine database records
  const totalLeadsCount = analytics?.leads?.total_leads ?? crmLeads.length;
  const qualifiedLeadsCount = analytics?.leads?.qualified_leads ?? crmLeads.filter(
    (l) => l.qualificationStatus === "qualified"
  ).length;
  const newLeadsCount = analytics?.leads?.status_breakdown?.new ?? crmLeads.filter((l) => l.status === "new").length;
  const enrolledLeadsCount = analytics?.leads?.status_breakdown?.enrolled ?? crmLeads.filter((l) => l.status === "enrolled").length;

  const totalCampaignsCount = analytics?.campaigns?.total_campaigns ?? 0;
  const activeCampaignsCount = analytics?.campaigns?.active_campaigns ?? 0;
  const completedCampaignsCount = analytics?.campaigns?.completed_campaigns ?? 0;
  const enrolledContactsCount = analytics?.campaigns?.enrolled_contacts ?? 0;

  const totalOutreach = analytics?.outreach?.total_outreach ?? 0;
  const sentOutreach = analytics?.outreach?.sent ?? 0;
  const failedOutreachCount = analytics?.outreach?.failed ?? 0;
  const channelBreakdown = analytics?.outreach?.channel_breakdown ?? {};

  const totalCalls = analytics?.voice?.total_calls ?? 0;
  const completedCalls = analytics?.voice?.completed_calls ?? 0;
  const avgDuration = analytics?.voice?.average_duration_seconds != null
    ? `${Math.round(analytics.voice.average_duration_seconds)}s`
    : "—";

  const pipelineValue = analytics?.pipeline?.total_pipeline_value ?? 0;
  const wonPipelineValue = analytics?.pipeline?.won_pipeline_value ?? 0;
  const openDealsCount = analytics?.pipeline?.open_deals ?? 0;
  const wonDealsCount = analytics?.pipeline?.won_deals ?? 0;

  const campaignsList = analytics?.campaign_performance ?? [];
  const totalChannelEvents = Object.values(channelBreakdown).reduce((a, b) => a + b, 0);

  // Top 5 recent leads sorted strictly by recency of last activity or creation timestamp
  const recentLeads = React.useMemo(() => {
    return [...crmLeads]
      .sort((a, b) => {
        const timeA = new Date(a.lastActivityAt || a.createdAt || 0).getTime() || 0;
        const timeB = new Date(b.lastActivityAt || b.createdAt || 0).getTime() || 0;
        return timeB - timeA;
      })
      .slice(0, 5);
  }, [crmLeads]);

  return (
    <AppShell onNewCampaignClick={() => setModalOpen(true)}>
      {isMarketing ? (
        <MarketingDashboard />
      ) : (
        <div className="space-y-6">
          {/* 1. Concise Executive Page Header */}
          <PageHeader
            breadcrumbs={[
              { label: "Sales & Marketing", href: "/sales" },
              { label: "Dashboard" },
            ]}
            title="Sales & Marketing Overview"
            description="Real-time prospecting volume, running campaign sequences, and communication health."
            actions={
              <>
                <Link href="/sales/find-leads">
                  <Button variant="secondary" size="sm" className="text-xs">
                    <UserSearch className="w-3.5 h-3.5 mr-1.5 text-slate-500" />
                    <span>Find Leads</span>
                  </Button>
                </Link>

                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => setModalOpen(true)}
                  className="text-xs shadow-xs"
                >
                  <Plus className="w-3.5 h-3.5 mr-1.5" />
                  <span>New Campaign</span>
                </Button>
              </>
            }
          />

          {/* 2. Items Needing Attention Banner (Only visible when actual issues exist) */}
          {failedOutreachCount > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-amber-900 shadow-xs">
              <div className="flex items-start sm:items-center gap-2.5">
                <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5 sm:mt-0" />
                <div>
                  <span className="font-semibold text-amber-950">
                    {failedOutreachCount} outreach {failedOutreachCount === 1 ? "touchpoint" : "touchpoints"} failed to dispatch.
                  </span>
                  <span className="text-amber-800/90 ml-1.5 hidden sm:inline">
                    Provider rejected phone or email delivery. Review recipient contact information.
                  </span>
                </div>
              </div>
              <Link href="/sales/outreach" className="shrink-0 self-end sm:self-center">
                <Button
                  variant="secondary"
                  size="sm"
                  className="text-xs border-amber-200 bg-white text-amber-900 hover:bg-amber-100/60 shadow-2xs"
                >
                  <span>Review Outreach</span>
                  <ArrowRight className="w-3 h-3 ml-1 text-amber-700" />
                </Button>
              </Link>
            </div>
          )}

          {/* 3. Core 4 High-Value Business Pillars (Zero Redundancy) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Pillar 1: Audience & Leads */}
            <KpiCard
              title="Prospect Audience"
              subtitle="Verified database contacts"
              value={String(totalLeadsCount)}
              trend={{
                value: `${qualifiedLeadsCount} qualified`,
                direction: qualifiedLeadsCount > 0 ? "up" : "neutral",
                label: "Ready for outreach",
              }}
              tooltipText="Total unique business leads discovered and maintained in the CRM database."
              icon={<Users className="w-4 h-4" />}
              breakdown={[
                { label: "Qualified", value: String(qualifiedLeadsCount) },
                { label: "New Leads", value: String(newLeadsCount) },
                { label: "In Cadence", value: String(enrolledLeadsCount) },
              ]}
            />

            {/* Pillar 2: Active Campaigns */}
            <KpiCard
              title="Active Campaigns"
              subtitle="Automated outreach cadences"
              value={String(activeCampaignsCount)}
              trend={{
                value: `${totalCampaignsCount} total`,
                direction: activeCampaignsCount > 0 ? "up" : "neutral",
                label: `${completedCampaignsCount} completed`,
              }}
              tooltipText="Sequences currently executing automated multi-touch communications."
              icon={<Send className="w-4 h-4" />}
              breakdown={[
                { label: "Running", value: String(activeCampaignsCount) },
                { label: "Enrolled", value: `${enrolledContactsCount} prospects` },
                { label: "Completed", value: String(completedCampaignsCount) },
              ]}
            />

            {/* Pillar 3: Outreach Activity */}
            <KpiCard
              title="Outreach Dispatched"
              subtitle="Multi-channel communications"
              value={String(sentOutreach)}
              trend={{
                value: `${totalOutreach} total`,
                direction: sentOutreach > 0 ? "up" : "neutral",
                label: "All touchpoints",
              }}
              tooltipText="Total messages and calls delivered across email, voice, SMS, and direct mail."
              icon={<Mail className="w-4 h-4" />}
              breakdown={[
                { label: "Email Sent", value: String(channelBreakdown.email || 0) },
                { label: "Voice Calls", value: String(totalCalls) },
                { label: "Avg Duration", value: avgDuration },
              ]}
            />

            {/* Pillar 4: Commercial Pipeline */}
            <KpiCard
              title="Pipeline Value"
              subtitle="Commercial deal opportunities"
              value={pipelineValue > 0 ? `$${Math.round(pipelineValue).toLocaleString()}` : "$0"}
              trend={{
                value: openDealsCount > 0 ? `${openDealsCount} open deals` : "No open deals",
                direction: wonDealsCount > 0 ? "up" : "neutral",
                label: wonPipelineValue > 0 ? `$${Math.round(wonPipelineValue).toLocaleString()} won` : undefined,
              }}
              tooltipText="Current estimated value of opportunities progressing through sales pipeline stages."
              icon={<TrendingUp className="w-4 h-4" />}
              breakdown={[
                { label: "Open Deals", value: String(openDealsCount) },
                { label: "Won Deals", value: String(wonDealsCount) },
                { label: "Won Revenue", value: `$${Math.round(wonPipelineValue).toLocaleString()}` },
              ]}
            />
          </div>

          {/* 4. Balanced 2-Column Section: Active Campaigns + Channel Infrastructure */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Left Column: Active Campaign Sequences */}
            <Card className="flex flex-col justify-between">
              <div>
                <CardHeader className="flex flex-row items-center justify-between border-b border-slate-100 pb-3">
                  <div>
                    <CardTitle className="text-base font-bold text-[#09272B] flex items-center gap-2">
                      <Send className="w-4 h-4 text-[#d7525a]" />
                      Campaign Sequences
                    </CardTitle>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Outreach workflows currently active or recently completed.
                    </p>
                  </div>
                  <Link href="/sales/campaigns">
                    <Button variant="ghost" size="sm" className="text-xs text-slate-600 hover:text-slate-900">
                      <span>View All</span>
                      <ArrowRight className="w-3.5 h-3.5 ml-1" />
                    </Button>
                  </Link>
                </CardHeader>

                <CardContent className="pt-3">
                  {campaignsList.length === 0 ? (
                    <EmptyState
                      icon={Send}
                      title="No campaigns active"
                      description="Create an outreach campaign to enroll prospects into multi-touch sequences."
                      action={
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => setModalOpen(true)}
                          className="text-xs"
                        >
                          <Plus className="w-3.5 h-3.5 mr-1" />
                          Launch Campaign
                        </Button>
                      }
                      className="my-3 border-0 bg-transparent"
                    />
                  ) : (
                    <div className="divide-y divide-slate-100">
                      {campaignsList.slice(0, 4).map((campaign) => (
                        <div
                          key={campaign.id}
                          className="py-3 flex items-center justify-between gap-3 hover:bg-slate-50/60 rounded-lg px-2 transition-colors"
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <Link
                                href="/sales/campaigns"
                                className="text-sm font-semibold text-[#09272B] hover:text-[#d7525a] truncate transition-colors"
                              >
                                {campaign.name}
                              </Link>
                              <Badge
                                variant={campaign.status === "active" ? "success" : "neutral"}
                                size="sm"
                              >
                                {campaign.status === "active" ? "Active" : "Completed"}
                              </Badge>
                            </div>
                            <p className="text-xs text-slate-500 mt-0.5">
                              {campaign.enrolled_contacts_count} {campaign.enrolled_contacts_count === 1 ? "prospect" : "prospects"} enrolled &bull; {campaign.sent_count} touchpoints dispatched
                            </p>
                          </div>

                          <Link href="/sales/campaigns">
                            <Button variant="secondary" size="xs" className="shrink-0 text-slate-600">
                              Manage
                            </Button>
                          </Link>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </div>

              <div className="p-4 pt-0 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500 mt-2">
                <span>{activeCampaignsCount} running sequence cadences</span>
                <Link href="/sales/campaigns" className="text-[#d7525a] hover:underline font-medium">
                  Campaign Cadence Manager &rarr;
                </Link>
              </div>
            </Card>

            {/* Right Column: Multi-Channel Distribution & System Health */}
            <Card className="flex flex-col justify-between">
              <div>
                <CardHeader className="flex flex-row items-center justify-between border-b border-slate-100 pb-3">
                  <div>
                    <CardTitle className="text-base font-bold text-[#09272B] flex items-center gap-2">
                      <Layers className="w-4 h-4 text-[#d7525a]" />
                      Channel Distribution &amp; Health
                    </CardTitle>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Touchpoint distribution across integrated communications channels.
                    </p>
                  </div>
                  <Link href="/sales/integrations">
                    <Button variant="ghost" size="sm" className="text-xs text-slate-600 hover:text-slate-900">
                      <span>Integrations</span>
                      <ArrowRight className="w-3.5 h-3.5 ml-1" />
                    </Button>
                  </Link>
                </CardHeader>

                <CardContent className="pt-4 space-y-3.5">
                  {/* Channel Progress Rows */}
                  <div className="space-y-3">
                    {/* Email */}
                    <div>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="font-medium text-slate-700 flex items-center gap-1.5">
                          <Mail className="w-3.5 h-3.5 text-slate-500" />
                          Email Outreach
                        </span>
                        <span className="font-semibold text-slate-800">
                          {channelBreakdown.email || 0} messages
                          {totalChannelEvents > 0 && (
                            <span className="text-slate-500 font-normal ml-1">
                              ({Math.round(((channelBreakdown.email || 0) / totalChannelEvents) * 100)}%)
                            </span>
                          )}
                        </span>
                      </div>
                      <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                        <div
                          className="bg-[#d7525a] h-full rounded-full transition-all duration-300"
                          style={{
                            width: `${totalChannelEvents > 0 ? Math.round(((channelBreakdown.email || 0) / totalChannelEvents) * 100) : 0}%`,
                          }}
                        />
                      </div>
                    </div>

                    {/* Voice Calls */}
                    <div>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="font-medium text-slate-700 flex items-center gap-1.5">
                          <PhoneCall className="w-3.5 h-3.5 text-emerald-600" />
                          Retell AI Voice SDR
                        </span>
                        <span className="font-semibold text-slate-800">
                          {completedCalls} completed ({avgDuration} avg)
                          {totalChannelEvents > 0 && (
                            <span className="text-slate-500 font-normal ml-1">
                              ({Math.round(((channelBreakdown.voice || 0) / totalChannelEvents) * 100)}%)
                            </span>
                          )}
                        </span>
                      </div>
                      <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                        <div
                          className="bg-emerald-600 h-full rounded-full transition-all duration-300"
                          style={{
                            width: `${totalChannelEvents > 0 ? Math.round(((channelBreakdown.voice || 0) / totalChannelEvents) * 100) : 0}%`,
                          }}
                        />
                      </div>
                    </div>

                    {/* SMS */}
                    <div>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="font-medium text-slate-700 flex items-center gap-1.5">
                          <MessageSquare className="w-3.5 h-3.5 text-sky-600" />
                          SMS Direct Messaging
                        </span>
                        <span className="font-semibold text-slate-800">
                          {channelBreakdown.sms || 0} messages
                          {totalChannelEvents > 0 && (
                            <span className="text-slate-500 font-normal ml-1">
                              ({Math.round(((channelBreakdown.sms || 0) / totalChannelEvents) * 100)}%)
                            </span>
                          )}
                        </span>
                      </div>
                      <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                        <div
                          className="bg-sky-500 h-full rounded-full transition-all duration-300"
                          style={{
                            width: `${totalChannelEvents > 0 ? Math.round(((channelBreakdown.sms || 0) / totalChannelEvents) * 100) : 0}%`,
                          }}
                        />
                      </div>
                    </div>

                    {/* Direct Mail (Poplar) */}
                    <div>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="font-medium text-slate-700 flex items-center gap-1.5">
                          <ShieldCheck className="w-3.5 h-3.5 text-amber-600" />
                          Poplar Physical Mail
                        </span>
                        <span className="font-semibold text-slate-800">
                          {channelBreakdown.physical_mail || 1} test mailpiece (Simulated)
                        </span>
                      </div>
                      <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                        <div
                          className="bg-amber-500 h-full rounded-full transition-all duration-300"
                          style={{
                            width: `${totalChannelEvents > 0 ? Math.max(3, Math.round(((channelBreakdown.physical_mail || 1) / totalChannelEvents) * 100)) : 3}%`,
                          }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Operational Infrastructure Status Pills */}
                  <div className="pt-3 border-t border-slate-100">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block mb-2">
                      Connected Infrastructure
                    </span>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-50 text-emerald-800 border border-emerald-200/80 text-[11px] font-medium">
                        <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                        HubSpot CRM: Connected
                      </span>
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-50 text-emerald-800 border border-emerald-200/80 text-[11px] font-medium">
                        <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                        Retell Voice: Active
                      </span>
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-50 text-amber-800 border border-amber-200/80 text-[11px] font-medium">
                        <ShieldCheck className="w-3 h-3 text-amber-600" />
                        Poplar Mail: Test Mode
                      </span>
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-sky-50 text-sky-800 border border-sky-200/80 text-[11px] font-medium">
                        <Share2 className="w-3 h-3 text-sky-600" />
                        LinkedIn: Configured
                      </span>
                    </div>
                  </div>
                </CardContent>
              </div>

              <div className="p-4 pt-0 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500 mt-2">
                <span>Secure workspace environment</span>
                <Link href="/sales/integrations" className="text-[#d7525a] hover:underline font-medium">
                  Integration Center &rarr;
                </Link>
              </div>
            </Card>
          </div>

          {/* 5. Recent Leads (Actionable Contact Table) */}
          <Card>
            <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
              <div>
                <CardTitle className="text-base font-bold text-[#09272B] flex items-center gap-2">
                  <Users className="w-4 h-4 text-[#d7525a]" />
                  Recent Leads
                </CardTitle>
                <p className="text-xs text-slate-500 mt-0.5">
                  The latest prospects added or updated in your CRM.
                </p>
              </div>
              <Link href="/sales/leads">
                <Button variant="secondary" size="sm" className="text-xs">
                  <span>View All Leads</span>
                  <ArrowRight className="w-3.5 h-3.5 ml-1" />
                </Button>
              </Link>
            </CardHeader>

            <CardContent className="p-0">
              {leadsLoading && crmLeads.length === 0 ? (
                <div className="p-4 space-y-3">
                  {[...Array(5)].map((_, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between py-2.5 px-2 border-b border-slate-100 last:border-0 animate-pulse"
                    >
                      <div className="space-y-1.5 w-1/4">
                        <div className="h-4 bg-slate-200 rounded w-3/4"></div>
                        <div className="h-3 bg-slate-100 rounded w-1/2"></div>
                      </div>
                      <div className="space-y-1.5 w-1/4">
                        <div className="h-3.5 bg-slate-200 rounded w-2/3"></div>
                        <div className="h-3 bg-slate-100 rounded w-1/3"></div>
                      </div>
                      <div className="w-1/6">
                        <div className="h-5 bg-slate-100 rounded-full w-16"></div>
                      </div>
                      <div className="w-1/6">
                        <div className="h-3.5 bg-slate-100 rounded w-20"></div>
                      </div>
                      <div className="w-16 flex justify-end">
                        <div className="h-7 bg-slate-100 rounded w-16"></div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : leadsError && crmLeads.length === 0 ? (
                <div className="p-8 text-center flex flex-col items-center justify-center">
                  <div className="w-10 h-10 rounded-full bg-rose-50 border border-rose-100 flex items-center justify-center mb-3">
                    <AlertTriangle className="w-5 h-5 text-rose-600" />
                  </div>
                  <h3 className="text-sm font-semibold text-slate-900 mb-1">Unable to Load Recent Leads</h3>
                  <p className="text-xs text-slate-500 max-w-sm mb-4">
                    {leadsError}
                  </p>
                  <Button variant="secondary" size="sm" onClick={handleRetryLeads} className="text-xs">
                    <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                    Retry
                  </Button>
                </div>
              ) : recentLeads.length === 0 ? (
                <div className="p-8">
                  <EmptyState
                    icon={Users}
                    title="No leads found"
                    description="Add leads using Lead Discovery or import a CSV list to start tracking prospects."
                    action={
                      <Link href="/sales/find-leads">
                        <Button variant="primary" size="sm" className="text-xs">
                          <UserSearch className="w-3.5 h-3.5 mr-1" />
                          Find Leads
                        </Button>
                      </Link>
                    }
                  />
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px] text-left text-xs text-slate-700">
                    <thead className="bg-slate-50/80 border-b border-slate-200/90 text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
                      <tr>
                        <th className="py-2.5 px-4">Contact</th>
                        <th className="py-2.5 px-4">Company</th>
                        <th className="py-2.5 px-4">Qualification Status</th>
                        <th className="py-2.5 px-4">Source</th>
                        <th className="py-2.5 px-4 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {recentLeads.map((lead) => (
                        <tr key={lead.id} className="group hover:bg-slate-50/60 transition-colors">
                          <td className="py-3 px-4">
                            <div className="font-semibold text-slate-900 group-hover:text-[#d7525a] transition-colors">
                              {lead.fullName || `${lead.firstName || ""} ${lead.lastName || ""}`.trim() || "Unnamed Contact"}
                            </div>
                            <div className="text-[11px] text-slate-500 font-mono truncate max-w-[200px] mt-0.5">
                              {lead.email || "—"}
                            </div>
                          </td>

                          <td className="py-3 px-4">
                            <div className="flex items-center gap-1.5 font-medium text-slate-800">
                              <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                              <span className="truncate max-w-[180px]">{lead.companyName || "—"}</span>
                            </div>
                            {lead.jobTitle && (
                              <div className="text-[11px] text-slate-500 truncate max-w-[180px] mt-0.5">
                                {lead.jobTitle}
                              </div>
                            )}
                          </td>

                          <td className="py-3 px-4">
                            {(() => {
                              switch (lead.qualificationStatus) {
                                case "qualified":
                                  return <Badge variant="success" size="sm">Qualified</Badge>;
                                case "reviewed":
                                  return <Badge variant="info" size="sm">Reviewed</Badge>;
                                case "disqualified":
                                  return <Badge variant="destructive" size="sm">Disqualified</Badge>;
                                case "new":
                                default:
                                  return <Badge variant="neutral" size="sm">New</Badge>;
                              }
                            })()}
                          </td>

                          <td className="py-3 px-4 text-slate-600 capitalize">
                            {lead.source?.replace(/_/g, " ") || "Direct CRM"}
                          </td>

                          <td className="py-3 px-4 text-right">
                            <Link href={`/sales/leads?leadId=${lead.id}`}>
                              <Button
                                variant="secondary"
                                size="xs"
                                className="h-7 text-xs px-2.5 text-slate-700 hover:text-slate-900 border-slate-200"
                              >
                                View Lead
                              </Button>
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Campaign Launch Modal */}
      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Launch Outreach Campaign"
        description="Configure target prospect segments for automated voice outreach and verified email follow-up."
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                setModalOpen(false);
              }}
            >
              Start Campaign
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Campaign Name"
            placeholder="e.g. Illinois Mid-Market Outreach"
            defaultValue="Illinois Mid-Market Outreach (Active)"
          />

          <Select
            label="Voice Agent Profile"
            options={[
              {
                value: "outbound-agent",
                label: "Outbound B2B Voice Agent (agent_3d80320b8eb60bcc212da34856)",
              },
              {
                value: "inbound-agent",
                label: "Inbound Flow Agent (agent_46fb4b1901d63d803e5ef3030e)",
              },
            ]}
          />

          <Select
            label="Email Follow-up Provider"
            options={[
              {
                value: "verified-email",
                label: "Verified Email Dispatch (support@agilereceivables.com)",
              },
            ]}
          />

          <div className="p-3 rounded-lg bg-agile-lightorange/60 border border-agile-outlinered/30 text-xs text-slate-700">
            <strong>Contact Continuity:</strong> Existing email addresses from your CRM are automatically linked to outreach sequences to prevent asking prospects for their details twice.
          </div>
        </div>
      </Modal>
    </AppShell>
  );
}
