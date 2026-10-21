"use client";

import * as React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import {
  Lightbulb,
  TrendingUp,
  Target,
  Sparkles,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";

export interface AIInsightItem {
  id: string;
  type: "recommendation" | "performance" | "audience" | "optimization";
  icon: React.ComponentType<{ className?: string }>;
  iconBg: string;
  iconColor: string;
  badge: string;
  text: string;
  impactScore?: string;
}

const DEFAULT_INSIGHTS: AIInsightItem[] = [
  {
    id: "insight-1",
    type: "recommendation",
    icon: Lightbulb,
    iconBg: "bg-amber-50 border-amber-200/60",
    iconColor: "text-amber-600",
    badge: "Scheduling Recommendation",
    text: "Optimal posting window for B2B CFOs on LinkedIn is Tuesday & Thursday at 8:30 AM EST (+34% CTR over baseline).",
    impactScore: "+34% CTR",
  },
  {
    id: "insight-2",
    type: "performance",
    icon: TrendingUp,
    iconBg: "bg-emerald-50 border-emerald-200/60",
    iconColor: "text-emerald-600",
    badge: "Creative Performance",
    text: "Video walkthroughs showcasing Retell AI telephony generated 2.8x higher demo conversion than static graphics.",
    impactScore: "2.8x Conv",
  },
  {
    id: "insight-3",
    type: "audience",
    icon: Target,
    iconBg: "bg-indigo-50 border-indigo-200/60",
    iconColor: "text-indigo-600",
    badge: "High-Intent Surge",
    text: "Mid-market manufacturing accounts generated 48% of all link clicks following the 14-day DSO case study release.",
    impactScore: "48% Clicks",
  },
  {
    id: "insight-4",
    type: "optimization",
    icon: Sparkles,
    iconBg: "bg-purple-50 border-purple-200/60",
    iconColor: "text-purple-600",
    badge: "Content Repurposing",
    text: "AI recommendation: Repurpose the 'Voice Telephony Automation' playbook into a 4-slide carousel for increased saves.",
    impactScore: "High Impact",
  },
];

export const AIInsightsWidget: React.FC = () => {
  const [insights] = React.useState<AIInsightItem[]>(DEFAULT_INSIGHTS);
  const [isRefreshing, setIsRefreshing] = React.useState(false);
  const [lastUpdated, setLastUpdated] = React.useState("Just now");

  const handleRefresh = () => {
    setIsRefreshing(true);
    setTimeout(() => {
      setIsRefreshing(false);
      setLastUpdated("Updated seconds ago");
    }, 700);
  };

  return (
    <Card className="rounded-xl border border-slate-200/80 bg-white shadow-xs hover:shadow-sm transition-all duration-200">
      <CardHeader className="p-4 sm:p-5 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 text-white flex items-center justify-center shadow-xs">
            <Sparkles className="w-3.5 h-3.5" />
          </div>
          <div>
            <CardTitle className="text-sm sm:text-base font-bold text-slate-900 tracking-tight">
              AI Insights Report
            </CardTitle>
            <p className="text-[11px] text-slate-400">Autonomous performance takeaways</p>
          </div>
        </div>

        {/* Regenerate Action */}
        <button
          type="button"
          onClick={handleRefresh}
          disabled={isRefreshing}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          title="Regenerate AI Analysis"
          aria-label="Regenerate AI Analysis"
        >
          <RefreshCw className={cn("w-3.5 h-3.5", isRefreshing && "animate-spin text-indigo-600")} />
        </button>
      </CardHeader>

      <CardContent className="p-4 sm:p-5 space-y-3">
        {insights.map((item) => {
          const Icon = item.icon;

          return (
            <div
              key={item.id}
              className="p-3 rounded-xl border border-slate-100 bg-slate-50/50 hover:bg-slate-50 hover:border-slate-200 transition-all duration-150 flex items-start gap-3"
            >
              {/* Icon */}
              <div
                className={cn(
                  "w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 mt-0.5",
                  item.iconBg,
                  item.iconColor
                )}
              >
                <Icon className="w-4 h-4" />
              </div>

              {/* Text Takeaway */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                    {item.badge}
                  </span>
                  {item.impactScore && (
                    <span className="text-[10px] font-extrabold text-indigo-700 bg-indigo-50 px-1.5 py-0.2 rounded-md">
                      {item.impactScore}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-700 leading-relaxed font-medium">
                  {item.text}
                </p>
              </div>
            </div>
          );
        })}

        <div className="pt-1 flex items-center justify-between text-[10px] text-slate-400 font-medium">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
            Telemetry: Retell &amp; Social Webhooks
          </span>
          <span>{lastUpdated}</span>
        </div>
      </CardContent>
    </Card>
  );
};
