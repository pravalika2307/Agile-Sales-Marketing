"use client";

import * as React from "react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  UploadCloud,
  Image as ImageIcon,
  Film,
  Calendar,
  Clock,
  Sparkles,
  Check,
  X,
  AlertCircle,
  HelpCircle,
} from "lucide-react";
import { LinkedInIcon, InstagramIcon, FacebookIcon } from "./social-icons";

export interface ComposePostModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPostCreated?: (post: any) => void;
}

export const ComposePostModal: React.FC<ComposePostModalProps> = ({
  isOpen,
  onClose,
  onPostCreated,
}) => {
  const [selectedPlatforms, setSelectedPlatforms] = React.useState<{
    linkedin: boolean;
    instagram: boolean;
    facebook: boolean;
  }>({
    linkedin: true,
    instagram: false,
    facebook: false,
  });

  const [postContent, setPostContent] = React.useState("");
  const [campaignTag, setCampaignTag] = React.useState("Q4 Brand Authority");
  const [scheduleType, setScheduleType] = React.useState<"now" | "later">("now");
  const [scheduledDate, setScheduledDate] = React.useState("2026-10-24");
  const [scheduledTime, setScheduledTime] = React.useState("10:00");
  const [uploadedFiles, setUploadedFiles] = React.useState<string[]>([
    "benchmark-report-cover.png",
  ]);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  const togglePlatform = (platform: "linkedin" | "instagram" | "facebook") => {
    setSelectedPlatforms((prev) => ({
      ...prev,
      [platform]: !prev[platform],
    }));
  };

  const handleRemoveFile = (index: number) => {
    setUploadedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleAddSampleMedia = () => {
    if (uploadedFiles.length < 3) {
      setUploadedFiles((prev) => [...prev, `social-asset-${prev.length + 1}.png`]);
    }
  };

  const hasSelectedPlatform =
    selectedPlatforms.linkedin ||
    selectedPlatforms.instagram ||
    selectedPlatforms.facebook;

  const handleSubmit = () => {
    if (!hasSelectedPlatform || !postContent.trim()) return;

    setIsSubmitting(true);
    setTimeout(() => {
      setIsSubmitting(false);
      onPostCreated?.({
        id: `post-${Date.now()}`,
        content: postContent,
        platforms: Object.entries(selectedPlatforms)
          .filter(([_, v]) => v)
          .map(([k]) => k),
        scheduledFor: scheduleType === "later" ? `${scheduledDate} ${scheduledTime}` : "Published Now",
        status: scheduleType === "later" ? "Scheduled" : "Published",
      });
      onClose();
    }, 400);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Compose Multi-Platform Social Post"
      description="Create, preview, and schedule organic content across LinkedIn, Instagram, and Facebook."
      maxWidth="lg"
      footer={
        <div className="flex items-center justify-between w-full">
          <div className="text-xs text-slate-400">
            {scheduleType === "later" ? "Will be queued for delivery" : "Ready for immediate publish"}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              disabled={!hasSelectedPlatform || !postContent.trim() || isSubmitting}
              className="bg-purple-600 hover:bg-purple-700 text-white font-semibold shadow-xs"
            >
              {isSubmitting ? "Processing..." : scheduleType === "later" ? "Schedule Post" : "Publish Post"}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-5">
        {/* Platform Selection */}
        <div>
          <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
            Target Social Channels
          </label>
          <div className="grid grid-cols-3 gap-3">
            {/* LinkedIn */}
            <button
              type="button"
              onClick={() => togglePlatform("linkedin")}
              className={`p-3 rounded-xl border flex items-center gap-2.5 transition-all text-left ${
                selectedPlatforms.linkedin
                  ? "border-blue-500 bg-blue-50/60 shadow-xs ring-1 ring-blue-500/20"
                  : "border-slate-200 hover:bg-slate-50 text-slate-600"
              }`}
            >
              <div
                className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold text-white shrink-0 ${
                  selectedPlatforms.linkedin ? "bg-[#0A66C2]" : "bg-slate-300"
                }`}
              >
                <LinkedInIcon className="w-4 h-4" />
              </div>
              <div className="truncate">
                <div className="font-bold text-xs text-header">LinkedIn</div>
                <div className="text-[10px] text-slate-400">Company & Reps</div>
              </div>
            </button>

            {/* Instagram */}
            <button
              type="button"
              onClick={() => togglePlatform("instagram")}
              className={`p-3 rounded-xl border flex items-center gap-2.5 transition-all text-left ${
                selectedPlatforms.instagram
                  ? "border-pink-500 bg-pink-50/50 shadow-xs ring-1 ring-pink-500/20"
                  : "border-slate-200 hover:bg-slate-50 text-slate-600"
              }`}
            >
              <div
                className={`w-8 h-8 rounded-lg flex items-center justify-center text-white shrink-0 ${
                  selectedPlatforms.instagram
                    ? "bg-gradient-to-tr from-amber-500 via-rose-500 to-purple-600"
                    : "bg-slate-300"
                }`}
              >
                <InstagramIcon className="w-4 h-4" />
              </div>
              <div className="truncate">
                <div className="font-bold text-xs text-header">Instagram</div>
                <div className="text-[10px] text-slate-400">Feed & Stories</div>
              </div>
            </button>

            {/* Facebook */}
            <button
              type="button"
              onClick={() => togglePlatform("facebook")}
              className={`p-3 rounded-xl border flex items-center gap-2.5 transition-all text-left ${
                selectedPlatforms.facebook
                  ? "border-indigo-600 bg-indigo-50/50 shadow-xs ring-1 ring-indigo-600/20"
                  : "border-slate-200 hover:bg-slate-50 text-slate-600"
              }`}
            >
              <div
                className={`w-8 h-8 rounded-lg flex items-center justify-center text-white shrink-0 ${
                  selectedPlatforms.facebook ? "bg-[#1877F2]" : "bg-slate-300"
                }`}
              >
                <FacebookIcon className="w-4 h-4" />
              </div>
              <div className="truncate">
                <div className="font-bold text-xs text-header">Facebook</div>
                <div className="text-[10px] text-slate-400">Business Page</div>
              </div>
            </button>
          </div>
          {!hasSelectedPlatform && (
            <p className="text-[11px] text-amber-600 mt-1.5 flex items-center gap-1">
              <AlertCircle className="w-3.5 h-3.5" />
              Please select at least one social media channel.
            </p>
          )}
        </div>

        {/* Post Copy / Content */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">
              Post Copy
            </label>
            <span className="text-[11px] font-mono text-slate-400">
              {postContent.length} / 3000 chars
            </span>
          </div>
          <textarea
            rows={4}
            value={postContent}
            onChange={(e) => setPostContent(e.target.value)}
            placeholder="Share an industry insight, case study takeaway, or company announcement..."
            className="w-full text-xs sm:text-sm p-3 rounded-xl border border-slate-200 focus:border-purple-500 focus:ring-1 focus:ring-purple-500 focus:outline-none transition-colors"
          />

          {/* Quick Hashtag & Campaign Tags */}
          <div className="flex flex-wrap items-center gap-1.5 mt-2">
            <span className="text-[10px] uppercase font-bold text-slate-400 mr-1">Tags:</span>
            {["#B2BSales", "#WorkingCapital", "#AgileInsights", "#Fintech"].map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => setPostContent((prev) => (prev ? `${prev} ${tag}` : tag))}
                className="text-[11px] px-2 py-0.5 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-600 font-medium transition-colors"
              >
                {tag}
              </button>
            ))}
          </div>
        </div>

        {/* Media Upload Skeleton */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">
              Media Attachments
            </label>
            <span className="text-[11px] text-slate-400">Up to 3 images or 1 video</span>
          </div>

          <div className="border-2 border-dashed border-slate-200 hover:border-purple-400 rounded-xl p-4 text-center bg-slate-50/50 hover:bg-purple-50/20 transition-all cursor-pointer"
               onClick={handleAddSampleMedia}>
            <div className="w-10 h-10 rounded-full bg-white border border-slate-200 shadow-2xs flex items-center justify-center mx-auto mb-2 text-purple-600">
              <UploadCloud className="w-5 h-5" />
            </div>
            <div className="text-xs font-semibold text-slate-700">
              Click to browse or drop visual assets here
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              PNG, JPG, WebP, or MP4 video (max 50MB)
            </p>
          </div>

          {/* Attached Files List */}
          {uploadedFiles.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2.5">
              {uploadedFiles.map((file, i) => (
                <div
                  key={i}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white border border-slate-200 text-xs font-medium text-slate-700 shadow-2xs"
                >
                  <ImageIcon className="w-3.5 h-3.5 text-purple-600" />
                  <span className="truncate max-w-[150px]">{file}</span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemoveFile(i);
                    }}
                    className="text-slate-400 hover:text-slate-600 ml-1"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Scheduling Options */}
        <div className="p-3.5 rounded-xl bg-slate-50/80 border border-slate-200/80 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
              Publishing Cadence
            </span>
            <div className="flex rounded-lg bg-white p-0.5 border border-slate-200 shadow-2xs">
              <button
                type="button"
                onClick={() => setScheduleType("now")}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                  scheduleType === "now"
                    ? "bg-purple-600 text-white font-semibold shadow-2xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Publish Now
              </button>
              <button
                type="button"
                onClick={() => setScheduleType("later")}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                  scheduleType === "later"
                    ? "bg-purple-600 text-white font-semibold shadow-2xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Schedule
              </button>
            </div>
          </div>

          {scheduleType === "later" && (
            <div className="grid grid-cols-2 gap-3 pt-2 border-t border-slate-200/60">
              <div>
                <label className="text-[11px] font-medium text-slate-600 block mb-1">
                  Target Date
                </label>
                <Input
                  type="date"
                  value={scheduledDate}
                  onChange={(e) => setScheduledDate(e.target.value)}
                  className="h-8 text-xs bg-white"
                />
              </div>
              <div>
                <label className="text-[11px] font-medium text-slate-600 block mb-1">
                  Target Time (EST)
                </label>
                <Input
                  type="time"
                  value={scheduledTime}
                  onChange={(e) => setScheduledTime(e.target.value)}
                  className="h-8 text-xs bg-white"
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
};
