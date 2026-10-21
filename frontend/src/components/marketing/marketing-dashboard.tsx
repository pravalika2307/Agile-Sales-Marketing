"use client";

import * as React from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MarketingKpiCards } from "./marketing-kpi-cards";
import { TrafficConversionsChart } from "./traffic-conversions-chart";
import { ContentCalendarKanban } from "./content-calendar-kanban";
import { AIInsightsWidget } from "./widgets/ai-insights-widget";
import { ClientApprovalQueueWidget } from "./widgets/client-approval-queue-widget";
import { ActiveAdCampaignsWidget } from "./widgets/active-ad-campaigns-widget";
import { ComposePostModal } from "@/components/social/compose-post-modal";
import {
  Share2,
  Plus,
  Megaphone,
} from "lucide-react";

export const MarketingDashboard: React.FC = () => {
  const [composeModalOpen, setComposeModalOpen] = React.useState(false);

  return (
    <div className="space-y-6">
      {/* ── Top Header / Command Center ───────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-200/80">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 text-white flex items-center justify-center shadow-xs">
              <Megaphone className="w-4 h-4" />
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900">
              Marketing Overview
            </h1>
            <Badge
              variant="neutral"
              className="bg-indigo-100 text-indigo-800 border-indigo-200 text-xs font-semibold px-2 py-0.5 rounded-full"
            >
              Enterprise Marketing Suite
            </Badge>
          </div>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">
            Omnichannel audience reach, automated social content calendar, and client approval workflows.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2.5">
          <Link href="/marketing/social-media">
            <Button
              variant="outline"
              size="sm"
              className="text-xs font-semibold border-indigo-200 hover:bg-indigo-50 text-indigo-700 bg-white"
            >
              <Share2 className="w-3.5 h-3.5 mr-1.5 text-indigo-600" />
              <span>Social Media Hub</span>
            </Button>
          </Link>

          <Button
            variant="primary"
            size="sm"
            onClick={() => setComposeModalOpen(true)}
            className="text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs"
          >
            <Plus className="w-3.5 h-3.5 mr-1" />
            <span>Compose Post</span>
          </Button>
        </div>
      </div>

      {/* ── 3. Top KPI Summary Cards (Specification 3) ─────────────────────── */}
      <MarketingKpiCards />

      {/* ── Main Layout: Wide Content Area + Right-Hand Widget Panel ─────── */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        {/* Left Column: Traffic & Conversions Chart + Content Calendar Kanban */}
        <div className="xl:col-span-8 space-y-6">
          {/* 4. Main Data Visualization (Specification 4) */}
          <TrafficConversionsChart />

          {/* 5. Content Calendar Kanban Interface (Specification 5) */}
          <div id="content-calendar">
            <ContentCalendarKanban />
          </div>
        </div>

        {/* Right Column: Stack of 3 Distinct Widgets (Specification 6) ──────── */}
        <div className="xl:col-span-4 space-y-6">
          {/* Widget 1: AI Insights Report */}
          <AIInsightsWidget />

          {/* Widget 2: Client Approval Queue (triggers n8n webhook) */}
          <ClientApprovalQueueWidget />

          {/* Widget 3: Active Ad Campaigns */}
          <ActiveAdCampaignsWidget />
        </div>
      </div>

      {/* Modal for Compose Post */}
      <ComposePostModal
        isOpen={composeModalOpen}
        onClose={() => setComposeModalOpen(false)}
        onPostCreated={() => {
          setComposeModalOpen(false);
        }}
      />
    </div>
  );
};
