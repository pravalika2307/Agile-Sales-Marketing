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
import { OutreachDetailDrawer } from "@/components/outreach/outreach-detail-drawer";
import {
  OutreachItem,
  OutreachChannel,
  OutreachStatus,
  OUTREACH_CHANNEL_LABELS,
  OUTREACH_STATUS_LABELS,
  OUTREACH_EVENT_LABELS,
  fetchOutreachRecords,
  filterOutreach,
  computeOutreachMetrics,
  getOutreachProvenance,
  OutreachFilterOptions,
} from "@/services/outreachService";
import {
  Search,
  RotateCcw,
  Mail,
  PhoneCall,
  MessageSquare,
  Share2,
  CheckCircle2,
  Clock,
  Radio,
  AlertCircle,
  Eye,
  Send,
  Layers,
  ArrowRight,
  User,
  Building2,
  Calendar,
} from "lucide-react";

export default function OutreachPage() {
  // Live backend outreach records fetched from real API
  const [records, setRecords] = React.useState<OutreachItem[]>([]);

  // Search & Filter state
  const [searchQuery, setSearchQuery] = React.useState("");
  const [channelFilter, setChannelFilter] = React.useState("ALL");
  const [statusFilter, setStatusFilter] = React.useState("ALL");
  const [campaignFilter, setCampaignFilter] = React.useState("ALL");

  // Detail Drawer state
  const [inspectedOutreach, setInspectedOutreach] = React.useState<OutreachItem | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = React.useState(false);

  // Pagination & Loading state
  const [currentPage, setCurrentPage] = React.useState(1);
  const [pageSize] = React.useState(10);
  const [isLoading, setIsLoading] = React.useState(true);
  const [hasError, setHasError] = React.useState(false);

  // Live dynamic fetch from backend API
  const loadRecords = React.useCallback(async () => {
    setIsLoading(true);
    setHasError(false);
    try {
      const data = await fetchOutreachRecords();
      setRecords(data);
    } catch (err) {
      console.error("Failed to fetch live outreach records from backend API:", err);
      setHasError(true);
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  // Derive unique campaign options from real records
  const uniqueCampaigns = React.useMemo(() => {
    const map = new Map<string, string>();
    records.forEach((r) => {
      if (r.campaignId && r.campaignName) {
        map.set(r.campaignId, r.campaignName);
      }
    });
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [records]);

  // Client-side filtering on loaded real records
  const filteredRecords = React.useMemo(() => {

    const criteria: OutreachFilterOptions = {
      searchQuery,
      channel: channelFilter !== "ALL" ? channelFilter : undefined,
      status: statusFilter !== "ALL" ? statusFilter : undefined,
      campaignId: campaignFilter !== "ALL" ? campaignFilter : undefined,
    };
    return filterOutreach(records, criteria);
  }, [records, searchQuery, channelFilter, statusFilter, campaignFilter]);

  // Real aggregate performance metrics (strictly zero/neutral when unrecorded)
  const metrics = React.useMemo(() => {
    return computeOutreachMetrics(records);
  }, [records]);

  // Reset pagination when filter criteria changes
  React.useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, channelFilter, statusFilter, campaignFilter]);

  // Paginated records
  const totalPages = Math.ceil(filteredRecords.length / pageSize) || 1;
  const paginatedRecords = React.useMemo(() => {
    const startIndex = (currentPage - 1) * pageSize;
    return filteredRecords.slice(startIndex, startIndex + pageSize);
  }, [filteredRecords, currentPage, pageSize]);

  // Reset filters handler
  const handleResetFilters = () => {
    setSearchQuery("");
    setChannelFilter("ALL");
    setStatusFilter("ALL");
    setCampaignFilter("ALL");
  };

  // Inspect detail handler
  const handleOpenDetail = (item: OutreachItem) => {
    setInspectedOutreach(item);
    setIsDrawerOpen(true);
  };

  const formatDate = (iso?: string | null) => {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    } catch {
      return iso;
    }
  };

  const getChannelIcon = (ch: OutreachChannel) => {
    switch (ch) {
      case "email":
        return <Mail className="w-3.5 h-3.5 text-slate-600" />;
      case "voice":
        return <PhoneCall className="w-3.5 h-3.5 text-emerald-600" />;
      case "sms":
        return <MessageSquare className="w-3.5 h-3.5 text-blue-600" />;
      case "linkedin":
        return <Share2 className="w-3.5 h-3.5 text-sky-600" />;
      default:
        return <Mail className="w-3.5 h-3.5 text-slate-600" />;
    }
  };

  const getStatusBadge = (status: OutreachStatus) => {
    switch (status) {
      case "sent":
        return (
          <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            Sent
          </Badge>
        );
      case "scheduled":
        return (
          <Badge className="bg-sky-50 text-sky-700 border-sky-200">
            <Clock className="w-3 h-3 mr-1" />
            Scheduled
          </Badge>
        );
      case "sending":
        return (
          <Badge className="bg-amber-50 text-amber-700 border-amber-200">
            <Radio className="w-3 h-3 mr-1 animate-pulse" />
            Sending
          </Badge>
        );
      case "failed":
        return (
          <Badge className="bg-rose-50 text-rose-700 border-rose-200">
            <AlertCircle className="w-3 h-3 mr-1" />
            Failed
          </Badge>
        );
      case "cancelled":
        return (
          <Badge className="bg-slate-100 text-slate-500 border-slate-200">
            Cancelled
          </Badge>
        );
      default:
        return (
          <Badge className="bg-slate-100 text-slate-600 border-slate-200">
            {OUTREACH_STATUS_LABELS[status] || status}
          </Badge>
        );
    }
  };

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight text-header">
                Outreach
              </h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-agile-lightorange text-agile-red border border-agile-outlinered/30">
                {records.length} outreach records
              </span>
            </div>
            <p className="text-sm text-secondary-text mt-1">
              Monitor and manage outbound communication across your sales campaigns.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={loadRecords}
              disabled={isLoading}
              className="text-xs border-slate-200 text-slate-700 hover:bg-slate-50"
            >
              <RotateCcw className={`w-3.5 h-3.5 mr-1.5 text-slate-500 ${isLoading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
            <Link href="/campaigns">
              <Button
                variant="outline"
                className="text-xs border-slate-200 text-slate-700 hover:bg-slate-50"
              >
                <Layers className="w-3.5 h-3.5 mr-1.5 text-slate-500" />
                View Campaigns
              </Button>
            </Link>
          </div>
        </div>

        {/* Factual Operational Counts (Strictly Raw Database Metrics) */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <Card className="border-slate-200 shadow-xs bg-white">
            <CardContent className="p-3.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
                Outreach Records
              </span>
              <div className="text-xl font-bold text-header mt-1">
                {metrics.totalCount}
              </div>
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                Database records
              </span>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-xs bg-white">
            <CardContent className="p-3.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
                Sent
              </span>
              <div className="text-xl font-bold text-slate-800 mt-1">
                {metrics.totalSent}
              </div>
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                Dispatched messages
              </span>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-xs bg-white">
            <CardContent className="p-3.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
                Delivered
              </span>
              <div className="text-xl font-bold text-slate-800 mt-1">
                {metrics.totalDelivered}
              </div>
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                Provider confirmed
              </span>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-xs bg-white">
            <CardContent className="p-3.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
                Opened
              </span>
              <div className="text-xl font-bold text-slate-800 mt-1">
                {metrics.totalOpened}
              </div>
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                Open events
              </span>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-xs bg-white">
            <CardContent className="p-3.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
                Replied
              </span>
              <div className="text-xl font-bold text-slate-800 mt-1">
                {metrics.totalReplied}
              </div>
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                Reply events
              </span>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-xs bg-white">
            <CardContent className="p-3.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
                Bounced
              </span>
              <div className="text-xl font-bold text-slate-800 mt-1">
                {metrics.totalBounced}
              </div>
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                Bounce events
              </span>
            </CardContent>
          </Card>
        </div>

        {/* Global Empty State: When 0 total database records exist */}
        {records.length === 0 && (
          <Card className="border-slate-200 shadow-xs bg-white text-center py-16 px-6">
            <div className="max-w-md mx-auto space-y-4">
              <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mx-auto text-slate-400">
                <Send className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-header">
                  No outreach activity yet
                </h3>
                <p className="text-sm text-slate-500 mt-1">
                  Outreach activity will appear here once campaigns begin sending email or initiating voice calls.
                </p>
              </div>
              <div className="flex items-center justify-center gap-3 pt-2">
                <Link href="/campaigns">
                  <Button className="bg-agile-red hover:bg-agile-red/90 text-white font-medium text-xs">
                    Go to Campaigns
                  </Button>
                </Link>
                <Link href="/find-leads">
                  <Button
                    variant="outline"
                    className="border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-medium"
                  >
                    Find Leads
                  </Button>
                </Link>
              </div>
            </div>
          </Card>
        )}

        {/* Records Present: Search, Filters & Data Table */}
        {records.length > 0 && (
          <>
            {/* Filter Bar */}
            <Card className="border-slate-200 shadow-xs bg-white">
              <CardContent className="p-4">
                <div className="flex flex-col md:flex-row gap-3">
                  {/* Search */}
                  <div className="relative flex-1">
                    <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                    <Input
                      type="text"
                      placeholder="Search recipient, contact, subject, or provider message ID..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-9 text-xs h-9"
                    />
                  </div>

                  {/* Channel Filter */}
                  <div className="w-full md:w-44">
                    <Select
                      value={channelFilter}
                      onChange={(e) => setChannelFilter(e.target.value)}
                      className="text-xs h-9"
                    >
                      <option value="ALL">All Channels</option>
                      <option value="email">Email</option>
                      <option value="voice">Voice Call</option>
                      <option value="sms">SMS</option>
                      <option value="linkedin">LinkedIn</option>
                    </Select>
                  </div>

                  {/* Status Filter */}
                  <div className="w-full md:w-44">
                    <Select
                      value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value)}
                      className="text-xs h-9"
                    >
                      <option value="ALL">All Statuses</option>
                      <option value="sent">Sent</option>
                      <option value="draft">Draft</option>
                      <option value="scheduled">Scheduled</option>
                      <option value="sending">Sending</option>
                      <option value="failed">Failed</option>
                      <option value="cancelled">Cancelled</option>
                    </Select>
                  </div>

                  {/* Campaign Filter (Real dynamic options) */}
                  {uniqueCampaigns.length > 0 && (
                    <div className="w-full md:w-48">
                      <Select
                        value={campaignFilter}
                        onChange={(e) => setCampaignFilter(e.target.value)}
                        className="text-xs h-9"
                      >
                        <option value="ALL">All Campaigns</option>
                        {uniqueCampaigns.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </Select>
                    </div>
                  )}

                  {/* Reset Filters */}
                  {(searchQuery ||
                    channelFilter !== "ALL" ||
                    statusFilter !== "ALL" ||
                    campaignFilter !== "ALL") && (
                    <Button
                      variant="ghost"
                      onClick={handleResetFilters}
                      className="text-xs text-slate-500 hover:text-slate-800 h-9 px-2.5 shrink-0"
                    >
                      <RotateCcw className="w-3.5 h-3.5 mr-1" />
                      Reset
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Outreach Table Card */}
            <Card className="border-slate-200 shadow-xs bg-white overflow-hidden">
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader className="bg-slate-50/80 border-b border-slate-200">
                      <TableRow>
                        <TableHead className="text-xs font-semibold text-slate-600 py-3.5 px-4">
                          Recipient & Contact
                        </TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 py-3.5 px-4">
                          Channel
                        </TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 py-3.5 px-4">
                          Campaign / Source
                        </TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 py-3.5 px-4">
                          Status
                        </TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 py-3.5 px-4">
                          Provider
                        </TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 py-3.5 px-4">
                          Sent / Dispatched
                        </TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 py-3.5 px-4">
                          Latest Event
                        </TableHead>
                        <TableHead className="text-xs font-semibold text-slate-600 py-3.5 px-4 text-right">
                          Action
                        </TableHead>
                      </TableRow>
                    </TableHeader>

                    <TableBody>
                      {isLoading ? (
                        <TableRow>
                          <TableCell
                            colSpan={8}
                            className="text-center py-12 text-slate-500 text-xs"
                          >
                            <div className="flex items-center justify-center gap-2">
                              <div className="w-4 h-4 border-2 border-agile-red border-t-transparent rounded-full animate-spin" />
                              <span>Loading outreach records from live API...</span>
                            </div>
                          </TableCell>
                        </TableRow>
                      ) : hasError ? (
                        <TableRow>
                          <TableCell
                            colSpan={8}
                            className="text-center py-12 text-slate-500 text-xs"
                          >
                            <AlertCircle className="w-8 h-8 text-rose-400 mx-auto mb-2" />
                            Failed to load outreach records from backend API.
                            <div className="mt-2">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={loadRecords}
                                className="text-xs border-slate-200"
                              >
                                Retry
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ) : paginatedRecords.length === 0 ? (
                        <TableRow>
                          <TableCell
                            colSpan={8}
                            className="text-center py-12 text-slate-500 text-xs"
                          >
                            <AlertCircle className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                            No matching outreach records found.
                            <div className="mt-2">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={handleResetFilters}
                                className="text-xs border-slate-200"
                              >
                                Clear search filters
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ) : (
                        paginatedRecords.map((item) => {
                          const latestEvent =
                            item.events.length > 0
                              ? item.events[item.events.length - 1]
                              : null;

                          return (
                            <TableRow
                              key={item.id}
                              onClick={() => handleOpenDetail(item)}
                              className="hover:bg-slate-50/70 transition-colors cursor-pointer group"
                            >
                              {/* Recipient & Contact */}
                              <TableCell className="py-3 px-4">
                                <div className="space-y-0.5">
                                  <div className="font-semibold text-header text-xs group-hover:text-agile-red transition-colors flex items-center gap-1.5">
                                    {item.contactName}
                                  </div>
                                  <div className="text-[11px] font-mono text-slate-500">
                                    {item.recipient}
                                  </div>
                                  {item.companyName && (
                                    <div className="text-[11px] text-slate-400 flex items-center gap-1">
                                      <Building2 className="w-3 h-3 text-slate-300" />
                                      {item.companyName}
                                    </div>
                                  )}
                                </div>
                              </TableCell>

                              {/* Channel */}
                              <TableCell className="py-3 px-4 whitespace-nowrap">
                                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-700 bg-slate-100/70 px-2 py-0.5 rounded border border-slate-200/80">
                                  {getChannelIcon(item.channel)}
                                  {OUTREACH_CHANNEL_LABELS[item.channel] || item.channel}
                                </span>
                              </TableCell>

                              {/* Campaign / Source */}
                              <TableCell className="py-3 px-4 max-w-[200px]">
                                <div className="space-y-0.5">
                                  <div className="text-xs text-slate-800 font-medium truncate" title={item.campaignName || "—"}>
                                    {item.campaignName || (item.callRecord ? "Voice Follow-up" : "Standalone Outreach")}
                                  </div>
                                  {item.callRecord && (
                                    <span className="text-[10px] font-mono text-emerald-600 bg-emerald-50 px-1.5 py-0.2 rounded border border-emerald-200">
                                      Retell: {item.callRecord.callId}
                                    </span>
                                  )}
                                </div>
                              </TableCell>

                              {/* Status & Provenance */}
                              <TableCell className="py-3 px-4 whitespace-nowrap">
                                <div className="flex flex-col gap-1 items-start">
                                  {getStatusBadge(item.status)}
                                  {(() => {
                                    const prov = getOutreachProvenance(item);
                                    if (prov.classification === "test_fixture") {
                                      return (
                                        <Badge variant="warning" className="text-[10px] py-0 px-1.5 font-normal">
                                          Test Fixture
                                        </Badge>
                                      );
                                    } else if (prov.classification === "unverified") {
                                      return (
                                        <Badge variant="warning" className="text-[10px] py-0 px-1.5 font-normal">
                                          Unverified
                                        </Badge>
                                      );
                                    } else if (prov.classification === "draft") {
                                      return (
                                        <Badge variant="neutral" className="text-[10px] py-0 px-1.5 font-normal">
                                          Draft (Unsent)
                                        </Badge>
                                      );
                                    }
                                    return (
                                      <Badge variant="success" className="text-[10px] py-0 px-1.5 font-normal">
                                        Verified Live
                                      </Badge>
                                    );
                                  })()}
                                </div>
                              </TableCell>

                              {/* Provider */}
                              <TableCell className="py-3 px-4 whitespace-nowrap">
                                <span className="font-mono text-[11px] text-slate-600 bg-slate-50 px-2 py-0.5 rounded border border-slate-200">
                                  {item.provider || "—"}
                                </span>
                              </TableCell>

                              {/* Sent Date */}
                              <TableCell className="py-3 px-4 text-xs text-slate-600 whitespace-nowrap">
                                {formatDate(item.sentAt || item.createdAt)}
                              </TableCell>

                              {/* Latest Event */}
                              <TableCell className="py-3 px-4 whitespace-nowrap">
                                {latestEvent ? (
                                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-600 bg-slate-50 px-2 py-0.5 rounded border border-slate-200">
                                    <span className="w-1.5 h-1.5 rounded-full bg-teal-500" />
                                    {OUTREACH_EVENT_LABELS[latestEvent.eventType] || latestEvent.eventType}
                                  </span>
                                ) : (
                                  <span className="text-xs text-slate-400">—</span>
                                )}
                              </TableCell>

                              {/* Actions */}
                              <TableCell className="py-3 px-4 text-right whitespace-nowrap">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleOpenDetail(item);
                                  }}
                                  className="h-7 text-xs px-2 text-slate-500 hover:text-agile-red hover:bg-agile-lightorange/50"
                                >
                                  <Eye className="w-3.5 h-3.5 mr-1" />
                                  Details
                                </Button>
                              </TableCell>
                            </TableRow>
                          );
                        })
                      )}
                    </TableBody>
                  </Table>
                </div>

                {/* Pagination Controls */}
                {filteredRecords.length > pageSize && (
                  <div className="p-4 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 bg-white">
                    <span className="text-xs text-slate-500">
                      Showing{" "}
                      <span className="font-medium text-slate-800">
                        {(currentPage - 1) * pageSize + 1}
                      </span>{" "}
                      to{" "}
                      <span className="font-medium text-slate-800">
                        {Math.min(currentPage * pageSize, filteredRecords.length)}
                      </span>{" "}
                      of{" "}
                      <span className="font-medium text-slate-800">
                        {filteredRecords.length}
                      </span>{" "}
                      outreach items
                    </span>

                    <Pagination
                      currentPage={currentPage}
                      totalPages={totalPages}
                      onPageChange={setCurrentPage}
                    />
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>

      {/* Outreach Detail Drawer */}
      <OutreachDetailDrawer
        outreach={inspectedOutreach}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
      />
    </AppShell>
  );
}
