"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  getAdminUpgradeRequests,
  submitAdminUpgradeDecision,
  UpgradeRequestDetail,
} from "@/services/entitlementsService";
import {
  ShieldAlert,
  ShieldCheck,
  Clock,
  CheckCircle2,
  XCircle,
  MessageSquare,
  PhoneCall,
  Mail,
  FileText,
  AlertCircle,
  Building2,
  Calendar,
  User,
  ArrowRight,
  RefreshCw,
  Sliders,
} from "lucide-react";

export default function AdminUpgradesPage() {
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [isPlatformAdmin, setIsPlatformAdmin] = useState(false);

  const [requests, setRequests] = useState<UpgradeRequestDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"pending" | "approved" | "rejected" | "all">("pending");

  // Selected request for review modal
  const [selectedRequest, setSelectedRequest] = useState<UpgradeRequestDetail | null>(null);
  const [decisionMode, setDecisionMode] = useState<"approve" | "reject">("approve");
  const [quotaInput, setQuotaInput] = useState<string>("5000");
  const [rejectionReason, setRejectionReason] = useState<string>("");
  const [adminNotes, setAdminNotes] = useState<string>("");
  const [confirmSubmitting, setConfirmSubmitting] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // 1. Verify User Role via /api/auth/me
  useEffect(() => {
    async function checkAuth() {
      try {
        setAuthLoading(true);
        const res = await fetch("/api/auth/me");
        if (res.ok) {
          const data = await res.json();
          const user = data.user || data;
          setCurrentUser(user);
          const role = (user.role || "").toLowerCase();
          if (role === "superadmin" || role === "platform_admin") {
            setIsPlatformAdmin(true);
          } else {
            setIsPlatformAdmin(false);
          }
        } else {
          setIsPlatformAdmin(false);
        }
      } catch (err) {
        setIsPlatformAdmin(false);
      } finally {
        setAuthLoading(false);
      }
    }
    checkAuth();
  }, []);

  // 2. Fetch requests if authorized
  const fetchRequests = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getAdminUpgradeRequests();
      setRequests(data);
    } catch (err: any) {
      setError(err.message || "Failed to load channel upgrade requests.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isPlatformAdmin) {
      fetchRequests();
    }
  }, [isPlatformAdmin]);

  // Open review modal
  const handleOpenReview = (req: UpgradeRequestDetail) => {
    setSelectedRequest(req);
    setDecisionMode("approve");
    setQuotaInput("5000");
    setRejectionReason("");
    setAdminNotes("");
    setConfirmSubmitting(false);
    setActionError(null);
    setActionSuccess(null);
  };

  // Submit decision
  const handleSubmitDecision = async () => {
    if (!selectedRequest) return;
    setActionError(null);
    setActionSuccess(null);

    if (decisionMode === "approve") {
      const quota = parseInt(quotaInput.trim(), 10);
      if (isNaN(quota) || quota <= 0) {
        setActionError("Please provide a valid positive allocated monthly quota.");
        return;
      }
    } else {
      if (!rejectionReason.trim()) {
        setActionError("A clear rejection reason is mandatory when declining an upgrade request.");
        return;
      }
    }

    try {
      setActionLoading(true);
      const payload: any = {
        action: decisionMode,
        admin_notes: adminNotes.trim() || undefined,
      };
      if (decisionMode === "approve") {
        payload.allocated_quota = parseInt(quotaInput.trim(), 10);
      } else {
        payload.rejection_reason = rejectionReason.trim();
      }

      const updated = await submitAdminUpgradeDecision(selectedRequest.id, payload);
      setActionSuccess(`Successfully ${decisionMode === "approve" ? "approved and unlocked" : "declined"} channel request.`);
      // Update local state
      setRequests((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
      setSelectedRequest(updated);
      setConfirmSubmitting(false);
      setTimeout(() => {
        fetchRequests();
      }, 1000);
    } catch (err: any) {
      setActionError(err.message || "Failed to submit administrative decision.");
    } finally {
      setActionLoading(false);
    }
  };

  // Channel helper
  const getChannelMeta = (ch: string) => {
    switch (ch.toLowerCase()) {
      case "sms":
        return { label: "SMS & MMS", icon: MessageSquare, color: "text-blue-600 bg-blue-50 border-blue-200" };
      case "voice":
        return { label: "AI Voice SDR", icon: PhoneCall, color: "text-purple-600 bg-purple-50 border-purple-200" };
      case "ringless_voicemail":
        return { label: "Ringless Voicemail", icon: Sliders, color: "text-amber-600 bg-amber-50 border-amber-200" };
      case "physical_mail":
        return { label: "Direct Mail", icon: FileText, color: "text-indigo-600 bg-indigo-50 border-indigo-200" };
      default:
        return { label: ch.toUpperCase(), icon: Mail, color: "text-slate-600 bg-slate-50 border-slate-200" };
    }
  };

  if (authLoading) {
    return (
      <AppShell>
        <div className="flex items-center justify-center min-h-[500px]">
          <div className="flex flex-col items-center gap-3">
            <RefreshCw className="w-6 h-6 animate-spin text-agile-red" />
            <p className="text-sm font-medium text-slate-500">Verifying administrative credentials...</p>
          </div>
        </div>
      </AppShell>
    );
  }

  // Unauthorized View
  if (!isPlatformAdmin) {
    return (
      <AppShell>
        <div className="max-w-2xl mx-auto py-16 px-4 text-center">
          <div className="w-16 h-16 rounded-2xl bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center mx-auto mb-5 shadow-xs">
            <ShieldAlert className="w-8 h-8" />
          </div>
          <h1 className="text-xl font-bold text-header mb-2">Platform Administrator Privileges Required</h1>
          <p className="text-sm text-slate-600 mb-6 leading-relaxed">
            This administrative console is restricted strictly to platform operations administrators.
            Your account ({currentUser?.email || "current session"}) does not possess the requisite{" "}
            <code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded text-rose-700 font-mono">superadmin</code> or{" "}
            <code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded text-rose-700 font-mono">platform_admin</code>{" "}
            authority to review or unlock tenant communication channels.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Link href="/settings/entitlements">
              <Button variant="outline">View Tenant Entitlements</Button>
            </Link>
            <Link href="/campaigns">
              <Button>Return to Campaigns</Button>
            </Link>
          </div>
        </div>
      </AppShell>
    );
  }

  // Filter requests
  const pendingRequests = requests.filter((r) => r.status === "pending");
  const approvedRequests = requests.filter((r) => r.status === "approved");
  const rejectedRequests = requests.filter((r) => r.status === "rejected");

  const displayedRequests = requests.filter((r) => {
    if (activeTab === "pending") return r.status === "pending";
    if (activeTab === "approved") return r.status === "approved";
    if (activeTab === "rejected") return r.status === "rejected";
    return true;
  });

  return (
    <AppShell>
      <div className="space-y-6 max-w-7xl mx-auto pb-12">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
                <ShieldCheck className="w-3 h-3" /> Platform Operations
              </span>
              <span className="text-xs text-slate-400 font-medium">Logged in as {currentUser?.email}</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-header">Channel Upgrade Queue</h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Review and approve outbound communication channel access for subscribing customer organizations.
            </p>
          </div>
          <div className="flex items-center gap-2.5">
            <Button variant="outline" size="sm" onClick={fetchRequests} disabled={loading} className="gap-2">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        </div>

        {/* Stats KPI Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="p-4 border-slate-200">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-500 uppercase">Pending Review</span>
              <Clock className="w-4 h-4 text-amber-500" />
            </div>
            <div className="text-2xl font-bold text-amber-600">{pendingRequests.length}</div>
            <p className="text-[11px] text-slate-400 mt-1">Awaiting operations decision</p>
          </Card>
          <Card className="p-4 border-slate-200">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-500 uppercase">Approved</span>
              <CheckCircle2 className="w-4 h-4 text-emerald-500" />
            </div>
            <div className="text-2xl font-bold text-emerald-600">{approvedRequests.length}</div>
            <p className="text-[11px] text-slate-400 mt-1">Unlocked active channels</p>
          </Card>
          <Card className="p-4 border-slate-200">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-500 uppercase">Declined</span>
              <XCircle className="w-4 h-4 text-rose-500" />
            </div>
            <div className="text-2xl font-bold text-rose-600">{rejectedRequests.length}</div>
            <p className="text-[11px] text-slate-400 mt-1">Insufficient history or volume</p>
          </Card>
          <Card className="p-4 border-slate-200">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-500 uppercase">Total Requests</span>
              <FileText className="w-4 h-4 text-slate-400" />
            </div>
            <div className="text-2xl font-bold text-header">{requests.length}</div>
            <p className="text-[11px] text-slate-400 mt-1">All recorded tenant requests</p>
          </Card>
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center gap-2 border-b border-slate-200">
          <button
            onClick={() => setActiveTab("pending")}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === "pending"
                ? "border-agile-red text-agile-red"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Pending ({pendingRequests.length})
          </button>
          <button
            onClick={() => setActiveTab("approved")}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === "approved"
                ? "border-agile-red text-agile-red"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Approved ({approvedRequests.length})
          </button>
          <button
            onClick={() => setActiveTab("rejected")}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === "rejected"
                ? "border-agile-red text-agile-red"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Declined ({rejectedRequests.length})
          </button>
          <button
            onClick={() => setActiveTab("all")}
            className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === "all"
                ? "border-agile-red text-agile-red"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            All History ({requests.length})
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="rounded-lg bg-rose-50 border border-rose-200 p-3 flex items-start gap-2.5 text-xs text-rose-800">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Table View */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-xs overflow-hidden">
          {loading ? (
            <div className="py-16 flex flex-col items-center justify-center gap-2">
              <RefreshCw className="w-6 h-6 animate-spin text-agile-red" />
              <p className="text-xs text-slate-400">Loading requests...</p>
            </div>
          ) : displayedRequests.length === 0 ? (
            <div className="py-16 text-center text-slate-400">
              <FileText className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p className="text-sm font-medium">No {activeTab !== "all" ? activeTab : ""} upgrade requests found.</p>
              <p className="text-xs mt-0.5">When customer tenants request advanced channels, they will queue here.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50/70 border-b border-slate-200 text-slate-500 uppercase font-semibold tracking-wider">
                  <tr>
                    <th className="py-3 px-4">Organization</th>
                    <th className="py-3 px-4">Requester</th>
                    <th className="py-3 px-4">Channel</th>
                    <th className="py-3 px-4">Volume & Justification</th>
                    <th className="py-3 px-4">Date</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {displayedRequests.map((req) => {
                    const channelMeta = getChannelMeta(req.channel);
                    const ChannelIcon = channelMeta.icon;
                    return (
                      <tr key={req.id} className="hover:bg-slate-50/60 transition-colors">
                        <td className="py-3.5 px-4 font-medium text-slate-900">
                          <div className="flex items-center gap-2">
                            <Building2 className="w-3.5 h-3.5 text-slate-400" />
                            <div>
                              <div className="font-semibold">{req.organization_name || "Unknown Org"}</div>
                              <div className="text-[10px] text-slate-400 font-mono">{req.organization_id.substring(0, 8)}...</div>
                            </div>
                          </div>
                        </td>
                        <td className="py-3.5 px-4 text-slate-600">
                          <div className="flex items-center gap-1.5">
                            <User className="w-3.5 h-3.5 text-slate-400" />
                            <span className="truncate max-w-[140px]">{req.requesting_user_email || "System"}</span>
                          </div>
                        </td>
                        <td className="py-3.5 px-4">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold border ${channelMeta.color}`}>
                            <ChannelIcon className="w-3 h-3" />
                            {channelMeta.label}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 max-w-xs text-slate-600">
                          <div className="font-medium text-slate-800">{req.estimated_volume || "Not specified"}</div>
                          <div className="text-[11px] text-slate-400 truncate max-w-[200px]" title={req.business_justification || ""}>
                            {req.business_justification || "No justification provided"}
                          </div>
                        </td>
                        <td className="py-3.5 px-4 text-slate-500 whitespace-nowrap">
                          {new Date(req.created_at).toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                          })}
                        </td>
                        <td className="py-3.5 px-4">
                          {req.status === "pending" && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                              <Clock className="w-3 h-3" /> Pending Review
                            </span>
                          )}
                          {req.status === "approved" && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                              <CheckCircle2 className="w-3 h-3" /> Approved
                            </span>
                          )}
                          {req.status === "rejected" && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
                              <XCircle className="w-3 h-3" /> Declined
                            </span>
                          )}
                        </td>
                        <td className="py-3.5 px-4 text-right">
                          <Button
                            variant={req.status === "pending" ? "primary" : "outline"}
                            size="sm"
                            onClick={() => handleOpenReview(req)}
                            className="text-xs h-7 gap-1"
                          >
                            {req.status === "pending" ? "Review" : "View Details"}
                            <ArrowRight className="w-3 h-3" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Review Modal */}
        <Modal
          isOpen={Boolean(selectedRequest)}
          onClose={() => setSelectedRequest(null)}
          title={`Review Channel Request: ${selectedRequest?.channel.toUpperCase()}`}
          description={`Organization: ${selectedRequest?.organization_name || selectedRequest?.organization_id}`}
          maxWidth="lg"
        >
          {selectedRequest && (
            <div className="space-y-4 py-1 text-sm">
              {/* Request Metadata */}
              <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 rounded-lg border border-slate-200 text-xs">
                <div>
                  <span className="text-slate-400 block mb-0.5">Requester Email:</span>
                  <span className="font-semibold text-slate-800">{selectedRequest.requesting_user_email || "N/A"}</span>
                </div>
                <div>
                  <span className="text-slate-400 block mb-0.5">Submitted Date:</span>
                  <span className="font-medium text-slate-800">{new Date(selectedRequest.created_at).toLocaleString()}</span>
                </div>
                <div>
                  <span className="text-slate-400 block mb-0.5">Requested Volume:</span>
                  <span className="font-semibold text-slate-800">{selectedRequest.estimated_volume || "Not specified"}</span>
                </div>
                <div>
                  <span className="text-slate-400 block mb-0.5">Current Status:</span>
                  <span className="font-bold uppercase tracking-wider">{selectedRequest.status}</span>
                </div>
              </div>

              {/* Justification */}
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Business Justification:</label>
                <div className="p-3 bg-white rounded-lg border border-slate-200 text-xs text-slate-700 italic leading-relaxed">
                  "{selectedRequest.business_justification || "No explicit justification submitted."}"
                </div>
              </div>

              {/* If already finalized */}
              {selectedRequest.status !== "pending" && (
                <div className={`p-3.5 rounded-lg border text-xs ${
                  selectedRequest.status === "approved"
                    ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                    : "bg-rose-50 border-rose-200 text-rose-800"
                }`}>
                  <div className="font-bold flex items-center gap-1.5 mb-1">
                    {selectedRequest.status === "approved" ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                    Decision: {selectedRequest.status.toUpperCase()}
                  </div>
                  {selectedRequest.reviewed_at && (
                    <div className="text-[11px] opacity-90">
                      Reviewed on: {new Date(selectedRequest.reviewed_at).toLocaleString()}
                    </div>
                  )}
                  {selectedRequest.rejection_reason && (
                    <div className="mt-1.5 pt-1.5 border-t border-rose-200/60">
                      <strong>Rejection Reason:</strong> {selectedRequest.rejection_reason}
                    </div>
                  )}
                  {selectedRequest.admin_notes && (
                    <div className="mt-1 text-[11px] opacity-80">
                      <strong>Notes:</strong> {selectedRequest.admin_notes}
                    </div>
                  )}
                </div>
              )}

              {/* If pending: Decision Workspace */}
              {selectedRequest.status === "pending" && (
                <div className="space-y-4 pt-2 border-t border-slate-200">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => { setDecisionMode("approve"); setConfirmSubmitting(false); }}
                      className={`flex-1 py-2 px-3 rounded-lg border text-xs font-semibold flex items-center justify-center gap-1.5 transition-all ${
                        decisionMode === "approve"
                          ? "bg-emerald-50 border-emerald-300 text-emerald-700 shadow-xs"
                          : "border-slate-200 text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" /> Approve & Unlock Channel
                    </button>
                    <button
                      type="button"
                      onClick={() => { setDecisionMode("reject"); setConfirmSubmitting(false); }}
                      className={`flex-1 py-2 px-3 rounded-lg border text-xs font-semibold flex items-center justify-center gap-1.5 transition-all ${
                        decisionMode === "reject"
                          ? "bg-rose-50 border-rose-300 text-rose-700 shadow-xs"
                          : "border-slate-200 text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      <XCircle className="w-3.5 h-3.5" /> Decline Request
                    </button>
                  </div>

                  {decisionMode === "approve" && (
                    <div className="space-y-3 bg-emerald-50/50 p-3 rounded-lg border border-emerald-100">
                      <div>
                        <label className="text-xs font-semibold text-slate-700 block mb-1">
                          Allocated Monthly Quota (Messages / Units):
                        </label>
                        <input
                          type="number"
                          value={quotaInput}
                          onChange={(e) => setQuotaInput(e.target.value)}
                          min="1"
                          className="w-full text-xs px-3 py-2 rounded border border-slate-300 focus:outline-hidden focus:ring-1 focus:ring-emerald-500 bg-white"
                          placeholder="e.g. 5000"
                        />
                        <span className="text-[10px] text-slate-400 mt-0.5 block">
                          Determines the consumption ceiling for this billing cycle.
                        </span>
                      </div>
                      <div>
                        <label className="text-xs font-semibold text-slate-700 block mb-1">Internal Operations Notes (Optional):</label>
                        <input
                          type="text"
                          value={adminNotes}
                          onChange={(e) => setAdminNotes(e.target.value)}
                          className="w-full text-xs px-3 py-1.5 rounded border border-slate-300 bg-white"
                          placeholder="e.g. 10DLC registration verified with Twilio"
                        />
                      </div>
                    </div>
                  )}

                  {decisionMode === "reject" && (
                    <div className="space-y-3 bg-rose-50/50 p-3 rounded-lg border border-rose-100">
                      <div>
                        <label className="text-xs font-semibold text-slate-700 block mb-1">
                          Mandatory Reason for Declining:
                        </label>
                        <textarea
                          rows={2}
                          value={rejectionReason}
                          onChange={(e) => setRejectionReason(e.target.value)}
                          className="w-full text-xs px-3 py-2 rounded border border-slate-300 focus:outline-hidden focus:ring-1 focus:ring-rose-500 bg-white"
                          placeholder="e.g. High bounce rates on initial email sequence; account requires 30 days seasoning."
                        />
                      </div>
                    </div>
                  )}

                  {/* Errors / Success Alerts */}
                  {actionError && (
                    <div className="rounded bg-rose-50 border border-rose-200 p-2 text-xs text-rose-700 flex items-center gap-1.5">
                      <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                      {actionError}
                    </div>
                  )}
                  {actionSuccess && (
                    <div className="rounded bg-emerald-50 border border-emerald-200 p-2 text-xs text-emerald-700 flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                      {actionSuccess}
                    </div>
                  )}

                  {/* Submission Confirmation Bar */}
                  {!confirmSubmitting ? (
                    <Button
                      onClick={() => setConfirmSubmitting(true)}
                      className={`w-full text-xs h-9 ${
                        decisionMode === "approve"
                          ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                          : "bg-rose-600 hover:bg-rose-700 text-white"
                      }`}
                    >
                      {decisionMode === "approve" ? "Review & Confirm Approval" : "Review & Confirm Decline"}
                    </Button>
                  ) : (
                    <div className="p-3 bg-slate-100 rounded-lg border border-slate-300 space-y-2 text-xs">
                      <p className="font-semibold text-slate-800">
                        Confirm Action: Are you sure you want to {decisionMode === "approve" ? "APPROVE and UNLOCK" : "DECLINE"} this channel for {selectedRequest.organization_name}?
                      </p>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          disabled={actionLoading}
                          onClick={handleSubmitDecision}
                          className={`flex-1 text-xs h-8 ${
                            decisionMode === "approve"
                              ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                              : "bg-rose-600 hover:bg-rose-700 text-white"
                          }`}
                        >
                          {actionLoading ? "Executing..." : "Yes, Submit Decision"}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={actionLoading}
                          onClick={() => setConfirmSubmitting(false)}
                          className="text-xs h-8"
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </Modal>
      </div>
    </AppShell>
  );
}
