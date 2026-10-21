"use client";

import * as React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { DollarSign } from "lucide-react";
import { cn } from "@/lib/utils";

export interface AdCampaignItem {
  id: string;
  name: string;
  platform: "meta" | "google" | "linkedin";
  status: "Active" | "Optimizing" | "Scaling";
  spent: number;
  totalBudget: number;
  dailySpend: number;
  roas: string;
}

const DEFAULT_CAMPAIGNS: AdCampaignItem[] = [
  {
    id: "camp-meta-1",
    name: "Active Meta — Lookalike B2B CFOs",
    platform: "meta",
    status: "Active",
    spent: 4250,
    totalBudget: 5000,
    dailySpend: 142,
    roas: "3.4x ROAS",
  },
  {
    id: "camp-goog-2",
    name: "Google Search — Invoice Automation Intent",
    platform: "google",
    status: "Active",
    spent: 3180,
    totalBudget: 4000,
    dailySpend: 106,
    roas: "4.1x ROAS",
  },
  {
    id: "camp-lnkd-3",
    name: "LinkedIn Sponsored — Revenue Ops Leaders",
    platform: "linkedin",
    status: "Optimizing",
    spent: 1850,
    totalBudget: 2500,
    dailySpend: 92,
    roas: "2.9x ROAS",
  },
];

export const ActiveAdCampaignsWidget: React.FC = () => {
  const [campaigns] = React.useState<AdCampaignItem[]>(DEFAULT_CAMPAIGNS);

  const totalSpent = campaigns.reduce((acc, c) => acc + c.spent, 0);
  const totalBudget = campaigns.reduce((acc, c) => acc + c.totalBudget, 0);
  const overallUtilization = Math.round((totalSpent / (totalBudget || 1)) * 100);

  return (
    <Card className="rounded-xl border border-slate-200/80 bg-white shadow-xs hover:shadow-sm transition-all duration-200">
      <CardHeader className="p-4 sm:p-5 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 border border-emerald-200/60 flex items-center justify-center">
            <DollarSign className="w-3.5 h-3.5" />
          </div>
          <div>
            <CardTitle className="text-sm sm:text-base font-bold text-slate-900 tracking-tight">
              Active Ad Campaigns
            </CardTitle>
            <p className="text-[11px] text-slate-400">Live pacing &amp; budget utilization</p>
          </div>
        </div>

        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
          3 Live Channels
        </span>
      </CardHeader>

      <CardContent className="p-4 sm:p-5 space-y-4">
        {campaigns.map((camp) => {
          const percentUsed = Math.min(
            100,
            Math.round((camp.spent / (camp.totalBudget || 1)) * 100)
          );

          // Color progress bar according to utilization
          let barGradient = "bg-emerald-500";
          if (percentUsed > 80) barGradient = "bg-amber-500";
          if (percentUsed > 90) barGradient = "bg-rose-500";

          return (
            <div
              key={camp.id}
              className="p-3 rounded-xl border border-slate-100 bg-slate-50/50 hover:bg-slate-50 transition-all duration-150 space-y-2"
            >
              {/* Campaign Name & Status Badge (Specification 6) */}
              <div className="flex items-center justify-between gap-2">
                <h4 className="text-xs font-bold text-slate-900 truncate">
                  {camp.name}
                </h4>
                <span
                  className={cn(
                    "text-[10px] font-bold px-2 py-0.5 rounded-full shrink-0",
                    camp.status === "Active"
                      ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                      : "bg-indigo-50 text-indigo-700 border border-indigo-200"
                  )}
                >
                  {camp.status}
                </span>
              </div>

              {/* Progress Bar & Budget Utilization Numbers */}
              <div>
                <div className="flex items-center justify-between text-[11px] mb-1">
                  <span className="text-slate-500 font-medium">Budget Utilization</span>
                  <span className="font-extrabold text-slate-800">
                    {percentUsed}%{" "}
                    <span className="text-slate-400 font-normal">
                      (${camp.spent.toLocaleString()} / ${camp.totalBudget.toLocaleString()})
                    </span>
                  </span>
                </div>

                {/* Horizontal Progress Bar */}
                <div className="w-full h-2 rounded-full bg-slate-200/80 overflow-hidden">
                  <div
                    className={cn("h-full rounded-full transition-all duration-500", barGradient)}
                    style={{ width: `${percentUsed}%` }}
                  />
                </div>
              </div>

              {/* Pacing & ROAS Subtext */}
              <div className="flex items-center justify-between text-[10px] text-slate-400 font-medium pt-0.5">
                <span>Daily Pacing: ${camp.dailySpend}/day</span>
                <span className="text-emerald-700 bg-emerald-50 px-1.5 py-0.2 rounded font-bold">
                  {camp.roas}
                </span>
              </div>
            </div>
          );
        })}

        {/* Global Summary Footprint */}
        <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs">
          <span className="text-slate-500 font-medium">Total Monthly Pacing</span>
          <span className="font-extrabold text-slate-900">
            ${totalSpent.toLocaleString()}{" "}
            <span className="text-slate-400 font-normal">
              of ${totalBudget.toLocaleString()} ({overallUtilization}%)
            </span>
          </span>
        </div>
      </CardContent>
    </Card>
  );
};
