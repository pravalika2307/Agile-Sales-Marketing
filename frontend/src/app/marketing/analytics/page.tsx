"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MarketingKpiCards } from "@/components/marketing/marketing-kpi-cards";
import { TrafficConversionsChart } from "@/components/marketing/traffic-conversions-chart";
import { AIInsightsWidget } from "@/components/marketing/widgets/ai-insights-widget";
import { Calendar, Target } from "lucide-react";
import {
  LinkedInIcon,
  FacebookIcon,
  XIcon,
} from "@/components/social/social-icons";

export default function MarketingAnalyticsPage() {
  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-200/80">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-500">Marketing</span>
              <span className="text-slate-300">/</span>
              <span className="text-xs font-semibold text-indigo-600">Analytics</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 mt-1">
              Marketing Analytics &amp; Attribution
            </h1>
            <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
              Cross-channel reach, blended traffic attribution, and MQL conversion velocity.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <Link href="/marketing/content-calendar">
              <Button
                variant="outline"
                size="sm"
                className="text-xs font-semibold border-indigo-200 text-indigo-700 hover:bg-indigo-50 bg-white"
              >
                <Calendar className="w-3.5 h-3.5 mr-1.5 text-indigo-600" />
                <span>Content Calendar</span>
              </Button>
            </Link>
          </div>
        </div>

        {/* KPI Cards */}
        <MarketingKpiCards />

        {/* Traffic & Conversions Chart + AI Insights */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
          <div className="xl:col-span-8 space-y-6">
            <TrafficConversionsChart />

            {/* Channel Performance Breakdown */}
            <Card className="rounded-xl border border-slate-200/80 bg-white shadow-xs">
              <CardHeader className="p-4 sm:p-5 border-b border-slate-100 flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm sm:text-base font-bold text-slate-900">
                    Channel Traffic &amp; Conversion Breakdown
                  </CardTitle>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Attribution weighted across first-touch and last-touch parameters
                  </p>
                </div>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                  +18.4% Net MoM
                </span>
              </CardHeader>

              <CardContent className="p-4 sm:p-5">
                <div className="space-y-4">
                  {[
                    {
                      name: "LinkedIn (Organic & Sponsored)",
                      icon: <LinkedInIcon className="w-4 h-4 text-[#0A66C2]" />,
                      share: "44%",
                      visits: "65,240",
                      conversions: 810,
                      barWidth: "44%",
                      barColor: "bg-[#0A66C2]",
                    },
                    {
                      name: "Google Search (High Intent)",
                      icon: <Target className="w-4 h-4 text-emerald-600" />,
                      share: "28%",
                      visits: "41,520",
                      conversions: 516,
                      barWidth: "28%",
                      barColor: "bg-emerald-500",
                    },
                    {
                      name: "Meta Ads & Instagram",
                      icon: <FacebookIcon className="w-4 h-4 text-[#1877F2]" />,
                      share: "18%",
                      visits: "26,690",
                      conversions: 331,
                      barWidth: "18%",
                      barColor: "bg-indigo-500",
                    },
                    {
                      name: "X (Twitter) B2B Threads",
                      icon: <XIcon className="w-4 h-4 text-slate-900" />,
                      share: "10%",
                      visits: "14,840",
                      conversions: 183,
                      barWidth: "10%",
                      barColor: "bg-slate-800",
                    },
                  ].map((chan) => (
                    <div key={chan.name} className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="flex items-center gap-2 font-bold text-slate-800">
                          {chan.icon}
                          {chan.name}
                        </span>
                        <div className="flex items-center gap-4 text-slate-500 font-medium">
                          <span>{chan.visits} visits</span>
                          <span className="font-bold text-slate-900">
                            {chan.conversions} conv ({chan.share})
                          </span>
                        </div>
                      </div>
                      <div className="w-full h-2 rounded-full bg-slate-100 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${chan.barColor}`}
                          style={{ width: chan.barWidth }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="xl:col-span-4 space-y-6">
            <AIInsightsWidget />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
