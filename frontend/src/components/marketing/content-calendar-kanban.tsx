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
} from "lucide-react";
import {
  LinkedInIcon,
  InstagramIcon,
  FacebookIcon,
  XIcon,
} from "@/components/social/social-icons";
import { cn } from "@/lib/utils";

export type ColumnId = "backlog" | "in_progress" | "awaiting_approval" | "scheduled";

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
}

const INITIAL_CARDS: KanbanCardItem[] = [
  {
    id: "kb-1",
    title: "Q4 CFO Working Capital & DSO Benchmark Report",
    summary: "Exclusive survey data from 140+ CFOs revealing strategies to shave 14 days off DSO.",
    platforms: ["linkedin", "x", "facebook"],
    statusBadge: { label: "New", variant: "new" },
    thumbnailUrl: "https://images.unsplash.com/photo-1551836022-d5d88e9218df?w=160&auto=format&fit=crop&q=80",
    columnId: "backlog",
    scheduledDate: "TBD",
    authorName: "Pravalika Palle",
    authorInitials: "PP",
  },
  {
    id: "kb-2",
    title: "Behind the Scenes: Voice Telephony Follow-Up Workflows",
    summary: "Video tour showcasing Retell AI telephone dispatch syncing directly with CRM pipelines.",
    platforms: ["linkedin", "instagram"],
    statusBadge: { label: "Video Asset", variant: "priority" },
    thumbnailUrl: "https://images.unsplash.com/photo-1557804506-669a67965ba0?w=160&auto=format&fit=crop&q=80",
    columnId: "backlog",
    scheduledDate: "TBD",
    authorName: "Lakshay Narula",
    authorInitials: "LN",
  },
  {
    id: "kb-3",
    title: "Healthcare Receivables Automation: Zero Manual Calling",
    summary: "How mid-market clinics replaced cold follow-up lists with automated voice cadences.",
    platforms: ["linkedin", "facebook"],
    statusBadge: { label: "In Progress", variant: "default" },
    thumbnailUrl: "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=160&auto=format&fit=crop&q=80",
    columnId: "in_progress",
    scheduledDate: "Drafting copy",
    authorName: "Elena Rostova",
    authorInitials: "ER",
  },
  {
    id: "kb-4",
    title: "Infographic: 5 Inefficiency Leaks in B2B Credit Teams",
    summary: "Carousels visualizing reconciliation delays, outdated contact lists, and manual dialers.",
    platforms: ["linkedin", "x", "instagram"],
    statusBadge: { label: "Design Ready", variant: "priority" },
    thumbnailUrl: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=160&auto=format&fit=crop&q=80",
    columnId: "in_progress",
    scheduledDate: "In Creative Review",
    authorName: "Pravalika Palle",
    authorInitials: "PP",
  },
  {
    id: "kb-5",
    title: "Client Case Study: Enterprise Cash Flow Turnaround",
    summary: "Awaiting client legal and marketing sign-off before dispatching to social networks.",
    platforms: ["linkedin", "facebook"],
    statusBadge: { label: "Review Ready", variant: "review" },
    thumbnailUrl: "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=160&auto=format&fit=crop&q=80",
    columnId: "awaiting_approval",
    scheduledDate: "Client Sign-Off Pending",
    authorName: "Marcus Chen",
    authorInitials: "MC",
  },
  {
    id: "kb-6",
    title: "SaaS Billing Automation & Churn Prevention Playbook",
    summary: "Pre-approved thought leadership article ready to trigger via n8n publishing pipeline.",
    platforms: ["linkedin", "x"],
    statusBadge: { label: "Approved", variant: "review" },
    thumbnailUrl: "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=160&auto=format&fit=crop&q=80",
    columnId: "awaiting_approval",
    scheduledDate: "Awaiting Client Sign-off",
    authorName: "Lakshay Narula",
    authorInitials: "LN",
  },
  {
    id: "kb-7",
    title: "Masterclass: Omnichannel Marketing for Commercial Credit",
    summary: "Live interactive webinar promotion scheduled across all enterprise accounts.",
    platforms: ["linkedin", "x", "facebook", "instagram"],
    statusBadge: { label: "Scheduled", variant: "scheduled" },
    thumbnailUrl: "https://images.unsplash.com/photo-1515187029135-18ee286d815b?w=160&auto=format&fit=crop&q=80",
    columnId: "scheduled",
    scheduledDate: "Oct 24, 2026 (09:00 AM EST)",
    authorName: "Pravalika Palle",
    authorInitials: "PP",
  },
  {
    id: "kb-8",
    title: "Product Feature Drop: Automated WhatsApp & SMS Cadences",
    summary: "Multi-channel announcement highlighting the newest communication layer for AR teams.",
    platforms: ["linkedin", "x", "instagram"],
    statusBadge: { label: "Scheduled", variant: "scheduled" },
    thumbnailUrl: "https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=160&auto=format&fit=crop&q=80",
    columnId: "scheduled",
    scheduledDate: "Oct 26, 2026 (02:30 PM EST)",
    authorName: "Lakshay Narula",
    authorInitials: "LN",
  },
];

const COLUMNS: { id: ColumnId; title: string; countColor: string; accentColor: string }[] = [
  { id: "backlog", title: "Backlog", countColor: "bg-slate-100 text-slate-700", accentColor: "border-t-slate-400" },
  { id: "in_progress", title: "In Progress", countColor: "bg-blue-100 text-blue-700", accentColor: "border-t-blue-500" },
  { id: "awaiting_approval", title: "Awaiting Approval", countColor: "bg-amber-100 text-amber-800", accentColor: "border-t-amber-500" },
  { id: "scheduled", title: "Scheduled", countColor: "bg-emerald-100 text-emerald-800", accentColor: "border-t-emerald-500" },
];

export const ContentCalendarKanban: React.FC = () => {
  const [cards, setCards] = React.useState<KanbanCardItem[]>(INITIAL_CARDS);
  const [draggingCardId, setDraggingCardId] = React.useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = React.useState<ColumnId | null>(null);
  const [selectedCard, setSelectedCard] = React.useState<KanbanCardItem | null>(null);
  const [createModalOpen, setCreateModalOpen] = React.useState(false);
  const [newTitle, setNewTitle] = React.useState("");

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

  const handleDrop = (e: React.DragEvent, targetColId: ColumnId) => {
    e.preventDefault();
    const cardId = e.dataTransfer.getData("text/plain") || draggingCardId;
    if (!cardId) return;

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
          } else {
            updatedBadge = { label: "Backlog", variant: "default" };
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
  };

  const handleCreatePost = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;

    const newCard: KanbanCardItem = {
      id: `kb-${Date.now()}`,
      title: newTitle.trim(),
      summary: "Newly planned social campaign asset ready for content drafting.",
      platforms: ["linkedin", "x"],
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

  return (
    <Card className="rounded-xl border border-slate-200/80 bg-white shadow-xs hover:shadow-sm transition-all duration-200">
      <CardHeader className="p-4 sm:p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
            <Calendar className="w-4 h-4" />
          </div>
          <div>
            <CardTitle className="text-base sm:text-lg font-bold text-slate-900 tracking-tight">
              Content Calendar (Kanban)
            </CardTitle>
            <p className="text-xs text-slate-500 mt-0.5">
              Drag-and-drop posts between planning phases, client sign-offs, and scheduled publishing.
            </p>
          </div>
        </div>

        {/* Action Button: Quick Add Post */}
        <Button
          variant="primary"
          size="sm"
          onClick={() => setCreateModalOpen(true)}
          className="text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs inline-flex items-center gap-1.5 self-start sm:self-auto"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>New Post Card</span>
        </Button>
      </CardHeader>

      <CardContent className="p-4 sm:p-5">
        {/* Kanban 4-Column Board */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {COLUMNS.map((col) => {
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

                {/* Cards List with HTML5 Drag-and-Drop */}
                <div className="space-y-2.5 flex-1 overflow-y-auto pr-0.5">
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
                          onClick={() => setSelectedCard(card)}
                          className={cn(
                            "group rounded-xl border border-slate-200/90 bg-white p-3 shadow-2xs hover:shadow-sm transition-all duration-150 cursor-grab active:cursor-grabbing hover:border-indigo-300 relative select-none",
                            isDragging ? "opacity-40 scale-98 border-dashed border-indigo-400" : ""
                          )}
                        >
                          {/* Card Header: Platform Icons & Status Badge */}
                          <div className="flex items-center justify-between gap-2 mb-2">
                            {/* Platform Icons (LinkedIn, Instagram, X, Facebook) as specified */}
                            <div className="flex items-center gap-1.5 p-1 rounded-md bg-slate-50 border border-slate-100">
                              {card.platforms.map((p) => (
                                <span key={p} title={p} className="shrink-0">
                                  {renderPlatformIcon(p)}
                                </span>
                              ))}
                            </div>

                            {/* Status Badge */}
                            {renderBadge(card.statusBadge)}
                          </div>

                          {/* Post Creative Asset Thumbnail + Bold Title (Specification 5) */}
                          <div className="flex items-start gap-2.5">
                            {/* Square Image Thumbnail representing creative asset */}
                            <div className="w-12 h-12 rounded-lg overflow-hidden shrink-0 bg-slate-100 border border-slate-200/80 relative">
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={card.thumbnailUrl}
                                alt={card.title}
                                className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                              />
                            </div>

                            {/* Bold Title */}
                            <div className="flex-1 min-w-0">
                              <h4 className="text-xs font-bold text-slate-900 line-clamp-2 leading-snug group-hover:text-indigo-600 transition-colors">
                                {card.title}
                              </h4>
                              <p className="text-[11px] text-slate-500 line-clamp-1 mt-0.5">
                                {card.summary}
                              </p>
                            </div>
                          </div>

                          {/* Card Footer: Scheduled Date & Assignee Avatar */}
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
            This card will be added to the <strong>Backlog</strong> column with LinkedIn &amp; X pre-selected. You can drag and drop it across In Progress, Awaiting Approval, and Scheduled stages.
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
                    onClick={() => {
                      setCards((prev) =>
                        prev.map((item) =>
                          item.id === selectedCard.id ? { ...item, columnId: c.id } : item
                        )
                      );
                      setSelectedCard((prev) => (prev ? { ...prev, columnId: c.id } : null));
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
    </Card>
  );
};
