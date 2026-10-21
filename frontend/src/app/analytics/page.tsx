"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { KpiCard } from "@/components/ui/kpi-card";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ChartCard } from "@/components/charts/chart-card";
import { BarChart, BarDatum } from "@/components/charts/bar-chart";
import {
  fetchAnalyticsOverview,
  AnalyticsOverviewResponse,
} from "@/services/analyticsService";
import {
  Users,
  PhoneCall,
  Mail,
  TrendingUp,
  RefreshCw,
  Send,
  AlertCircle,
  Inbox,
  CheckCircle2,
  Clock,
  ExternalLink,
  KanbanSquare,
  BarChart3,
  Flame,
} from "lucide-react";

import { useAppMode } from "@/contexts/AppModeContext";
import MarketingAnalyticsPage from "@/app/marketing/analytics/page";

export function SalesAnalyticsContent() {
  const [data, setData] = React.useState<AnalyticsOverviewResponse | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [timeRange, setTimeRange] = React.useState("all");
  const [activeTab, setActiveTab] = React.useState("campaigns");
  const [lastRefreshed, setLastRefreshed] = React.useState<Date | null>(null);

  const loadData = React.useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const overview = await fetchAnalyticsOverview();
      setData(overview);
      setLastRefreshed(new Date());
    } catch (err: unknown) {
      console.error("Failed to load analytics overview:", err);
      setError(
        err instanceof Error
          ? err.message
          : "An unexpected error occurred while communicating with the analytics API."
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadData();
  }, [loadData]);

  // Derived metrics with strict data integrity (zero distinguished from unavailable)
  const leads = data?.leads;
  const campaigns = data?.campaigns;
  const outreach = data?.outreach;
  const voice = data?.voice;
  const pipeline = data?.pipeline;
  const campaignPerformance = data?.campaign_performance || [];

  const qualificationRate =
    leads && leads.total_leads > 0
      ? `${Math.round((leads.qualified_leads / leads.total_leads) * 100)}%`
      : "—";

  const deliveryRate =
    outreach && outreach.sent > 0
      ? `${Math.round((outreach.delivered / outreach.sent) * 100)}%`
      : "—";

  const openRate =
    outreach && outreach.delivered > 0
      ? `${Math.round((outreach.opened / outreach.delivered) * 100)}%`
      : "—";

  const replyRate =
    outreach && outreach.delivered > 0
      ? `${Math.round((outreach.replied / outreach.delivered) * 100)}%`
      : "—";

  // Real chart data for Outreach Funnel (strictly actual counts)
  const outreachBarData: BarDatum[] = React.useMemo(() => {
    if (!outreach || outreach.total_outreach === 0) return [];
    return [
      { label: "Drafts", value: outreach.draft },
      { label: "Scheduled", value: outreach.scheduled },
      { label: "Sent", value: outreach.sent },
      { label: "Delivered", value: outreach.delivered },
      { label: "Opened", value: outreach.opened },
      { label: "Replied", value: outreach.replied },
      { label: "Bounced", value: outreach.bounced },
    ];
  }, [outreach]);

  // Real chart data for Campaign Enrollment (top campaigns by enrolled contacts)
  const campaignBarData: BarDatum[] = React.useMemo(() => {
    if (!campaignPerformance || campaignPerformance.length === 0) return [];
    return campaignPerformance.slice(0, 6).map((c) => ({
      label: c.name.length > 14 ? c.name.slice(0, 14) + "..." : c.name,
      value: c.enrolled_contacts_count,
      secondaryValue: c.sent_count,
    }));
  }, [campaignPerformance]);

  return (
    <AppShell>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-header">
              Analytics & Operations
            </h1>
            <Badge variant="neutral" className="text-[10px] font-mono border-slate-300">
              Live PostgreSQL Data
            </Badge>
          </div>
          <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
            Real tenant-scoped operational metrics derived from persisted campaigns, outreach, voice SDR sessions, and deals.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <div className="w-36">
            <Select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              className="h-9 text-xs"
              options={[
                { value: "all", label: "All Persisted Data" },
                { value: "30d", label: "Past 30 Days" },
                { value: "7d", label: "Past 7 Days" },
              ]}
            />
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={loadData}
            disabled={isLoading}
            className="h-9 text-xs flex items-center gap-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </Button>

          <Link href="/campaigns">
            <Button variant="primary" size="sm" className="h-9 text-xs flex items-center gap-1.5">
              <Send className="w-3.5 h-3.5" />
              <span>Campaigns</span>
            </Button>
          </Link>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-xs text-rose-700 flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold">Unable to fetch analytics records</p>
            <p className="mt-0.5 text-rose-600">{error}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={loadData} className="text-xs h-7">
            Retry
          </Button>
        </div>
      )}

      {/* Timestamp indicator */}
      {lastRefreshed && (
        <div className="text-[11px] text-slate-400 flex items-center gap-1.5">
          <Clock className="w-3 h-3 text-slate-400" />
          <span>Last synchronized: {lastRefreshed.toLocaleTimeString()}</span>
        </div>
      )}

      {/* Top Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1: Leads & Qualification */}
        <KpiCard
          title="Total Leads"
          subtitle="CRM prospect pool"
          value={leads ? String(leads.total_leads) : "0"}
          accentColor="peach"
          trend={{
            value: qualificationRate !== "—" ? `${qualificationRate} qualified` : "—",
            direction: leads && leads.qualified_leads > 0 ? "up" : "neutral",
            label: leads && leads.total_leads > 0 ? "Qualified rate" : "No leads yet",
          }}
          tooltipText="Actual leads stored in the database for your organization"
          icon={<Users className="w-4 h-4" />}
          breakdown={[
            { label: "Qualified", value: String(leads?.qualified_leads ?? 0) },
            {
              label: "New Status",
              value: String(leads?.status_breakdown?.new ?? 0),
            },
            {
              label: "In Sequence",
              value: String(campaigns?.enrolled_contacts ?? 0),
            },
          ]}
        />

        {/* KPI 2: Outreach Execution */}
        <KpiCard
          title="Outreach Sent"
          subtitle="Email dispatches"
          value={outreach ? String(outreach.sent) : "0"}
          accentColor="coral"
          trend={{
            value: deliveryRate !== "—" ? `${deliveryRate} delivery` : "—",
            direction: outreach && outreach.delivered > 0 ? "up" : "neutral",
            label: outreach && outreach.sent > 0 ? "Delivered rate" : "No messages sent",
          }}
          tooltipText="Messages verified as sent by Amazon SES or Resend (drafts and scheduled items strictly excluded)"
          icon={<Mail className="w-4 h-4" />}
          breakdown={[
            { label: "Delivered", value: String(outreach?.delivered ?? 0) },
            { label: "Opened", value: String(outreach?.opened ?? 0) },
            { label: "Replied", value: String(outreach?.replied ?? 0) },
            { label: "Bounces", value: String(outreach?.bounced ?? 0) },
          ]}
        />

        {/* KPI 3: Voice SDR Execution */}
        <KpiCard
          title="Voice Calls"
          subtitle="Retell SDR sessions"
          value={voice ? String(voice.completed_calls) : "0"}
          accentColor="navy"
          trend={{
            value:
              voice?.average_duration_seconds !== null && voice?.average_duration_seconds !== undefined
                ? `${Math.round(voice.average_duration_seconds)}s avg`
                : "—",
            direction: voice && voice.completed_calls > 0 ? "up" : "neutral",
            label: voice && voice.completed_calls > 0 ? "Avg call length" : "No calls logged",
          }}
          tooltipText="Outbound sales calls processed through Retell AI voice agents and webhooks"
          icon={<PhoneCall className="w-4 h-4" />}
          breakdown={[
            { label: "Total Logged", value: String(voice?.total_calls ?? 0) },
            { label: "Completed", value: String(voice?.completed_calls ?? 0) },
            {
              label: "Meetings Booked",
              value: String(voice?.outcome_breakdown?.MEETING_REQUESTED ?? 0),
            },
          ]}
        />

        {/* KPI 4: Deals & Pipeline */}
        <KpiCard
          title="Pipeline Value"
          subtitle="Genuine deal pipeline"
          value={
            pipeline && pipeline.total_pipeline_value > 0
              ? `$${Math.round(pipeline.total_pipeline_value).toLocaleString()}`
              : "$0"
          }
          accentColor="peach"
          trend={{
            value:
              pipeline && pipeline.won_pipeline_value > 0
                ? `$${Math.round(pipeline.won_pipeline_value).toLocaleString()} won`
                : "—",
            direction: pipeline && pipeline.won_deals > 0 ? "up" : "neutral",
            label: pipeline && pipeline.total_deals > 0 ? "Won revenue" : "No active deals",
          }}
          tooltipText="Aggregate value of real pipeline deals attached to your organization"
          icon={<TrendingUp className="w-4 h-4" />}
          breakdown={[
            { label: "Total Deals", value: String(pipeline?.total_deals ?? 0) },
            { label: "Open Deals", value: String(pipeline?.open_deals ?? 0) },
            { label: "Won Deals", value: String(pipeline?.won_deals ?? 0) },
          ]}
        />
      </div>

      {/* Outreach Funnel & Performance Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <ChartCard
          title="Outreach Pipeline Status"
          description="Real distribution of draft, scheduled, sent, delivered, and responded messages"
        >
          <BarChart
            data={outreachBarData}
            primaryColor="#d7525a"
            primaryLabel="Messages"
          />
        </ChartCard>

        <ChartCard
          title="Campaign Audience Enrollment"
          description="Enrolled contacts vs sent messages across your top active campaigns"
        >
          <BarChart
            data={campaignBarData}
            primaryColor="#091b29"
            secondaryColor="#d7525a"
            primaryLabel="Enrolled Contacts"
            secondaryLabel="Sent Outreach"
          />
        </ChartCard>
      </div>

      {/* Operational Tabs */}
      <Card>
        <CardHeader className="pb-3 border-b border-slate-100">
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList>
              <TabsTrigger value="campaigns">
                <span className="flex items-center gap-1.5">
                  <Send className="w-3.5 h-3.5" />
                  Campaign Performance ({campaignPerformance.length})
                </span>
              </TabsTrigger>
              <TabsTrigger value="voice">
                <span className="flex items-center gap-1.5">
                  <PhoneCall className="w-3.5 h-3.5" />
                  Voice SDR Outcomes
                </span>
              </TabsTrigger>
              <TabsTrigger value="outreach">
                <span className="flex items-center gap-1.5">
                  <Mail className="w-3.5 h-3.5" />
                  Outreach Channels
                </span>
              </TabsTrigger>
              <TabsTrigger value="leads">
                <span className="flex items-center gap-1.5">
                  <Users className="w-3.5 h-3.5" />
                  Lead Segmentation
                </span>
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </CardHeader>

        <CardContent className="pt-4">
          {/* TAB 1: Campaign Performance Table */}
          {activeTab === "campaigns" && (
            <div className="space-y-4">
              {campaignPerformance.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 p-12 text-center flex flex-col items-center justify-center space-y-2.5">
                  <div className="w-10 h-10 rounded-full bg-white border border-slate-200 flex items-center justify-center text-slate-400 shadow-xs">
                    <Send className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-header">
                      No Campaigns Recorded
                    </h4>
                    <p className="text-xs text-slate-500 max-w-md mt-1">
                      Create and activate campaigns in the Workflow Builder to start tracking sequence delivery and response metrics.
                    </p>
                  </div>
                  <div className="pt-2">
                    <Link href="/campaigns">
                      <Button variant="primary" size="sm" className="text-xs">
                        Create Your First Campaign
                      </Button>
                    </Link>
                  </div>
                </div>
              ) : (
                <div className="rounded-lg border border-slate-200 overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-slate-50/75">
                        <TableHead className="font-semibold text-slate-700">Campaign</TableHead>
                        <TableHead className="font-semibold text-slate-700">Type</TableHead>
                        <TableHead className="font-semibold text-slate-700">Status</TableHead>
                        <TableHead className="font-semibold text-slate-700 text-right">Enrolled</TableHead>
                        <TableHead className="font-semibold text-slate-700 text-right">Sent</TableHead>
                        <TableHead className="font-semibold text-slate-700 text-right">Delivered</TableHead>
                        <TableHead className="font-semibold text-slate-700 text-right">Opened</TableHead>
                        <TableHead className="font-semibold text-slate-700 text-right">Replied</TableHead>
                        <TableHead className="font-semibold text-slate-700 text-right">Bounced</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {campaignPerformance.map((camp) => (
                        <TableRow key={camp.id} className="hover:bg-slate-50/50 transition-colors">
                          <TableCell className="font-medium text-header text-xs">
                            {camp.name}
                          </TableCell>
                          <TableCell className="text-xs text-slate-600">
                            <Badge variant="neutral" className="text-[10px] font-normal">
                              {camp.type.replace(/_/g, " ")}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant={
                                camp.status === "active"
                                  ? "coral"
                                  : camp.status === "completed"
                                  ? "success"
                                  : camp.status === "paused"
                                  ? "warning"
                                  : "neutral"
                              }
                              className="text-[10px] capitalize"
                            >
                              {camp.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right text-xs font-mono">
                            {camp.enrolled_contacts_count}
                          </TableCell>
                          <TableCell className="text-right text-xs font-mono font-semibold text-slate-800">
                            {camp.sent_count}
                          </TableCell>
                          <TableCell className="text-right text-xs font-mono text-emerald-600">
                            {camp.delivered_count}
                          </TableCell>
                          <TableCell className="text-right text-xs font-mono text-blue-600">
                            {camp.opened_count}
                          </TableCell>
                          <TableCell className="text-right text-xs font-mono font-bold text-agile-red">
                            {camp.replied_count}
                          </TableCell>
                          <TableCell className="text-right text-xs font-mono text-rose-500">
                            {camp.bounced_count}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: Voice SDR Outcomes */}
          {activeTab === "voice" && (
            <div className="space-y-4">
              {voice && voice.total_calls > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {Object.entries(voice.outcome_breakdown).map(([outcome, count]) => (
                    <div
                      key={outcome}
                      className="p-4 rounded-lg border border-slate-200 bg-white shadow-xs flex items-center justify-between"
                    >
                      <div>
                        <p className="text-xs font-semibold text-header">
                          {outcome.replace(/_/g, " ")}
                        </p>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          Webhook Outcome
                        </p>
                      </div>
                      <span className="text-lg font-bold font-mono text-slate-800">
                        {count}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 p-12 text-center flex flex-col items-center justify-center space-y-2">
                  <div className="w-10 h-10 rounded-full bg-white border border-slate-200 flex items-center justify-center text-slate-400 shadow-xs">
                    <PhoneCall className="w-5 h-5" />
                  </div>
                  <h4 className="text-sm font-semibold text-header">
                    No Voice Calls Logged
                  </h4>
                  <p className="text-xs text-slate-500 max-w-md">
                    Outbound calls placed through Retell AI and their webhook outcomes will appear here automatically.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: Outreach Channel Breakdown */}
          {activeTab === "outreach" && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
                <div className="p-4 rounded-lg border border-slate-200 bg-white">
                  <span className="text-xs text-slate-500">Drafts Pending Review</span>
                  <p className="text-xl font-bold font-mono text-slate-700 mt-1">
                    {outreach?.draft ?? 0}
                  </p>
                  <p className="text-[10px] text-slate-400 mt-1">Not counted as sent</p>
                </div>

                <div className="p-4 rounded-lg border border-slate-200 bg-white">
                  <span className="text-xs text-slate-500">Scheduled In Queue</span>
                  <p className="text-xl font-bold font-mono text-blue-600 mt-1">
                    {outreach?.scheduled ?? 0}
                  </p>
                  <p className="text-[10px] text-slate-400 mt-1">Awaiting dispatch time</p>
                </div>

                <div className="p-4 rounded-lg border border-slate-200 bg-white">
                  <span className="text-xs text-slate-500">Sent Out</span>
                  <p className="text-xl font-bold font-mono text-slate-900 mt-1">
                    {outreach?.sent ?? 0}
                  </p>
                  <p className="text-[10px] text-slate-400 mt-1">Provider delivered</p>
                </div>

                <div className="p-4 rounded-lg border border-slate-200 bg-white">
                  <span className="text-xs text-slate-500">Failed / Rejected</span>
                  <p className="text-xl font-bold font-mono text-rose-600 mt-1">
                    {outreach?.failed ?? 0}
                  </p>
                  <p className="text-[10px] text-slate-400 mt-1">Execution error or block</p>
                </div>
              </div>

              {outreach && Object.keys(outreach.channel_breakdown).length > 0 && (
                <div className="rounded-lg border border-slate-200 p-4 bg-white mt-4">
                  <h4 className="text-xs font-bold text-header uppercase tracking-wider mb-3">
                    Active Channels
                  </h4>
                  <div className="flex flex-wrap gap-3">
                    {Object.entries(outreach.channel_breakdown).map(([ch, count]) => (
                      <div
                        key={ch}
                        className="flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50/50"
                      >
                        <Mail className="w-3.5 h-3.5 text-slate-500" />
                        <span className="text-xs font-medium text-slate-700 capitalize">{ch}</span>
                        <Badge variant="neutral" className="text-[10px] font-mono">
                          {count}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 4: Lead Segmentation */}
          {activeTab === "leads" && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Status Breakdown */}
                <div className="rounded-lg border border-slate-200 p-4 bg-white space-y-3">
                  <h4 className="text-xs font-bold text-header uppercase tracking-wider">
                    Lead Status Breakdown
                  </h4>
                  {leads && Object.keys(leads.status_breakdown).length > 0 ? (
                    <div className="space-y-2">
                      {Object.entries(leads.status_breakdown).map(([statusName, count]) => (
                        <div
                          key={statusName}
                          className="flex items-center justify-between py-1.5 border-b border-slate-100 last:border-0 text-xs"
                        >
                          <span className="text-slate-600 capitalize">{statusName}</span>
                          <span className="font-mono font-semibold text-slate-800">{count}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-400">No lead status data available.</p>
                  )}
                </div>

                {/* Temperature Breakdown */}
                <div className="rounded-lg border border-slate-200 p-4 bg-white space-y-3">
                  <h4 className="text-xs font-bold text-header uppercase tracking-wider">
                    Lead Temperature Breakdown
                  </h4>
                  {leads && Object.keys(leads.temperature_breakdown).length > 0 ? (
                    <div className="space-y-2">
                      {Object.entries(leads.temperature_breakdown).map(([temp, count]) => (
                        <div
                          key={temp}
                          className="flex items-center justify-between py-1.5 border-b border-slate-100 last:border-0 text-xs"
                        >
                          <span className="text-slate-600 capitalize flex items-center gap-1.5">
                            <Flame className="w-3 h-3 text-agile-red" />
                            {temp}
                          </span>
                          <span className="font-mono font-semibold text-slate-800">{count}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-400">No temperature segmentation recorded.</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </AppShell>
  );
}

export default function AnalyticsPage() {
  const { mode } = useAppMode();
  if (mode === "marketing") {
    return <MarketingAnalyticsPage />;
  }
  return <SalesAnalyticsContent />;
}
