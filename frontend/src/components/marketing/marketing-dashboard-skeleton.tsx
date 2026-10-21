"use client";

import * as React from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Megaphone,
  Sparkles,
  Users,
  Send,
  Mail,
  BarChart3,
  Calendar,
  Layers,
  ArrowRight,
  TrendingUp,
  Target,
  FileText,
  Clock,
  CheckCircle2,
  ExternalLink,
  Plus,
  HelpCircle,
  Share2,
} from "lucide-react";

export const MarketingDashboardSkeleton: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* ── Top Header / Command Center ───────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-200/80">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-indigo-600 text-white flex items-center justify-center shadow-xs">
              <Megaphone className="w-4 h-4" />
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-header">
              Marketing Overview
            </h1>
            <Badge
              variant="neutral"
              className="bg-purple-100 text-purple-700 border-purple-200 text-xs font-semibold px-2 py-0.5 rounded-full"
            >
              Marketing Mode · Foundation Skeleton
            </Badge>
          </div>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">
            Audience segmentation, educational nurture cadences, and MQL-to-sales qualification pipeline.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2.5">
          <Link href="/marketing/social-media">
            <Button
              variant="outline"
              size="sm"
              className="text-xs font-semibold border-purple-200 hover:bg-purple-50 text-purple-700"
            >
              <Share2 className="w-3.5 h-3.5 mr-1.5 text-purple-600" />
              <span>Social Media Hub</span>
            </Button>
          </Link>

          <Button
            variant="outline"
            size="sm"
            className="text-xs font-medium border-slate-200 hover:bg-slate-50 text-slate-700"
          >
            <Calendar className="w-3.5 h-3.5 mr-1.5 text-slate-400" />
            <span>Last 30 Days</span>
          </Button>

          <Button
            variant="primary"
            size="sm"
            className="text-xs font-semibold bg-purple-600 hover:bg-purple-700 text-white shadow-xs"
          >
            <Plus className="w-3.5 h-3.5 mr-1" />
            <span>New Marketing Campaign</span>
          </Button>
        </div>
      </div>

      {/* ── Metric KPI Overview Cards ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1: Reachable Audience */}
        <Card className="border border-slate-200/80 shadow-2xs hover:shadow-xs transition-shadow bg-white">
          <CardContent className="p-4 sm:p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Total Reachable Audience
              </span>
              <div className="w-8 h-8 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
                <Users className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl sm:text-3xl font-extrabold tracking-tight text-header">
                2,480
              </span>
              <span className="text-xs font-semibold text-emerald-600 flex items-center">
                +14.2%
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Active CRM contacts across 5 audience lists
            </p>
          </CardContent>
        </Card>

        {/* KPI 2: Active Marketing Campaigns */}
        <Card className="border border-slate-200/80 shadow-2xs hover:shadow-xs transition-shadow bg-white">
          <CardContent className="p-4 sm:p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Active Campaigns
              </span>
              <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                <Send className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl sm:text-3xl font-extrabold tracking-tight text-header">
                3
              </span>
              <span className="inline-flex items-center text-[10px] font-medium text-indigo-600 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-full">
                1 Draft · 2 Live
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Nurture sequences & product broadcasts
            </p>
          </CardContent>
        </Card>

        {/* KPI 3: Email Engagement Rate */}
        <Card className="border border-slate-200/80 shadow-2xs hover:shadow-xs transition-shadow bg-white">
          <CardContent className="p-4 sm:p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Avg. Engagement Rate
              </span>
              <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                <BarChart3 className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl sm:text-3xl font-extrabold tracking-tight text-header">
                42.8%
              </span>
              <span className="text-xs text-slate-400">
                (14.6% CTR)
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Verified inbox open & link click events
            </p>
          </CardContent>
        </Card>

        {/* KPI 4: Marketing Qualified Leads */}
        <Card className="border border-slate-200/80 shadow-2xs hover:shadow-xs transition-shadow bg-white">
          <CardContent className="p-4 sm:p-5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                MQLs Generated
              </span>
              <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
                <Target className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl sm:text-3xl font-extrabold tracking-tight text-header">
                38
              </span>
              <span className="inline-flex items-center text-[10px] font-medium text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
                Lead Score ≥ 60
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Warm prospects ready for sales SDR handoff
            </p>
          </CardContent>
        </Card>
      </div>

      {/* ── Main Two-Column Layout ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Marketing Campaigns & Coordinated Journey */}
        <div className="lg:col-span-2 space-y-6">
          {/* Section: Marketing Campaigns */}
          <Card className="border border-slate-200/80 shadow-2xs bg-white">
            <div className="p-4 sm:p-5 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h2 className="font-bold text-sm sm:text-base text-header">
                  Marketing Campaigns & Sequences
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Multi-channel announcements and educational nurture cadences.
                </p>
              </div>
              <Link
                href="/campaigns"
                className="text-xs font-semibold text-purple-600 hover:text-purple-700 flex items-center gap-1"
              >
                <span>View All Campaigns</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </Link>
            </div>

            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50/70 text-slate-400 font-semibold border-b border-slate-100 uppercase tracking-wider text-[10px]">
                    <tr>
                      <th className="py-3 px-4">Campaign Name</th>
                      <th className="py-3 px-4">Type</th>
                      <th className="py-3 px-4">Audience</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4 text-right">Performance</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-600">
                    {/* Row 1 */}
                    <tr className="hover:bg-slate-50/50 transition-colors">
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-header">Q4 Benchmark Report Release</div>
                        <div className="text-[11px] text-slate-400">Executive survey & data insights</div>
                      </td>
                      <td className="py-3.5 px-4">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-purple-50 text-purple-700 border border-purple-200/50">
                          marketing_social
                        </span>
                      </td>
                      <td className="py-3.5 px-4 font-medium text-slate-700">840 contacts</td>
                      <td className="py-3.5 px-4">
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/60">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          Active
                        </span>
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <div className="font-semibold text-slate-800">46.5% Open</div>
                        <div className="text-[10px] text-slate-400">18.2% Click</div>
                      </td>
                    </tr>

                    {/* Row 2 */}
                    <tr className="hover:bg-slate-50/50 transition-colors">
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-header">Mid-Market CFO Nurture Cadence</div>
                        <div className="text-[11px] text-slate-400">3-Step educational drip series</div>
                      </td>
                      <td className="py-3.5 px-4">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-indigo-50 text-indigo-700 border border-indigo-200/50">
                          hybrid
                        </span>
                      </td>
                      <td className="py-3.5 px-4 font-medium text-slate-700">520 contacts</td>
                      <td className="py-3.5 px-4">
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/60">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          Active
                        </span>
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <div className="font-semibold text-slate-800">38.2% Open</div>
                        <div className="text-[10px] text-slate-400">11.4% Click</div>
                      </td>
                    </tr>

                    {/* Row 3 */}
                    <tr className="hover:bg-slate-50/50 transition-colors">
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-header">Product Spotlight: Retell Telephony</div>
                        <div className="text-[11px] text-slate-400">Monthly feature announcement newsletter</div>
                      </td>
                      <td className="py-3.5 px-4">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-purple-50 text-purple-700 border border-purple-200/50">
                          marketing_social
                        </span>
                      </td>
                      <td className="py-3.5 px-4 font-medium text-slate-700">1,120 contacts</td>
                      <td className="py-3.5 px-4">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600">
                          Draft
                        </span>
                      </td>
                      <td className="py-3.5 px-4 text-right text-slate-400">—</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Section: Coordinated Sales & Marketing Handoff Funnel */}
          <Card className="border border-slate-200/80 shadow-2xs bg-white">
            <div className="p-4 sm:p-5 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h2 className="font-bold text-sm sm:text-base text-header flex items-center gap-2">
                  <span>One Coordinated Sales & Marketing Journey</span>
                  <span className="inline-flex items-center text-[10px] font-medium text-purple-700 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded-full">
                    Workflow Architecture
                  </span>
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  How marketing touches warm prospects and trigger high-priority sales SDR outreach.
                </p>
              </div>
            </div>

            <CardContent className="p-4 sm:p-6">
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-center">
                {/* Step 1 */}
                <div className="rounded-xl border border-slate-200/70 p-3 bg-slate-50/50 flex flex-col items-center">
                  <div className="w-7 h-7 rounded-full bg-purple-100 text-purple-700 font-bold text-xs flex items-center justify-center mb-2">
                    1
                  </div>
                  <div className="font-semibold text-xs text-header">Audience Ingestion</div>
                  <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                    HubSpot sync & CSV list segmentation
                  </div>
                </div>

                {/* Step 2 */}
                <div className="rounded-xl border border-purple-200/70 p-3 bg-purple-50/30 flex flex-col items-center">
                  <div className="w-7 h-7 rounded-full bg-purple-600 text-white font-bold text-xs flex items-center justify-center mb-2">
                    2
                  </div>
                  <div className="font-semibold text-xs text-purple-900">Marketing Nurture</div>
                  <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                    Benchmark reports & educational emails
                  </div>
                </div>

                {/* Step 3 */}
                <div className="rounded-xl border border-amber-200/70 p-3 bg-amber-50/30 flex flex-col items-center">
                  <div className="w-7 h-7 rounded-full bg-amber-500 text-white font-bold text-xs flex items-center justify-center mb-2">
                    3
                  </div>
                  <div className="font-semibold text-xs text-amber-900">MQL Threshold</div>
                  <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                    High engagement elevates lead score ≥ 60
                  </div>
                </div>

                {/* Step 4 */}
                <div className="rounded-xl border border-agile-outlinered/50 p-3 bg-agile-lightorange/30 flex flex-col items-center">
                  <div className="w-7 h-7 rounded-full bg-agile-red text-white font-bold text-xs flex items-center justify-center mb-2">
                    4
                  </div>
                  <div className="font-semibold text-xs text-agile-red">Sales Opportunity</div>
                  <div className="text-[11px] text-slate-500 mt-1 leading-snug">
                    SDR phone call & commercial deal creation
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right 1 Col: Audience Segments & Templates Library */}
        <div className="space-y-6">
          {/* Audience Segments */}
          <Card className="border border-slate-200/80 shadow-2xs bg-white">
            <div className="p-4 border-b border-slate-100 flex items-center justify-between">
              <h3 className="font-bold text-xs sm:text-sm text-header flex items-center gap-1.5">
                <Users className="w-4 h-4 text-purple-600" />
                <span>Audience Segments</span>
              </h3>
              <Link href="/leads" className="text-xs font-semibold text-purple-600 hover:text-purple-700">
                Manage
              </Link>
            </div>
            <CardContent className="p-3 space-y-2">
              <div className="p-2.5 rounded-lg border border-slate-100 hover:border-slate-200 bg-slate-50/50 transition-colors flex items-center justify-between">
                <div>
                  <div className="font-semibold text-xs text-header">Financial Services Decision Makers</div>
                  <div className="text-[10px] text-slate-400">Source: HubSpot Sync</div>
                </div>
                <span className="inline-flex items-center text-xs font-bold text-slate-700 bg-white border border-slate-200 px-2 py-0.5 rounded-full">
                  640
                </span>
              </div>

              <div className="p-2.5 rounded-lg border border-slate-100 hover:border-slate-200 bg-slate-50/50 transition-colors flex items-center justify-between">
                <div>
                  <div className="font-semibold text-xs text-header">Mid-Market CFOs (Q4 Target)</div>
                  <div className="text-[10px] text-slate-400">Source: CSV Import</div>
                </div>
                <span className="inline-flex items-center text-xs font-bold text-slate-700 bg-white border border-slate-200 px-2 py-0.5 rounded-full">
                  480
                </span>
              </div>

              <div className="p-2.5 rounded-lg border border-slate-100 hover:border-slate-200 bg-slate-50/50 transition-colors flex items-center justify-between">
                <div>
                  <div className="font-semibold text-xs text-header">Engaged Webinar Registrants</div>
                  <div className="text-[10px] text-slate-400">Source: Event Webhook</div>
                </div>
                <span className="inline-flex items-center text-xs font-bold text-slate-700 bg-white border border-slate-200 px-2 py-0.5 rounded-full">
                  215
                </span>
              </div>
            </CardContent>
          </Card>

          {/* Marketing Content & Templates */}
          <Card className="border border-slate-200/80 shadow-2xs bg-white">
            <div className="p-4 border-b border-slate-100 flex items-center justify-between">
              <h3 className="font-bold text-xs sm:text-sm text-header flex items-center gap-1.5">
                <FileText className="w-4 h-4 text-indigo-600" />
                <span>Marketing Templates</span>
              </h3>
              <span className="inline-flex items-center text-[10px] font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-full">
                5 Ready
              </span>
            </div>
            <CardContent className="p-3 space-y-2">
              <div className="p-2.5 rounded-lg border border-slate-100 hover:border-slate-200 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-xs text-header">Benchmark Report Release</span>
                  <span className="text-[10px] font-medium text-purple-700 bg-purple-50 px-1.5 py-0.5 rounded">
                    announcement
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 mt-1 line-clamp-1">
                  &ldquo;Exclusive: 2026 B2B Working Capital & Receivables Benchmark...&rdquo;
                </p>
              </div>

              <div className="p-2.5 rounded-lg border border-slate-100 hover:border-slate-200 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-xs text-header">Client Case Study Teaser</span>
                  <span className="text-[10px] font-medium text-indigo-700 bg-indigo-50 px-1.5 py-0.5 rounded">
                    nurture
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 mt-1 line-clamp-1">
                  &ldquo;How {"{{company.name}}"} can eliminate 14 days off DSO...&rdquo;
                </p>
              </div>

              <div className="p-2.5 rounded-lg border border-slate-100 hover:border-slate-200 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-xs text-header">Product Newsletter (Monthly)</span>
                  <span className="text-[10px] font-medium text-purple-700 bg-purple-50 px-1.5 py-0.5 rounded">
                    announcement
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 mt-1 line-clamp-1">
                  &ldquo;What is new in Agile Sales & Marketing this month...&rdquo;
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};
