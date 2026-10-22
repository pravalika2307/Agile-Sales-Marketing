"use client";

import * as React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import {
  ShieldCheck,
  CheckCircle2,
  Send,
  Loader2,
  Check,
} from "lucide-react";
import { cn } from "@/lib/utils";

export interface ApprovalQueueItem {
  id: string;
  campaignName: string;
  postTitle: string;
  copyExcerpt: string;
  thumbnailUrl: string;
  assignedUser: {
    name: string;
    role: string;
    initials: string;
  };
  clientName: string;
  status: "pending_review" | "webhook_triggered" | "approved";
  submissionDate: string;
}

const DEFAULT_APPROVAL_ITEMS: ApprovalQueueItem[] = [
  {
    id: "appr-1",
    campaignName: "Q4 CFO Benchmark Campaign",
    postTitle: "Eliminating 14 Days DSO in Healthcare",
    copyExcerpt: "Exclusive data from 140+ CFOs reveals that DSO can be reduced by 14 days with unified sales & receivables cadence...",
    thumbnailUrl: "https://images.unsplash.com/photo-1551836022-d5d88e9218df?w=160&auto=format&fit=crop&q=80",
    assignedUser: {
      name: "Pravalika Palle",
      role: "Campaign Lead",
      initials: "PP",
    },
    clientName: "Apex Medical Systems",
    status: "pending_review",
    submissionDate: "Today, 10:15 AM",
  },
  {
    id: "appr-2",
    campaignName: "Enterprise Cashflow Series",
    postTitle: "Retell AI Telephony Workflow Demo",
    copyExcerpt: "Watch how our automated voice follow-up cadences confirm invoice delivery and book reconciliation meetings...",
    thumbnailUrl: "https://images.unsplash.com/photo-1557804506-669a67965ba0?w=160&auto=format&fit=crop&q=80",
    assignedUser: {
      name: "Lakshay Narula",
      role: "Growth Operations",
      initials: "LN",
    },
    clientName: "Global Logistics Corp",
    status: "pending_review",
    submissionDate: "Yesterday, 4:40 PM",
  },
  {
    id: "appr-3",
    campaignName: "Commercial Credit Modernization",
    postTitle: "5 Inefficiency Leaks in B2B Teams",
    copyExcerpt: "Infographic carousel detailing reconciliation gaps, broken dials, and email spam traps...",
    thumbnailUrl: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=160&auto=format&fit=crop&q=80",
    assignedUser: {
      name: "Elena Rostova",
      role: "Creative Director",
      initials: "ER",
    },
    clientName: "Veritas Financial Group",
    status: "pending_review",
    submissionDate: "Oct 19, 2026",
  },
];

export const ClientApprovalQueueWidget: React.FC = () => {
  const [items, setItems] = React.useState<ApprovalQueueItem[]>(DEFAULT_APPROVAL_ITEMS);
  const [reviewingItem, setReviewingItem] = React.useState<ApprovalQueueItem | null>(null);
  const [isTriggeringWebhook, setIsTriggeringWebhook] = React.useState(false);
  const [notificationToast, setNotificationToast] = React.useState<string | null>(null);

  const handleTriggerN8nWebhook = (item: ApprovalQueueItem) => {
    setIsTriggeringWebhook(true);

    // Simulate dispatching to n8n webhook endpoint
    setTimeout(() => {
      setIsTriggeringWebhook(false);
      setItems((prev) =>
        prev.map((i) =>
          i.id === item.id ? { ...i, status: "webhook_triggered" } : i
        )
      );
      setReviewingItem(null);
      setNotificationToast(
        `Approval triggered via n8n webhook for "${item.campaignName}". Event payload dispatched successfully.`
      );

      // Auto-clear toast
      setTimeout(() => {
        setNotificationToast(null);
      }, 5000);
    }, 900);
  };

  return (
    <>
      <Card className="rounded-xl border border-slate-200/80 bg-white shadow-xs hover:shadow-sm transition-all duration-200">
        <CardHeader className="p-4 sm:p-5 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-amber-50 text-amber-600 border border-amber-200/60 flex items-center justify-center">
              <ShieldCheck className="w-3.5 h-3.5" />
            </div>
            <div>
              <CardTitle className="text-sm sm:text-base font-bold text-slate-900 tracking-tight">
                Client Approval Queue
              </CardTitle>
              <p className="text-[11px] text-slate-400">Awaiting client final sign-off</p>
            </div>
          </div>

          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
            {items.filter((i) => i.status === "pending_review").length} Pending
          </span>
        </CardHeader>

        <CardContent className="p-4 sm:p-5 space-y-3">
          {notificationToast && (
            <div className="p-2.5 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-start gap-2 animate-in fade-in">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              <span>{notificationToast}</span>
            </div>
          )}

          {items.map((item) => {
            const isTriggered = item.status === "webhook_triggered";

            return (
              <div
                key={item.id}
                className={cn(
                  "p-3 rounded-xl border transition-all duration-150 flex items-center justify-between gap-3",
                  isTriggered
                    ? "bg-emerald-50/40 border-emerald-200/80"
                    : "bg-slate-50/60 border-slate-200/70 hover:bg-slate-50 hover:border-slate-300"
                )}
              >
                {/* Left: Thumbnail & Details */}
                <div className="flex items-center gap-3 min-w-0">
                  {/* Square Creative Asset Thumbnail */}
                  <div className="w-11 h-11 rounded-lg overflow-hidden shrink-0 bg-slate-100 border border-slate-200">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={item.thumbnailUrl}
                      alt={item.campaignName}
                      className="w-full h-full object-cover"
                    />
                  </div>

                  <div className="min-w-0">
                    {/* Campaign Name */}
                    <span className="text-[10px] font-bold text-indigo-600 uppercase tracking-wider block truncate">
                      {item.campaignName}
                    </span>

                    {/* Post Title */}
                    <h4 className="text-xs font-bold text-slate-900 truncate">
                      {item.postTitle}
                    </h4>

                    {/* Assigned User Avatar & Client */}
                    <div className="flex items-center gap-1.5 mt-1">
                      <div
                        className="w-4 h-4 rounded-full bg-slate-200 text-slate-700 font-bold text-[8px] flex items-center justify-center shrink-0"
                        title={`Assigned to ${item.assignedUser.name}`}
                      >
                        {item.assignedUser.initials}
                      </div>
                      <span className="text-[10px] text-slate-500 truncate">
                        {item.assignedUser.name} · {item.clientName}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Right: Prominent "Review" Button (Specification 6) */}
                <div className="shrink-0">
                  {isTriggered ? (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-100/80 text-emerald-800 text-xs font-bold border border-emerald-300/60">
                      <Check className="w-3.5 h-3.5" />
                      Triggered
                    </span>
                  ) : (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => setReviewingItem(item)}
                      className="text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs px-3 py-1 rounded-lg transition-transform active:scale-95"
                    >
                      Review
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      {/* Review & Trigger n8n Webhook Modal */}
      <Modal
        isOpen={!!reviewingItem}
        onClose={() => setReviewingItem(null)}
        title="Client Sign-Off & n8n Review"
        description="Verify post copy and trigger n8n approval webhook for automated client sign-off."
        maxWidth="md"
      >
        {reviewingItem && (
          <div className="space-y-4 py-2">
            <div className="flex items-start gap-3 p-3.5 rounded-xl bg-slate-50 border border-slate-200">
              <div className="w-14 h-14 rounded-lg overflow-hidden shrink-0 bg-slate-200 border border-slate-300">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={reviewingItem.thumbnailUrl}
                  alt={reviewingItem.campaignName}
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-[10px] font-bold text-indigo-600 uppercase">
                  {reviewingItem.campaignName}
                </span>
                <h4 className="text-xs font-bold text-slate-900 mt-0.5">{reviewingItem.postTitle}</h4>
                <p className="text-xs text-slate-600 mt-1 line-clamp-2">
                  {reviewingItem.copyExcerpt}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-2.5 rounded-lg border border-slate-200 bg-white">
                <span className="text-[10px] text-slate-400 uppercase font-semibold">Assigned Specialist</span>
                <p className="font-bold text-slate-800 mt-0.5">{reviewingItem.assignedUser.name}</p>
                <p className="text-[10px] text-slate-400">{reviewingItem.assignedUser.role}</p>
              </div>
              <div className="p-2.5 rounded-lg border border-slate-200 bg-white">
                <span className="text-[10px] text-slate-400 uppercase font-semibold">Client Organization</span>
                <p className="font-bold text-slate-800 mt-0.5">{reviewingItem.clientName}</p>
                <p className="text-[10px] text-amber-600 font-medium">Pending Final Sign-Off</p>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-indigo-50/80 border border-indigo-200/70 text-xs text-indigo-900">
              <span className="font-bold flex items-center gap-1.5 mb-1">
                <Send className="w-3.5 h-3.5 text-indigo-600" />
                n8n Approval Webhook Integration
              </span>
              Triggering this action sends an HMAC-signed event to the client approval pipeline in n8n, emailing client decision-makers with a one-click authorization token.
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setReviewingItem(null)}
                disabled={isTriggeringWebhook}
              >
                Cancel
              </Button>

              <Button
                variant="primary"
                size="sm"
                onClick={() => handleTriggerN8nWebhook(reviewingItem)}
                disabled={isTriggeringWebhook}
                className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold inline-flex items-center gap-1.5"
              >
                {isTriggeringWebhook ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Triggering n8n Webhook...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" />
                    <span>Trigger n8n Webhook</span>
                  </>
                )}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
};
