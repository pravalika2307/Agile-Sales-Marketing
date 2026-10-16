"use client";

import * as React from "react";
import {
  DealItem,
  PipelineStageItem,
  DEAL_STATUS_LABELS,
  formatCurrency,
} from "@/services/pipelineService";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import {
  X,
  DollarSign,
  Calendar,
  User,
  Building2,
  Clock,
  CheckCircle2,
  XCircle,
  RotateCcw,
  Layers,
  ArrowRight,
} from "lucide-react";

export interface DealDetailDrawerProps {
  deal: DealItem | null;
  stages: PipelineStageItem[];
  isOpen: boolean;
  onClose: () => void;
  onStageChange: (dealId: string, targetStageId: string) => void;
  onStatusChange: (dealId: string, newStatus: "open" | "won" | "lost") => void;
  onDeleteDeal?: (dealId: string) => void;
}

export const DealDetailDrawer: React.FC<DealDetailDrawerProps> = ({
  deal,
  stages,
  isOpen,
  onClose,
  onStageChange,
  onStatusChange,
  onDeleteDeal,
}) => {
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

  if (!isOpen || !deal) return null;

  const currentStage = stages.find((s) => s.id === deal.pipelineStageId);

  const formatDate = (iso?: string | null) => {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return iso;
    }
  };

  const getStatusBadge = (status: "open" | "won" | "lost") => {
    switch (status) {
      case "won":
        return (
          <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            Won
          </Badge>
        );
      case "lost":
        return (
          <Badge className="bg-rose-50 text-rose-700 border-rose-200">
            <XCircle className="w-3 h-3 mr-1" />
            Lost
          </Badge>
        );
      default:
        return (
          <Badge className="bg-sky-50 text-sky-700 border-sky-200">
            <Clock className="w-3 h-3 mr-1" />
            Open
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
      <div className="relative w-full max-w-lg bg-white h-full shadow-2xl border-l border-slate-200 z-10 flex flex-col overflow-hidden animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-5 border-b border-slate-100 flex items-start justify-between gap-3 bg-slate-50/50">
          <div>
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Opportunity
              </span>
              <span className="text-slate-300">•</span>
              <span className="font-mono text-[11px] text-slate-400">
                {deal.id.substring(0, 8)}...
              </span>
              <span className="text-slate-300">•</span>
              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-600 bg-white px-2 py-0.5 rounded border border-slate-200">
                <Layers className="w-3 h-3 text-slate-400" />
                {currentStage ? `${currentStage.name} (${currentStage.probabilityPct}%)` : "—"}
              </span>
            </div>

            <h2 className="text-lg font-bold text-header leading-tight">
              {deal.name}
            </h2>
            <div className="text-xl font-bold text-header mt-1 text-agile-red">
              {formatCurrency(deal.amount)}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {getStatusBadge(deal.status)}
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

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* Stage Progression & Move */}
          <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Pipeline Stage Progression
              </span>
              <span className="text-xs font-medium text-slate-600">
                Probability: {currentStage?.probabilityPct ?? 0}%
              </span>
            </div>

            <div className="space-y-2">
              <label className="text-xs text-slate-500 block">
                Move deal to stage:
              </label>
              <Select
                value={deal.pipelineStageId}
                onChange={(e) => onStageChange(deal.id, e.target.value)}
                className="text-xs h-9 bg-white"
              >
                {stages.map((stage) => (
                  <option key={stage.id} value={stage.id}>
                    {stage.orderIndex}. {stage.name} ({stage.probabilityPct}%)
                  </option>
                ))}
              </Select>
            </div>

            {/* Quick Status Toggles */}
            <div className="pt-2 border-t border-slate-200/70 flex items-center gap-2">
              <span className="text-xs text-slate-400">Status:</span>
              {deal.status !== "won" && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onStatusChange(deal.id, "won")}
                  className="h-7 text-xs border-emerald-200 text-emerald-700 hover:bg-emerald-50 px-2"
                >
                  <CheckCircle2 className="w-3 h-3 mr-1" />
                  Mark as Won
                </Button>
              )}
              {deal.status !== "lost" && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onStatusChange(deal.id, "lost")}
                  className="h-7 text-xs border-rose-200 text-rose-700 hover:bg-rose-50 px-2"
                >
                  <XCircle className="w-3 h-3 mr-1" />
                  Mark as Lost
                </Button>
              )}
              {deal.status !== "open" && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onStatusChange(deal.id, "open")}
                  className="h-7 text-xs border-slate-200 text-slate-700 hover:bg-slate-50 px-2"
                >
                  <RotateCcw className="w-3 h-3 mr-1" />
                  Reopen
                </Button>
              )}
            </div>
          </div>

          {/* Deal Metadata */}
          <div className="border border-slate-200 rounded-xl p-4 space-y-3 bg-white">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Deal Overview
            </h3>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <span className="text-slate-400 block mb-0.5">Monetary Value</span>
                <span className="font-semibold text-slate-800 text-sm">
                  {formatCurrency(deal.amount)}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block mb-0.5">Expected Close Date</span>
                <span className="text-slate-800 font-medium flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5 text-slate-400" />
                  {formatDate(deal.expectedCloseDate)}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block mb-0.5">Associated Contact</span>
                <span className="text-slate-800 font-medium flex items-center gap-1.5">
                  <User className="w-3.5 h-3.5 text-slate-400" />
                  {deal.contactName || "—"}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block mb-0.5">Associated Company</span>
                <span className="text-slate-800 font-medium flex items-center gap-1.5">
                  <Building2 className="w-3.5 h-3.5 text-slate-400" />
                  {deal.companyName || "—"}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block mb-0.5">Created Date</span>
                <span className="text-slate-600">{formatDate(deal.createdAt)}</span>
              </div>
              <div>
                <span className="text-slate-400 block mb-0.5">Last Updated</span>
                <span className="text-slate-600">{formatDate(deal.updatedAt)}</span>
              </div>
            </div>
          </div>

          {/* Activity / Communications Policy Banner */}
          <div className="border border-slate-200 rounded-xl p-4 bg-slate-50/50 space-y-1.5 text-xs text-slate-500">
            <span className="font-semibold text-slate-700 block">
              Enterprise Data Integrity Notice
            </span>
            <p>
              Timeline events, call transcripts, and email touchpoints are populated exclusively from verified CRM activity logs. No synthetic engagement records are generated.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
          <span>Enterprise Deal Pipeline</span>
          <div className="flex items-center gap-2">
            {onDeleteDeal && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onDeleteDeal(deal.id)}
                className="text-xs text-rose-600 border-rose-200 hover:bg-rose-50"
              >
                Delete Deal
              </Button>
            )}
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
    </div>
  );
};
