"use client";

import * as React from "react";
import {
  OutreachItem,
  OUTREACH_CHANNEL_LABELS,
  OUTREACH_STATUS_LABELS,
  OUTREACH_EVENT_LABELS,
  CALL_OUTCOME_LABELS,
  getOutreachProvenance,
} from "@/services/outreachService";
import { Badge } from "@/components/ui/badge";
import {
  X,
  Mail,
  PhoneCall,
  MessageSquare,
  Share2,
  Calendar,
  CheckCircle2,
  Clock,
  AlertCircle,
  FileText,
  Radio,
  Server,
  User,
  Building2,
  ArrowRight,
  ExternalLink,
} from "lucide-react";

export interface OutreachDetailDrawerProps {
  outreach: OutreachItem | null;
  isOpen: boolean;
  onClose: () => void;
}

export const OutreachDetailDrawer: React.FC<OutreachDetailDrawerProps> = ({
  outreach,
  isOpen,
  onClose,
}) => {
  const [activeTab, setActiveTab] = React.useState<"overview" | "message" | "voice" | "timeline">(
    "overview"
  );

  // ESC handler
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (isOpen) {
      document.body.style.overflow = "hidden";
      window.addEventListener("keydown", handleKeyDown);
    } else {
      document.body.style.overflow = "unset";
    }
    return () => {
      document.body.style.overflow = "unset";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  // Reset tab on item change
  React.useEffect(() => {
    if (outreach) {
      setActiveTab("overview");
    }
  }, [outreach?.id]);

  if (!isOpen || !outreach) return null;

  const formatDate = (iso?: string | null) => {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      });
    } catch {
      return iso;
    }
  };

  const getChannelIcon = (ch: string) => {
    switch (ch) {
      case "email":
        return <Mail className="w-3.5 h-3.5" />;
      case "voice":
        return <PhoneCall className="w-3.5 h-3.5 text-emerald-600" />;
      case "sms":
        return <MessageSquare className="w-3.5 h-3.5 text-blue-600" />;
      case "linkedin":
        return <Share2 className="w-3.5 h-3.5 text-sky-600" />;
      default:
        return <Mail className="w-3.5 h-3.5" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "sent": {
        if (outreach?.provider === "mock") {
          return (
            <Badge className="bg-amber-50 text-amber-700 border-amber-200">
              <Radio className="w-3 h-3 mr-1" />
              Simulated (Mock)
            </Badge>
          );
        }
        if (outreach?.firstDeliveredAt) {
          return (
            <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200">
              <CheckCircle2 className="w-3 h-3 mr-1" />
              Delivered
            </Badge>
          );
        }
        return (
          <Badge className="bg-sky-50 text-sky-700 border-sky-200">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            Sent (Submitted)
          </Badge>
        );
      }
      case "delivered":
        return (
          <Badge className="bg-teal-50 text-teal-700 border-teal-200">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            Delivered
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
      default:
        return (
          <Badge className="bg-slate-100 text-slate-700 border-slate-200">
            {OUTREACH_STATUS_LABELS[outreach.status] || outreach.status}
          </Badge>
        );
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/30 backdrop-blur-xs transition-opacity animate-in fade-in duration-150"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer Surface */}
      <div className="relative w-full max-w-xl bg-white h-full shadow-2xl border-l border-slate-200 z-10 flex flex-col overflow-hidden animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-5 border-b border-slate-100 flex items-start justify-between gap-3 bg-slate-50/50">
          <div>
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Outreach Record
              </span>
              <span className="text-slate-300">•</span>
              <span className="font-mono text-[11px] text-slate-400">
                {outreach.id.substring(0, 8)}...
              </span>
              <span className="text-slate-300">•</span>
              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-600 bg-white px-2 py-0.5 rounded border border-slate-200">
                {getChannelIcon(outreach.channel)}
                {OUTREACH_CHANNEL_LABELS[outreach.channel] || outreach.channel}
              </span>
            </div>

            <h2 className="text-lg font-bold text-header leading-tight">
              {outreach.contactName || outreach.recipient}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5 font-mono">
              {outreach.recipient}
            </p>
          </div>

          <div className="flex items-center gap-2">
            {getStatusBadge(outreach.status)}
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              aria-label="Close drawer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="px-5 border-b border-slate-200 bg-white flex gap-4">
          <button
            type="button"
            onClick={() => setActiveTab("overview")}
            className={`py-3 text-xs font-semibold border-b-2 transition-colors ${
              activeTab === "overview"
                ? "border-agile-red text-agile-red"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Overview
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("message")}
            className={`py-3 text-xs font-semibold border-b-2 transition-colors ${
              activeTab === "message"
                ? "border-agile-red text-agile-red"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Message Content
          </button>
          {outreach.callRecord && (
            <button
              type="button"
              onClick={() => setActiveTab("voice")}
              className={`py-3 text-xs font-semibold border-b-2 transition-colors flex items-center gap-1.5 ${
                activeTab === "voice"
                  ? "border-agile-red text-agile-red"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <PhoneCall className="w-3 h-3 text-emerald-600" />
              Linked Voice Call
            </button>
          )}
          <button
            type="button"
            onClick={() => setActiveTab("timeline")}
            className={`py-3 text-xs font-semibold border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === "timeline"
                ? "border-agile-red text-agile-red"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Events & Audit
            <span className="px-1.5 py-0.2 bg-slate-100 text-slate-600 rounded-full text-[10px]">
              {outreach.events.length}
            </span>
          </button>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* TAB 1: OVERVIEW */}
          {activeTab === "overview" && (
            <div className="space-y-6">
              {/* Provenance & Delivery Verification Card */}
              {(() => {
                const prov = getOutreachProvenance(outreach);
                return (
                  <div
                    className={`border rounded-xl p-4 space-y-2.5 ${
                      prov.classification === "test_fixture"
                        ? "bg-amber-50/60 border-amber-200"
                        : prov.classification === "unverified"
                        ? "bg-amber-50/60 border-amber-200"
                        : prov.classification === "draft"
                        ? "bg-slate-50/70 border-slate-200"
                        : "bg-emerald-50/40 border-emerald-200"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 text-slate-500" />
                        Provenance & Verification
                      </h3>
                      <Badge variant={prov.badgeVariant}>{prov.badgeLabel}</Badge>
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed">
                      {prov.explanation}
                    </p>
                    <div className="text-[11px] font-mono text-slate-500 space-y-0.5 pt-2 border-t border-slate-200/60">
                      <div><span className="text-slate-400">Record ID:</span> {outreach.id}</div>
                      <div><span className="text-slate-400">Org ID:</span> {outreach.organizationId}</div>
                      {outreach.callRecord && (
                        <div><span className="text-slate-400">Retell Call ID:</span> {outreach.callRecord.callId}</div>
                      )}
                    </div>
                  </div>
                );
              })()}

              {/* Recipient & Campaign Card */}
              <div className="bg-slate-50/70 border border-slate-200 rounded-xl p-4 space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  Target Information
                </h3>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <span className="text-slate-400 block mb-0.5">Recipient Contact</span>
                    <span className="font-semibold text-slate-800 flex items-center gap-1.5">
                      <User className="w-3.5 h-3.5 text-slate-400" />
                      {outreach.contactName}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">Email Address</span>
                    <span className="font-mono text-slate-700">{outreach.recipient}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">Company Account</span>
                    <span className="text-slate-800 flex items-center gap-1.5 font-medium">
                      <Building2 className="w-3.5 h-3.5 text-slate-400" />
                      {outreach.companyName || "—"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">Originating Campaign</span>
                    <span className="text-slate-800 font-medium">
                      {outreach.campaignName || "Standalone Outreach"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Delivery Provider Card */}
              <div className="border border-slate-200 rounded-xl p-4 space-y-3 bg-white">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                  <Server className="w-3.5 h-3.5 text-slate-400" />
                  Provider Dispatch
                </h3>
                <div className="space-y-2.5 text-xs">
                  <div className="flex items-center justify-between py-1 border-b border-slate-100">
                    <span className="text-slate-500">Outreach Channel</span>
                    <span className="font-semibold text-slate-800 uppercase tracking-wide">
                      {outreach.channel}
                    </span>
                  </div>
                  <div className="flex items-center justify-between py-1 border-b border-slate-100">
                    <span className="text-slate-500">Delivery Provider</span>
                    <span className="font-mono text-slate-700 bg-slate-100 px-2 py-0.5 rounded">
                      {outreach.provider || "—"}
                    </span>
                  </div>
                  <div className="flex flex-col gap-1 py-1 border-b border-slate-100">
                    <span className="text-slate-500">Provider Message ID</span>
                    <span className="font-mono text-[11px] text-slate-600 break-all bg-slate-50 p-1.5 rounded border border-slate-100">
                      {outreach.providerMessageId || "—"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Lifecycle Timestamps */}
              <div className="border border-slate-200 rounded-xl p-4 space-y-3 bg-white">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  Lifecycle Timestamps
                </h3>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <span className="text-slate-400 block mb-0.5">Created</span>
                    <span className="text-slate-700">{formatDate(outreach.createdAt)}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">Dispatched / Sent</span>
                    <span className="text-slate-700">{formatDate(outreach.sentAt)}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">Delivered (Provider Webhook)</span>
                    <span className="text-slate-700">
                      {outreach.firstDeliveredAt ? (
                        <span className="text-teal-700 font-medium">
                          {formatDate(outreach.firstDeliveredAt)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">First Opened</span>
                    <span className="text-slate-700">{formatDate(outreach.firstOpenedAt)}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">First Clicked</span>
                    <span className="text-slate-700">{formatDate(outreach.firstClickedAt)}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">First Replied</span>
                    <span className="text-slate-700">{formatDate(outreach.firstRepliedAt)}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">Bounced</span>
                    <span className="text-slate-700">{formatDate(outreach.firstBouncedAt)}</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: MESSAGE CONTENT */}
          {activeTab === "message" && (
            <div className="space-y-4">
              <div className="border border-slate-200 rounded-xl overflow-hidden bg-white">
                {outreach.subject && (
                  <div className="p-4 bg-slate-50 border-b border-slate-200">
                    <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                      Subject
                    </span>
                    <h4 className="text-sm font-semibold text-header">
                      {outreach.subject}
                    </h4>
                  </div>
                )}

                <div className="p-4">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-2">
                    Body Content
                  </span>
                  {outreach.body ? (
                    <div className="bg-slate-50/60 p-4 rounded-lg border border-slate-100 font-sans text-xs text-slate-700 leading-relaxed whitespace-pre-wrap">
                      {outreach.body}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-400 italic">
                      No message body content recorded for this outreach.
                    </p>
                  )}
                </div>
              </div>

              {/* Inbound Reply Received */}
              {(() => {
                const replyEvt = outreach.events.find((e) => e.eventType === "replied");
                if (!replyEvt && !outreach.firstRepliedAt) return null;
                const rMeta = (replyEvt?.metadata || {}) as Record<string, any>;
                const rBody = rMeta.body || rMeta.snippet;
                const rSubj = rMeta.subject;
                const rSender = rMeta.from_email || outreach.recipient;

                return (
                  <div className="border border-purple-200 rounded-xl overflow-hidden bg-purple-50/30">
                    <div className="p-3.5 bg-purple-100/60 border-b border-purple-200 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <MessageSquare className="w-4 h-4 text-purple-700" />
                        <span className="text-xs font-bold text-purple-900">
                          Inbound Prospect Reply
                        </span>
                      </div>
                      <span className="text-[11px] font-mono text-purple-700">
                        {formatDate(replyEvt?.occurredAt || outreach.firstRepliedAt)}
                      </span>
                    </div>
                    <div className="p-4 space-y-2">
                      {rSubj && (
                        <div className="text-xs font-semibold text-slate-800">
                          Subject: {rSubj}
                        </div>
                      )}
                      <div className="text-[11px] text-slate-500 font-mono">
                        From: {rSender}
                      </div>
                      <div className="bg-white p-3.5 rounded-lg border border-purple-200 font-sans text-xs text-slate-700 leading-relaxed whitespace-pre-wrap">
                        {rBody || "(Reply event recorded from prospect)"}
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          )}

          {/* TAB 3: LINKED VOICE CALL */}
          {activeTab === "voice" && outreach.callRecord && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
                    <PhoneCall className="w-3.5 h-3.5 text-emerald-600" />
                    Retell Telephony Session
                  </span>
                  {outreach.callRecord.callOutcome && (
                    <Badge className="bg-emerald-100 text-emerald-800 border-emerald-300 font-semibold">
                      {CALL_OUTCOME_LABELS[outreach.callRecord.callOutcome] ||
                        outreach.callRecord.callOutcome}
                    </Badge>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs bg-white p-3 rounded-lg border border-slate-200">
                  <div>
                    <span className="text-slate-400 block mb-0.5">Call ID</span>
                    <span className="font-mono text-slate-700 break-all text-[11px]">
                      {outreach.callRecord.callId}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">Direction</span>
                    <span className="capitalize font-semibold text-slate-800">
                      {outreach.callRecord.direction}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">Call Status</span>
                    <span className="capitalize text-slate-700">
                      {outreach.callRecord.callStatus}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">Duration</span>
                    <span className="text-slate-700">
                      {outreach.callRecord.durationMs
                        ? `${Math.round(outreach.callRecord.durationMs / 1000)}s`
                        : "—"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">Caller Phone</span>
                    <span className="font-mono text-slate-700">
                      {outreach.callRecord.callerPhone || outreach.callRecord.toPhone || "—"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block mb-0.5">Follow-up Status</span>
                    <span className="text-slate-700 capitalize">
                      {outreach.callRecord.followupStatus}
                    </span>
                  </div>
                </div>

                {outreach.callRecord.summary && (
                  <div className="p-3 bg-white rounded-lg border border-slate-200">
                    <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                      Call Summary
                    </span>
                    <p className="text-xs text-slate-700 leading-relaxed">
                      {outreach.callRecord.summary}
                    </p>
                  </div>
                )}

                {outreach.callRecord.followupReason && (
                  <div className="p-3 bg-white rounded-lg border border-slate-200">
                    <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                      Deterministic Follow-up Decision
                    </span>
                    <p className="text-xs text-slate-700 font-mono">
                      {outreach.callRecord.followupReason}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 4: TIMELINE / EVENTS */}
          {activeTab === "timeline" && (
            <div className="space-y-4">
              <div className="border border-slate-200 rounded-xl p-4 bg-white">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-4">
                  Lifecycle Audit Trail ({outreach.events.length})
                </h3>

                {outreach.events.length === 0 ? (
                  <div className="text-center py-6 text-xs text-slate-400">
                    No events recorded yet.
                  </div>
                ) : (
                  <div className="relative pl-5 space-y-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
                    {outreach.events.map((evt, idx) => (
                      <div key={evt.id || idx} className="relative group">
                        <div className="absolute -left-5 top-1 w-2.5 h-2.5 rounded-full bg-agile-red ring-4 ring-white" />
                        <div className="space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-slate-800">
                              {OUTREACH_EVENT_LABELS[evt.eventType] || evt.eventType}
                            </span>
                            <span className="text-[11px] font-mono text-slate-400">
                              {formatDate(evt.occurredAt)}
                            </span>
                          </div>

                          <div className="flex items-center gap-2">
                            <span className="text-[11px] font-mono uppercase text-slate-400">
                              event: {evt.eventType}
                            </span>
                          </div>

                          {evt.eventType === "replied" && evt.metadata ? (
                            <div className="mt-2 p-3 bg-purple-50/70 rounded-lg border border-purple-200 text-xs text-purple-900 space-y-1.5">
                              {Boolean((evt.metadata as any).subject) && (
                                <div className="font-semibold text-xs">
                                  Subject: {(evt.metadata as any).subject}
                                </div>
                              )}
                              {Boolean((evt.metadata as any).from_email) && (
                                <div className="text-[11px] text-purple-700 font-mono">
                                  From: {(evt.metadata as any).from_email}
                                </div>
                              )}
                              {Boolean((evt.metadata as any).body || (evt.metadata as any).snippet) && (
                                <div className="bg-white p-2.5 rounded border border-purple-200 text-xs text-slate-700 whitespace-pre-wrap leading-relaxed font-sans">
                                  {(evt.metadata as any).body || (evt.metadata as any).snippet}
                                </div>
                              )}
                            </div>
                          ) : evt.metadata && Object.keys(evt.metadata).length > 0 ? (
                            <div className="mt-2 p-2.5 bg-slate-50 rounded border border-slate-100 text-[11px] font-mono text-slate-600 overflow-x-auto">
                              <pre className="whitespace-pre-wrap">
                                {JSON.stringify(evt.metadata, null, 2)}
                              </pre>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
          <span>Enterprise S&M Outreach Engine</span>
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-slate-700 hover:bg-slate-50 font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
