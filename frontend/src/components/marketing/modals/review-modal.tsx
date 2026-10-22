"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  X,
  Sparkles,
  CheckCircle2,
  ThumbsUp,
  MessageSquare,
  Repeat,
  Send,
  MoreHorizontal,
  Calendar,
  AlertCircle,
  Lightbulb,
  Check,
} from "lucide-react";
import {
  LinkedInIcon,
  InstagramIcon,
  FacebookIcon,
  XIcon,
} from "@/components/social/social-icons";
import { KanbanCardItem } from "@/components/marketing/content-calendar-kanban";
import { regeneratePostWithFeedback } from "@/services/marketingService";

interface ReviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  post: KanbanCardItem | null;
  onApprove: (postId: string) => Promise<void> | void;
  onPostUpdated?: (updatedPost: KanbanCardItem) => void;
}

const PRESET_RULES = [
  "Never use the word 'revolutionary'",
  "Emphasize 72-hour DSO reduction",
  "Make tone conversational for B2B CFOs",
  "Add explicit ROI metric callout",
];

export const ReviewModal: React.FC<ReviewModalProps> = ({
  isOpen,
  onClose,
  post,
  onApprove,
  onPostUpdated,
}) => {
  const [feedbackText, setFeedbackText] = React.useState("");
  const [isRegenerating, setIsRegenerating] = React.useState(false);
  const [isApproving, setIsApproving] = React.useState(false);
  const [statusNotice, setStatusNotice] = React.useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // Local copy of post content for immediate reflection after regeneration
  const [currentCaption, setCurrentCaption] = React.useState("");

  React.useEffect(() => {
    if (post) {
      setCurrentCaption(post.summary || post.title || "");
      setFeedbackText("");
      setStatusNotice(null);
    }
  }, [post]);

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

  if (!isOpen || !post) return null;

  const handleRegenerate = async () => {
    if (!feedbackText.trim()) {
      setStatusNotice({
        type: "error",
        message: "Please enter a feedback rule or constraint to guide regeneration.",
      });
      return;
    }

    setIsRegenerating(true);
    setStatusNotice(null);

    try {
      const res = await regeneratePostWithFeedback(post.id, feedbackText.trim());
      if (res.success && res.post) {
        setCurrentCaption(res.post.caption);
        setStatusNotice({
          type: "success",
          message: "Feedback rule saved to client memory! Caption regenerated.",
        });
        if (onPostUpdated) {
          onPostUpdated({
            ...post,
            summary: res.post.caption,
          });
        }
      }
    } catch (err: any) {
      setStatusNotice({
        type: "error",
        message: err?.message || "Failed to regenerate post with feedback.",
      });
    } finally {
      setIsRegenerating(false);
    }
  };

  const handleApprove = async () => {
    setIsApproving(true);
    setStatusNotice(null);
    try {
      await onApprove(post.id);
      onClose();
    } catch (err: any) {
      setStatusNotice({
        type: "error",
        message: err?.message || "Failed to approve and schedule post.",
      });
      setIsApproving(false);
    }
  };

  const renderPlatformIcon = (platform: string) => {
    switch (platform) {
      case "linkedin":
        return <LinkedInIcon className="w-3.5 h-3.5 text-[#0A66C2]" />;
      case "instagram":
        return <InstagramIcon className="w-3.5 h-3.5 text-[#E4405F]" />;
      case "facebook":
        return <FacebookIcon className="w-3.5 h-3.5 text-[#1877F2]" />;
      case "x":
        return <XIcon className="w-3 h-3 text-slate-800" />;
      default:
        return null;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal Dialog */}
      <div
        role="dialog"
        aria-modal="true"
        className="relative w-full max-w-5xl rounded-2xl bg-white shadow-2xl border border-slate-200/90 z-10 overflow-hidden my-auto animate-in fade-in zoom-in-95 duration-150"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50/60">
          <div className="flex items-center gap-3">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse" />
            <div>
              <h3 className="text-base font-bold text-slate-900 leading-none">
                AI Approval &amp; Feedback Review
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                Supervised training loop: Verify draft creative or teach the AI your tone constraints.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Status Notice Banner */}
        {statusNotice && (
          <div
            className={`px-6 py-2.5 text-xs flex items-center justify-between border-b ${
              statusNotice.type === "success"
                ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                : "bg-rose-50 text-rose-800 border-rose-200"
            }`}
          >
            <div className="flex items-center gap-2">
              {statusNotice.type === "success" ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              ) : (
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              )}
              <span>{statusNotice.message}</span>
            </div>
            <button
              onClick={() => setStatusNotice(null)}
              className="text-[11px] underline font-medium ml-4"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Dual-Column Body */}
        <div className="grid grid-cols-1 lg:grid-cols-12 divide-y lg:divide-y-0 lg:divide-x divide-slate-200 max-h-[calc(88vh-130px)] overflow-y-auto">
          {/* LEFT COLUMN: Realistic Platform Mockup (col-span-7) */}
          <div className="lg:col-span-7 p-6 bg-slate-100/60 space-y-4 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                  Platform Preview Mockup
                </span>
                <div className="flex items-center gap-1.5 bg-white px-2.5 py-1 rounded-full border border-slate-200 text-xs text-slate-700">
                  {post.platforms.map((p) => (
                    <span key={p} className="flex items-center gap-1">
                      {renderPlatformIcon(p)}
                      <span className="capitalize text-[11px] font-semibold">{p}</span>
                    </span>
                  ))}
                </div>
              </div>

              {/* Feed Card Simulation (LinkedIn / Meta style) */}
              <div className="rounded-xl border border-slate-300/80 bg-white shadow-xs overflow-hidden">
                {/* Author Info */}
                <div className="p-4 pb-3 flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-[#D7525A] text-white flex items-center justify-center font-bold text-sm shadow-2xs">
                      AR
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-bold text-slate-900">Agile Receivables</span>
                        <span className="text-[10px] text-slate-400 font-medium">• 1st</span>
                      </div>
                      <p className="text-[11px] text-slate-500 leading-tight">
                        AI-Powered Revenue Cycle &amp; Patient AR Automation
                      </p>
                      <p className="text-[10px] text-slate-400 mt-0.5 flex items-center gap-1">
                        <span>Just now</span>
                        <span>•</span>
                        <span>Edited</span>
                        <span>•</span>
                        <span>🌐</span>
                      </p>
                    </div>
                  </div>
                  <button className="text-slate-400 hover:text-slate-600 p-1">
                    <MoreHorizontal className="w-4 h-4" />
                  </button>
                </div>

                {/* Post Caption / Text */}
                <div className="px-4 pb-3 text-xs sm:text-[13px] text-slate-800 leading-relaxed whitespace-pre-line space-y-2">
                  <p className="font-semibold text-slate-900">{post.title}</p>
                  <p>{currentCaption}</p>
                  <div className="pt-2 text-indigo-600 text-xs font-medium space-x-1.5">
                    <span>#HealthcareRCM</span>
                    <span>#Receivables</span>
                    <span>#CFOInsights</span>
                    <span>#B2BFinance</span>
                  </div>
                </div>

                {/* Creative Visual Asset */}
                <div className="w-full bg-slate-950 border-y border-slate-200 overflow-hidden relative group aspect-[16/9] max-h-[300px]">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={post.thumbnailUrl}
                    alt={post.title}
                    className="w-full h-full object-cover group-hover:scale-102 transition-transform duration-300"
                  />
                  <div className="absolute bottom-2 left-2 px-2 py-1 bg-black/60 backdrop-blur-xs rounded text-[10px] font-semibold text-white">
                    {post.contentPillar || "Product Feature"}
                  </div>
                </div>

                {/* Social Proof / Metrics */}
                <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
                  <div className="flex items-center gap-1">
                    <span className="flex -space-x-1">
                      <span className="w-4 h-4 rounded-full bg-blue-600 text-white flex items-center justify-center text-[9px]">👍</span>
                      <span className="w-4 h-4 rounded-full bg-rose-600 text-white flex items-center justify-center text-[9px]">❤️</span>
                    </span>
                    <span className="ml-1 font-medium">42 reactions</span>
                  </div>
                  <span>14 comments • 6 reposts</span>
                </div>

                {/* Action Bar */}
                <div className="px-2 py-1.5 grid grid-cols-4 gap-1 text-slate-600 text-xs font-medium text-center">
                  <button className="py-2 hover:bg-slate-50 rounded flex items-center justify-center gap-1.5 transition-colors">
                    <ThumbsUp className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">Like</span>
                  </button>
                  <button className="py-2 hover:bg-slate-50 rounded flex items-center justify-center gap-1.5 transition-colors">
                    <MessageSquare className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">Comment</span>
                  </button>
                  <button className="py-2 hover:bg-slate-50 rounded flex items-center justify-center gap-1.5 transition-colors">
                    <Repeat className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">Repost</span>
                  </button>
                  <button className="py-2 hover:bg-slate-50 rounded flex items-center justify-center gap-1.5 transition-colors">
                    <Send className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">Send</span>
                  </button>
                </div>
              </div>
            </div>

            <p className="text-[11px] text-slate-500 text-center pt-2">
              Visual mockup rendered to LinkedIn &amp; Meta desktop feed specifications.
            </p>
          </div>

          {/* RIGHT COLUMN: Feedback & AI Training Controls (col-span-5) */}
          <div className="lg:col-span-5 p-6 flex flex-col justify-between space-y-6 bg-white">
            <div className="space-y-5">
              {/* Pillar & Meta Info */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    Content Pillar
                  </span>
                  <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-rose-50 text-[#D7525A] border border-rose-200">
                    {post.contentPillar || "Product Feature"}
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-amber-50/70 border border-amber-200/80 text-xs text-amber-900 space-y-1">
                  <div className="font-bold flex items-center gap-1.5 text-amber-800">
                    <Sparkles className="w-3.5 h-3.5 text-amber-600" />
                    <span>AI Learning Opportunity</span>
                  </div>
                  <p className="text-[11px] leading-relaxed text-amber-900/90">
                    Entering feedback below trains the AI model for this client. Every correction becomes a persistent rule stored in <code>ClientFeedbackRules</code>.
                  </p>
                </div>
              </div>

              {/* Feedback Input Section */}
              <div className="space-y-2">
                <label className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                  <Lightbulb className="w-3.5 h-3.5 text-[#D7525A]" />
                  Correction / Training Rule
                </label>
                <textarea
                  rows={4}
                  value={feedbackText}
                  onChange={(e) => setFeedbackText(e.target.value)}
                  placeholder="e.g. Never use the word 'revolutionary'. Tone should sound like an executive peer, not a sales pitch. Emphasize 72-hour DSO reduction..."
                  className="w-full p-3 text-xs text-slate-800 rounded-xl border border-slate-300 focus:outline-hidden focus:ring-1 focus:ring-[#D7525A] focus:border-[#D7525A] placeholder:text-slate-400 bg-slate-50/50 leading-relaxed"
                />

                {/* Preset Rule Chips */}
                <div className="space-y-1.5 pt-1">
                  <span className="text-[10px] font-bold uppercase text-slate-400">Quick Rule Presets:</span>
                  <div className="flex flex-wrap gap-1.5">
                    {PRESET_RULES.map((rule) => (
                      <button
                        key={rule}
                        type="button"
                        onClick={() => setFeedbackText(rule)}
                        className="text-[11px] px-2.5 py-1 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors border border-slate-200/60 text-left"
                      >
                        {rule}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Actions: Regenerate vs Approve */}
            <div className="space-y-3 pt-4 border-t border-slate-100">
              {/* Secondary Action: Regenerate */}
              <button
                type="button"
                onClick={handleRegenerate}
                disabled={isRegenerating || isApproving}
                className="w-full py-2.5 px-4 rounded-xl border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold shadow-2xs transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isRegenerating ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
                    <span>Regenerating with Rule...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5 text-[#D7525A]" />
                    <span>Regenerate with AI</span>
                  </>
                )}
              </button>

              {/* Primary Action: Approve & Schedule */}
              <button
                type="button"
                onClick={handleApprove}
                disabled={isApproving || isRegenerating}
                className="w-full py-2.5 px-4 rounded-xl bg-[#D7525A] hover:bg-[#c2434b] text-white text-xs font-bold shadow-xs transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isApproving ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                    <span>Scheduling Post...</span>
                  </>
                ) : (
                  <>
                    <Check className="w-4 h-4 stroke-[2.5]" />
                    <span>Approve &amp; Schedule</span>
                  </>
                )}
              </button>

              <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
                <span className="flex items-center gap-1">
                  <Calendar className="w-3 h-3 text-slate-400" />
                  Scheduled Date: {post.scheduledDate || "Automated Cadence"}
                </span>
                <span>ID: {post.id.slice(0, 8)}...</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
