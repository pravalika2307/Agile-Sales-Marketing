"use client";

import * as React from "react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  BarChart3,
  TrendingUp,
  Eye,
  ThumbsUp,
  MessageSquare,
  Share2,
  MousePointerClick,
  Info,
  CheckCircle2,
} from "lucide-react";
import { LinkedInIcon } from "./social-icons";

export interface ManualLinkedInStatsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onStatsSaved?: (stats: any) => void;
}

export const ManualLinkedInStatsModal: React.FC<ManualLinkedInStatsModalProps> = ({
  isOpen,
  onClose,
  onStatsSaved,
}) => {
  const [selectedPost, setSelectedPost] = React.useState("post-1");
  const [impressions, setImpressions] = React.useState("1840");
  const [uniqueViews, setUniqueViews] = React.useState("1220");
  const [reactions, setReactions] = React.useState("64");
  const [comments, setComments] = React.useState("18");
  const [reposts, setReposts] = React.useState("9");
  const [clicks, setClicks] = React.useState("42");
  const [isSaving, setIsSaving] = React.useState(false);

  // Parse numerical metrics
  const numImpressions = Math.max(0, parseInt(impressions, 10) || 0);
  const numReactions = Math.max(0, parseInt(reactions, 10) || 0);
  const numComments = Math.max(0, parseInt(comments, 10) || 0);
  const numReposts = Math.max(0, parseInt(reposts, 10) || 0);
  const numClicks = Math.max(0, parseInt(clicks, 10) || 0);

  const totalInteractions = numReactions + numComments + numReposts + numClicks;
  const engagementRate =
    numImpressions > 0 ? ((totalInteractions / numImpressions) * 100).toFixed(2) : "0.00";

  const handleSave = () => {
    setIsSaving(true);
    setTimeout(() => {
      setIsSaving(false);
      onStatsSaved?.({
        postId: selectedPost,
        impressions: numImpressions,
        uniqueViews: Math.max(0, parseInt(uniqueViews, 10) || 0),
        reactions: numReactions,
        comments: numComments,
        reposts: numReposts,
        clicks: numClicks,
        engagementRate: parseFloat(engagementRate),
      });
      onClose();
    }, 400);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Enter LinkedIn Performance Stats (Manual)"
      description="Manually record organic post metrics from LinkedIn Analytics while third-party API and n8n connectors are pending."
      maxWidth="md"
      footer={
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-1.5 text-xs text-slate-500 font-medium">
            <span>Engagement Rate:</span>
            <span className="font-bold text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full text-[11px]">
              {engagementRate}%
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={onClose} disabled={isSaving}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSave}
              disabled={isSaving || numImpressions === 0}
              className="bg-[#0A66C2] hover:bg-[#084e96] text-white font-semibold shadow-xs"
            >
              {isSaving ? "Saving..." : "Save LinkedIn Stats"}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        {/* Helper Banner */}
        <div className="p-3 rounded-xl bg-blue-50/60 border border-blue-200/60 text-xs text-blue-900 flex items-start gap-2.5">
          <LinkedInIcon className="w-4 h-4 text-[#0A66C2] shrink-0 mt-0.5" />
          <div className="leading-relaxed">
            Copy organic numbers from your <strong>LinkedIn Page Analytics</strong>. These stats will immediately reflect in your Marketing Overview KPI cards and campaign performance logs.
          </div>
        </div>

        {/* Post Selection */}
        <div>
          <label className="text-xs font-bold text-slate-700 uppercase tracking-wider block mb-1">
            Target Published Post
          </label>
          <select
            value={selectedPost}
            onChange={(e) => setSelectedPost(e.target.value)}
            className="w-full text-xs sm:text-sm p-2.5 rounded-xl border border-slate-200 bg-white focus:outline-none focus:border-blue-500 font-medium"
          >
            <option value="post-1">Q4 B2B Working Capital Benchmark Report Release</option>
            <option value="post-2">Case Study: Eliminating 14 Days of DSO in Healthcare</option>
            <option value="post-3">Product Spotlight: Retell Telephony Integration</option>
            <option value="post-4">Agile Executive Webinar: Cash Flow Acceleration</option>
          </select>
        </div>

        {/* Impression & Reach Inputs */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[11px] font-semibold text-slate-600 flex items-center gap-1 mb-1">
              <Eye className="w-3.5 h-3.5 text-slate-400" />
              <span>Total Impressions</span>
            </label>
            <Input
              type="number"
              min="0"
              value={impressions}
              onChange={(e) => setImpressions(e.target.value)}
              placeholder="e.g. 1840"
              className="h-8 text-xs font-medium"
            />
          </div>

          <div>
            <label className="text-[11px] font-semibold text-slate-600 flex items-center gap-1 mb-1">
              <Eye className="w-3.5 h-3.5 text-slate-400" />
              <span>Unique Members Reached</span>
            </label>
            <Input
              type="number"
              min="0"
              value={uniqueViews}
              onChange={(e) => setUniqueViews(e.target.value)}
              placeholder="e.g. 1220"
              className="h-8 text-xs font-medium"
            />
          </div>
        </div>

        {/* Engagement Interaction Inputs */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1">
          <div>
            <label className="text-[10px] font-semibold uppercase text-slate-500 flex items-center gap-1 mb-1">
              <ThumbsUp className="w-3 h-3 text-blue-600" />
              <span>Reactions</span>
            </label>
            <Input
              type="number"
              min="0"
              value={reactions}
              onChange={(e) => setReactions(e.target.value)}
              className="h-8 text-xs"
            />
          </div>

          <div>
            <label className="text-[10px] font-semibold uppercase text-slate-500 flex items-center gap-1 mb-1">
              <MessageSquare className="w-3 h-3 text-emerald-600" />
              <span>Comments</span>
            </label>
            <Input
              type="number"
              min="0"
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              className="h-8 text-xs"
            />
          </div>

          <div>
            <label className="text-[10px] font-semibold uppercase text-slate-500 flex items-center gap-1 mb-1">
              <Share2 className="w-3 h-3 text-purple-600" />
              <span>Reposts</span>
            </label>
            <Input
              type="number"
              min="0"
              value={reposts}
              onChange={(e) => setReposts(e.target.value)}
              className="h-8 text-xs"
            />
          </div>

          <div>
            <label className="text-[10px] font-semibold uppercase text-slate-500 flex items-center gap-1 mb-1">
              <MousePointerClick className="w-3 h-3 text-indigo-600" />
              <span>Link Clicks</span>
            </label>
            <Input
              type="number"
              min="0"
              value={clicks}
              onChange={(e) => setClicks(e.target.value)}
              className="h-8 text-xs"
            />
          </div>
        </div>

        {/* Formula breakdown card */}
        <div className="rounded-xl p-3 bg-slate-50 border border-slate-200/70 flex items-center justify-between text-xs text-slate-600">
          <div>
            <span className="font-semibold text-header">Total Interactions:</span>{" "}
            <span className="font-mono font-bold text-slate-800">{totalInteractions}</span>
            <span className="text-[11px] text-slate-400 ml-1">
              ({numReactions} + {numComments} + {numReposts} + {numClicks})
            </span>
          </div>
          <div className="font-medium text-[11px] text-slate-500">
            Formula: (Interactions / Impressions)
          </div>
        </div>
      </div>
    </Modal>
  );
};
