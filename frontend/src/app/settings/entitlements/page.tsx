"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Card } from "@/components/ui/card";
import {
  ChannelCapability,
  ChannelListResponse,
  getChannelCapabilities,
  getMyUpgradeRequests,
  submitUpgradeRequest,
  UpgradeRequestDetail,
} from "@/services/entitlementsService";
import {
  CheckCircle2,
  Lock,
  Clock,
  XCircle,
  MessageSquare,
  PhoneCall,
  Mail,
  FileText,
  Sliders,
  AlertCircle,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  RefreshCw,
} from "lucide-react";

export default function CustomerEntitlementsPage() {
  const [capabilities, setCapabilities] = useState<ChannelListResponse | null>(null);
  const [myRequests, setMyRequests] = useState<UpgradeRequestDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal State
  const [requestModalOpen, setRequestModalOpen] = useState(false);
  const [selectedChannel, setSelectedChannel] = useState<string>("sms");
  const [estimatedVolume, setEstimatedVolume] = useState("");
  const [justification, setJustification] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);
  const [modalSuccess, setModalSuccess] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [caps, reqs] = await Promise.all([
        getChannelCapabilities(),
        getMyUpgradeRequests().catch(() => []),
      ]);
      setCapabilities(caps);
      setMyRequests(reqs);
    } catch (err: any) {
      setError(err.message || "Failed to load channel entitlements.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleOpenRequest = (channelKey: string) => {
    setSelectedChannel(channelKey);
    setEstimatedVolume("");
    setJustification("");
    setModalError(null);
    setModalSuccess(null);
    setRequestModalOpen(true);
  };

  const handleRequestSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalError(null);
    setModalSuccess(null);

    if (!justification.trim()) {
      setModalError("Please provide a brief business justification for this channel.");
      return;
    }

    try {
      setSubmitting(true);
      const resp = await submitUpgradeRequest({
        channel: selectedChannel,
        estimated_volume: estimatedVolume.trim() || undefined,
        justification: justification.trim(),
      });
      setModalSuccess(resp.message || "Request submitted successfully!");
      setTimeout(() => {
        setRequestModalOpen(false);
        loadData();
      }, 1200);
    } catch (err: any) {
      setModalError(err.message || "Failed to submit upgrade request.");
    } finally {
      setSubmitting(false);
    }
  };

  const getChannelIcon = (ch: string) => {
    switch (ch.toLowerCase()) {
      case "email":
        return Mail;
      case "sms":
        return MessageSquare;
      case "voice":
        return PhoneCall;
      case "ringless_voicemail":
        return Sliders;
      case "physical_mail":
        return FileText;
      default:
        return Sparkles;
    }
  };

  return (
    <AppShell>
      <div className="space-y-6 max-w-6xl mx-auto pb-12">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
                <ShieldCheck className="w-3 h-3" /> Multi-Tenant SaaS Plan
              </span>
              <span className="text-xs text-slate-400 font-medium">Billing Tier: {capabilities?.billing_status || "Trial"}</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-header">Communication Channels & Entitlements</h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Manage your active outbound distribution channels and request carrier unlock for advanced cadences.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={loadData} disabled={loading} className="gap-2">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>

        {error && (
          <div className="rounded-lg bg-rose-50 border border-rose-200 p-3.5 flex items-start gap-2.5 text-xs text-rose-800">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Channel Capabilities Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {capabilities?.channels.map((ch) => {
            const Icon = getChannelIcon(ch.channel);
            const isEmail = ch.channel === "email";

            return (
              <Card key={ch.channel} className="p-5 flex flex-col justify-between border-slate-200 hover:border-slate-300 transition-all shadow-xs">
                <div>
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="w-9 h-9 rounded-lg bg-slate-100 flex items-center justify-center text-slate-700 shrink-0">
                      <Icon className="w-4 h-4" />
                    </div>
                    <div>
                      {ch.is_unlocked ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <CheckCircle2 className="w-3 h-3" /> Active / Unlocked
                        </span>
                      ) : ch.status === "provider_unavailable" ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-500 border border-slate-200">
                          <Clock className="w-3 h-3" /> In Development
                        </span>
                      ) : ch.status === "upgrade_requested" ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                          <Clock className="w-3 h-3" /> Review Pending
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
                          <Lock className="w-3 h-3" /> Upgrade Required
                        </span>
                      )}
                    </div>
                  </div>

                  <h3 className="font-bold text-sm text-header mb-1">{ch.display_name}</h3>
                  <p className="text-xs text-slate-500 mb-3 leading-relaxed min-h-[40px]">{ch.description}</p>

                  <div className="text-[11px] space-y-1.5 py-2.5 border-y border-slate-100 mb-3">
                    <div className="flex justify-between text-slate-600">
                      <span className="text-slate-400">Provider:</span>
                      <span className="font-medium">{ch.provider}</span>
                    </div>
                    <div className="flex justify-between items-start text-slate-600">
                      <span className="text-slate-400">Connection Status:</span>
                      <span className={`font-medium text-right text-[10px] max-w-[170px] truncate ${
                        ch.provider_configured ? "text-emerald-700" : "text-amber-700"
                      }`} title={ch.provider_status_message || (ch.provider_configured ? "Connected" : "Setup Required")}>
                        {ch.provider_status_message || (ch.provider_configured ? "Connected" : "Setup Required")}
                      </span>
                    </div>
                    <div className="flex justify-between text-slate-600">
                      <span className="text-slate-400">Pricing Model:</span>
                      <span className="font-medium text-right truncate max-w-[170px]" title={ch.pricing_model}>{ch.pricing_model}</span>
                    </div>
                    {ch.allocated_quota !== undefined && ch.allocated_quota !== null && (
                      <div className="flex justify-between text-slate-600">
                        <span className="text-slate-400">Monthly Quota:</span>
                        <span className="font-semibold text-emerald-700">{ch.allocated_quota.toLocaleString()} units</span>
                      </div>
                    )}
                  </div>

                  <div className="space-y-1 mb-4">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block">Key Features</span>
                    <ul className="text-[11px] text-slate-600 space-y-0.5">
                      {ch.features.slice(0, 3).map((f, i) => (
                        <li key={i} className="flex items-center gap-1.5 truncate">
                          <span className="w-1 h-1 rounded-full bg-agile-red shrink-0" />
                          <span className="truncate">{f}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div>
                  {ch.is_unlocked ? (
                    <div className="text-center py-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50/60 rounded-md border border-emerald-100">
                      Ready for Campaign Sequences
                    </div>
                  ) : ch.status === "provider_unavailable" ? (
                    <div className="text-center py-1.5 text-xs font-medium text-slate-400 bg-slate-50 rounded-md border border-slate-200">
                      Provider Under Development
                    </div>
                  ) : ch.status === "upgrade_requested" ? (
                    <div className="text-center py-1.5 text-xs font-medium text-amber-700 bg-amber-50/60 rounded-md border border-amber-200">
                      Awaiting Platform Review
                    </div>
                  ) : (
                    <Button
                      onClick={() => handleOpenRequest(ch.channel)}
                      className="w-full text-xs h-8 gap-1.5 bg-agile-red hover:bg-agile-red/90 text-white"
                    >
                      Request Channel Access
                      <ArrowRight className="w-3 h-3" />
                    </Button>
                  )}
                </div>
              </Card>
            );
          })}
        </div>

        {/* Upgrade Requests History */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-xs overflow-hidden pt-4">
          <div className="px-5 pb-3 border-b border-slate-100 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-header">Upgrade Request History</h2>
              <p className="text-xs text-slate-400">Status of your channel activation submissions to platform operations.</p>
            </div>
          </div>

          {myRequests.length === 0 ? (
            <div className="py-12 text-center text-slate-400">
              <Clock className="w-6 h-6 mx-auto mb-1.5 opacity-40" />
              <p className="text-xs font-medium">No upgrade requests submitted yet.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 uppercase font-semibold">
                  <tr>
                    <th className="py-2.5 px-4">Channel</th>
                    <th className="py-2.5 px-4">Estimated Volume</th>
                    <th className="py-2.5 px-4">Justification</th>
                    <th className="py-2.5 px-4">Date</th>
                    <th className="py-2.5 px-4">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {myRequests.map((req) => (
                    <tr key={req.id}>
                      <td className="py-3 px-4 font-bold uppercase">{req.channel}</td>
                      <td className="py-3 px-4 text-slate-700">{req.estimated_volume || "Not specified"}</td>
                      <td className="py-3 px-4 text-slate-600 truncate max-w-xs" title={req.business_justification || ""}>
                        {req.business_justification || "—"}
                      </td>
                      <td className="py-3 px-4 text-slate-500">{new Date(req.created_at).toLocaleDateString()}</td>
                      <td className="py-3 px-4">
                        {req.status === "pending" && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                            Pending Review
                          </span>
                        )}
                        {req.status === "approved" && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            Approved & Unlocked
                          </span>
                        )}
                        {req.status === "rejected" && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200" title={req.rejection_reason || ""}>
                            Declined
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Request Access Modal */}
        <Modal
          isOpen={requestModalOpen}
          onClose={() => setRequestModalOpen(false)}
          title={`Request Access: ${selectedChannel.toUpperCase()}`}
          description="Submit a request to platform operations to activate this outbound communication channel."
          maxWidth="md"
        >
          <form onSubmit={handleRequestSubmit} className="space-y-4 py-1 text-xs">
            <div>
              <label className="font-semibold text-slate-700 block mb-1">Target Channel:</label>
              <select
                value={selectedChannel}
                onChange={(e) => setSelectedChannel(e.target.value)}
                className="w-full px-3 py-2 rounded border border-slate-300 bg-slate-50 font-medium"
              >
                <option value="sms">SMS & MMS Outreach (Twilio)</option>
                <option value="voice">AI Voice SDR Calls (Retell AI)</option>
                <option value="ringless_voicemail">Ringless Voicemail (RVM)</option>
                <option value="physical_mail">Physical Direct Mail (Poplar)</option>
              </select>
            </div>

            <div>
              <label className="font-semibold text-slate-700 block mb-1">Estimated Monthly Volume:</label>
              <input
                type="text"
                value={estimatedVolume}
                onChange={(e) => setEstimatedVolume(e.target.value)}
                placeholder="e.g. 2,500 messages / month"
                className="w-full px-3 py-2 rounded border border-slate-300 focus:outline-hidden focus:ring-1 focus:ring-agile-red"
              />
            </div>

            <div>
              <label className="font-semibold text-slate-700 block mb-1">
                Business Justification & Use Case <span className="text-rose-500">*</span>:
              </label>
              <textarea
                rows={3}
                required
                value={justification}
                onChange={(e) => setJustification(e.target.value)}
                placeholder="Describe your intended outreach cadence, target prospects, and sender compliance."
                className="w-full px-3 py-2 rounded border border-slate-300 focus:outline-hidden focus:ring-1 focus:ring-agile-red"
              />
            </div>

            {modalError && (
              <div className="rounded bg-rose-50 border border-rose-200 p-2.5 text-rose-700 flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                {modalError}
              </div>
            )}
            {modalSuccess && (
              <div className="rounded bg-emerald-50 border border-emerald-200 p-2.5 text-emerald-700 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                {modalSuccess}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <Button type="button" variant="outline" size="sm" onClick={() => setRequestModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={submitting}>
                {submitting ? "Submitting..." : "Submit Upgrade Request"}
              </Button>
            </div>
          </form>
        </Modal>
      </div>
    </AppShell>
  );
}
