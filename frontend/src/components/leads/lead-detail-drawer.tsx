"use client";

import * as React from "react";
import { CRMLead } from "@/services/crmLeadService";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  X,
  Mail,
  Phone,
  Building2,
  Globe,
  MapPin,
  Sparkles,
  ShieldCheck,
  Briefcase,
  UserCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  HelpCircle,
  RefreshCw,
  Send,
  ArrowRight,
  Layers,
  Info,
  Trash2,
  Activity,
  Clock,
} from "lucide-react";
import {
  evaluateLeadQualification,
  routeLead,
  checkCampaignEligibility,
  enrollLeadInCampaign,
  LeadQualificationResult,
  LeadRouteResult,
  CampaignEligibilityResult,
  LeadCampaignEnrollResult,
} from "@/services/leadQualificationService";
import { fetchCampaigns, CampaignItem } from "@/services/campaignService";
import {
  fetchUnifiedActivities,
  UnifiedActivityItem,
} from "@/services/analyticsService";

export interface LeadDetailDrawerProps {
  lead: CRMLead | null;
  isOpen: boolean;
  onClose: () => void;
  onAddToCampaign?: (lead: CRMLead) => void;
  onLeadUpdated?: () => void;
  onDeleteLead?: (lead: CRMLead) => void;
}

export const LeadDetailDrawer: React.FC<LeadDetailDrawerProps> = ({
  lead,
  isOpen,
  onClose,
  onAddToCampaign,
  onLeadUpdated,
  onDeleteLead,
}) => {
  // Tabs: overview, qualification, routing, campaign, activities
  const [activeTab, setActiveTab] = React.useState<"overview" | "qualification" | "routing" | "campaign" | "activities">("overview");

  // Activities State
  const [activities, setActivities] = React.useState<UnifiedActivityItem[]>([]);
  const [isLoadingActivities, setIsLoadingActivities] = React.useState(false);
  const [activitiesError, setActivitiesError] = React.useState<string | null>(null);

  const loadActivities = React.useCallback(async () => {
    if (!lead?.id) return;
    setIsLoadingActivities(true);
    setActivitiesError(null);
    try {
      const res = await fetchUnifiedActivities({ lead_id: lead.id, limit: 50 });
      setActivities(res.items);
    } catch (err: unknown) {
      setActivitiesError(err instanceof Error ? err.message : "Failed to load activities.");
    } finally {
      setIsLoadingActivities(false);
    }
  }, [lead?.id]);

  // Qualification State
  const [isEvaluating, setIsEvaluating] = React.useState(false);
  const [evalResult, setEvalResult] = React.useState<LeadQualificationResult | null>(null);
  const [evalError, setEvalError] = React.useState<string | null>(null);

  // Routing State
  const [isRouting, setIsRouting] = React.useState(false);
  const [routeResult, setRouteResult] = React.useState<LeadRouteResult | null>(null);
  const [routeError, setRouteError] = React.useState<string | null>(null);

  // Campaign Eligibility State
  const [campaigns, setCampaigns] = React.useState<CampaignItem[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = React.useState<string>("");
  const [isCheckingEligibility, setIsCheckingEligibility] = React.useState(false);
  const [eligibilityResult, setEligibilityResult] = React.useState<CampaignEligibilityResult | null>(null);
  const [eligibilityError, setEligibilityError] = React.useState<string | null>(null);

  // Enrollment State
  const [isEnrolling, setIsEnrolling] = React.useState(false);
  const [enrollResult, setEnrollResult] = React.useState<LeadCampaignEnrollResult | null>(null);
  const [enrollError, setEnrollError] = React.useState<string | null>(null);

  // Reset internal states on drawer open/lead change
  React.useEffect(() => {
    if (isOpen) {
      setEvalResult(null);
      setEvalError(null);
      setRouteResult(null);
      setRouteError(null);
      setEligibilityResult(null);
      setEligibilityError(null);
      setEnrollResult(null);
      setEnrollError(null);
      setActiveTab("overview");
      loadActivities();

      // Load campaigns for eligibility check
      fetchCampaigns()
        .then((res) => {
          setCampaigns(res.campaigns);
          if (res.campaigns.length > 0 && !selectedCampaignId) {
            setSelectedCampaignId(res.campaigns[0].id);
          }
        })
        .catch(() => {
          // ignore silent fail
        });
    }
  }, [isOpen, lead?.id, loadActivities]);

  // ESC key handler
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

  if (!isOpen || !lead) return null;

  // Handle Qualification Evaluation
  const handleRunEvaluation = async () => {
    setIsEvaluating(true);
    setEvalError(null);
    try {
      const res = await evaluateLeadQualification(lead.id, { dryRun: false });
      setEvalResult(res);
      onLeadUpdated?.();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to evaluate lead.";
      setEvalError(msg);
    } finally {
      setIsEvaluating(false);
    }
  };

  // Handle Lead Routing
  const handleRouteLead = async () => {
    setIsRouting(true);
    setRouteError(null);
    try {
      const res = await routeLead(lead.id, { dryRun: false, forceReroute: true });
      setRouteResult(res);
      onLeadUpdated?.();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to route lead.";
      setRouteError(msg);
    } finally {
      setIsRouting(false);
    }
  };

  // Handle Campaign Eligibility Check
  const handleCheckEligibility = async () => {
    if (!selectedCampaignId) return;
    setIsCheckingEligibility(true);
    setEligibilityError(null);
    setEnrollResult(null);
    try {
      const res = await checkCampaignEligibility(lead.id, selectedCampaignId);
      setEligibilityResult(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to verify eligibility.";
      setEligibilityError(msg);
    } finally {
      setIsCheckingEligibility(false);
    }
  };

  // Handle Safe Campaign Enrollment
  const handleEnrollLead = async () => {
    if (!selectedCampaignId) return;
    setIsEnrolling(true);
    setEnrollError(null);
    try {
      const res = await enrollLeadInCampaign(lead.id, selectedCampaignId);
      setEnrollResult(res);
      onLeadUpdated?.();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to enroll lead.";
      setEnrollError(msg);
    } finally {
      setIsEnrolling(false);
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
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Lead Record
              </span>
              <span className="text-slate-300">•</span>
              <span className="font-mono text-[11px] text-slate-400">
                {lead.id}
              </span>
            </div>
            <h2 className="text-lg font-bold text-slate-900 leading-tight">
              {lead.fullName}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {lead.jobTitle} at{" "}
              <span className="font-semibold text-slate-700">
                {lead.companyName}
              </span>
            </p>
          </div>

          <div className="flex items-center gap-1">
            {onDeleteLead && (
              <button
                type="button"
                onClick={() => onDeleteLead(lead)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                title="Delete Lead"
                aria-label="Delete Lead"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
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

        {/* Badges Strip */}
        <div className="px-5 py-2.5 border-b border-slate-100 bg-white flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            {lead.leadScore !== null ? (
              <span
                className={`text-xs font-bold px-2 py-0.5 rounded border ${
                  lead.leadScore >= 70
                    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                    : lead.leadScore >= 40
                    ? "bg-amber-50 text-amber-700 border-amber-200"
                    : "bg-slate-100 text-slate-600 border-slate-200"
                }`}
              >
                Score: {lead.leadScore}/100
              </span>
            ) : (
              <span className="text-xs text-slate-400 font-medium px-2 py-0.5 rounded bg-slate-50 border border-slate-200">
                Unscored
              </span>
            )}

            {lead.qualificationStatus === "qualified" && (
              <Badge variant="success" dot>
                Qualified
              </Badge>
            )}
            {lead.qualificationStatus === "disqualified" && (
              <Badge variant="neutral">Disqualified</Badge>
            )}
            {lead.qualificationStatus === "new" && (
              <Badge variant="peach">Unassessed</Badge>
            )}

            {lead.temperature === "HOT" && <Badge variant="coral" dot>HOT</Badge>}
            {lead.temperature === "WARM" && <Badge variant="peach" dot>WARM</Badge>}
            {lead.temperature === "COLD" && <Badge variant="neutral">COLD</Badge>}

            {lead.assigneeName ? (
              <span className="text-xs text-sky-700 bg-sky-50 border border-sky-200 px-2 py-0.5 rounded flex items-center gap-1">
                <UserCheck className="w-3 h-3" />
                {lead.assigneeName}
              </span>
            ) : (
              <span className="text-xs text-slate-400 bg-slate-50 border border-slate-200 px-2 py-0.5 rounded">
                Unassigned
              </span>
            )}
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="px-5 border-b border-slate-200 bg-slate-50/50 flex gap-4 text-xs font-semibold">
          <button
            onClick={() => setActiveTab("overview")}
            className={`py-2.5 border-b-2 transition-colors ${
              activeTab === "overview"
                ? "border-agile-red text-agile-red font-bold"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Overview
          </button>
          <button
            onClick={() => setActiveTab("qualification")}
            className={`py-2.5 border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === "qualification"
                ? "border-agile-red text-agile-red font-bold"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            ICP Qualification
          </button>
          <button
            onClick={() => setActiveTab("routing")}
            className={`py-2.5 border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === "routing"
                ? "border-agile-red text-agile-red font-bold"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <UserCheck className="w-3.5 h-3.5" />
            Routing Rules
          </button>
          <button
            onClick={() => setActiveTab("campaign")}
            className={`py-2.5 border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === "campaign"
                ? "border-agile-red text-agile-red font-bold"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <Briefcase className="w-3.5 h-3.5" />
            Campaign Eligibility
          </button>
          <button
            onClick={() => setActiveTab("activities")}
            className={`py-2.5 border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === "activities"
                ? "border-agile-red text-agile-red font-bold"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            Activities
            {activities.length > 0 && (
              <span className="ml-0.5 px-1.5 py-0.2 rounded-full text-[10px] bg-slate-200 text-slate-700 font-semibold">
                {activities.length}
              </span>
            )}
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6 text-xs text-slate-700">
          {/* TAB 1: OVERVIEW */}
          {activeTab === "overview" && (
            <div className="space-y-6">
              {/* Contact Information */}
              <div className="space-y-2.5">
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  Contact Information
                </h4>
                <div className="rounded-lg border border-slate-200/80 p-3.5 bg-slate-50/50 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500 flex items-center gap-2">
                      <Mail className="w-3.5 h-3.5 text-slate-400" />
                      Email Address
                    </span>
                    <span className="font-mono text-slate-800 font-medium select-all">
                      {lead.email}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500 flex items-center gap-2">
                      <Phone className="w-3.5 h-3.5 text-slate-400" />
                      Phone Number
                    </span>
                    <span className="font-mono text-slate-800 font-medium select-all">
                      {lead.phone || "Not on file"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500 flex items-center gap-2">
                      <MapPin className="w-3.5 h-3.5 text-slate-400" />
                      Location
                    </span>
                    <span className="text-slate-800 font-medium">{lead.location}</span>
                  </div>
                </div>
              </div>

              {/* Company Profile */}
              <div className="space-y-2.5">
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  Company Snapshot
                </h4>
                <div className="rounded-lg border border-slate-200/80 p-3.5 bg-slate-50/50 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500 flex items-center gap-2">
                      <Building2 className="w-3.5 h-3.5 text-slate-400" />
                      Company Name
                    </span>
                    <span className="text-slate-800 font-semibold">{lead.companyName}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Industry</span>
                    <span className="text-slate-800 font-medium">{lead.industry}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Employee Range</span>
                    <span className="text-slate-800 font-medium">{lead.companySize}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500 flex items-center gap-2">
                      <Globe className="w-3.5 h-3.5 text-slate-400" />
                      Website
                    </span>
                    <a
                      href={lead.website}
                      target="_blank"
                      rel="noreferrer"
                      className="text-agile-red hover:underline font-medium"
                    >
                      {lead.companyDomain || "—"}
                    </a>
                  </div>
                </div>
              </div>

              {/* Sales Ownership Card */}
              <div className="space-y-2.5">
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  Sales Assignment
                </h4>
                <div className="rounded-lg border border-slate-200/80 p-3.5 bg-slate-50/50 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Assigned Sales Rep</span>
                    <span className="font-semibold text-slate-800">
                      {lead.assigneeName || "Unassigned"}
                    </span>
                  </div>
                  {lead.routedAt && (
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">Routed At</span>
                      <span className="text-slate-700">
                        {new Date(lead.routedAt).toLocaleString()}
                      </span>
                    </div>
                  )}
                  {lead.routingNotes && (
                    <div className="pt-2 border-t border-slate-200/60 text-[11px] text-slate-600">
                      <span className="font-semibold text-slate-500 block mb-0.5">Routing Notes:</span>
                      {lead.routingNotes}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: ICP QUALIFICATION & SCORING */}
          {activeTab === "qualification" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-bold text-sm text-slate-900">
                    Deterministic ICP Evaluation
                  </h4>
                  <p className="text-xs text-slate-500">
                    Evaluates company firmographics and contact persona against active ICP criteria.
                  </p>
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleRunEvaluation}
                  disabled={isEvaluating}
                  className="text-xs shadow-xs flex items-center gap-1.5"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isEvaluating ? "animate-spin" : ""}`} />
                  {isEvaluating ? "Evaluating..." : "Evaluate Now"}
                </Button>
              </div>

              {evalError && (
                <div className="p-3 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                  <p className="text-xs">{evalError}</p>
                </div>
              )}

              {/* Evaluation Outcome Banner */}
              {evalResult ? (
                <div className="rounded-lg border border-slate-200 p-4 bg-slate-50/80 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-2xl font-black text-slate-900">
                        {evalResult.score}/100
                      </span>
                      <Badge
                        variant={
                          evalResult.is_qualified
                            ? "success"
                            : evalResult.qualification_status === "disqualified"
                            ? "neutral"
                            : "peach"
                        }
                      >
                        {evalResult.qualification_status.toUpperCase()}
                      </Badge>
                    </div>
                    <span className="text-[11px] font-semibold text-slate-500">
                      Target ICP: {evalResult.icp_name || "Default Org ICP"}
                    </span>
                  </div>

                  <p className="text-xs text-slate-700 bg-white p-2.5 rounded border border-slate-200/70">
                    {evalResult.qualification_reason}
                  </p>

                  <div className="grid grid-cols-3 gap-2 text-center text-xs pt-2 border-t border-slate-200/60">
                    <div className="p-2 rounded bg-emerald-50 border border-emerald-100 text-emerald-800">
                      <span className="font-bold block text-sm">
                        {evalResult.matched_criteria_count}
                      </span>
                      Matched
                    </div>
                    <div className="p-2 rounded bg-amber-50 border border-amber-100 text-amber-800">
                      <span className="font-bold block text-sm">
                        {evalResult.missing_criteria_count}
                      </span>
                      Missing Data
                    </div>
                    <div className="p-2 rounded bg-slate-100 border border-slate-200 text-slate-700">
                      <span className="font-bold block text-sm">
                        {evalResult.unmatched_criteria_count}
                      </span>
                      Unmatched
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-4 rounded-lg border border-slate-200 bg-slate-50/50 text-slate-600 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-800">Persisted Record Status:</span>
                    <span className="capitalize font-semibold text-slate-700">
                      {lead.qualificationStatus}
                    </span>
                  </div>
                  <div className="text-xs text-slate-600">
                    <span className="text-slate-400 block mb-0.5">Qualification Reason:</span>
                    <p className="p-2.5 bg-white rounded border border-slate-200 text-slate-700">
                      {lead.qualificationReason || "No evaluation explanation recorded yet."}
                    </p>
                  </div>
                </div>
              )}

              {/* Criteria Breakdown List */}
              {evalResult && evalResult.criteria.length > 0 && (
                <div className="space-y-2 pt-2">
                  <h5 className="font-bold text-xs uppercase tracking-wider text-slate-500">
                    Criteria Breakdown
                  </h5>
                  <div className="space-y-2">
                    {evalResult.criteria.map((crit, idx) => (
                      <div
                        key={idx}
                        className="p-3 rounded-lg border border-slate-200 bg-white shadow-xs flex items-start justify-between gap-3"
                      >
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            {crit.status === "matched" && (
                              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                            )}
                            {crit.status === "unmatched" && (
                              <XCircle className="w-4 h-4 text-rose-500 shrink-0" />
                            )}
                            {crit.status === "missing_data" && (
                              <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
                            )}
                            {crit.status === "not_configured" && (
                              <HelpCircle className="w-4 h-4 text-slate-400 shrink-0" />
                            )}
                            <span className="font-semibold text-slate-900">
                              {crit.criterion}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-600 pl-6">
                            {crit.detail}
                          </p>
                        </div>
                        <div className="text-right shrink-0">
                          <span
                            className={`font-mono font-bold text-xs ${
                              crit.points > 0 ? "text-emerald-700" : "text-slate-400"
                            }`}
                          >
                            +{crit.points}/{crit.max_points}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: ROUTING RULES */}
          {activeTab === "routing" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-bold text-sm text-slate-900">
                    Automated Sales Routing
                  </h4>
                  <p className="text-xs text-slate-500">
                    Evaluates tenant routing rules in priority order and assigns lead ownership.
                  </p>
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleRouteLead}
                  disabled={isRouting}
                  className="text-xs shadow-xs flex items-center gap-1.5"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isRouting ? "animate-spin" : ""}`} />
                  {isRouting ? "Routing..." : "Route Lead"}
                </Button>
              </div>

              {routeError && (
                <div className="p-3 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                  <p className="text-xs">{routeError}</p>
                </div>
              )}

              {/* Current Assignment Status */}
              <div className="p-4 rounded-lg border border-slate-200 bg-slate-50/80 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Current Assignee:</span>
                  <span className="font-bold text-slate-900 text-sm">
                    {routeResult?.assignee_name || lead.assigneeName || "Unassigned"}
                  </span>
                </div>
                {(routeResult?.matched_rule_name || lead.routingNotes) && (
                  <div className="pt-2 border-t border-slate-200/60 text-xs text-slate-600 space-y-1">
                    <span className="font-semibold text-slate-500">Routing Evaluation:</span>
                    <p className="p-2.5 bg-white rounded border border-slate-200">
                      {routeResult?.explanation || lead.routingNotes}
                    </p>
                  </div>
                )}
              </div>

              <div className="p-3 rounded-lg bg-sky-50 border border-sky-200 text-sky-800 text-xs flex items-start gap-2">
                <Info className="w-4 h-4 mt-0.5 shrink-0" />
                <p>
                  Routing rules check qualification status, minimum lead score, industry, geography,
                  and company size. Active tenant rules execute deterministically.
                </p>
              </div>
            </div>
          )}

          {/* TAB 4: CAMPAIGN ELIGIBILITY & SAFE ENROLLMENT */}
          {activeTab === "campaign" && (
            <div className="space-y-4">
              <div>
                <h4 className="font-bold text-sm text-slate-900">
                  Campaign Eligibility & Safe Enrollment
                </h4>
                <p className="text-xs text-slate-500">
                  Verifies qualification status, suppression/opt-out status, and duplicate enrollment prevention.
                </p>
              </div>

              {/* Campaign Picker */}
              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-700 block">
                  Select Target Campaign:
                </label>
                {campaigns.length === 0 ? (
                  <div className="p-3 bg-slate-50 rounded border text-slate-500 text-xs">
                    No active campaigns found in organization. Create a campaign first.
                  </div>
                ) : (
                  <select
                    value={selectedCampaignId}
                    onChange={(e) => {
                      setSelectedCampaignId(e.target.value);
                      setEligibilityResult(null);
                      setEnrollResult(null);
                    }}
                    className="w-full text-xs p-2.5 rounded-lg border border-slate-300 bg-white text-slate-800 focus:outline-hidden focus:ring-1 focus:ring-agile-red"
                  >
                    {campaigns.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.type}) — {c.status}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCheckEligibility}
                  disabled={isCheckingEligibility || !selectedCampaignId}
                  className="text-xs bg-white text-slate-700"
                >
                  {isCheckingEligibility ? "Checking..." : "Verify Eligibility"}
                </Button>

                {eligibilityResult?.is_eligible && !eligibilityResult.already_enrolled && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleEnrollLead}
                    disabled={isEnrolling}
                    className="text-xs shadow-xs flex items-center gap-1.5"
                  >
                    <Send className="w-3.5 h-3.5" />
                    {isEnrolling ? "Enrolling..." : "Enroll Safely"}
                  </Button>
                )}
              </div>

              {eligibilityError && (
                <div className="p-3 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 text-xs">
                  {eligibilityError}
                </div>
              )}

              {/* Eligibility Report */}
              {eligibilityResult && (
                <div className="p-4 rounded-lg border border-slate-200 bg-slate-50/80 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-900 text-xs">Eligibility Status:</span>
                    <Badge variant={eligibilityResult.is_eligible ? "success" : "neutral"}>
                      {eligibilityResult.is_eligible ? "Eligible" : "Not Eligible"}
                    </Badge>
                  </div>

                  {eligibilityResult.reasons.length > 0 && (
                    <div className="space-y-1 text-xs">
                      <span className="font-semibold text-emerald-700 block">Criteria Satisfied:</span>
                      <ul className="list-disc pl-4 space-y-0.5 text-slate-700">
                        {eligibilityResult.reasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {eligibilityResult.suppression_reasons.length > 0 && (
                    <div className="space-y-1 text-xs">
                      <span className="font-semibold text-rose-700 block">Suppression Blockers:</span>
                      <ul className="list-disc pl-4 space-y-0.5 text-rose-800">
                        {eligibilityResult.suppression_reasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Enrollment Result */}
              {enrollResult && (
                <div className="p-3 rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-800 text-xs space-y-1">
                  <div className="flex items-center gap-1.5 font-bold">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                    {enrollResult.message}
                  </div>
                  <p className="text-[11px] text-emerald-700">
                    Lead is queued for campaign steps. Real dispatch rules and scheduled timings are respected.
                  </p>
                </div>
              )}

              {enrollError && (
                <div className="p-3 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 text-xs">
                  {enrollError}
                </div>
              )}
            </div>
          )}

          {/* TAB 5: Unified Activities Stream */}
          {activeTab === "activities" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                <div>
                  <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                    Activity History
                  </h3>
                  <p className="text-[11px] text-slate-500">
                    Chronological audit of verified outreach emails and voice calls.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={loadActivities}
                  disabled={isLoadingActivities}
                  className="text-xs inline-flex items-center gap-1.5 h-7 px-2"
                >
                  <RefreshCw
                    className={`w-3 h-3 text-slate-500 ${isLoadingActivities ? "animate-spin" : ""}`}
                  />
                  <span>Refresh</span>
                </Button>
              </div>

              {activitiesError && (
                <div className="p-3 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 text-xs">
                  {activitiesError}
                </div>
              )}

              {isLoadingActivities && (
                <div className="py-8 text-center space-y-2">
                  <RefreshCw className="w-5 h-5 text-slate-400 animate-spin mx-auto" />
                  <p className="text-xs text-slate-400">Loading activities...</p>
                </div>
              )}

              {!isLoadingActivities && activities.length === 0 && (
                <div className="p-8 text-center border border-dashed border-slate-200 rounded-xl bg-slate-50/50 space-y-2">
                  <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center mx-auto text-slate-400">
                    <Clock className="w-5 h-5" />
                  </div>
                  <h4 className="text-xs font-bold text-slate-700">No activities recorded yet</h4>
                  <p className="text-[11px] text-slate-500 max-w-xs mx-auto leading-relaxed">
                    No email outreach or voice calls have been dispatched for this lead yet. Verified activities will appear here chronologically once campaigns run.
                  </p>
                </div>
              )}

              {!isLoadingActivities && activities.length > 0 && (
                <div className="space-y-3 relative before:absolute before:inset-0 before:left-3.5 before:w-0.5 before:bg-slate-200 before:z-0">
                  {activities.map((act) => {
                    const isEmail = act.channel === "email";
                    const isVoice = act.channel === "voice";

                    return (
                      <div
                        key={act.id}
                        className="relative z-10 pl-8 space-y-1.5 group"
                      >
                        {/* Timeline Node Icon */}
                        <div
                          className={`absolute left-1.5 top-2 -translate-x-1/2 w-5 h-5 rounded-full flex items-center justify-center border-2 border-white shadow-xs ${
                            isEmail
                              ? "bg-blue-500 text-white"
                              : isVoice
                              ? "bg-purple-600 text-white"
                              : "bg-slate-400 text-white"
                          }`}
                        >
                          {isEmail && <Mail className="w-2.5 h-2.5" />}
                          {isVoice && <Phone className="w-2.5 h-2.5" />}
                        </div>

                        {/* Card Container */}
                        <div className="p-3 rounded-lg border border-slate-200 bg-white hover:border-slate-300 transition-colors shadow-2xs space-y-2">
                          <div className="flex items-start justify-between gap-2">
                            <div className="space-y-0.5">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="text-xs font-bold text-slate-800">
                                  {act.title}
                                </span>
                                {isEmail && act.email_details && (
                                  <>
                                    {act.email_details.is_replied && (
                                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200">
                                        Replied
                                      </span>
                                    )}
                                    {act.email_details.is_delivered && !act.email_details.is_replied && (
                                      <Badge variant="success" className="text-[10px] px-1.5 py-0">
                                        Delivered
                                      </Badge>
                                    )}
                                    {act.email_details.is_bounced && (
                                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200">
                                        Bounced
                                      </span>
                                    )}
                                    {act.email_details.status === "sent" && !act.email_details.is_delivered && !act.email_details.is_bounced && (
                                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                                        Submitted to Provider
                                      </span>
                                    )}
                                    {act.email_details.status === "draft" && (
                                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">
                                        Draft
                                      </span>
                                    )}
                                  </>
                                )}
                                {isVoice && act.voice_details && (
                                  <>
                                    <span
                                      className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${
                                        act.voice_details.is_connected
                                          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                          : "bg-slate-100 text-slate-600 border-slate-200"
                                      }`}
                                    >
                                      {act.voice_details.is_connected ? "Connected" : "Not Connected"}
                                    </span>
                                    {act.voice_details.call_outcome && (
                                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200">
                                        {act.voice_details.call_outcome}
                                      </span>
                                    )}
                                    {act.voice_details.duration_seconds !== null && act.voice_details.duration_seconds !== undefined && (
                                      <span className="text-[10px] text-slate-400">
                                        {act.voice_details.duration_seconds}s
                                      </span>
                                    )}
                                  </>
                                )}
                              </div>

                              {act.campaign_name && (
                                <p className="text-[11px] text-slate-400">
                                  Campaign: <span className="font-medium text-slate-600">{act.campaign_name}</span>
                                </p>
                              )}
                            </div>

                            <span className="text-[10px] font-mono text-slate-400 whitespace-nowrap">
                              {new Date(act.occurred_at).toLocaleString(undefined, {
                                month: "short",
                                day: "numeric",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </span>
                          </div>

                          {act.description && (
                            <p className="text-xs text-slate-600 bg-slate-50/70 p-2 rounded border border-slate-100 font-mono text-[11px]">
                              {act.description}
                            </p>
                          )}

                          {isVoice && act.voice_details?.summary && (
                            <p className="text-xs text-slate-600 italic bg-purple-50/40 p-2 rounded border border-purple-100 text-[11px]">
                              &quot;{act.voice_details.summary}&quot;
                            </p>
                          )}

                          {isEmail && act.email_details && (
                            <div className="flex items-center gap-3 text-[10px] text-slate-400 pt-0.5 border-t border-slate-50">
                              {act.email_details.sent_at && (
                                <span>Sent: {new Date(act.email_details.sent_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                              )}
                              {act.email_details.delivered_at && (
                                <span className="text-emerald-600 font-medium">Delivered: {new Date(act.email_details.delivered_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                              )}
                              {act.email_details.replied_at && (
                                <span className="text-purple-600 font-medium">Replied: {new Date(act.email_details.replied_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Drawer Footer Actions */}
        <div className="p-4 border-t border-slate-100 bg-slate-50/50 flex items-center justify-between gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={onClose}
            className="text-xs"
          >
            Close
          </Button>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setActiveTab("qualification")}
              className="text-xs bg-white text-slate-700"
            >
              Qualification Details
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setActiveTab("campaign");
              }}
              className="text-xs shadow-xs"
            >
              Campaign Actions
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
