"use client";

import * as React from "react";
import { AppShell } from "@/components/layout/app-shell";
import {
  getHubSpotStatus,
  triggerHubSpotSync,
  HubSpotStatusResponse,
  HubSpotSyncSummary,
} from "@/services/hubspotService";
import {
  getLinkedInStatus,
  getLinkedInAuthorizeUrl,
  disconnectLinkedIn,
  getLinkedInCapabilities,
  LinkedInStatusResponse,
  LinkedInCapabilitiesResponse,
} from "@/services/linkedinService";
import {
  getPhysicalMailHealth,
  getPhysicalMailStatus,
  PhysicalMailHealth,
} from "@/services/physicalMailService";
import {
  Layers,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Users,
  Building2,
  DollarSign,
  ExternalLink,
  ShieldAlert,
  ShieldCheck,
  ArrowRight,
  Database,
  Lock,
  Clock,
  Sparkles,
  PhoneCall,
  Bot,
  Radio,
  Sliders,
  Mail,
  FileText,
  Calendar,
  Send,
  Copy,
  Info,
} from "lucide-react";

export default function IntegrationsPage() {
  const [status, setStatus] = React.useState<HubSpotStatusResponse | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [isSyncing, setIsSyncing] = React.useState(false);
  const [syncFeedback, setSyncFeedback] = React.useState<{
    type: "success" | "warning" | "error";
    message: string;
    details?: string;
  } | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  // LinkedIn OAuth State
  const [linkedinStatus, setLinkedinStatus] = React.useState<LinkedInStatusResponse | null>(null);
  const [linkedinCapabilities, setLinkedinCapabilities] = React.useState<LinkedInCapabilitiesResponse | null>(null);
  const [isLinkedInLoading, setIsLinkedInLoading] = React.useState(true);
  const [isConnectingLinkedIn, setIsConnectingLinkedIn] = React.useState(false);
  const [isDisconnectingLinkedIn, setIsDisconnectingLinkedIn] = React.useState(false);
  const [linkedinFeedback, setLinkedinFeedback] = React.useState<{
    type: "success" | "warning" | "error";
    message: string;
  } | null>(null);

  // Poplar Direct Mail Health State
  const [poplarHealth, setPoplarHealth] = React.useState<PhysicalMailHealth | null>(null);
  const [isPoplarLoading, setIsPoplarLoading] = React.useState(true);
  const [poplarError, setPoplarError] = React.useState<string | null>(null);

  const fetchStatus = React.useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getHubSpotStatus();
      setStatus(data);
    } catch (err: any) {
      console.error("Error fetching HubSpot status:", err);
      setError(err.message || "Failed to load HubSpot integration status.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchLinkedInData = React.useCallback(async () => {
    setIsLinkedInLoading(true);
    try {
      const [lStatus, lCaps] = await Promise.all([
        getLinkedInStatus().catch((e) => {
          console.warn("LinkedIn status error:", e);
          return {
            configured: false,
            connected: false,
            status: "not_configured" as const,
            message: e.message || "Unable to retrieve status",
          };
        }),
        getLinkedInCapabilities().catch((e) => {
          console.warn("LinkedIn capabilities error:", e);
          return null;
        }),
      ]);
      setLinkedinStatus(lStatus);
      setLinkedinCapabilities(lCaps);
    } catch (err: any) {
      console.warn("LinkedIn data fetch notice:", err);
    } finally {
      setIsLinkedInLoading(false);
    }
  }, []);

  const fetchPoplarHealth = React.useCallback(async () => {
    setIsPoplarLoading(true);
    setPoplarError(null);
    try {
      const health = await getPhysicalMailHealth();
      setPoplarHealth(health);
      if (!health.connected) {
        setPoplarError(health.error || health.message || "Poplar API connection failed");
      }
    } catch (err: any) {
      console.warn("Poplar health check notice:", err);
      const errMsg = err.message || "Failed to query Poplar API";
      setPoplarError(errMsg);
      try {
        const statusData = await getPhysicalMailStatus();
        setPoplarHealth({
          configured: statusData.configured,
          connected: false,
          environment: statusData.environment || "test",
          allow_live_sending: statusData.allow_live_sending,
          message: errMsg,
        });
      } catch {
        setPoplarHealth({
          configured: false,
          connected: false,
          environment: "test",
          allow_live_sending: false,
          message: errMsg,
        });
      }
    } finally {
      setIsPoplarLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (typeof window !== "undefined") {
      const urlParams = new URLSearchParams(window.location.search);
      const liParam = urlParams.get("linkedin");
      const liErr = urlParams.get("linkedin_error");
      if (liParam === "connected") {
        setLinkedinFeedback({
          type: "success",
          message: "LinkedIn account successfully connected via OpenID Connect.",
        });
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (liErr) {
        setLinkedinFeedback({
          type: "error",
          message: `LinkedIn authorization notice: ${decodeURIComponent(liErr)}`,
        });
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    }
    fetchStatus();
    fetchLinkedInData();
    fetchPoplarHealth();
  }, [fetchStatus, fetchLinkedInData, fetchPoplarHealth]);

  const handleConnectLinkedIn = async () => {
    setIsConnectingLinkedIn(true);
    setLinkedinFeedback(null);
    try {
      const { authorization_url } = await getLinkedInAuthorizeUrl();
      if (authorization_url) {
        window.location.href = authorization_url;
      } else {
        throw new Error("Missing authorization URL in response");
      }
    } catch (err: any) {
      console.error("Failed to initiate LinkedIn authorization:", err);
      setLinkedinFeedback({
        type: "error",
        message: err.message || "Failed to initiate LinkedIn authorization.",
      });
      setIsConnectingLinkedIn(false);
    }
  };

  const handleDisconnectLinkedIn = async () => {
    if (!confirm("Are you sure you want to disconnect this LinkedIn account?")) return;
    setIsDisconnectingLinkedIn(true);
    setLinkedinFeedback(null);
    try {
      await disconnectLinkedIn();
      await fetchLinkedInData();
      setLinkedinFeedback({
        type: "success",
        message: "LinkedIn account disconnected successfully.",
      });
    } catch (err: any) {
      console.error("Failed to disconnect LinkedIn:", err);
      setLinkedinFeedback({
        type: "error",
        message: err.message || "Failed to disconnect LinkedIn account.",
      });
    } finally {
      setIsDisconnectingLinkedIn(false);
    }
  };

  const handleSyncNow = async () => {
    setIsSyncing(true);
    setSyncFeedback(null);
    setError(null);
    try {
      const summary: HubSpotSyncSummary = await triggerHubSpotSync();

      // Immediately update status metrics from summary so UI reflects new counts & timestamps instantly
      setStatus((prev) => {
        const updatedContacts = summary.contacts.imported + summary.contacts.updated;
        const updatedCompanies = summary.companies.imported + summary.companies.updated;
        const updatedDeals = summary.deals.imported + summary.deals.updated;

        if (!prev) {
          return {
            configured: true,
            connected: true,
            portal_id: summary.portal_id || "244174914",
            account_type: "STANDARD",
            ui_domain: "app-na2.hubspot.com",
            last_sync: {
              run_id: summary.run_id,
              status: summary.status,
              started_at: summary.started_at,
              completed_at: summary.completed_at,
              contacts_count: updatedContacts,
              companies_count: updatedCompanies,
              deals_count: updatedDeals,
              permission_errors: summary.permission_errors,
            },
            scopes: {
              contacts: {
                readable: summary.contacts.status !== "missing_scope",
                status: summary.contacts.status === "missing_scope" ? "missing_scope" : "active",
                scope_required: "crm.objects.contacts.read",
              },
              companies: {
                readable: summary.companies.status !== "missing_scope",
                status: summary.companies.status === "missing_scope" ? "missing_scope" : "active",
                scope_required: "crm.objects.companies.read",
              },
              deals: {
                readable: summary.deals.status !== "missing_scope",
                status: summary.deals.status === "missing_scope" ? "missing_scope" : "active",
                scope_required: "crm.objects.deals.read",
              },
            },
            message: summary.message,
          };
        }

        return {
          ...prev,
          last_sync: {
            run_id: summary.run_id,
            status: summary.status,
            started_at: summary.started_at,
            completed_at: summary.completed_at,
            contacts_count: updatedContacts,
            companies_count: updatedCompanies,
            deals_count: updatedDeals,
            permission_errors: summary.permission_errors,
          },
        };
      });

      // Background re-fetch of live status
      fetchStatus().catch((err) => console.warn("Background status refresh notice:", err));

      if (summary.status === "completed") {
        setSyncFeedback({
          type: "success",
          message: `HubSpot synchronization finished successfully. Synced ${summary.contacts.imported + summary.contacts.updated} contacts, ${summary.companies.imported + summary.companies.updated} companies, and ${summary.deals.imported + summary.deals.updated} deals.`,
        });
      } else if (summary.status === "partial") {
        const warningMsg = summary.permission_errors?.companies || "Some objects require permissions.";
        setSyncFeedback({
          type: "warning",
          message: `HubSpot sync completed with scope notices: ${summary.contacts.imported + summary.contacts.updated} contacts synced.`,
          details: warningMsg,
        });
      } else {
        setSyncFeedback({
          type: "error",
          message: summary.message || "Synchronization encountered an issue.",
        });
      }
    } catch (err: any) {
      setSyncFeedback({
        type: "error",
        message: err.message || "Failed to trigger synchronization.",
      });
    } finally {
      setIsSyncing(false);
    }
  };

  const formatTimestamp = (isoString?: string | null) => {
    if (!isoString) return "Never";
    try {
      const date = new Date(isoString);
      return date.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return isoString;
    }
  };

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Top Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
              <Layers className="w-4 h-4 text-agile-red" />
              <span>Integrations &amp; External CRMs</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
              CRM Synchronization
            </h1>
            <p className="text-sm text-slate-500 mt-1 max-w-2xl">
              Connect external CRM platforms into Agile Sales &amp; Marketing. Genuine production records are preserved with tenant isolation and duplicate prevention.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                fetchStatus();
                fetchLinkedInData();
                fetchPoplarHealth();
              }}
              disabled={isLoading || isSyncing || isLinkedInLoading || isPoplarLoading}
              className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors disabled:opacity-50 shadow-xs"
              title="Refresh connection status"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading || isLinkedInLoading || isPoplarLoading ? "animate-spin text-agile-red" : "text-slate-500"}`} />
              <span>Refresh</span>
            </button>

            <button
              id="sync-hubspot-btn"
              onClick={handleSyncNow}
              disabled={isSyncing}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-agile-red rounded-lg hover:bg-agile-red/90 transition-all shadow-sm hover:shadow disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSyncing ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Syncing HubSpot...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Sync Now</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Global Error Banner */}
        {error && (
          <div className="p-4 rounded-xl bg-red-50 border border-red-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-red-800">
            <div className="flex items-start gap-3">
              <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
              <div className="text-sm">
                <p className="font-semibold">Connection Check Notice</p>
                <p className="mt-0.5 text-red-700">{error}</p>
              </div>
            </div>
            <button
              onClick={() => fetchStatus()}
              disabled={isLoading}
              className="px-3.5 py-1.5 text-xs font-semibold bg-red-100 hover:bg-red-200 text-red-800 rounded-lg transition-colors border border-red-300 self-start sm:self-auto shrink-0"
            >
              {isLoading ? "Checking..." : "Retry Connection"}
            </button>
          </div>
        )}

        {/* Sync Feedback Alert */}
        {syncFeedback && (
          <div
            className={`p-4 rounded-xl border flex items-start gap-3 text-sm transition-all animate-fadeIn ${
              syncFeedback.type === "success"
                ? "bg-emerald-50 border-emerald-200 text-emerald-900"
                : syncFeedback.type === "warning"
                ? "bg-amber-50 border-amber-200 text-amber-900"
                : "bg-red-50 border-red-200 text-red-900"
            }`}
          >
            {syncFeedback.type === "success" && <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />}
            {syncFeedback.type === "warning" && <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />}
            {syncFeedback.type === "error" && <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />}
            <div className="flex-1">
              <p className="font-semibold">{syncFeedback.message}</p>
              {syncFeedback.details && (
                <p className="mt-1 text-xs opacity-90 leading-relaxed font-mono bg-white/60 p-2 rounded border border-amber-200/50">
                  {syncFeedback.details}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Main HubSpot Connection Card */}
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
          <div className="p-6 sm:p-7 border-b border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="flex items-start gap-4">
              {/* HubSpot Logo Badge */}
              <div className="w-14 h-14 rounded-2xl bg-orange-500/10 border border-orange-500/20 flex items-center justify-center text-orange-600 shrink-0 shadow-inner">
                <svg className="w-8 h-8 fill-current" viewBox="0 0 24 24">
                  <path d="M18.8 7.3c-.9 0-1.7.5-2.1 1.2l-3.3-1.9c.1-.4.2-.8.2-1.2 0-2.3-1.9-4.2-4.2-4.2S5.2 3.1 5.2 5.4c0 .4.1.8.2 1.2L2.1 8.5C1.7 7.8.9 7.3 0 7.3v3.4c.5 0 1-.3 1.3-.7l3.3 1.9c-.1.4-.2.8-.2 1.2 0 2.3 1.9 4.2 4.2 4.2 1.2 0 2.3-.5 3-1.3l3.3 1.9c-.1.4-.2.8-.2 1.2 0 2.3 1.9 4.2 4.2 4.2s4.2-1.9 4.2-4.2-1.9-4.2-4.2-4.2c-1.2 0-2.3.5-3 1.3L12.5 13c.1-.4.2-.8.2-1.2 0-.4-.1-.8-.2-1.2l3.3-1.9c.4.7 1.2 1.2 2.1 1.2 1.4 0 2.5-1.1 2.5-2.5s-1.1-2.5-2.5-2.5zm-9.4.6c-1.4 0-2.5-1.1-2.5-2.5S8 2.9 9.4 2.9s2.5 1.1 2.5 2.5-1.1 2.5-2.5 2.5zm0 6.6c-1.4 0-2.5-1.1-2.5-2.5s1.1-2.5 2.5-2.5 2.5 1.1 2.5 2.5-1.1 2.5-2.5 2.5zm9.4 5.9c-1.4 0-2.5-1.1-2.5-2.5s1.1-2.5 2.5-2.5 2.5 1.1 2.5 2.5-1.1 2.5-2.5 2.5z"/>
                </svg>
              </div>

              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-bold text-slate-900">HubSpot CRM</h2>
                  {isLoading && !status ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
                      <RefreshCw className="w-3 h-3 animate-spin text-agile-red" />
                      Checking status...
                    </span>
                  ) : status?.connected ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      Connected &amp; Authenticated
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
                      <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                      Disconnected
                    </span>
                  )}
                </div>

                <p className="text-xs text-slate-500 mt-1">
                  Private App API Token Authentication &bull; Read-Only Production Sync
                </p>

                {status?.portal_id ? (
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-xs text-slate-600">
                    <span className="font-mono bg-slate-100 px-2 py-0.5 rounded text-slate-700 font-medium">
                      Portal ID: {status.portal_id}
                    </span>
                    {status.account_type && (
                      <span>Tier: <strong className="text-slate-800">{status.account_type}</strong></span>
                    )}
                    {status.ui_domain && (
                      <span className="flex items-center gap-1 text-slate-500">
                        Domain: {status.ui_domain}
                      </span>
                    )}
                  </div>
                ) : isLoading ? (
                  <div className="h-4 w-44 bg-slate-100 animate-pulse rounded mt-2" />
                ) : null}
              </div>
            </div>

            {/* Sync Metadata Box */}
            <div className="bg-slate-50/80 rounded-xl p-3.5 border border-slate-100 flex flex-col gap-1 text-xs md:text-right shrink-0">
              <span className="text-slate-400 font-medium">Last Synchronization</span>
              <span className="font-semibold text-slate-800 font-mono text-xs">
                {isLoading && !status
                  ? "Checking..."
                  : formatTimestamp(status?.last_sync?.completed_at || status?.last_sync?.started_at)}
              </span>
              <div className="flex items-center gap-2 md:justify-end mt-0.5">
                <span className="text-slate-500">Run Status:</span>
                {isLoading && !status ? (
                  <span className="text-slate-500 text-[10px] bg-slate-100 px-1.5 py-0.5 rounded">
                    Checking...
                  </span>
                ) : status?.last_sync?.status === "completed" ? (
                  <span className="text-emerald-700 font-semibold uppercase tracking-wider text-[10px] bg-emerald-100/70 px-1.5 py-0.5 rounded">
                    Completed
                  </span>
                ) : status?.last_sync?.status === "partial" ? (
                  <span className="text-amber-700 font-semibold uppercase tracking-wider text-[10px] bg-amber-100/70 px-1.5 py-0.5 rounded">
                    Partial (Scope Attention)
                  </span>
                ) : (
                  <span className="text-slate-600 font-semibold uppercase tracking-wider text-[10px] bg-slate-200/70 px-1.5 py-0.5 rounded">
                    {status?.last_sync?.status || "Never Run"}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* CRM Object Synchronization Breakdown */}
          <div className="p-6 sm:p-7 space-y-6">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700">
                Synchronized CRM Objects
              </h3>
              <span className="text-xs text-slate-400">
                Data flows one-way: HubSpot &rarr; Agile Sales &amp; Marketing
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              {/* Contacts Card */}
              <div className="rounded-xl border border-slate-200 bg-white p-5 hover:border-slate-300 transition-all flex flex-col justify-between space-y-4">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="w-9 h-9 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                      <Users className="w-5 h-5" />
                    </div>
                    {isLoading && !status ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
                        Checking...
                      </span>
                    ) : status?.scopes?.contacts?.readable ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-100">
                        <CheckCircle2 className="w-3 h-3" />
                        Operational
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-red-700 bg-red-50 px-2 py-0.5 rounded-full border border-red-100">
                        <XCircle className="w-3 h-3" />
                        Unavailable
                      </span>
                    )}
                  </div>

                  <div>
                    <h4 className="font-bold text-slate-900 text-base">Contacts</h4>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Customer prospects &amp; decision makers
                    </p>
                  </div>
                </div>

                <div className="pt-3 border-t border-slate-100 space-y-2">
                  <div className="flex items-baseline justify-between">
                    <span className="text-xs text-slate-500">Imported in DB:</span>
                    <span className="text-xl font-extrabold text-slate-900 font-mono">
                      {isLoading && !status ? "..." : (status?.last_sync?.contacts_count ?? 0)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500">
                    <span>Scope:</span>
                    <span className="font-mono text-slate-600">crm.objects.contacts.read</span>
                  </div>
                </div>
              </div>

              {/* Companies Card */}
              <div className={`rounded-xl border p-5 transition-all flex flex-col justify-between space-y-4 ${
                !isLoading && status?.scopes?.companies?.status === "missing_scope"
                  ? "border-amber-300 bg-amber-50/20"
                  : "border-slate-200 bg-white"
              }`}>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="w-9 h-9 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                      <Building2 className="w-5 h-5" />
                    </div>
                    {isLoading && !status ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
                        Checking...
                      </span>
                    ) : status?.scopes?.companies?.readable ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-100">
                        <CheckCircle2 className="w-3 h-3" />
                        Operational
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                        <AlertTriangle className="w-3 h-3" />
                        Scope Required
                      </span>
                    )}
                  </div>

                  <div>
                    <h4 className="font-bold text-slate-900 text-base">Companies</h4>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Business accounts &amp; enterprise domains
                    </p>
                  </div>
                </div>

                <div className="pt-3 border-t border-slate-100 space-y-2">
                  <div className="flex items-baseline justify-between">
                    <span className="text-xs text-slate-500">Imported in DB:</span>
                    <span className="text-xl font-extrabold text-slate-900 font-mono">
                      {isLoading && !status ? "..." : (status?.last_sync?.companies_count ?? 0)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500">
                    <span>Required Scope:</span>
                    <span className="font-mono text-amber-800 font-semibold">crm.objects.companies.read</span>
                  </div>
                </div>
              </div>

              {/* Deals Card */}
              <div className="rounded-xl border border-slate-200 bg-white p-5 hover:border-slate-300 transition-all flex flex-col justify-between space-y-4">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="w-9 h-9 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                      <DollarSign className="w-5 h-5" />
                    </div>
                    {isLoading && !status ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
                        Checking...
                      </span>
                    ) : status?.scopes?.deals?.readable ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-100">
                        <CheckCircle2 className="w-3 h-3" />
                        Operational
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-red-700 bg-red-50 px-2 py-0.5 rounded-full border border-red-100">
                        <XCircle className="w-3 h-3" />
                        Unavailable
                      </span>
                    )}
                  </div>

                  <div>
                    <h4 className="font-bold text-slate-900 text-base">Deals</h4>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Sales pipeline opportunities &amp; revenue
                    </p>
                  </div>
                </div>

                <div className="pt-3 border-t border-slate-100 space-y-2">
                  <div className="flex items-baseline justify-between">
                    <span className="text-xs text-slate-500">Imported in DB:</span>
                    <div className="text-right">
                      <span className="text-xl font-extrabold text-slate-900 font-mono">
                        {isLoading && !status ? "..." : (status?.last_sync?.deals_count ?? 0)}
                      </span>
                      <span className="text-[10px] text-slate-400 block">
                        (0 in HubSpot portal)
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500">
                    <span>Scope:</span>
                    <span className="font-mono text-slate-600">crm.objects.deals.read</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Actionable Scope Guidance Box */}
            {status?.scopes?.companies?.status === "missing_scope" && (
              <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-5 space-y-3">
                <div className="flex items-start gap-3">
                  <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <h4 className="text-sm font-bold text-amber-900">
                      Permission Required: Company Synchronization
                    </h4>
                    <p className="text-xs text-amber-800 leading-relaxed">
                      HubSpot API returned HTTP 403 Forbidden for Company objects because the active token lacks the read permission for companies. Contacts and deals continue syncing normally.
                    </p>
                  </div>
                </div>

                <div className="bg-white/80 rounded-lg p-3.5 border border-amber-200/60 text-xs text-amber-950 space-y-2 font-sans">
                  <p className="font-semibold text-amber-900 flex items-center gap-1.5">
                    <span>How to apply newly enabled scopes in HubSpot:</span>
                  </p>
                  <ol className="list-decimal list-inside space-y-1.5 text-slate-700 pl-1 leading-relaxed">
                    <li>Log into your HubSpot portal (Portal ID: <strong>{status.portal_id || "244174914"}</strong>).</li>
                    <li>Go to <strong>Settings &gt; Integrations &gt; Private Apps</strong> and open your app.</li>
                    <li>In the <strong>Scopes</strong> tab, confirm <code className="bg-amber-100 text-amber-900 px-1 py-0.5 rounded font-mono font-semibold">crm.objects.companies.read</code> is checked and click <strong>Save changes</strong>.</li>
                    <li><strong className="text-amber-900">Important:</strong> Switch to the <strong>Auth</strong> tab, click <strong>Show token</strong> (or <strong>Rotate token</strong> if prompted), and copy the updated token.</li>
                    <li>Paste the updated token into your backend environment file (<code className="bg-slate-100 text-slate-800 px-1 py-0.5 rounded font-mono">HUBSPOT_ACCESS_TOKEN</code> in <code className="bg-slate-100 text-slate-800 px-1 py-0.5 rounded font-mono">backend/.env</code>).</li>
                    <li>Click <strong>Refresh</strong> or <strong>Sync Now</strong> above to complete company synchronization.</li>
                  </ol>
                </div>
              </div>
            )}

            {/* Architecture & Safety Commitments */}
            <div className="rounded-xl bg-slate-50 p-4 border border-slate-200/60 text-xs text-slate-600 space-y-2">
              <div className="flex items-center gap-2 font-semibold text-slate-800">
                <Database className="w-4 h-4 text-agile-red" />
                <span>Production Safety &amp; Read-Only Guarantees</span>
              </div>
              <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px] text-slate-600 pt-1">
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <strong>Zero-Write to HubSpot:</strong> No records are ever modified or deleted in HubSpot CRM.
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <strong>Idempotent Upsert:</strong> Duplicate records are prevented using external HubSpot object IDs.
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <strong>Tenant Isolation:</strong> Synced CRM records are strictly partitioned to your tenant organization.
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <strong>Data Integrity:</strong> Preserved local records (including voice test leads) are completely protected.
                </li>
              </ul>
            </div>
          </div>
        </div>

        {/* Poplar Direct Mail Card */}
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
          <div className="p-6 sm:p-7 border-b border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="flex items-start gap-4">
              <div className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-600 shrink-0 shadow-inner">
                <Mail className="w-7 h-7" />
              </div>
              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-bold text-slate-900">Poplar Physical Direct Mail</h2>
                  {isPoplarLoading && !poplarHealth ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
                      <RefreshCw className="w-3 h-3 animate-spin text-agile-red" />
                      Checking status...
                    </span>
                  ) : poplarHealth?.connected ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      Connected (Test Sandbox)
                    </span>
                  ) : poplarHealth?.configured ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                      <AlertTriangle className="w-3 h-3 text-amber-600" />
                      Configured &bull; Connectivity Notice
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                      Not Configured
                    </span>
                  )}

                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                    <ShieldCheck className="w-3.5 h-3.5 text-blue-600" />
                    Fail-Closed Safe Mode
                  </span>
                </div>

                <p className="text-xs text-slate-500 mt-1">
                  Automated Direct Mail &bull; Postcards &amp; Letters &bull; USPS CASS Address Validation &bull; Poplar API v1
                </p>

                {poplarHealth?.account_id && (
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-xs text-slate-600">
                    <span className="font-mono bg-slate-100 px-2 py-0.5 rounded text-slate-700 font-medium">
                      Account ID: {poplarHealth.account_id}
                    </span>
                    {poplarHealth.account_name && (
                      <span>Account: <strong className="text-slate-800">{poplarHealth.account_name}</strong></span>
                    )}
                    <span className="inline-flex items-center gap-1 font-mono text-[11px] bg-amber-50 text-amber-800 px-2 py-0.5 rounded border border-amber-200">
                      Env: {poplarHealth.environment.toUpperCase()}
                    </span>
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center gap-3 self-start md:self-auto shrink-0">
              <button
                onClick={fetchPoplarHealth}
                disabled={isPoplarLoading}
                className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg transition-colors disabled:opacity-50 shadow-xs"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isPoplarLoading ? "animate-spin text-amber-600" : "text-slate-500"}`} />
                <span>Verify Connectivity</span>
              </button>
            </div>
          </div>

          <div className="p-6 sm:p-7 space-y-6">
            {poplarError && (
              <div className="p-4 rounded-xl border border-red-200 bg-red-50 text-red-900 flex items-start gap-3 text-sm">
                <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold">Poplar Connection Error</p>
                  <p className="text-xs text-red-700 mt-0.5">{poplarError}</p>
                </div>
              </div>
            )}

            {/* Account & Safety Banner */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 space-y-1">
                <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">Environment</span>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-slate-900 capitalize">{poplarHealth?.environment || "test"}</span>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-emerald-100 text-emerald-800">Sandbox</span>
                </div>
                <p className="text-[11px] text-slate-500">
                  {poplarHealth?.connected
                    ? "Connected to Poplar Test API with zero live postage liability."
                    : "Test sandbox environment configured. Connection verification required."}
                </p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 space-y-1">
                <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">Live Sending Gate</span>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-rose-700">Blocked (Enforced)</span>
                </div>
                <p className="text-[11px] text-slate-500">Live mail delivery disabled (<code className="font-mono text-[10px]">POPLAR_ALLOW_LIVE_SENDING=False</code>).</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 space-y-1">
                <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">Creative Library</span>
                <div className="flex items-center gap-2">
                  {poplarHealth?.connected ? (
                    <>
                      <span className="text-sm font-bold text-slate-900">Synchronized</span>
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-emerald-100 text-emerald-800">Ready</span>
                    </>
                  ) : (
                    <>
                      <span className="text-sm font-bold text-slate-500">Disconnected</span>
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-600">Requires Connection</span>
                    </>
                  )}
                </div>
                <p className="text-[11px] text-slate-500">
                  {poplarHealth?.connected
                    ? "Directly selects verified artwork templates or custom PDFs."
                    : "Creative templates accessible once provider connection is verified."}
                </p>
              </div>
            </div>

            {/* Supported Mailpiece Formats */}
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <FileText className="w-4 h-4 text-amber-600" />
                <span>Supported Mailpiece Formats &amp; Specifications</span>
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                <div className="p-3.5 rounded-xl border border-slate-200/80 bg-white space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-900">4x6 Classic Postcard</span>
                    <span className="text-[11px] font-semibold text-emerald-700 font-mono">~$0.78 / pc</span>
                  </div>
                  <p className="text-[11px] text-slate-500">Dimensions: 4.25&quot; x 6.25&quot; bleed &bull; 1275x1875px at 300 DPI &bull; Premium Coated Gloss</p>
                </div>

                <div className="p-3.5 rounded-xl border border-slate-200/80 bg-white space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-900">6x9 Large Postcard</span>
                    <span className="text-[11px] font-semibold text-emerald-700 font-mono">~$1.15 / pc</span>
                  </div>
                  <p className="text-[11px] text-slate-500">Dimensions: 6.25&quot; x 9.25&quot; bleed &bull; 1875x2775px at 300 DPI &bull; High-impact outreach</p>
                </div>

                <div className="p-3.5 rounded-xl border border-slate-200/80 bg-white space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-900">6x11 Panoramic Postcard</span>
                    <span className="text-[11px] font-semibold text-emerald-700 font-mono">~$1.42 / pc</span>
                  </div>
                  <p className="text-[11px] text-slate-500">Dimensions: 6.25&quot; x 11.25&quot; bleed &bull; 1875x3375px at 300 DPI &bull; Maximum mailbox presence</p>
                </div>

                <div className="p-3.5 rounded-xl border border-slate-200/80 bg-white space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-900">B&amp;W Envelope Letter</span>
                    <span className="text-[11px] font-semibold text-emerald-700 font-mono">~$0.98 / pc</span>
                  </div>
                  <p className="text-[11px] text-slate-500">Dimensions: 8.5&quot; x 11&quot; &bull; #10 Double-window envelope &bull; Formal notices &amp; invoices</p>
                </div>

                <div className="p-3.5 rounded-xl border border-slate-200/80 bg-white space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-900">Full-Color Letter</span>
                    <span className="text-[11px] font-semibold text-emerald-700 font-mono">~$1.25 / pc</span>
                  </div>
                  <p className="text-[11px] text-slate-500">Dimensions: 8.5&quot; x 11&quot; &bull; Full-color double-sided &bull; Executive brand presentation</p>
                </div>

                <div className="p-3.5 rounded-xl border border-slate-200/80 bg-white space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-900">Folded Self-Mailer</span>
                    <span className="text-[11px] font-semibold text-emerald-700 font-mono">~$1.45 / pc</span>
                  </div>
                  <p className="text-[11px] text-slate-500">Bifold or Trifold &bull; Wafer-sealed &bull; Multi-page product brochures</p>
                </div>
              </div>
            </div>

            {/* Safety & Production Guarantees */}
            <div className="rounded-xl bg-slate-50 p-4 border border-slate-200/60 text-xs text-slate-600 space-y-2">
              <div className="flex items-center gap-2 font-semibold text-slate-800">
                <ShieldCheck className="w-4 h-4 text-amber-600" />
                <span>Physical Mail Production &amp; Safety Guarantees</span>
              </div>
              <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px] text-slate-600 pt-1">
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <strong>Explicit Approval Gate:</strong> Dispatches require positive user confirmation and idempotency keys before Poplar submission.
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <strong>CASS Address Validation:</strong> Missing postal codes, invalid state codes, or non-US addresses are flagged before print.
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <strong>Test Environment Enforcement:</strong> Orders in test mode simulate production routing without charging actual postage.
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <strong>Durable Audit Trails:</strong> Mailpiece IDs, proof URLs, and USPS fulfillment events are tracked in PostgreSQL.
                </li>
              </ul>
            </div>
          </div>
        </div>

        {/* LinkedIn Account Integration Card */}
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
          <div className="p-6 sm:p-7 border-b border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="flex items-start gap-4">
              {/* LinkedIn Icon Badge */}
              <div className="w-14 h-14 rounded-2xl bg-[#0077b5]/10 border border-[#0077b5]/20 flex items-center justify-center text-[#0077b5] shrink-0 shadow-inner">
                <svg className="w-7 h-7 fill-current" viewBox="0 0 24 24">
                  <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/>
                </svg>
              </div>

              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-bold text-slate-900">LinkedIn Account Integration</h2>
                  {isLinkedInLoading && !linkedinStatus ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
                      <RefreshCw className="w-3 h-3 animate-spin text-agile-red" />
                      Checking status...
                    </span>
                  ) : linkedinStatus?.connected ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      Connected &amp; Authenticated
                    </span>
                  ) : linkedinStatus?.status === "expired" ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                      <AlertTriangle className="w-3 h-3 text-amber-600" />
                      Token Expired
                    </span>
                  ) : !linkedinStatus?.configured ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                      Not Configured
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                      Disconnected
                    </span>
                  )}
                </div>

                <p className="text-xs text-slate-500 mt-1">
                  OpenID Connect &bull; OAuth 2.0 Authorization Code Flow &bull; Agile Receivables Official Application
                </p>

                {linkedinStatus?.member_id && (
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-xs text-slate-600">
                    <span className="font-mono bg-slate-100 px-2 py-0.5 rounded text-slate-700 font-medium">
                      Member ID: {linkedinStatus.member_id}
                    </span>
                    {linkedinStatus.member_email && (
                      <span>Email: <strong className="text-slate-800">{linkedinStatus.member_email}</strong></span>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Connection Actions */}
            <div className="flex items-center gap-3 self-start md:self-auto shrink-0">
              {linkedinStatus?.connected ? (
                <button
                  onClick={handleDisconnectLinkedIn}
                  disabled={isDisconnectingLinkedIn}
                  className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-rose-700 bg-rose-50 border border-rose-200 hover:bg-rose-100 rounded-lg transition-colors disabled:opacity-50"
                >
                  {isDisconnectingLinkedIn ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Disconnecting...</span>
                    </>
                  ) : (
                    <span>Disconnect Account</span>
                  )}
                </button>
              ) : (
                <button
                  onClick={handleConnectLinkedIn}
                  disabled={isConnectingLinkedIn || !linkedinStatus?.configured}
                  className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-[#0077b5] hover:bg-[#006097] rounded-lg transition-all shadow-xs hover:shadow disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isConnectingLinkedIn ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Connecting...</span>
                    </>
                  ) : (
                    <>
                      <ExternalLink className="w-3.5 h-3.5" />
                      <span>Connect LinkedIn Account</span>
                    </>
                  )}
                </button>
              )}
            </div>
          </div>

          <div className="p-6 sm:p-7 space-y-6">
            {/* Feedback Alerts */}
            {linkedinFeedback && (
              <div
                className={`p-4 rounded-xl border flex items-start gap-3 text-sm transition-all animate-fadeIn ${
                  linkedinFeedback.type === "success"
                    ? "bg-emerald-50 border-emerald-200 text-emerald-900"
                    : "bg-red-50 border-red-200 text-red-900"
                }`}
              >
                {linkedinFeedback.type === "success" ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
                )}
                <div className="flex-1">
                  <p className="font-semibold">{linkedinFeedback.message}</p>
                </div>
              </div>
            )}

            {/* If Not Configured */}
            {!linkedinStatus?.configured && (
              <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 p-6 text-center space-y-2">
                <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center mx-auto text-slate-400">
                  <Lock className="w-5 h-5" />
                </div>
                <h4 className="text-sm font-semibold text-slate-700">LinkedIn Integration Credentials Unset</h4>
                <p className="text-xs text-slate-500 max-w-lg mx-auto">
                  To enable OAuth connection for Agile Receivables, configure <code className="bg-slate-200 px-1 py-0.5 rounded font-mono text-[11px]">LINKEDIN_CLIENT_ID</code> and <code className="bg-slate-200 px-1 py-0.5 rounded font-mono text-[11px]">LINKEDIN_CLIENT_SECRET</code> in your backend environment.
                </p>
              </div>
            )}

            {/* If Connected: Display Connected Account Card */}
            {linkedinStatus?.connected && (
              <div className="rounded-xl border border-slate-200 bg-slate-50/40 p-5 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="flex items-center gap-3.5">
                    {linkedinStatus.profile_picture_url ? (
                      <img
                        src={linkedinStatus.profile_picture_url}
                        alt={linkedinStatus.member_name || "LinkedIn Member"}
                        className="w-12 h-12 rounded-full border border-slate-200 object-cover shadow-xs"
                      />
                    ) : (
                      <div className="w-12 h-12 rounded-full bg-[#0077b5]/10 border border-[#0077b5]/20 flex items-center justify-center text-[#0077b5] font-bold text-base shadow-xs">
                        {linkedinStatus.member_name ? linkedinStatus.member_name.charAt(0).toUpperCase() : "LI"}
                      </div>
                    )}
                    <div>
                      <h4 className="text-sm font-bold text-slate-900">
                        {linkedinStatus.member_name || "Authenticated LinkedIn Member"}
                      </h4>
                      <p className="text-xs text-slate-500">
                        {linkedinStatus.member_email || "Email address authorized via OpenID"}
                      </p>
                      <span className="text-[11px] text-emerald-700 font-medium inline-flex items-center gap-1 mt-0.5">
                        <CheckCircle2 className="w-3 h-3" />
                        Authorized via OpenID Connect
                      </span>
                    </div>
                  </div>

                  <div className="flex flex-col sm:items-end gap-1 text-[11px] text-slate-500">
                    <div>
                      <span className="text-slate-400">Connected: </span>
                      <span className="font-medium text-slate-700">{formatTimestamp(linkedinStatus.connected_at)}</span>
                    </div>
                    {linkedinStatus.expires_at && (
                      <div>
                        <span className="text-slate-400">Access Expiry: </span>
                        <span className="font-medium text-slate-700">{formatTimestamp(linkedinStatus.expires_at)}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Granted OpenID Scopes */}
                <div className="pt-3 border-t border-slate-200/80 flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold text-slate-600">Active Scopes:</span>
                  {(linkedinStatus.scopes || ["openid", "profile", "email"]).map((sc) => (
                    <span
                      key={sc}
                      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-mono font-medium bg-sky-50 text-sky-800 border border-sky-200"
                    >
                      {sc}
                    </span>
                  ))}
                </div>

                {/* LinkedIn API Capability Matrix */}
                <div className="space-y-3 pt-4 border-t border-slate-200/80">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                      <ShieldCheck className="w-4 h-4 text-[#0077b5]" />
                      <span>API Capability &amp; Scope Breakdown</span>
                    </h3>
                    <span className="text-[11px] text-slate-500">
                      Standard OpenID Scopes Active &bull; Headless DM APIs Gated by LinkedIn
                    </span>
                  </div>

                  <div className="border border-slate-200 rounded-xl overflow-hidden text-xs">
                    <div className="bg-slate-100/75 px-4 py-2.5 font-semibold text-slate-700 grid grid-cols-12 gap-2 border-b border-slate-200">
                      <span className="col-span-3">Capability</span>
                      <span className="col-span-2">Status</span>
                      <span className="col-span-3">OAuth Scope / Product</span>
                      <span className="col-span-4">Execution Model</span>
                    </div>

                    <div className="divide-y divide-slate-100 bg-white">
                      <div className="px-4 py-2.5 grid grid-cols-12 gap-2 items-center">
                        <span className="col-span-3 font-semibold text-slate-900">Member Profile</span>
                        <span className="col-span-2">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            Available
                          </span>
                        </span>
                        <span className="col-span-3 font-mono text-[11px] text-slate-600">openid, profile</span>
                        <span className="col-span-4 text-slate-600 text-[11px]">Direct automated OAuth profile retrieval</span>
                      </div>

                      <div className="px-4 py-2.5 grid grid-cols-12 gap-2 items-center">
                        <span className="col-span-3 font-semibold text-slate-900">Email Verification</span>
                        <span className="col-span-2">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            Available
                          </span>
                        </span>
                        <span className="col-span-3 font-mono text-[11px] text-slate-600">email</span>
                        <span className="col-span-4 text-slate-600 text-[11px]">Direct automated primary email verification</span>
                      </div>

                      <div className="px-4 py-2.5 grid grid-cols-12 gap-2 items-center">
                        <span className="col-span-3 font-semibold text-slate-900">Connection Invitations</span>
                        <span className="col-span-2">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-sky-50 text-sky-700 border border-sky-200">
                            Assisted Mode
                          </span>
                        </span>
                        <span className="col-span-3 font-mono text-[11px] text-slate-600">Enterprise Partner API</span>
                        <span className="col-span-4 text-slate-600 text-[11px]">Tailored 300-char notes &bull; 1-click copy &amp; confirm</span>
                      </div>

                      <div className="px-4 py-2.5 grid grid-cols-12 gap-2 items-center">
                        <span className="col-span-3 font-semibold text-slate-900">Direct Messaging (DM)</span>
                        <span className="col-span-2">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-sky-50 text-sky-700 border border-sky-200">
                            Assisted Mode
                          </span>
                        </span>
                        <span className="col-span-3 font-mono text-[11px] text-slate-600">Member Messaging API</span>
                        <span className="col-span-4 text-slate-600 text-[11px]">Follow-up scripts with cal.com link &bull; 1-click copy</span>
                      </div>

                      <div className="px-4 py-2.5 grid grid-cols-12 gap-2 items-center">
                        <span className="col-span-3 font-semibold text-slate-900">Company Page Updates</span>
                        <span className="col-span-2">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                            Restricted
                          </span>
                        </span>
                        <span className="col-span-3 font-mono text-[11px] text-slate-600">w_organization_social</span>
                        <span className="col-span-4 text-slate-600 text-[11px]">Requires LinkedIn Page Admin approval</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Assisted Mode Safe Workflow Banner */}
                <div className="rounded-xl border border-sky-200 bg-sky-50/60 p-4 space-y-3">
                  <div className="flex items-start gap-3">
                    <ShieldCheck className="w-5 h-5 text-sky-600 shrink-0 mt-0.5" />
                    <div className="space-y-1">
                      <h4 className="text-sm font-bold text-sky-900">
                        Assisted Outreach Mode Active &bull; 100% LinkedIn TOS Compliant
                      </h4>
                      <p className="text-xs text-sky-800 leading-relaxed">
                        Automated headless invitations and direct messaging are strictly gated by LinkedIn to enterprise partner tiers. Agile Sales &amp; Marketing automatically generates personalized 300-character connection notes and follow-ups with your booking link (<a href="https://cal.com/agilereceivables/30min" target="_blank" rel="noopener noreferrer" className="font-semibold underline">cal.com/agilereceivables/30min</a>), providing one-click copy and tracking without risky browser automation or account bans.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Architecture & Security Commitments */}
            <div className="rounded-xl bg-slate-50 p-4 border border-slate-200/60 text-xs text-slate-600 space-y-2">
              <div className="flex items-center gap-2 font-semibold text-slate-800">
                <Lock className="w-4 h-4 text-[#0077b5]" />
                <span>LinkedIn Integration Security Guarantees</span>
              </div>
              <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px] text-slate-600 pt-1">
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <strong>Replay-Protected State:</strong> OAuth states are cryptographically random and invalidated on first use.
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <strong>Encrypted at Rest:</strong> Access tokens are encrypted using AES-128-CBC authenticated encryption (Fernet).
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <strong>Strict Tenant Isolation:</strong> LinkedIn accounts are permanently scoped to your active organization.
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <strong>Redacted Responses:</strong> Plaintext tokens and client secrets are never rendered in frontend bundles.
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
