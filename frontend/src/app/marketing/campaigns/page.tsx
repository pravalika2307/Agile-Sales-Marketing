"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import {
  Plus,
  Search,
  Calendar,
} from "lucide-react";
import { ActiveAdCampaignsWidget } from "@/components/marketing/widgets/active-ad-campaigns-widget";

interface MarketingCampaign {
  id: string;
  name: string;
  type: "paid_ad" | "nurture" | "social_blast" | "webinar";
  status: "Active" | "Scheduled" | "Draft" | "Completed";
  channels: string[];
  reach: string;
  conversions: number;
  budget: string;
  dateRange: string;
}

const MARKETING_CAMPAIGNS: MarketingCampaign[] = [
  {
    id: "mkt-camp-1",
    name: "Q4 CFO Benchmark & Liquidity Whitepaper",
    type: "social_blast",
    status: "Active",
    channels: ["LinkedIn", "X", "Facebook"],
    reach: "48,290",
    conversions: 342,
    budget: "$3,500",
    dateRange: "Oct 10 – Nov 15, 2026",
  },
  {
    id: "mkt-camp-2",
    name: "Active Meta — Lookalike B2B Finance Leaders",
    type: "paid_ad",
    status: "Active",
    channels: ["Meta Ads", "Instagram"],
    reach: "64,120",
    conversions: 512,
    budget: "$5,000",
    dateRange: "Oct 01 – Oct 31, 2026",
  },
  {
    id: "mkt-camp-3",
    name: "Healthcare Invoice Automation Video Series",
    type: "nurture",
    status: "Active",
    channels: ["LinkedIn", "YouTube", "Email"],
    reach: "22,400",
    conversions: 184,
    budget: "$2,200",
    dateRange: "Oct 15 – Nov 30, 2026",
  },
  {
    id: "mkt-camp-4",
    name: "Omnichannel Receivables Masterclass Webinar",
    type: "webinar",
    status: "Scheduled",
    channels: ["LinkedIn Live", "Email Blast", "X"],
    reach: "12,800",
    conversions: 94,
    budget: "$1,800",
    dateRange: "Nov 05 – Nov 20, 2026",
  },
];

export default function MarketingCampaignsPage() {
  const [searchTerm, setSearchTerm] = React.useState("");
  const [activeTab, setActiveTab] = React.useState<"all" | "paid" | "nurture">("all");
  const [newCampaignModal, setNewCampaignModal] = React.useState(false);

  const filtered = MARKETING_CAMPAIGNS.filter((c) => {
    const matchesSearch = c.name.toLowerCase().includes(searchTerm.toLowerCase());
    if (activeTab === "paid") return matchesSearch && c.type === "paid_ad";
    if (activeTab === "nurture") return matchesSearch && (c.type === "nurture" || c.type === "social_blast");
    return matchesSearch;
  });

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-200/80">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-500">Marketing</span>
              <span className="text-slate-300">/</span>
              <span className="text-xs font-semibold text-indigo-600">Campaigns</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 mt-1">
              Marketing Campaigns &amp; Pacing
            </h1>
            <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
              Multi-channel social campaigns, educational nurture cadences, and paid media ad spend.
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

            <Button
              variant="primary"
              size="sm"
              onClick={() => setNewCampaignModal(true)}
              className="text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs"
            >
              <Plus className="w-3.5 h-3.5 mr-1" />
              <span>New Marketing Campaign</span>
            </Button>
          </div>
        </div>

        {/* Top Pacing Overview Widget */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            {/* Filter Tabs & Search */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="inline-flex items-center rounded-lg bg-slate-100 p-1 border border-slate-200/80 text-xs">
                <button
                  type="button"
                  onClick={() => setActiveTab("all")}
                  className={`px-3 py-1 rounded-md font-semibold transition-colors ${
                    activeTab === "all" ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  All Campaigns ({MARKETING_CAMPAIGNS.length})
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("paid")}
                  className={`px-3 py-1 rounded-md font-semibold transition-colors ${
                    activeTab === "paid" ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  Paid Ads
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("nurture")}
                  className={`px-3 py-1 rounded-md font-semibold transition-colors ${
                    activeTab === "nurture" ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  Nurture &amp; Social
                </button>
              </div>

              <div className="w-full sm:w-64">
                <Input
                  icon={<Search className="w-4 h-4 text-slate-400" />}
                  placeholder="Search marketing campaigns..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="h-8 text-xs bg-white"
                />
              </div>
            </div>

            {/* Campaign Cards List */}
            <div className="space-y-3">
              {filtered.map((camp) => (
                <Card
                  key={camp.id}
                  className="rounded-xl border border-slate-200/80 bg-white shadow-xs hover:shadow-sm transition-all"
                >
                  <CardContent className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    <div className="space-y-1.5 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-bold text-indigo-600 uppercase tracking-wider bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-200/60">
                          {camp.type.replace("_", " ")}
                        </span>
                        <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200/60">
                          {camp.status}
                        </span>
                      </div>

                      <h3 className="text-sm font-bold text-slate-900 truncate">{camp.name}</h3>

                      <div className="flex items-center gap-3 text-xs text-slate-400 flex-wrap">
                        <span>Channels: {camp.channels.join(", ")}</span>
                        <span>•</span>
                        <span>{camp.dateRange}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-6 sm:shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-slate-100">
                      <div className="text-right">
                        <span className="text-[10px] text-slate-400 block font-semibold uppercase">Total Reach</span>
                        <span className="text-sm font-bold text-slate-900">{camp.reach}</span>
                      </div>

                      <div className="text-right">
                        <span className="text-[10px] text-slate-400 block font-semibold uppercase">Conversions</span>
                        <span className="text-sm font-bold text-emerald-600">{camp.conversions}</span>
                      </div>

                      <div className="text-right">
                        <span className="text-[10px] text-slate-400 block font-semibold uppercase">Budget</span>
                        <span className="text-sm font-bold text-indigo-950">{camp.budget}</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>

          {/* Right Column: Live Paid Pacing Widget */}
          <div className="space-y-6">
            <ActiveAdCampaignsWidget />
          </div>
        </div>

        {/* New Campaign Modal */}
        <Modal
          isOpen={newCampaignModal}
          onClose={() => setNewCampaignModal(false)}
          title="Create Marketing Campaign"
          description="Initialize a new marketing campaign across paid or organic channels."
          maxWidth="md"
        >
          <div className="space-y-4 py-2">
            <div>
              <label className="text-xs font-bold text-slate-700 block mb-1">Campaign Name *</label>
              <input
                type="text"
                placeholder="e.g. Q4 CFO Working Capital Push"
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-hidden focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="text-xs font-bold text-slate-700 block mb-1">Campaign Type</label>
              <select className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 bg-white">
                <option value="social_blast">Social Media Campaign (LinkedIn, X, Meta)</option>
                <option value="paid_ad">Paid Advertising (Meta, Google, LinkedIn Ads)</option>
                <option value="nurture">Educational Nurture Sequence</option>
                <option value="webinar">Live Webinar / Masterclass</option>
              </select>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <Button variant="outline" size="sm" onClick={() => setNewCampaignModal(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                className="bg-indigo-600 hover:bg-indigo-700 text-white"
                onClick={() => {
                  setNewCampaignModal(false);
                  alert("Marketing campaign created.");
                }}
              >
                Create Campaign
              </Button>
            </div>
          </div>
        </Modal>
      </div>
    </AppShell>
  );
}
