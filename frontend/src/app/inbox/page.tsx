"use client";

import React, { useEffect, useState, useMemo } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  InboundEmailItem,
  InboundEmailDetail,
  InboundEmailListResponse,
  GraphConfigStatusResponse,
  GraphCheckpointStatusResponse,
  GraphSyncResultResponse,
  getInboundEmails,
  getInboundEmailDetail,
  updateManualReview,
  triggerMailboxSync,
  getGraphConfigStatus,
  getGraphSyncRuns,
  getCheckpointStatus,
} from "@/services/inboundEmailService";
import {
  Inbox,
  Mail,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  Clock,
  AlertTriangle,
  User,
  Building,
  Target,
  ExternalLink,
  Filter,
  FileText,
  XCircle,
  HelpCircle,
  Eye,
  Check,
  Lock,
  GitBranch,
} from "lucide-react";

export default function SupportInboxPage() {
  const [emails, setEmails] = useState<InboundEmailItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [unmatchedCount, setUnmatchedCount] = useState(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const [configStatus, setConfigStatus] = useState<GraphConfigStatusResponse | null>(null);
  const [checkpointStatus, setCheckpointStatus] = useState<GraphCheckpointStatusResponse | null>(null);
  const [recentSyncRuns, setRecentSyncRuns] = useState<GraphSyncResultResponse[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<GraphSyncResultResponse | null>(null);
  const [syncModalOpen, setSyncModalOpen] = useState(false);

  // Filters & Search
  const [activeTab, setActiveTab] = useState<"all" | "unmatched" | "matched" | "reviewed">("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 25;

  // Detail Modal
  const [selectedEmail, setSelectedEmail] = useState<InboundEmailDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [reviewStatusInput, setReviewStatusInput] = useState<"reviewed" | "dismissed" | "archived" | "pending">("reviewed");
  const [reviewNotesInput, setReviewNotesInput] = useState("");
  const [savingReview, setSavingReview] = useState(false);
  const [reviewSuccess, setReviewSuccess] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Map tab to status filters
      let statusParam: string | undefined = undefined;
      let reviewParam: string | undefined = undefined;

      if (activeTab === "unmatched") {
        statusParam = "unmatched";
        reviewParam = "pending";
      } else if (activeTab === "matched") {
        statusParam = "matched";
      } else if (activeTab === "reviewed") {
        reviewParam = "reviewed";
      }

      const [emailData, statusData, runsData, checkpointData] = await Promise.all([
        getInboundEmails({
          status: statusParam,
          review_status: reviewParam,
          search: searchTerm,
          page: currentPage,
          limit: pageSize,
        }).catch((err) => {
          console.warn("Failed fetching inbound emails:", err);
          return { items: [], total: 0, unmatched_count: 0, unread_count: 0, page: 1, limit: pageSize };
        }),
        getGraphConfigStatus().catch(() => null),
        getGraphSyncRuns(5).catch(() => []),
        getCheckpointStatus().catch(() => null),
      ]);

      setEmails(emailData.items || []);
      setTotalCount(emailData.total || 0);
      setUnmatchedCount(emailData.unmatched_count || 0);
      setUnreadCount(emailData.unread_count || 0);
      setConfigStatus(statusData);
      setRecentSyncRuns(runsData || []);
      setCheckpointStatus(checkpointData);
    } catch (err: any) {
      setError(err.message || "Failed to load support inbox.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [activeTab, currentPage]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentPage(1);
    loadData();
  };

  const handleSyncMailbox = async () => {
    try {
      setSyncing(true);
      const result = await triggerMailboxSync({ max_messages: 50, folder: "Inbox" });
      setSyncResult(result);
      setSyncModalOpen(true);
      // Reload inbox data
      await loadData();
    } catch (err: any) {
      setError(err.message || "Failed to trigger mailbox synchronization.");
    } finally {
      setSyncing(false);
    }
  };

  const handleOpenEmail = async (email: InboundEmailItem) => {
    try {
      setLoadingDetail(true);
      setSelectedEmail(null);
      setReviewSuccess(null);
      const detail = await getInboundEmailDetail(email.id);
      setSelectedEmail(detail);
      setReviewStatusInput((detail.manual_review_status as any) || "reviewed");
      setReviewNotesInput(detail.review_notes || "");
    } catch (err: any) {
      alert(err.message || "Failed to load email details.");
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleSaveReview = async () => {
    if (!selectedEmail) return;
    try {
      setSavingReview(true);
      setReviewSuccess(null);
      const updated = await updateManualReview(selectedEmail.id, {
        status: reviewStatusInput,
        review_notes: reviewNotesInput,
      });
      setSelectedEmail(updated);
      setReviewSuccess("Manual review status updated successfully.");
      // Update item in table
      setEmails((prev) =>
        prev.map((e) => (e.id === updated.id ? { ...e, manual_review_status: updated.manual_review_status } : e))
      );
    } catch (err: any) {
      alert(err.message || "Failed to save review status.");
    } finally {
      setSavingReview(false);
    }
  };

  return (
    <AppShell>
      <div className="space-y-6 max-w-7xl mx-auto pb-12">
        {/* Header & Controls */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
          <div>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-agile-red/10 text-agile-red flex items-center justify-center">
                <Inbox className="w-5 h-5" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Support Inbox</h1>
                <p className="text-sm text-slate-500">
                  Microsoft Graph inbound email reader for{" "}
                  <span className="font-mono text-slate-700 font-medium">
                    {configStatus?.support_mailbox || "support@agilereceivables.com"}
                  </span>
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Fail-closed safety badge */}
            {configStatus && (
              <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-medium">
                {configStatus.enabled ? (
                  <span className="flex items-center gap-1.5 text-emerald-700 bg-emerald-50 border-emerald-200">
                    <span className="w-2 h-2 rounded-full bg-emerald-500" />
                    Live Sync Enabled
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-amber-700 bg-amber-50 border-amber-200">
                    <span className="w-2 h-2 rounded-full bg-amber-500" />
                    Fail-Closed Safety Active
                  </span>
                )}
              </div>
            )}

            <Button
              variant="outline"
              size="sm"
              onClick={loadData}
              disabled={loading || syncing}
              className="gap-2"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>

            <Button
              variant="primary"
              size="sm"
              onClick={handleSyncMailbox}
              disabled={syncing || Boolean(checkpointStatus?.is_syncing)}
              className="gap-2 bg-agile-red hover:bg-[#c0434b] text-white disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${syncing || checkpointStatus?.is_syncing ? "animate-spin" : ""}`} />
              {syncing || checkpointStatus?.is_syncing ? "Syncing..." : "Sync Mailbox"}
            </Button>
          </div>
        </div>

        {/* Active Concurrency Lock Banner */}
        {checkpointStatus?.is_syncing && (
          <div className="p-4 rounded-lg bg-blue-50 border border-blue-200 text-blue-800 flex items-start gap-3">
            <Lock className="w-5 h-5 text-blue-600 shrink-0 mt-0.5 animate-pulse" />
            <div className="text-sm">
              <p className="font-semibold text-blue-900">Synchronization In Progress</p>
              <p className="text-xs text-blue-700 mt-0.5">
                A mailbox sync job is currently executing for <code className="font-mono">{checkpointStatus.mailbox}</code>.
                Overlapping concurrent imports are prevented by the active synchronization lock.
              </p>
            </div>
          </div>
        )}

        {/* Global Error Banner */}
        {error && (
          <div className="p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-medium">Error loading support inbox</p>
              <p className="text-xs text-red-600 mt-1">{error}</p>
            </div>
          </div>
        )}

        {/* Configuration Safety Banner if Safety Disabled */}
        {configStatus && !configStatus.enabled && (
          <div className="p-4 rounded-lg bg-amber-50/70 border border-amber-200 text-amber-800 flex items-start gap-3">
            <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div className="text-sm space-y-1">
              <p className="font-semibold text-amber-900">Microsoft Graph Live Sync Safety Guard Active</p>
              <p className="text-xs text-amber-700">
                Live mailbox synchronization is guarded by default (<code>MICROSOFT_GRAPH_ENABLED=False</code>). Real Microsoft Graph requests and external connections are blocked until explicitly enabled in your backend environment.
              </p>
            </div>
          </div>
        )}

        {/* KPI Metrics */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="p-4 border-slate-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Total Inbound</p>
                <p className="text-2xl font-bold text-slate-900 mt-1">{totalCount}</p>
              </div>
              <div className="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                <Mail className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs text-slate-500 mt-2">Emails ingested from support mailbox</p>
          </Card>

          <Card className="p-4 border-slate-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Needs Review</p>
                <p className="text-2xl font-bold text-amber-600 mt-1">{unmatchedCount}</p>
              </div>
              <div className="w-10 h-10 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs text-slate-500 mt-2">Unmatched sender emails pending triage</p>
          </Card>

          <Card className="p-4 border-slate-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Unread Messages</p>
                <p className="text-2xl font-bold text-slate-900 mt-1">{unreadCount}</p>
              </div>
              <div className="w-10 h-10 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
                <Clock className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs text-slate-500 mt-2">Unopened incoming messages</p>
          </Card>

          <Card className="p-4 border-slate-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Mailbox & Checkpoint</p>
                <p className="text-sm font-semibold text-slate-800 mt-1 truncate max-w-[170px]" title={configStatus?.support_mailbox}>
                  {configStatus?.support_mailbox || "support@agilereceivables.com"}
                </p>
              </div>
              <div className="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                <ShieldCheck className="w-5 h-5" />
              </div>
            </div>
            <div className="space-y-1 mt-2.5 border-t border-slate-100 pt-2 text-[11px] text-slate-600">
              <div className="flex items-center justify-between">
                <span>Checkpoint:</span>
                <span className="font-semibold text-slate-800">
                  {checkpointStatus?.has_checkpoint ? "Incremental Active" : "Initial Checkpoint"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>Auto-Sync:</span>
                <span className="font-semibold text-slate-800">
                  {configStatus?.auto_sync_enabled ? `Every ${configStatus.sync_interval_minutes}m` : "Guarded (Off)"}
                </span>
              </div>
              {checkpointStatus?.last_successful_sync_at && (
                <div className="flex items-center justify-between">
                  <span>Last Sync:</span>
                  <span className="text-slate-700 font-mono text-[10px]">
                    {new Date(checkpointStatus.last_successful_sync_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* Filter Tabs & Search Bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2">
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg w-full sm:w-auto">
            <button
              onClick={() => { setActiveTab("all"); setCurrentPage(1); }}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                activeTab === "all" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              All Messages ({totalCount})
            </button>
            <button
              onClick={() => { setActiveTab("unmatched"); setCurrentPage(1); }}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors flex items-center gap-1.5 ${
                activeTab === "unmatched" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Needs Review
              {unmatchedCount > 0 && (
                <span className="bg-amber-100 text-amber-800 text-[10px] px-1.5 py-0.2 rounded-full font-semibold">
                  {unmatchedCount}
                </span>
              )}
            </button>
            <button
              onClick={() => { setActiveTab("matched"); setCurrentPage(1); }}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                activeTab === "matched" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              CRM Matched
            </button>
            <button
              onClick={() => { setActiveTab("reviewed"); setCurrentPage(1); }}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                activeTab === "reviewed" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Reviewed
            </button>
          </div>

          <form onSubmit={handleSearchSubmit} className="flex items-center gap-2 w-full sm:w-72">
            <div className="relative w-full">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search sender or subject..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-xs bg-white border border-slate-200 rounded-md focus:outline-hidden focus:ring-1 focus:ring-agile-red"
              />
            </div>
            <Button type="submit" variant="outline" size="sm" className="text-xs">
              Search
            </Button>
          </form>
        </div>

        {/* Message List Table */}
        <Card className="border-slate-200 overflow-hidden">
          {loading ? (
            <div className="p-12 text-center text-slate-500">
              <RefreshCw className="w-6 h-6 animate-spin mx-auto text-agile-red mb-3" />
              <p className="text-sm font-medium">Loading inbound messages...</p>
            </div>
          ) : emails.length === 0 ? (
            <div className="p-12 text-center text-slate-500">
              <Inbox className="w-10 h-10 text-slate-300 mx-auto mb-3" />
              <p className="text-base font-semibold text-slate-700">No inbound emails found</p>
              <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
                {searchTerm
                  ? "No messages match your search filter. Try clearing your search query."
                  : activeTab === "unmatched"
                  ? "No unmatched messages require manual review. All messages are matched to CRM entities."
                  : "Click 'Sync Mailbox' to fetch inbound emails from the support mailbox."}
              </p>
              {searchTerm && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => { setSearchTerm(""); loadData(); }}
                  className="mt-4 text-xs"
                >
                  Clear Search
                </Button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-50/75 border-b border-slate-200 text-slate-600 font-medium">
                    <th className="py-3 px-4">Sender</th>
                    <th className="py-3 px-4">Subject & Snippet</th>
                    <th className="py-3 px-4">CRM Match</th>
                    <th className="py-3 px-4">Review Status</th>
                    <th className="py-3 px-4">Received</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {emails.map((email) => {
                    const isUnread = !email.is_read;
                    const isUnmatched = email.sync_status === "unmatched";

                    return (
                      <tr
                        key={email.id}
                        className={`hover:bg-slate-50/50 transition-colors cursor-pointer ${
                          isUnread ? "bg-blue-50/20 font-medium" : ""
                        }`}
                        onClick={() => handleOpenEmail(email)}
                      >
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          <div className="flex flex-col">
                            <span className="font-semibold text-slate-900">
                              {email.sender_name || email.sender_email}
                            </span>
                            <span className="text-[11px] text-slate-500 font-mono">
                              {email.sender_email}
                            </span>
                          </div>
                        </td>

                        <td className="py-3.5 px-4 max-w-md">
                          <div className="flex flex-col">
                            <span className="font-medium text-slate-800 truncate">
                              {email.subject || "(No Subject)"}
                            </span>
                            <span className="text-[11px] text-slate-500 line-clamp-1 mt-0.5">
                              {email.body_preview || "(Empty preview)"}
                            </span>
                          </div>
                        </td>

                        <td className="py-3.5 px-4 whitespace-nowrap">
                          {email.matched_entity ? (
                            <div className="flex items-center gap-1.5 text-emerald-700">
                              <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                              <div className="flex flex-col text-[11px]">
                                {email.matched_entity.contact_name && (
                                  <span>{email.matched_entity.contact_name} (Contact)</span>
                                )}
                                {!email.matched_entity.contact_name && email.matched_entity.lead_company_name && (
                                  <span>{email.matched_entity.lead_company_name} (Lead)</span>
                                )}
                                {!email.matched_entity.contact_name && !email.matched_entity.lead_company_name && email.matched_entity.company_name && (
                                  <span>{email.matched_entity.company_name} (Company)</span>
                                )}
                              </div>
                            </div>
                          ) : (
                            <Badge variant="warning" size="sm">
                              Unmatched
                            </Badge>
                          )}
                        </td>

                        <td className="py-3.5 px-4 whitespace-nowrap">
                          {email.manual_review_status === "reviewed" && (
                            <Badge variant="success" size="sm">
                              Reviewed
                            </Badge>
                          )}
                          {email.manual_review_status === "pending" && (
                            <Badge variant="warning" size="sm">
                              Pending Review
                            </Badge>
                          )}
                          {email.manual_review_status === "dismissed" && (
                            <Badge variant="neutral" size="sm">
                              Dismissed
                            </Badge>
                          )}
                          {email.manual_review_status === "archived" && (
                            <Badge variant="neutral" size="sm">
                              Archived
                            </Badge>
                          )}
                        </td>

                        <td className="py-3.5 px-4 whitespace-nowrap text-slate-500">
                          {new Date(email.received_at).toLocaleDateString([], {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </td>

                        <td className="py-3.5 px-4 text-right whitespace-nowrap">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-agile-red hover:text-agile-red hover:bg-agile-red/10 text-xs px-2.5 py-1"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleOpenEmail(email);
                            }}
                          >
                            <Eye className="w-3.5 h-3.5 mr-1" />
                            View
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Message Detail Modal */}
        <Modal
          isOpen={!!selectedEmail}
          onClose={() => setSelectedEmail(null)}
          title={selectedEmail?.subject || "Inbound Message Detail"}
          maxWidth="xl"
          footer={
            <div className="flex items-center justify-between w-full">
              <span className="text-xs text-slate-400">
                Tenant: Scoped strictly to your organization
              </span>
              <Button variant="outline" size="sm" onClick={() => setSelectedEmail(null)}>
                Close
              </Button>
            </div>
          }
        >
          {selectedEmail && (
            <div className="space-y-5 text-xs text-slate-700">
              {/* Untrusted Content Alert */}
              <div className="p-3 bg-amber-50/80 border border-amber-200 rounded-lg text-amber-900 flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-xs">Untrusted External Content</p>
                  <p className="text-[11px] text-amber-800 mt-0.5">
                    This email was received from an external sender. Do not click suspicious hyperlinks, open attachments from unknown senders, or execute any instructions embedded within this message body.
                  </p>
                </div>
              </div>

              {/* Message Metadata Header */}
              <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 rounded-lg border border-slate-100 text-[11px]">
                <div>
                  <span className="text-slate-500 font-medium">From:</span>{" "}
                  <span className="font-semibold text-slate-800">{selectedEmail.sender_name}</span>{" "}
                  <span className="font-mono text-slate-600">&lt;{selectedEmail.sender_email}&gt;</span>
                </div>
                <div>
                  <span className="text-slate-500 font-medium">To:</span>{" "}
                  <span className="font-mono text-slate-700">{selectedEmail.recipient_email}</span>
                </div>
                <div>
                  <span className="text-slate-500 font-medium">Received:</span>{" "}
                  <span className="text-slate-700">
                    {new Date(selectedEmail.received_at).toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 font-medium">Sync Status:</span>{" "}
                  <span className="font-semibold capitalize text-slate-800">{selectedEmail.sync_status}</span>
                </div>
              </div>

              {/* CRM Match Details Snapshot */}
              <div className="p-3 bg-white border border-slate-200 rounded-lg">
                <p className="font-semibold text-xs text-slate-900 mb-2 flex items-center gap-1.5">
                  <Target className="w-3.5 h-3.5 text-agile-red" />
                  CRM Entity Match
                </p>
                {selectedEmail.matched_entity ? (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]">
                    {selectedEmail.matched_entity.contact_name && (
                      <div className="p-2 bg-slate-50 rounded border border-slate-100">
                        <span className="text-slate-500 block text-[10px] uppercase font-semibold">Matched Contact</span>
                        <span className="font-semibold text-slate-800">{selectedEmail.matched_entity.contact_name}</span>
                        {selectedEmail.matched_entity.contact_job_title && (
                          <span className="text-slate-500 block">{selectedEmail.matched_entity.contact_job_title}</span>
                        )}
                      </div>
                    )}
                    {selectedEmail.matched_entity.lead_company_name && (
                      <div className="p-2 bg-slate-50 rounded border border-slate-100">
                        <span className="text-slate-500 block text-[10px] uppercase font-semibold">Matched Lead</span>
                        <span className="font-semibold text-slate-800">{selectedEmail.matched_entity.lead_company_name}</span>
                        {selectedEmail.matched_entity.lead_score !== null && (
                          <span className="text-slate-500 block">Score: {selectedEmail.matched_entity.lead_score}</span>
                        )}
                      </div>
                    )}
                    {selectedEmail.matched_entity.company_name && (
                      <div className="p-2 bg-slate-50 rounded border border-slate-100">
                        <span className="text-slate-500 block text-[10px] uppercase font-semibold">Company</span>
                        <span className="font-semibold text-slate-800">{selectedEmail.matched_entity.company_name}</span>
                        {selectedEmail.matched_entity.company_domain && (
                          <span className="text-slate-500 block font-mono">{selectedEmail.matched_entity.company_domain}</span>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-[11px] text-slate-500 italic">
                    No matching Contact or Lead record found for sender <span className="font-mono text-slate-700">{selectedEmail.sender_email}</span> in your organization CRM. Flagged for manual review.
                  </p>
                )}
              </div>

              {/* Message Body Content */}
              <div>
                <p className="font-semibold text-xs text-slate-900 mb-1.5 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-slate-500" />
                  Message Body
                </p>
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg max-h-72 overflow-y-auto whitespace-pre-wrap font-sans text-xs text-slate-800 leading-relaxed select-text">
                  {selectedEmail.body_content || selectedEmail.body_preview || "(Empty Message Body)"}
                </div>
              </div>

              {/* Manual Review Triage Section */}
              <div className="p-3 bg-slate-50/75 border border-slate-200 rounded-lg space-y-3">
                <p className="font-semibold text-xs text-slate-900 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-blue-600" />
                  Manual Review & Triage
                </p>

                {reviewSuccess && (
                  <div className="p-2 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded text-xs flex items-center gap-1.5">
                    <Check className="w-3.5 h-3.5 text-emerald-600" />
                    {reviewSuccess}
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-medium text-slate-700 mb-1">
                      Review Status
                    </label>
                    <select
                      value={reviewStatusInput}
                      onChange={(e) => setReviewStatusInput(e.target.value as any)}
                      className="w-full text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded-md focus:outline-hidden focus:ring-1 focus:ring-agile-red"
                    >
                      <option value="pending">Pending Review</option>
                      <option value="reviewed">Reviewed & Handled</option>
                      <option value="dismissed">Dismissed / Spam</option>
                      <option value="archived">Archived</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-slate-700 mb-1">
                      Review Notes
                    </label>
                    <input
                      type="text"
                      placeholder="Add notes about manual triage or contact association..."
                      value={reviewNotesInput}
                      onChange={(e) => setReviewNotesInput(e.target.value)}
                      className="w-full text-xs px-2.5 py-1.5 bg-white border border-slate-200 rounded-md focus:outline-hidden focus:ring-1 focus:ring-agile-red"
                    />
                  </div>
                </div>

                <div className="flex justify-end pt-1">
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleSaveReview}
                    disabled={savingReview}
                    className="text-xs bg-agile-red hover:bg-[#c0434b] text-white"
                  >
                    {savingReview ? "Saving..." : "Save Review Decision"}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </Modal>

        {/* Sync Result Modal */}
        <Modal
          isOpen={syncModalOpen}
          onClose={() => setSyncModalOpen(false)}
          title="Mailbox Synchronization Result"
          maxWidth="md"
          footer={
            <Button variant="primary" size="sm" onClick={() => setSyncModalOpen(false)}>
              Close
            </Button>
          }
        >
          {syncResult && (
            <div className="space-y-4 text-xs text-slate-700">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-800">Mailbox Target:</span>
                <span className="font-mono text-slate-600">{syncResult.mailbox}</span>
              </div>

              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-800">Status:</span>
                {syncResult.status === "completed" && (
                  <Badge variant="success" size="sm">Completed</Badge>
                )}
                {syncResult.status === "blocked_by_safety_guard" && (
                  <Badge variant="warning" size="sm">Blocked by Safety Guard</Badge>
                )}
                {syncResult.status === "failed" && (
                  <Badge variant="warning" size="sm">Failed</Badge>
                )}
              </div>

              {syncResult.error_message && (
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-md text-amber-800 text-xs">
                  <p className="font-semibold">Notice:</p>
                  <p className="mt-0.5">{syncResult.error_message}</p>
                </div>
              )}

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2">
                <div className="p-2.5 bg-slate-50 rounded border text-center">
                  <p className="text-[10px] text-slate-500 uppercase font-semibold">Fetched</p>
                  <p className="text-base font-bold text-slate-800 mt-0.5">{syncResult.messages_fetched}</p>
                </div>
                <div className="p-2.5 bg-slate-50 rounded border text-center">
                  <p className="text-[10px] text-slate-500 uppercase font-semibold">Imported</p>
                  <p className="text-base font-bold text-emerald-700 mt-0.5">{syncResult.messages_imported}</p>
                </div>
                <div className="p-2.5 bg-slate-50 rounded border text-center">
                  <p className="text-[10px] text-slate-500 uppercase font-semibold">Matched</p>
                  <p className="text-base font-bold text-blue-700 mt-0.5">{syncResult.messages_matched}</p>
                </div>
                <div className="p-2.5 bg-slate-50 rounded border text-center">
                  <p className="text-[10px] text-slate-500 uppercase font-semibold">Unmatched</p>
                  <p className="text-base font-bold text-amber-700 mt-0.5">{syncResult.messages_unmatched}</p>
                </div>
              </div>
            </div>
          )}
        </Modal>
      </div>
    </AppShell>
  );
}
