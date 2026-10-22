"use client";

import * as React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import {
  Calendar,
  Plus,
  GripVertical,
  Clock,
  CheckCircle2,
  RefreshCw,
  ExternalLink,
} from "lucide-react";
import {
  LinkedInIcon,
  InstagramIcon,
  FacebookIcon,
  XIcon,
} from "@/components/social/social-icons";
import { cn } from "@/lib/utils";
import {
  fetchMarketingKanban,
  updateKanbanPostStatus,
  KanbanCardData,
} from "@/services/marketingService";
import { ReviewModal } from "./modals/review-modal";

export type ColumnId = "backlog" | "in_progress" | "awaiting_approval" | "scheduled" | "posted";

export type SocialPlatform = "linkedin" | "instagram" | "x" | "facebook";

export interface KanbanCardItem {
  id: string;
  title: string;
  summary: string;
  platforms: SocialPlatform[];
  statusBadge: {
    label: string;
    variant: "new" | "priority" | "review" | "scheduled" | "default";
  };
  thumbnailUrl: string;
  columnId: ColumnId;
  scheduledDate?: string;
  authorName: string;
  authorInitials: string;
  contentPillar?: string;
  permalink?: string | null;
  aiCost?: number | null;
  analytics?: {
    impressions: number;
    reach: number;
    likes: number;
    comments: number;
    shares: number;
    totalEngagement: number;
    engagementRate: number;
    linkClicks: number;
  } | null;
}

const FALLBACK_CARDS: KanbanCardItem[] = [
  {
    id: "kb-1",
    title: "Patient AR Isn't Just a Follow-Up Problem. It's a Workflow Problem.",
    summary: "Early-stage delinquency cadences replacing cold calls with automated omnichannel nudges.",
    platforms: ["linkedin"],
    statusBadge: { label: "Backlog", variant: "new" },
    thumbnailUrl: "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=160&auto=format&fit=crop&q=80",
    columnId: "backlog",
    scheduledDate: "Oct 2026",
    authorName: "Pravalika Palle",
    authorInitials: "PP",
    contentPillar: "Product Feature",
  },
  {
    id: "kb-2",
    title: "Facing the 2025 Healthcare Financial Crisis? Agile Has Solutions",
    summary: "Healthcare RCM insights examining operating margin pressures and digital payment acceleration.",
    platforms: ["facebook", "instagram"],
    statusBadge: { label: "Backlog", variant: "new" },
    thumbnailUrl: "https://images.unsplash.com/photo-1551836022-d5d88e9218df?w=160&auto=format&fit=crop&q=80",
    columnId: "backlog",
    scheduledDate: "Drafting",
    authorName: "Marcus Chen",
    authorInitials: "MC",
    contentPillar: "Healthcare RCM",
  },
  {
    id: "kb-3",
    title: "72-Hour Friendly Nudge: Omnichannel AR Follow-Up Cadence",
    summary: "Cadence that actually works: 72-hour friendly nudge; day 7 confirm payment date; day 14 escalate.",
    platforms: ["facebook", "instagram"],
    statusBadge: { label: "In Progress", variant: "default" },
    thumbnailUrl: "https://images.unsplash.com/photo-1557804506-669a67965ba0?w=160&auto=format&fit=crop&q=80",
    columnId: "in_progress",
    scheduledDate: "Drafting Copy",
    authorName: "Lakshay Narula",
    authorInitials: "LN",
    contentPillar: "Social Media",
  },
  {
    id: "kb-4",
    title: "Kunal's Interview: Behind the Scenes of Retell AI Telephony",
    summary: "Video asset interview exploring conversational voice bots for inbound patient inquiries.",
    platforms: ["linkedin"],
    statusBadge: { label: "Video Asset", variant: "priority" },
    thumbnailUrl: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=160&auto=format&fit=crop&q=80",
    columnId: "in_progress",
    scheduledDate: "In Creative Review",
    authorName: "Pravalika Palle",
    authorInitials: "PP",
    contentPillar: "Product Feature",
  },
  {
    id: "kb-5",
    title: "Why Faster Payments Matter More Than Ever in Healthcare Revenue Cycle",
    summary: "Healthcare RCM leadership post awaiting client review and CMO sign-off before social scheduling.",
    platforms: ["linkedin"],
    statusBadge: { label: "Awaiting Sign-off", variant: "review" },
    thumbnailUrl: "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=160&auto=format&fit=crop&q=80",
    columnId: "awaiting_approval",
    scheduledDate: "Review Pending",
    authorName: "Lakshay Narula",
    authorInitials: "LN",
    contentPillar: "Healthcare RCM",
  },
  {
    id: "kb-6",
    title: "Manage Payment Disputes From One Centralized Platform",
    summary: "Product Feature post showcasing dispute management dashboard (Achieved peak 38.5% ER).",
    platforms: ["linkedin"],
    statusBadge: { label: "Review Ready", variant: "review" },
    thumbnailUrl: "https://images.unsplash.com/photo-1551836022-d5d88e9218df?w=160&auto=format&fit=crop&q=80",
    columnId: "awaiting_approval",
    scheduledDate: "Sign-off Pending",
    authorName: "Pravalika Palle",
    authorInitials: "PP",
    contentPillar: "Product Feature",
  },
  {
    id: "kb-7",
    title: "Patient AR Is Becoming a Revenue Strategy — Not a Back-Office Task",
    summary: "Thought leadership release on transforming AR teams into strategic value centers.",
    platforms: ["linkedin"],
    statusBadge: { label: "Scheduled", variant: "scheduled" },
    thumbnailUrl: "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=160&auto=format&fit=crop&q=80",
    columnId: "scheduled",
    scheduledDate: "Oct 24, 2026",
    authorName: "Marcus Chen",
    authorInitials: "MC",
    contentPillar: "Product Feature",
  },
  {
    id: "kb-8",
    title: "What If You Could Add Patient AR + Call Center Capacity Without Adding Another Team?",
    summary: "Omnichannel scaling playbook highlighting AI phone agents and automated WhatsApp dispatch.",
    platforms: ["linkedin"],
    statusBadge: { label: "Scheduled", variant: "scheduled" },
    thumbnailUrl: "https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=160&auto=format&fit=crop&q=80",
    columnId: "scheduled",
    scheduledDate: "Oct 28, 2026",
    authorName: "Lakshay Narula",
    authorInitials: "LN",
    contentPillar: "Product Feature",
  },
];

const COLUMNS: { id: ColumnId; title: string; countColor: string; accentColor: string }[] = [
  { id: "backlog", title: "Backlog", countColor: "bg-slate-100 text-slate-700", accentColor: "border-t-slate-400" },
  { id: "in_progress", title: "In Progress", countColor: "bg-blue-100 text-blue-700", accentColor: "border-t-blue-500" },
  { id: "awaiting_approval", title: "Awaiting Approval", countColor: "bg-amber-100 text-amber-800", accentColor: "border-t-amber-500" },
  { id: "scheduled", title: "Scheduled", countColor: "bg-emerald-100 text-emerald-800", accentColor: "border-t-emerald-500" },
  { id: "posted", title: "Published / Posted", countColor: "bg-indigo-100 text-indigo-800", accentColor: "border-t-indigo-500" },
];

export const ContentCalendarKanban: React.FC = () => {
  const [cards, setCards] = React.useState<KanbanCardItem[]>(FALLBACK_CARDS);
  const [loading, setLoading] = React.useState(true);
  const [draggingCardId, setDraggingCardId] = React.useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = React.useState<ColumnId | null>(null);
  const [selectedCard, setSelectedCard] = React.useState<KanbanCardItem | null>(null);
  const [reviewCard, setReviewCard] = React.useState<KanbanCardItem | null>(null);
  const [createModalOpen, setCreateModalOpen] = React.useState(false);
  const [newTitle, setNewTitle] = React.useState("");
  const [showAllColumns, setShowAllColumns] = React.useState(false);

  // Load real seeded posts from /api/marketing/kanban
  const loadKanbanData = React.useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchMarketingKanban();
      if (data.cards && data.cards.length > 0) {
        setCards(data.cards);
      }
    } catch (err: unknown) {
      console.warn("Could not fetch live marketing Kanban posts, using fallbacks:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadKanbanData();
  }, [loadKanbanData]);

  // Drag and drop handlers
  const handleDragStart = (e: React.DragEvent, cardId: string) => {
    e.dataTransfer.setData("text/plain", cardId);
    e.dataTransfer.effectAllowed = "move";
    setDraggingCardId(cardId);
  };

  const handleDragEnd = () => {
    setDraggingCardId(null);
    setDragOverColumn(null);
  };

  const handleDragOver = (e: React.DragEvent, colId: ColumnId) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (dragOverColumn !== colId) {
      setDragOverColumn(colId);
    }
  };

  const handleDragLeave = (e: React.DragEvent, colId: ColumnId) => {
    e.preventDefault();
    if (dragOverColumn === colId) {
      setDragOverColumn(null);
    }
  };

  const handleDrop = async (e: React.DragEvent, targetColId: ColumnId) => {
    e.preventDefault();
    const cardId = e.dataTransfer.getData("text/plain") || draggingCardId;
    if (!cardId) return;

    // Optimistic UI update
    setCards((prev) =>
      prev.map((card) => {
        if (card.id === cardId) {
          let updatedBadge = card.statusBadge;
          if (targetColId === "scheduled") {
            updatedBadge = { label: "Scheduled", variant: "scheduled" };
          } else if (targetColId === "awaiting_approval") {
            updatedBadge = { label: "Awaiting Review", variant: "review" };
          } else if (targetColId === "in_progress") {
            updatedBadge = { label: "In Progress", variant: "default" };
          } else if (targetColId === "posted") {
            updatedBadge = { label: "Published", variant: "priority" };
          } else {
            updatedBadge = { label: "Backlog", variant: "new" };
          }
          return {
            ...card,
            columnId: targetColId,
            statusBadge: updatedBadge,
          };
        }
        return card;
      })
    );

    setDraggingCardId(null);
    setDragOverColumn(null);

    // Persist to PostgreSQL database via API
    try {
      await updateKanbanPostStatus(cardId, targetColId);
    } catch (err: unknown) {
      console.error("Failed to persist card status move to database:", err);
    }
  };

  // Dedicated handlers for Approval & Feedback Review Modal
  const handleApproveReviewCard = async (postId: string) => {
    setCards((prev) =>
      prev.map((item) =>
        item.id === postId
          ? {
              ...item,
              columnId: "scheduled",
              statusBadge: { label: "Scheduled", variant: "scheduled" },
            }
          : item
      )
    );
    try {
      await updateKanbanPostStatus(postId, "scheduled");
    } catch (err: unknown) {
      console.error("Failed to approve and schedule post:", err);
    }
  };

  const handleReviewPostUpdated = (updatedPost: KanbanCardItem) => {
    setCards((prev) =>
      prev.map((item) => (item.id === updatedPost.id ? updatedPost : item))
    );
    setReviewCard(updatedPost);
  };

  const handleCreatePost = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;

    const newCard: KanbanCardItem = {
      id: `kb-${Date.now()}`,
      title: newTitle.trim(),
      summary: "Newly planned social campaign asset ready for content drafting.",
      platforms: ["linkedin", "facebook"],
      statusBadge: { label: "New", variant: "new" },
      thumbnailUrl: "https://images.unsplash.com/photo-1551836022-d5d88e9218df?w=160&auto=format&fit=crop&q=80",
      columnId: "backlog",
      scheduledDate: "Unscheduled",
      authorName: "Pravalika Palle",
      authorInitials: "PP",
    };

    setCards([newCard, ...cards]);
    setNewTitle("");
    setCreateModalOpen(false);
  };

  const renderPlatformIcon = (platform: SocialPlatform) => {
    switch (platform) {
      case "linkedin":
        return <LinkedInIcon className="w-3.5 h-3.5 text-[#0A66C2]" />;
      case "instagram":
        return <InstagramIcon className="w-3.5 h-3.5 text-[#E4405F]" />;
      case "x":
        return <XIcon className="w-3.5 h-3.5 text-slate-800" />;
      case "facebook":
        return <FacebookIcon className="w-3.5 h-3.5 text-[#1877F2]" />;
    }
  };

  const renderBadge = (badge: KanbanCardItem["statusBadge"]) => {
    switch (badge.variant) {
      case "new":
        return (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
            {badge.label}
          </span>
        );
      case "priority":
        return (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200">
            {badge.label}
          </span>
        );
      case "review":
        return (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
            {badge.label}
          </span>
        );
      case "scheduled":
        return (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
            {badge.label}
          </span>
        );
      default:
        return (
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
            {badge.label}
          </span>
        );
    }
  };

  // Determine active columns to display (either the 4 planning columns or all 5 including Posted)
  const columnsToRender = showAllColumns ? COLUMNS : COLUMNS.slice(0, 4);

  return (
    <Card className="rounded-xl border border-slate-200/80 bg-white shadow-xs hover:shadow-sm transition-all duration-200">
      <CardHeader className="p-4 sm:p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
            <Calendar className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <CardTitle className="text-base sm:text-lg font-bold text-slate-900 tracking-tight">
                Content Calendar (Kanban)
              </CardTitle>
              {loading && <RefreshCw className="w-3.5 h-3.5 animate-spin text-slate-400" />}
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Live PostgreSQL workflow: Drag-and-drop posts between planning phases, client sign-offs, and scheduled publishing.
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 self-start sm:self-auto">
          {/* Toggle View for Published Posts */}
          <button
            type="button"
            onClick={() => setShowAllColumns(!showAllColumns)}
            className="text-xs font-semibold px-2.5 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-600 transition-colors"
          >
            {showAllColumns ? "Show Planning Queue (4 Cols)" : "Show All Stages + Published (5 Cols)"}
          </button>

          <Button
            variant="primary"
            size="sm"
            onClick={() => setCreateModalOpen(true)}
            className="text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs inline-flex items-center gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Post Card</span>
          </Button>
        </div>
      </CardHeader>

      <CardContent className="p-4 sm:p-5">
        {/* Kanban Board Grid */}
        <div
          className={cn(
            "grid gap-4",
            showAllColumns
              ? "grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5"
              : "grid-cols-1 md:grid-cols-2 xl:grid-cols-4"
          )}
        >
          {columnsToRender.map((col) => {
            const columnCards = cards.filter((c) => c.columnId === col.id);
            const isOver = dragOverColumn === col.id;

            return (
              <div
                key={col.id}
                onDragOver={(e) => handleDragOver(e, col.id)}
                onDragLeave={(e) => handleDragLeave(e, col.id)}
                onDrop={(e) => handleDrop(e, col.id)}
                className={cn(
                  "rounded-xl bg-slate-50/70 border p-3 flex flex-col min-h-[420px] transition-all duration-200",
                  col.accentColor,
                  isOver
                    ? "border-2 border-dashed border-indigo-500 bg-indigo-50/40 shadow-xs"
                    : "border-slate-200/80"
                )}
              >
                {/* Column Header */}
                <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-200/60">
                  <span className="text-xs font-bold text-slate-800 tracking-tight flex items-center gap-2">
                    {col.title}
                  </span>
                  <span
                    className={cn(
                      "text-[10px] font-bold px-2 py-0.5 rounded-full shrink-0",
                      col.countColor
                    )}
                  >
                    {columnCards.length}
                  </span>
                </div>

                {/* Cards List */}
                <div className="space-y-2.5 flex-1 overflow-y-auto max-h-[580px] pr-0.5">
                  {columnCards.length === 0 ? (
                    <div className="h-32 flex flex-col items-center justify-center border border-dashed border-slate-200 rounded-lg text-slate-400 text-xs text-center p-3">
                      <span>No posts in {col.title.toLowerCase()}</span>
                      <span className="text-[10px] text-slate-400 mt-1">Drag cards here</span>
                    </div>
                  ) : (
                    columnCards.map((card) => {
                      const isDragging = draggingCardId === card.id;

                      return (
                        <div
                          key={card.id}
                          draggable
                          onDragStart={(e) => handleDragStart(e, card.id)}
                          onDragEnd={handleDragEnd}
                          onClick={() => {
                            if (card.columnId === "awaiting_approval") {
                              setReviewCard(card);
                            } else {
                              setSelectedCard(card);
                            }
                          }}
                          className={cn(
                            "group rounded-xl border border-slate-200/90 bg-white p-3 shadow-2xs hover:shadow-sm transition-all duration-150 cursor-grab active:cursor-grabbing hover:border-indigo-300 relative select-none",
                            isDragging ? "opacity-40 scale-98 border-dashed border-indigo-400" : ""
                          )}
                        >
                          {/* Card Header */}
                          <div className="flex items-center justify-between gap-2 mb-2">
                            <div className="flex items-center gap-1.5 p-1 rounded-md bg-slate-50 border border-slate-100">
                              {card.platforms.map((p) => (
                                <span key={p} title={p} className="shrink-0">
                                  {renderPlatformIcon(p)}
                                </span>
                              ))}
                            </div>

                            {renderBadge(card.statusBadge)}
                          </div>

                          {/* Post Creative Asset Thumbnail + Bold Title */}
                          <div className="flex items-start gap-2.5">
                            <div className="w-12 h-12 rounded-lg overflow-hidden shrink-0 bg-slate-100 border border-slate-200/80 relative">
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={card.thumbnailUrl}
                                alt={card.title}
                                className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                              />
                            </div>

                            <div className="flex-1 min-w-0">
                              <h4 className="text-xs font-bold text-slate-900 line-clamp-2 leading-snug group-hover:text-indigo-600 transition-colors">
                                {card.title}
                              </h4>
                              <p className="text-[11px] text-slate-500 line-clamp-1 mt-0.5">
                                {card.summary}
                              </p>
                            </div>
                          </div>

                          {/* Performance badge if analytics present */}
                          {card.analytics && card.analytics.engagementRate > 0 && (
                            <div className="mt-2 flex items-center justify-between text-[10px] bg-slate-50 px-2 py-0.5 rounded border border-slate-100 text-slate-600 font-medium">
                              <span>ER: {card.analytics.engagementRate}%</span>
                              <span>Likes: {card.analytics.likes}</span>
                            </div>
                          )}

                          {/* Card Footer */}
                          <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-400">
                            <span className="flex items-center gap-1 font-medium text-slate-500">
                              <Clock className="w-3 h-3 text-slate-400" />
                              <span className="truncate max-w-[110px]">{card.scheduledDate}</span>
                            </span>

                            <div className="flex items-center gap-1">
                              <span
                                className="w-5 h-5 rounded-full bg-slate-100 border border-slate-200 text-slate-700 font-bold text-[9px] flex items-center justify-center shrink-0"
                                title={card.authorName}
                              >
                                {card.authorInitials}
                              </span>
                              <GripVertical className="w-3.5 h-3.5 text-slate-300 group-hover:text-slate-500" />
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>

      {/* Quick Add Post Modal */}
      <Modal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title="Add Content Calendar Post"
        description="Create a new social creative draft in the Backlog queue."
        maxWidth="md"
      >
        <form onSubmit={handleCreatePost} className="space-y-4 py-2">
          <div>
            <label className="text-xs font-bold text-slate-700 block mb-1">
              Social Post Title *
            </label>
            <input
              type="text"
              required
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="e.g. Q4 Working Capital Benchmark Survey"
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 focus:outline-hidden focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <div className="p-3 rounded-lg bg-indigo-50 border border-indigo-100 text-xs text-indigo-900">
            <span className="font-semibold block mb-0.5">Kanban Multi-Platform Placement</span>
            This card will be added to the <strong>Backlog</strong> column with LinkedIn &amp; Facebook pre-selected. You can drag and drop it across In Progress, Awaiting Approval, Scheduled, and Published stages.
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setCreateModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="sm"
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
            >
              Create Post Card
            </Button>
          </div>
        </form>
      </Modal>

      {/* Post Detail Preview Modal */}
      <Modal
        isOpen={!!selectedCard}
        onClose={() => setSelectedCard(null)}
        title="Post Card Details"
        description="Inspect campaign metadata, platform distribution, and scheduling status."
        maxWidth="md"
      >
        {selectedCard && (
          <div className="space-y-4 py-2">
            <div className="flex items-start gap-3 p-3 rounded-xl bg-slate-50 border border-slate-200">
              <div className="w-16 h-16 rounded-lg overflow-hidden shrink-0 bg-slate-200 border border-slate-300">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={selectedCard.thumbnailUrl}
                  alt={selectedCard.title}
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="flex-1 min-w-0">
                <h4 className="text-sm font-bold text-slate-900">{selectedCard.title}</h4>
                <p className="text-xs text-slate-500 mt-1">{selectedCard.summary}</p>
                <div className="mt-2 flex items-center gap-2">
                  {renderBadge(selectedCard.statusBadge)}
                  <span className="text-[11px] text-slate-400 font-medium">
                    Owner: {selectedCard.authorName}
                  </span>
                </div>
              </div>
            </div>

            {selectedCard.permalink && (
              <a
                href={selectedCard.permalink}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-medium hover:underline"
              >
                <span>View Live Social Post</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            )}

            <div className="space-y-1">
              <span className="text-xs font-bold text-slate-700">Target Social Platforms</span>
              <div className="flex items-center gap-2 pt-1">
                {selectedCard.platforms.map((p) => (
                  <span
                    key={p}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-slate-200 text-xs font-semibold bg-white text-slate-700 shadow-2xs"
                  >
                    {renderPlatformIcon(p)}
                    <span className="capitalize">{p}</span>
                  </span>
                ))}
              </div>
            </div>

            <div className="space-y-1">
              <span className="text-xs font-bold text-slate-700">Move Column</span>
              <div className="grid grid-cols-2 gap-2 pt-1">
                {COLUMNS.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={async () => {
                      const targetId = c.id;
                      setCards((prev) =>
                        prev.map((item) =>
                          item.id === selectedCard.id ? { ...item, columnId: targetId } : item
                        )
                      );
                      setSelectedCard((prev) => (prev ? { ...prev, columnId: targetId } : null));
                      try {
                        await updateKanbanPostStatus(selectedCard.id, targetId);
                      } catch (err: unknown) {
                        console.error("Failed to move card via button:", err);
                      }
                    }}
                    className={cn(
                      "p-2 text-xs rounded-lg border font-semibold text-left transition-colors flex items-center justify-between",
                      selectedCard.columnId === c.id
                        ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                        : "border-slate-200 hover:bg-slate-50 text-slate-700"
                    )}
                  >
                    <span>{c.title}</span>
                    {selectedCard.columnId === c.id && (
                      <CheckCircle2 className="w-3.5 h-3.5 text-indigo-600" />
                    )}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <Button variant="outline" size="sm" onClick={() => setSelectedCard(null)}>
                Close
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Dedicated Approval & AI Training Feedback Modal */}
      <ReviewModal
        isOpen={!!reviewCard}
        onClose={() => setReviewCard(null)}
        post={reviewCard}
        onApprove={handleApproveReviewCard}
        onPostUpdated={handleReviewPostUpdated}
      />
    </Card>
  );
};
