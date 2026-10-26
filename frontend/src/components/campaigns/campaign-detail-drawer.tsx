"use client";

import * as React from "react";
import {
  CampaignItem,
  CampaignContactItem,
  OutreachItem,
  CAMPAIGN_STATUS_LABELS,
  CAMPAIGN_TYPE_LABELS,
  ENROLLMENT_STATUS_LABELS,
  getCampaignDetails,
  enrollContactsInCampaign,
  executeCampaignPlanning,
  sendOutreachMessage,
  removeContactFromCampaign,
  deleteCampaign,
} from "@/services/campaignService";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import { Modal } from "@/components/ui/modal";
import { PhysicalMailPreflightModal } from "./physical-mail-preflight-modal";
import { simulateMockCallCompletion } from "@/services/voiceService";
import {
  getChannelCapabilities,
  ChannelCapability,
} from "@/services/entitlementsService";
import { Input } from "@/components/ui/input";
import {
  X,
  Send,
  Play,
  Pause,
  CheckCircle2,
  Mail,
  Users,
  Clock,
  Layers,
  Calendar,
  AlertCircle,
  FileText,
  UserPlus,
  RefreshCw,
  Search,
  Zap,
  GitBranch,
  Trash2,
  ListOrdered,
  Plus,
  Check,
  AlertTriangle,
  MessageSquare,
  PhoneCall,
  ExternalLink,
} from "lucide-react";
import {
  ContactListItem,
  fetchCampaignAttachedLists,
  attachListToCampaign,
  detachListFromCampaign,
  syncCampaignList,
  fetchContactLists,
} from "@/services/contactListService";

export interface CampaignDetailDrawerProps {
  campaign: CampaignItem | null;
  isOpen: boolean;
  onClose: () => void;
  onStatusChange?: (campaignId: string, newStatus: "active" | "paused" | "completed") => Promise<void> | void;
  onCampaignUpdated?: () => void;
  onCampaignDeleted?: (campaignId: string) => void;
  onOpenWorkflowBuilder?: (campaign: CampaignItem) => void;
}

interface AvailableContact {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  company?: {
    name: string;
  } | null;
}

export const CampaignDetailDrawer: React.FC<CampaignDetailDrawerProps> = ({
  campaign: initialCampaign,
  isOpen,
  onClose,
  onStatusChange,
  onCampaignUpdated,
  onCampaignDeleted,
  onOpenWorkflowBuilder,
}) => {
  const [campaign, setCampaign] = React.useState<CampaignItem | null>(initialCampaign);
  const [isLoadingDetails, setIsLoadingDetails] = React.useState(false);
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = React.useState<string | null>(null);

  // Status transition loading
  const [isUpdatingStatus, setIsUpdatingStatus] = React.useState(false);

  // Enroll Contacts Modal
  const [isEnrollModalOpen, setIsEnrollModalOpen] = React.useState(false);
  const [availableContacts, setAvailableContacts] = React.useState<AvailableContact[]>([]);
  const [isLoadingContacts, setIsLoadingContacts] = React.useState(false);
  const [contactSearchQuery, setContactSearchQuery] = React.useState("");
  const [selectedContactIds, setSelectedContactIds] = React.useState<string[]>([]);
  const [isEnrolling, setIsEnrolling] = React.useState(false);

  // Remove Contact Modal State
  const [contactToRemove, setContactToRemove] = React.useState<CampaignContactItem | null>(null);
  const [isRemovingContact, setIsRemovingContact] = React.useState(false);
  const [removeContactError, setRemoveContactError] = React.useState<string | null>(null);

  // Delete Campaign Modal State
  const [isDeleteCampaignModalOpen, setIsDeleteCampaignModalOpen] = React.useState(false);
  const [isDeletingCampaign, setIsDeletingCampaign] = React.useState(false);
  const [deleteCampaignError, setDeleteCampaignError] = React.useState<string | null>(null);

  // Sequence Execution
  const [isPhysicalMailModalOpen, setIsPhysicalMailModalOpen] = React.useState(false);
  const [isExecutingPlanning, setIsExecutingPlanning] = React.useState(false);
  const [sendingOutreachId, setSendingOutreachId] = React.useState<string | null>(null);
  const [simulatingOutreachId, setSimulatingOutreachId] = React.useState<string | null>(null);

  // Channel capabilities & entitlement state
  const [channelCapabilities, setChannelCapabilities] = React.useState<Record<string, ChannelCapability>>({});

  React.useEffect(() => {
    if (isOpen) {
      getChannelCapabilities()
        .then((res) => {
          const map: Record<string, ChannelCapability> = {};
          for (const ch of res.channels || []) {
            map[ch.channel] = ch;
          }
          setChannelCapabilities(map);
        })
        .catch((err) => {
          console.warn("Could not load channel capabilities in drawer:", err);
        });
    }
  }, [isOpen]);

  const uniqueChannels = React.useMemo(() => {
    if (!campaign) return ["email"];
    const found = new Set<string>();
    for (const step of campaign.steps || []) {
      if (["email", "voice", "sms", "physical_mail"].includes(step.stepType)) {
        found.add(step.stepType);
      }
    }
    for (const n of campaign.workflowConfig?.nodes || []) {
      if (["email", "voice", "sms", "physical_mail"].includes(n.type)) {
        found.add(n.type);
      }
    }
    if (found.size === 0) {
      found.add("email");
    }
    return Array.from(found);
  }, [campaign]);

  // Attached Lists State
  const [attachedLists, setAttachedLists] = React.useState<ContactListItem[]>([]);
  const [isLoadingAttachedLists, setIsLoadingAttachedLists] = React.useState(false);
  const [isAttachListModalOpen, setIsAttachListModalOpen] = React.useState(false);
  const [availableListsToAttach, setAvailableListsToAttach] = React.useState<ContactListItem[]>([]);
  const [isLoadingAvailableLists, setIsLoadingAvailableLists] = React.useState(false);
  const [selectedListIdToAttach, setSelectedListIdToAttach] = React.useState("");
  const [isAttachingList, setIsAttachingList] = React.useState(false);
  const [attachListError, setAttachListError] = React.useState<string | null>(null);
  const [syncingListId, setSyncingListId] = React.useState<string | null>(null);

  const loadAttachedLists = React.useCallback(async (campId: string) => {
    setIsLoadingAttachedLists(true);
    try {
      const lists = await fetchCampaignAttachedLists(campId);
      setAttachedLists(lists);
    } catch (err: unknown) {
      console.error("Failed to load attached lists:", err);
    } finally {
      setIsLoadingAttachedLists(false);
    }
  }, []);

  const handleOpenAttachListModal = async () => {
    setIsAttachListModalOpen(true);
    setAttachListError(null);
    setIsLoadingAvailableLists(true);
    try {
      const res = await fetchContactLists({ limit: 100 });
      const attachedIds = new Set(attachedLists.map((l) => l.id));
      const filtered = res.items.filter((l) => !attachedIds.has(l.id));
      setAvailableListsToAttach(filtered);
      if (filtered.length > 0) {
        setSelectedListIdToAttach(filtered[0].id);
      }
    } catch (err: unknown) {
      setAttachListError(err instanceof Error ? err.message : "Failed to load lists.");
    } finally {
      setIsLoadingAvailableLists(false);
    }
  };

  const handleAttachList = async () => {
    if (!campaign || !selectedListIdToAttach) return;
    setIsAttachingList(true);
    setAttachListError(null);
    try {
      const res = await attachListToCampaign(campaign.id, selectedListIdToAttach, true);
      const targetList = availableListsToAttach.find((l) => l.id === selectedListIdToAttach);
      const name = targetList ? targetList.name : "list";
      const msg = `Attached "${name}". ${res.newly_enrolled_count} members enrolled.${
        res.unresolved_email_count > 0 ? ` (${res.unresolved_email_count} skipped: unresolved email)` : ""
      }`;
      setActionSuccess(msg);
      setIsAttachListModalOpen(false);
      await Promise.all([refreshCampaign(campaign.id), loadAttachedLists(campaign.id)]);
      onCampaignUpdated?.();
    } catch (err: unknown) {
      setAttachListError(err instanceof Error ? err.message : "Failed to attach list.");
    } finally {
      setIsAttachingList(false);
    }
  };

  const handleDetachList = async (listId: string) => {
    if (!campaign) return;
    try {
      await detachListFromCampaign(campaign.id, listId);
      setActionSuccess("List detached from campaign. Enrolled contacts and outreach records were preserved.");
      await loadAttachedLists(campaign.id);
      onCampaignUpdated?.();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to detach list.");
    }
  };

  const handleSyncList = async (listId: string) => {
    if (!campaign) return;
    setSyncingListId(listId);
    try {
      const res = await syncCampaignList(campaign.id, listId);
      const msg = `Sync complete: ${res.newly_enrolled_count} newly enrolled, ${res.already_enrolled_count} already enrolled.${
        res.unresolved_email_count > 0 ? ` ${res.unresolved_email_count} skipped (unresolved email).` : ""
      }`;
      setActionSuccess(msg);
      await refreshCampaign(campaign.id);
      onCampaignUpdated?.();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to sync list.");
    } finally {
      setSyncingListId(null);
    }
  };

  const handleConfirmRemoveContact = async () => {
    if (!campaign || !contactToRemove) return;
    setIsRemovingContact(true);
    setRemoveContactError(null);
    try {
      await removeContactFromCampaign(campaign.id, contactToRemove.contactId);
      setActionSuccess(`Removed ${contactToRemove.contactName} from ${campaign.name}.`);
      setContactToRemove(null);
      await refreshCampaign(campaign.id);
      onCampaignUpdated?.();
    } catch (err: unknown) {
      setRemoveContactError(err instanceof Error ? err.message : "Failed to remove contact from campaign.");
    } finally {
      setIsRemovingContact(false);
    }
  };

  const handleConfirmDeleteCampaign = async () => {
    if (!campaign) return;
    setIsDeletingCampaign(true);
    setDeleteCampaignError(null);
    try {
      await deleteCampaign(campaign.id);
      setIsDeleteCampaignModalOpen(false);
      onClose();
      onCampaignDeleted?.(campaign.id);
      onCampaignUpdated?.();
    } catch (err: unknown) {
      setDeleteCampaignError(err instanceof Error ? err.message : "Failed to delete campaign.");
    } finally {
      setIsDeletingCampaign(false);
    }
  };


  // Refresh details when opened or initialCampaign changes
  const refreshCampaign = React.useCallback(async (campId: string) => {
    setIsLoadingDetails(true);
    setActionError(null);
    try {
      const fresh = await getCampaignDetails(campId);
      setCampaign(fresh);
    } catch (err: unknown) {
      console.error("Failed to load campaign details:", err);
      setActionError(err instanceof Error ? err.message : "Failed to load campaign details");
    } finally {
      setIsLoadingDetails(false);
    }
  }, []);

  React.useEffect(() => {
    if (isOpen && initialCampaign?.id) {
      refreshCampaign(initialCampaign.id);
      loadAttachedLists(initialCampaign.id);
    } else {
      setCampaign(initialCampaign);
    }
  }, [isOpen, initialCampaign, refreshCampaign, loadAttachedLists]);

  // Load available contacts for enrollment modal
  const handleOpenEnrollModal = async () => {
    setIsEnrollModalOpen(true);
    setIsLoadingContacts(true);
    setSelectedContactIds([]);
    setContactSearchQuery("");
    try {
      const res = await fetch("/api/contacts?limit=200", { cache: "no-store" });
      if (res.ok) {
        const data = await res.json();
        setAvailableContacts(data);
      } else {
        setActionError("Failed to fetch contacts for enrollment.");
      }
    } catch {
      setActionError("Error connecting to contacts API.");
    } finally {
      setIsLoadingContacts(false);
    }
  };

  // Debounced search for available contacts
  React.useEffect(() => {
    if (!isEnrollModalOpen) return;
    const timer = setTimeout(async () => {
      setIsLoadingContacts(true);
      try {
        const q = contactSearchQuery.trim();
        const url = q
          ? `/api/contacts?search=${encodeURIComponent(q)}&limit=200`
          : `/api/contacts?limit=200`;
        const res = await fetch(url, { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          setAvailableContacts(data);
        }
      } catch {
        // preserve current contacts on error
      } finally {
        setIsLoadingContacts(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [contactSearchQuery, isEnrollModalOpen]);

  // Confirm enrollment
  const handleConfirmEnrollment = async () => {
    if (!campaign || selectedContactIds.length === 0) return;
    setIsEnrolling(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const result = await enrollContactsInCampaign(campaign.id, selectedContactIds);
      const enrolledCount = result.enrolledContactIds?.length || 0;
      const alreadyCount = result.alreadyEnrolledContactIds?.length || 0;
      const rejectedCount = result.rejectedContactIds?.length || 0;

      if (enrolledCount === 0 && alreadyCount === 0) {
        setActionError(
          rejectedCount > 0
            ? `${rejectedCount} contact${rejectedCount === 1 ? " was" : "s were"} rejected (not found in your organization).`
            : "No contacts were enrolled into the campaign."
        );
        return;
      }

      let msg = "";
      if (enrolledCount > 0) {
        msg += `Successfully enrolled ${enrolledCount} contact${enrolledCount === 1 ? "" : "s"}.`;
      }
      if (alreadyCount > 0) {
        msg += (msg ? " " : "") + `${alreadyCount} contact${alreadyCount === 1 ? " was" : "s were"} already enrolled.`;
      }
      if (rejectedCount > 0) {
        msg += ` (${rejectedCount} rejected).`;
      }

      setActionSuccess(msg);
      setIsEnrollModalOpen(false);
      setSelectedContactIds([]);
      await refreshCampaign(campaign.id);
      onCampaignUpdated?.();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to enroll contacts");
    } finally {
      setIsEnrolling(false);
    }
  };

  // Status transition
  const handleStatusTransition = async (newStatus: "active" | "paused" | "completed") => {
    if (!campaign) return;
    setIsUpdatingStatus(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      if (onStatusChange) {
        await onStatusChange(campaign.id, newStatus);
      }
      await refreshCampaign(campaign.id);
      setActionSuccess(`Campaign status updated to ${newStatus}.`);
      onCampaignUpdated?.();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : `Failed to transition status to ${newStatus}`);
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  // Plan outreach execution (generate Step 1 draft outreaches)
  const handleExecutePlanning = async () => {
    if (!campaign) return;
    setIsExecutingPlanning(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const result = await executeCampaignPlanning(campaign.id);
      setActionSuccess(
        `Outreach sequence planned: ${result.plannedOutreachesCount} draft message${
          result.plannedOutreachesCount === 1 ? "" : "s"
        } generated for Step 1.`
      );
      await refreshCampaign(campaign.id);
      onCampaignUpdated?.();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to execute sequence planning");
    } finally {
      setIsExecutingPlanning(false);
    }
  };

  // Simulate mock voice call completion
  const handleSimulateMockVoiceCompletion = async (outreachId: string, outcome: string) => {
    setSimulatingOutreachId(outreachId);
    setActionError(null);
    setActionSuccess(null);
    try {
      const res = await simulateMockCallCompletion({
        outreach_id: outreachId,
        outcome,
      });

      if (res.duplicate) {
        setActionSuccess(
          "Simulated call completion already processed (idempotent duplicate skipped)."
        );
      } else if (res.followup_email_created) {
        setActionSuccess(
          `Mock voice call completed (${outcome}). Step 2 follow-up email created with booking link.`
        );
      } else {
        setActionSuccess(
          `Mock voice call completed with outcome "${outcome}". Outreach transitioned to terminal state.`
        );
      }

      if (campaign) {
        await refreshCampaign(campaign.id);
      }
      onCampaignUpdated?.();
    } catch (err: unknown) {
      setActionError(
        err instanceof Error ? err.message : "Failed to complete simulated voice call"
      );
      if (campaign) {
        await refreshCampaign(campaign.id);
      }
    } finally {
      setSimulatingOutreachId(null);
    }
  };

  // Send single outreach message
  const handleSendOutreach = async (outreachId: string) => {
    setSendingOutreachId(outreachId);
    setActionError(null);
    setActionSuccess(null);
    try {
      const sent = await sendOutreachMessage(outreachId);
      if (sent.provider === "mock") {
        setActionSuccess(
          `Simulated send completed for ${sent.recipientEmail} (mock provider — no external email was transmitted).`
        );
      } else {
        setActionSuccess(
          `Email submitted to ${sent.provider || "provider"} for delivery to ${sent.recipientEmail}. Delivery confirmation pending.`
        );
      }
      if (campaign) {
        await refreshCampaign(campaign.id);
      }
      onCampaignUpdated?.();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to send outreach message");
      if (campaign) {
        await refreshCampaign(campaign.id);
      }
    } finally {
      setSendingOutreachId(null);
    }
  };

  // ESC handler
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

  if (!isOpen || !campaign) return null;

  // Filter contacts for enrollment modal
  const enrolledContactIdSet = new Set((campaign.contacts || []).map((c) => c.contactId));
  const filteredAvailableContacts = availableContacts.filter((contact) => {
    const q = contactSearchQuery.toLowerCase().trim();
    if (!q) return true;
    const name = `${contact.first_name || ""} ${contact.last_name || ""}`.toLowerCase();
    const email = (contact.email || "").toLowerCase();
    const company = (contact.company?.name || "").toLowerCase();
    const qWords = q.split(/\s+/).filter(Boolean);
    const allWordsMatch = qWords.every(
      (w) => name.includes(w) || email.includes(w) || company.includes(w)
    );
    return name.includes(q) || email.includes(q) || company.includes(q) || allWordsMatch;
  });

  const totalOutreachEvents = campaign.metrics.sent;
  const queuedContactsCount = (campaign.contacts || []).filter((c) => c.enrollmentStatus === "queued").length;
  const inProgressContactsCount = (campaign.contacts || []).filter((c) => c.enrollmentStatus === "in_progress").length;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/30 backdrop-blur-xs transition-opacity animate-in fade-in duration-150"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer Surface */}
      <div className="relative w-full max-w-xl bg-white h-full shadow-2xl border-l border-slate-200 z-10 flex flex-col overflow-hidden animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-5 border-b border-slate-100 flex items-start justify-between gap-3 bg-slate-50/50">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Campaign Sequence
              </span>
              <span className="text-slate-300">•</span>
              <span className="font-mono text-[11px] text-slate-400">
                {campaign.id.substring(0, 8)}...
              </span>
            </div>
            <h2 className="text-lg font-bold text-header leading-tight">
              {campaign.name}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {CAMPAIGN_TYPE_LABELS[campaign.type]} • Created{" "}
              {new Date(campaign.createdAt).toLocaleDateString()}
            </p>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => refreshCampaign(campaign.id)}
              disabled={isLoadingDetails}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              title="Refresh details"
            >
              <RefreshCw className={`w-4 h-4 ${isLoadingDetails ? "animate-spin text-agile-red" : ""}`} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              aria-label="Close drawer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Action Header Strip */}
        <div className="px-5 py-3 border-b border-slate-100 bg-white flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            {campaign.status === "active" && (
              <Badge variant="coral" dot>
                Active
              </Badge>
            )}
            {campaign.status === "draft" && (
              <Badge variant="neutral">Draft</Badge>
            )}
            {campaign.status === "paused" && (
              <Badge variant="warning">Paused</Badge>
            )}
            {campaign.status === "completed" && (
              <Badge variant="success">Completed</Badge>
            )}

            <span className="text-xs text-slate-500 font-medium ml-1">
              {campaign.contacts.length} enrolled contacts
            </span>
          </div>

          {/* Lifecycle actions */}
          <div className="flex items-center gap-1.5">
            {campaign.status === "draft" && (
              <Button
                variant="primary"
                size="sm"
                disabled={isUpdatingStatus}
                onClick={() => handleStatusTransition("active")}
                className="text-xs shadow-xs inline-flex items-center gap-1"
              >
                <Play className="w-3 h-3" />
                <span>{isUpdatingStatus ? "Activating..." : "Activate"}</span>
              </Button>
            )}
            {campaign.status === "active" && (
              <Button
                variant="secondary"
                size="sm"
                disabled={isUpdatingStatus}
                onClick={() => handleStatusTransition("paused")}
                className="text-xs inline-flex items-center gap-1"
              >
                <Pause className="w-3 h-3" />
                <span>{isUpdatingStatus ? "Pausing..." : "Pause"}</span>
              </Button>
            )}
            {campaign.status === "paused" && (
              <Button
                variant="primary"
                size="sm"
                disabled={isUpdatingStatus}
                onClick={() => handleStatusTransition("active")}
                className="text-xs shadow-xs inline-flex items-center gap-1"
              >
                <Play className="w-3 h-3" />
                <span>{isUpdatingStatus ? "Resuming..." : "Resume"}</span>
              </Button>
            )}
            {campaign.status !== "completed" && (
              <Button
                variant="outline"
                size="sm"
                disabled={isUpdatingStatus}
                onClick={() => handleStatusTransition("completed")}
                className="text-xs"
              >
                Complete
              </Button>
            )}
            {onOpenWorkflowBuilder && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onOpenWorkflowBuilder(campaign)}
                className="text-xs inline-flex items-center gap-1 border-agile-red/30 text-agile-red hover:bg-agile-lightorange"
                title="Open Visual Campaign Workflow Builder"
              >
                <GitBranch className="w-3 h-3 text-agile-red" />
                <span>Workflow Editor</span>
              </Button>
            )}
            {(campaign.steps.some((s) => s.stepType === "physical_mail") || campaign.channels?.includes("physical_mail")) && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsPhysicalMailModalOpen(true)}
                className="text-xs inline-flex items-center gap-1 border-rose-300 text-rose-700 hover:bg-rose-50"
                title="Direct Mail Pre-Flight & Test Dispatch"
              >
                <Send className="w-3 h-3 text-rose-600" />
                <span>Direct Mail</span>
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              disabled={isDeletingCampaign}
              onClick={() => {
                setDeleteCampaignError(null);
                setIsDeleteCampaignModalOpen(true);
              }}
              className="text-xs text-rose-600 border-rose-200 hover:bg-rose-50 hover:text-rose-700 inline-flex items-center gap-1"
              title="Delete Campaign"
              aria-label="Delete Campaign"
            >
              <Trash2 className="w-3 h-3" />
              <span>Delete</span>
            </Button>
          </div>
        </div>

        {/* Feedback Banners */}
        {actionSuccess && (
          <div className="mx-5 mt-4 p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center justify-between gap-2 animate-in fade-in">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>{actionSuccess}</span>
            </div>
            <button
              onClick={() => setActionSuccess(null)}
              className="text-emerald-500 hover:text-emerald-700"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
        {actionError && (
          <div className="mx-5 mt-4 p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between gap-2 animate-in fade-in">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{actionError}</span>
            </div>
            <button
              onClick={() => setActionError(null)}
              className="text-rose-500 hover:text-rose-700"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6 text-xs text-slate-700">
          {/* Section: Campaign Overview */}
          <div className="space-y-3">
            <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Overview & Schedule
            </h4>
            <div className="rounded-lg border border-slate-200/80 p-3.5 bg-slate-50/50 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Campaign Type</span>
                <span className="text-slate-800 font-semibold">
                  {CAMPAIGN_TYPE_LABELS[campaign.type]}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Lifecycle Status</span>
                <span className="font-semibold text-header">
                  {CAMPAIGN_STATUS_LABELS[campaign.status]}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Supported Channels</span>
                <span className="text-slate-800 font-medium flex items-center gap-2 flex-wrap justify-end">
                  {uniqueChannels.map((ch, idx) => {
                    const isVoiceUnlocked = channelCapabilities["voice"]?.is_unlocked ?? false;
                    const isSmsUnlocked = channelCapabilities["sms"]?.is_unlocked ?? false;
                    const isMailUnlocked = channelCapabilities["physical_mail"]?.is_unlocked ?? false;

                    return (
                      <React.Fragment key={ch}>
                        {idx > 0 && <span className="text-slate-300">•</span>}
                        {ch === "email" && (
                          <span className="flex items-center gap-1 text-slate-700">
                            <Mail className="w-3.5 h-3.5 text-slate-400" />
                            Email
                          </span>
                        )}
                        {ch === "voice" && (
                          <span
                            className={`flex items-center gap-1 ${
                              isVoiceUnlocked ? "text-purple-700" : "text-amber-700"
                            }`}
                            title={
                              isVoiceUnlocked
                                ? "Voice SDR Enabled (Retell AI)"
                                : "Administrative channel upgrade required"
                            }
                          >
                            <PhoneCall className={`w-3.5 h-3.5 ${isVoiceUnlocked ? "text-purple-600" : "text-amber-600"}`} />
                            Voice SDR {isVoiceUnlocked ? "(Retell AI)" : "(Upgrade Required)"}
                          </span>
                        )}
                        {ch === "sms" && (
                          <span
                            className={`flex items-center gap-1 ${
                              isSmsUnlocked ? "text-emerald-700" : "text-amber-700"
                            }`}
                            title={isSmsUnlocked ? "SMS Enabled (Twilio)" : "Administrative channel upgrade required"}
                          >
                            <MessageSquare className={`w-3.5 h-3.5 ${isSmsUnlocked ? "text-emerald-600" : "text-amber-600"}`} />
                            SMS {isSmsUnlocked ? "(Twilio)" : "(Upgrade Required)"}
                          </span>
                        )}
                        {ch === "physical_mail" && (
                          <span
                            className={`flex items-center gap-1 ${
                              isMailUnlocked ? "text-rose-700" : "text-amber-700"
                            }`}
                            title={isMailUnlocked ? "Direct Mail Enabled (Poplar)" : "Administrative channel upgrade required"}
                          >
                            <Send className={`w-3.5 h-3.5 ${isMailUnlocked ? "text-rose-600" : "text-amber-600"}`} />
                            Direct Mail {isMailUnlocked ? "(Poplar)" : "(Upgrade Required)"}
                          </span>
                        )}
                      </React.Fragment>
                    );
                  })}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Last Modified</span>
                <span className="text-slate-800 font-mono text-[11px]">
                  {new Date(campaign.updatedAt).toLocaleString()}
                </span>
              </div>
            </div>
          </div>

          {/* Section: Sequence Steps (CampaignStep model) */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Sequence Steps ({campaign.steps.length})
              </h4>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-slate-400 font-medium hidden sm:inline">
                  Step ordering
                </span>
                {onOpenWorkflowBuilder && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onOpenWorkflowBuilder(campaign)}
                    className="text-[11px] h-6 px-2 text-agile-red hover:text-agile-red hover:bg-agile-lightorange inline-flex items-center gap-1"
                  >
                    <GitBranch className="w-3 h-3" />
                    <span>Visual Builder</span>
                  </Button>
                )}
              </div>
            </div>

            {campaign.steps.length === 0 ? (
              <div className="p-4 rounded-lg border border-dashed border-slate-200 text-center text-slate-400 text-xs">
                No steps configured yet.
              </div>
            ) : (
              <div className="space-y-2.5">
                {campaign.steps.map((step) => {
                  const isVoice = step.stepType === "voice";
                  const isWait = step.stepType === "wait";
                  const isCondition = step.stepType === "condition";
                  const isSms = step.stepType === "sms";
                  const isPhysicalMail = step.stepType === "physical_mail";
                  const isVoiceUnlocked = channelCapabilities["voice"]?.is_unlocked ?? false;

                  return (
                    <div
                      key={step.id}
                      className="p-3.5 rounded-lg border border-slate-200/80 bg-white shadow-xs space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span
                            className={`w-5 h-5 rounded font-bold text-[10px] flex items-center justify-center ${
                              isVoice
                                ? "bg-purple-600 text-white"
                                : isWait
                                ? "bg-amber-500 text-white"
                                : isCondition
                                ? "bg-indigo-600 text-white"
                                : isSms
                                ? "bg-emerald-600 text-white"
                                : isPhysicalMail
                                ? "bg-rose-600 text-white"
                                : "bg-header text-white"
                            }`}
                          >
                            {step.stepNumber}
                          </span>
                          <span className="font-semibold text-slate-800 text-xs flex items-center gap-1.5">
                            {isVoice && <PhoneCall className="w-3.5 h-3.5 text-purple-600" />}
                            {isWait && <Clock className="w-3.5 h-3.5 text-amber-500" />}
                            {isCondition && <GitBranch className="w-3.5 h-3.5 text-indigo-500" />}
                            {isSms && <MessageSquare className="w-3.5 h-3.5 text-emerald-600" />}
                            {isPhysicalMail && <Send className="w-3.5 h-3.5 text-rose-500" />}
                            {!isVoice && !isWait && !isCondition && !isSms && !isPhysicalMail && (
                              <Mail className="w-3.5 h-3.5 text-slate-400" />
                            )}
                            {step.title || (
                              isVoice
                                ? `Step ${step.stepNumber}: AI Voice SDR Call`
                                : isWait
                                ? `Wait Delay: ${step.delayDays}d ${step.delayHours}h`
                                : isCondition
                                ? `Condition Check: ${step.conditionType || "Prospect Engagement"}`
                                : isSms
                                ? `Step ${step.stepNumber}: SMS Outreach`
                                : isPhysicalMail
                                ? `Step ${step.stepNumber}: Physical Mail`
                                : `Step ${step.stepNumber}: Email Outreach`
                            )}
                          </span>
                        </div>
                        <span className="text-[10px] text-slate-400">
                          {isWait
                            ? `Duration: ${step.delayDays}d ${step.delayHours}h`
                            : `Delay: ${step.delayDays}d ${step.delayHours}h`}
                        </span>
                      </div>

                      {/* Voice SDR Step Details & Entitlement Warning */}
                      {isVoice && (
                        <div className="pl-7 space-y-1.5 text-[11px]">
                          <div className="flex items-center gap-2">
                            <span className="text-slate-400 font-medium">Provider:</span>
                            <span className="text-purple-800 font-semibold">Retell AI Voice SDR</span>
                            <span className="text-slate-300">•</span>
                            <span className="text-slate-500">Agent: {String(step.config?.agent_type || "Outbound SDR")}</span>
                          </div>
                          {!isVoiceUnlocked && (
                            <div className="mt-2 p-2.5 rounded bg-amber-50 border border-amber-200 text-amber-800 text-[11px] space-y-1">
                              <div className="flex items-center gap-1.5 font-semibold text-amber-900">
                                <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                                <span>AI Voice SDR Channel Upgrade Required</span>
                              </div>
                              <p className="text-[10.5px] text-amber-700 leading-relaxed">
                                AI Voice SDR calls are configured as Step 1 of this workflow, but live voice calling requires an administrative channel upgrade for this organization.
                              </p>
                              <Link
                                href="/settings/entitlements"
                                className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-700 hover:text-indigo-900 pt-0.5"
                              >
                                <span>Request Administrative Upgrade in Settings</span>
                                <ExternalLink className="w-3 h-3" />
                              </Link>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Wait Step Details */}
                      {isWait && (
                        <div className="pl-7 text-[11px] text-slate-500">
                          Cadence delay: Sequence pauses for {step.delayDays} day(s) before evaluating conditions or dispatching subsequent touches.
                        </div>
                      )}

                      {/* Condition Step Details */}
                      {isCondition && (
                        <div className="pl-7 text-[11px] text-slate-500">
                          Branching rule: Evaluates prospect engagement ({step.conditionType || "email_replied"}) to route responses.
                        </div>
                      )}

                      {/* SMS Step Details */}
                      {isSms && (
                        <div className="pl-7 space-y-1 text-[11px]">
                          {step.bodyTemplate && (
                            <div className="pt-1">
                              <span className="text-slate-400 font-medium block mb-0.5">SMS Body:</span>
                              <p className="text-slate-600 font-mono text-[10px] bg-slate-50 p-2 rounded border border-slate-200/60 whitespace-pre-wrap">
                                {step.bodyTemplate}
                              </p>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Physical Mail Step Details */}
                      {isPhysicalMail && (
                        <div className="pl-7 space-y-2 text-[11px]">
                          <div className="flex items-center gap-2">
                            <span className="text-slate-400 font-medium">Provider:</span>
                            <span className="text-rose-700 font-semibold">Poplar Programmatic Direct Mail</span>
                            <span className="text-slate-300">•</span>
                            <span className="text-slate-500">Format: Postcard / Demand Letter</span>
                          </div>
                          <div className="p-2.5 rounded bg-rose-50/50 border border-rose-200/60 text-slate-700 space-y-1.5">
                            <p className="text-[10.5px]">
                              Direct mail pieces are generated using automated USPS CASS address verification and personalized merge tags.
                            </p>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setIsPhysicalMailModalOpen(true)}
                              className="text-xs border-rose-300 text-rose-700 hover:bg-rose-100/60 bg-white"
                            >
                              <Send className="w-3 h-3 mr-1 text-rose-600" />
                              Launch Direct Mail Pre-Flight & Test Dispatch
                            </Button>
                          </div>
                        </div>
                      )}

                      {/* Email Step Details */}
                      {!isVoice && !isWait && !isCondition && !isSms && !isPhysicalMail && (
                        <div className="pl-7 space-y-1 text-[11px]">
                          <div>
                            <span className="text-slate-400 font-medium">Subject: </span>
                            <span className="text-slate-700 font-mono">
                              {step.subjectTemplate || "— (No subject configured)"}
                            </span>
                          </div>
                          {step.bodyTemplate && (
                            <div className="pt-1">
                              <span className="text-slate-400 font-medium block mb-0.5">
                                Template Content:
                              </span>
                              <p className="text-slate-600 font-mono text-[10px] bg-slate-50 p-2 rounded border border-slate-200/60 whitespace-pre-wrap">
                                {step.bodyTemplate}
                              </p>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Section: Attached Lists (List-Driven Lead Management) */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <ListOrdered className="w-3.5 h-3.5 text-agile-red" />
                  <span>Attached Lists ({attachedLists.length})</span>
                </h4>
                <span className="text-[10px] text-slate-400">
                  Reusable audience lists attached to this campaign
                </span>
              </div>

              <Button
                variant="outline"
                size="sm"
                onClick={handleOpenAttachListModal}
                className="text-xs inline-flex items-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5 text-slate-500" />
                <span>Attach List</span>
              </Button>
            </div>

            {attachedLists.length === 0 ? (
              <div className="p-4 rounded-lg border border-dashed border-slate-200 text-center space-y-1 bg-slate-50/30">
                <p className="text-xs font-medium text-slate-600">
                  No lists attached to this campaign.
                </p>
                <p className="text-[11px] text-slate-400">
                  Attach a named contact list to sync its members into this campaign.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {attachedLists.map((list) => (
                  <div
                    key={list.id}
                    className="p-3 rounded-lg border border-slate-200 bg-white flex items-center justify-between gap-2 shadow-xs"
                  >
                    <div>
                      <span className="font-semibold text-slate-800 block text-xs">
                        {list.name}
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {list.member_count} member{list.member_count !== 1 ? "s" : ""}
                        {list.description ? ` • ${list.description}` : ""}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={syncingListId === list.id}
                        onClick={() => handleSyncList(list.id)}
                        className="text-xs h-7 px-2 inline-flex items-center gap-1 text-agile-red border-agile-red/30 hover:bg-agile-lightorange"
                        title="Sync newly added list members into this campaign"
                      >
                        <RefreshCw className={`w-3 h-3 ${syncingListId === list.id ? "animate-spin" : ""}`} />
                        <span>{syncingListId === list.id ? "Syncing..." : "Sync New Members"}</span>
                      </Button>

                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDetachList(list.id)}
                        className="text-xs h-7 px-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50"
                        title="Detach list from campaign"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Section: Campaign Contacts (CampaignContact model) & ENROLLMENT WORKFLOW */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  Enrolled Audience ({campaign.contacts.length})
                </h4>
                <span className="text-[10px] text-slate-400">
                  {queuedContactsCount} queued • {inProgressContactsCount} in-progress
                </span>
              </div>

              {/* Add Contacts / Enroll Contacts Button */}
              <Button
                variant="outline"
                size="sm"
                onClick={handleOpenEnrollModal}
                className="text-xs inline-flex items-center gap-1.5"
              >
                <UserPlus className="w-3.5 h-3.5 text-slate-500" />
                <span>Enroll Contacts</span>
              </Button>
            </div>

            {campaign.contacts.length === 0 ? (
              <div className="p-6 rounded-lg border border-dashed border-slate-200 text-center space-y-2 bg-slate-50/30">
                <Users className="w-6 h-6 text-slate-300 mx-auto" />
                <p className="text-xs font-medium text-slate-600">
                  No contacts enrolled yet.
                </p>
                <p className="text-[11px] text-slate-400 max-w-xs mx-auto">
                  Click &ldquo;Enroll Contacts&rdquo; above to select and enroll genuine prospects from your CRM leads.
                </p>
              </div>
            ) : (
              <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                {campaign.contacts.map((contact) => (
                  <div
                    key={contact.id}
                    className="p-3 rounded-lg border border-slate-200/80 bg-slate-50/50 flex items-center justify-between gap-2"
                  >
                    <div>
                      <span className="font-semibold text-slate-800 block text-xs">
                        {contact.contactName}
                      </span>
                      <span className="font-mono text-[11px] text-slate-500 block">
                        {contact.contactEmail} • {contact.companyName}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-slate-400 font-mono">
                        Step {contact.currentStep}
                      </span>
                      <span
                        className={`text-[10px] font-semibold px-2 py-0.5 rounded border uppercase tracking-wider ${
                          contact.enrollmentStatus === "completed"
                            ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                            : contact.enrollmentStatus === "in_progress"
                            ? "bg-amber-50 text-amber-700 border-amber-200"
                            : contact.enrollmentStatus === "replied"
                            ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                            : contact.enrollmentStatus === "bounced"
                            ? "bg-rose-50 text-rose-700 border-rose-200"
                            : "bg-slate-100 text-slate-600 border-slate-200"
                        }`}
                      >
                        {ENROLLMENT_STATUS_LABELS[contact.enrollmentStatus] || contact.enrollmentStatus}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={isRemovingContact}
                        onClick={() => {
                          setRemoveContactError(null);
                          setContactToRemove(contact);
                        }}
                        className="h-6 w-6 p-0 text-slate-400 hover:text-rose-600 hover:bg-rose-50"
                        title="Remove from Campaign"
                        aria-label={`Remove ${contact.contactName} from campaign`}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Section: SEQUENCE EXECUTION & OUTREACH ORCHESTRATION */}
          <div className="space-y-3 border-t border-slate-100 pt-5">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  Sequence Execution
                </h4>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Distinguished from campaign activation. Evaluates eligible queued contacts and generates Step 1 draft outreaches.
                </p>
              </div>

              <Button
                variant="primary"
                size="sm"
                disabled={
                  isExecutingPlanning ||
                  campaign.status !== "active" ||
                  queuedContactsCount === 0
                }
                onClick={handleExecutePlanning}
                className="text-xs inline-flex items-center gap-1.5 shadow-xs shrink-0"
                title={
                  campaign.status !== "active"
                    ? "Activate campaign first to plan execution"
                    : queuedContactsCount === 0
                    ? "No queued contacts ready for Step 1"
                    : "Plan sequence execution"
                }
              >
                <Zap className="w-3.5 h-3.5" />
                <span>{isExecutingPlanning ? "Planning..." : "Plan Outreach"}</span>
              </Button>
            </div>

            {campaign.status !== "active" && (
              <div className="p-3 rounded-lg border border-amber-200/80 bg-amber-50/50 flex items-start gap-2 text-amber-800 text-[11px]">
                <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div>
                  <span className="font-semibold">Campaign is {campaign.status}.</span>
                  <p className="text-amber-700 mt-0.5">
                    Activate the campaign using the top button before executing sequence outreach.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Section: REAL OUTREACH MESSAGES LIST & SENDING ACTION */}
          <div className="space-y-3 border-t border-slate-100 pt-5">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  Outreach Messages ({campaign.outreaches?.length || 0})
                </h4>
                <p className="text-[10px] text-slate-400">
                  Database outreach records with delivery status
                </p>
              </div>
            </div>

            {!campaign.outreaches || campaign.outreaches.length === 0 ? (
              <div className="p-5 rounded-lg border border-dashed border-slate-200 text-center space-y-1 bg-slate-50/20">
                <Mail className="w-5 h-5 text-slate-300 mx-auto" />
                <p className="text-xs text-slate-500 font-medium">
                  No outreach messages generated yet.
                </p>
                <p className="text-[11px] text-slate-400">
                  When you click &ldquo;Plan Outreach&rdquo; on an active campaign, Step 1 outreach drafts will appear here.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
                {campaign.outreaches.map((outreach) => (
                  <div
                    key={outreach.id}
                    className="p-3.5 rounded-lg border border-slate-200 bg-white shadow-xs space-y-2.5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-slate-800 text-xs">
                            {outreach.contactName || outreach.recipientEmail}
                          </span>
                          {outreach.companyName && (
                            <span className="text-[11px] text-slate-400">
                              • {outreach.companyName}
                            </span>
                          )}
                        </div>
                        <span className="font-mono text-[11px] text-slate-500 block mt-0.5">
                          To: {outreach.recipientEmail}
                        </span>
                      </div>

                      {/* Status badge */}
                      {outreach.status === "sent" ? (
                        outreach.provider?.startsWith("mock") ? (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded border uppercase tracking-wider bg-amber-50 text-amber-700 border-amber-200">
                            Simulated (Safe Mock)
                          </span>
                        ) : outreach.firstDeliveredAt ? (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded border uppercase tracking-wider bg-emerald-50 text-emerald-700 border-emerald-200">
                            Delivered
                          </span>
                        ) : (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded border uppercase tracking-wider bg-sky-50 text-sky-700 border-sky-200">
                            Sent (Submitted)
                          </span>
                        )
                      ) : (
                        <span
                          className={`text-[10px] font-semibold px-2 py-0.5 rounded border uppercase tracking-wider ${
                            outreach.status === "sending"
                              ? "bg-blue-50 text-blue-700 border-blue-200 animate-pulse"
                              : outreach.status === "scheduled"
                              ? "bg-purple-50 text-purple-700 border-purple-200"
                              : outreach.status === "failed"
                              ? "bg-rose-50 text-rose-700 border-rose-200"
                              : "bg-slate-100 text-slate-700 border-slate-200"
                          }`}
                        >
                          {outreach.status}
                        </span>
                      )}
                    </div>

                    {/* Subject & snippet */}
                    <div className="text-[11px] bg-slate-50 p-2.5 rounded border border-slate-100 space-y-1">
                      <div className="flex items-center gap-1 font-medium text-slate-700">
                        <span className="text-slate-400">
                          {outreach.channel === "sms" ? "SMS Channel:" : "Subject:"}
                        </span>
                        <span>
                          {outreach.channel === "sms"
                            ? "Direct SMS Message"
                            : outreach.subject || "(No subject)"}
                        </span>
                      </div>
                      {outreach.body && (
                        <p className="text-slate-500 line-clamp-2 text-[10.5px]">
                          {outreach.body}
                        </p>
                      )}
                    </div>

                    {/* Provider error message if failed */}
                    {outreach.error && (
                      <div className="p-2 rounded bg-rose-50 border border-rose-200 text-rose-700 text-[10.5px] flex items-start gap-1.5">
                        <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-rose-600" />
                        <div>
                          <span className="font-semibold">Delivery Error:</span> {outreach.error}
                        </div>
                      </div>
                    )}

                    {/* Simulated Voice Call Control Panel */}
                    {outreach.channel === "voice" && outreach.status === "sending" && (
                      <div className="p-2.5 bg-blue-50/70 border border-blue-200/80 rounded-lg space-y-2 mt-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] font-medium text-blue-900 flex items-center gap-1.5">
                            <PhoneCall className="w-3.5 h-3.5 text-blue-600 animate-pulse" />
                            Mock SDR Call In-Flight ({outreach.providerMessageId || "Simulated"})
                          </span>
                          <span className="text-[10px] text-blue-700 bg-blue-100 px-2 py-0.5 rounded font-mono font-medium">
                            Test Simulation
                          </span>
                        </div>
                        <p className="text-[10.5px] text-blue-800 leading-relaxed">
                          Outbound live calling is safely disabled. Choose an outcome to complete call simulation and trigger automated follow-up:
                        </p>
                        <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
                          <Button
                            variant="primary"
                            size="sm"
                            disabled={simulatingOutreachId === outreach.id}
                            onClick={() => handleSimulateMockVoiceCompletion(outreach.id, "INTERESTED")}
                            className="text-[10.5px] h-6 px-2.5 bg-emerald-600 hover:bg-emerald-700 text-white inline-flex items-center gap-1"
                          >
                            <Check className="w-3 h-3" />
                            <span>{simulatingOutreachId === outreach.id ? "Completing..." : "Simulate Prospect Answered (Interested)"}</span>
                          </Button>
                          <Button
                            variant="secondary"
                            size="sm"
                            disabled={simulatingOutreachId === outreach.id}
                            onClick={() => handleSimulateMockVoiceCompletion(outreach.id, "NOT_INTERESTED")}
                            className="text-[10.5px] h-6 px-2 text-slate-700"
                          >
                            Not Interested
                          </Button>
                          <Button
                            variant="secondary"
                            size="sm"
                            disabled={simulatingOutreachId === outreach.id}
                            onClick={() => handleSimulateMockVoiceCompletion(outreach.id, "NO_ANSWER")}
                            className="text-[10.5px] h-6 px-2 text-rose-700"
                          >
                            No Answer
                          </Button>
                        </div>
                      </div>
                    )}

                    {/* Send action */}
                    <div className="flex items-center justify-between pt-1">
                      <span className="text-[10px] text-slate-500 font-mono">
                        {outreach.provider?.startsWith("mock")
                          ? `Provider: Mock (${outreach.channel === "sms" ? "Twilio SMS Simulation" : outreach.channel === "voice" ? "Retell Voice Simulation" : "Email Simulation"})`
                          : outreach.provider
                          ? `Provider: ${outreach.provider}`
                          : `Channel: ${outreach.channel.toUpperCase()}`}
                        {outreach.sentAt
                          ? ` • ${outreach.provider?.startsWith("mock") ? "Simulated" : "Sent"} ${new Date(outreach.sentAt).toLocaleTimeString()}`
                          : ""}
                        {outreach.firstDeliveredAt
                          ? ` • Delivered ${new Date(outreach.firstDeliveredAt).toLocaleTimeString()}`
                          : ""}
                      </span>

                      {(outreach.status === "draft" || outreach.status === "scheduled") && (
                        <Button
                          variant="primary"
                          size="sm"
                          disabled={sendingOutreachId === outreach.id}
                          onClick={() => handleSendOutreach(outreach.id)}
                          className="text-[11px] h-7 px-2.5 inline-flex items-center gap-1"
                        >
                          <Send className="w-3 h-3" />
                          <span>
                            {sendingOutreachId === outreach.id
                              ? "Sending..."
                              : outreach.channel === "sms"
                              ? "Send SMS (Mock)"
                              : outreach.channel === "voice"
                              ? "Simulate Voice Call"
                              : "Send Email"}
                          </span>
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Section: Campaign Performance (Strict Data Integrity) */}
          <div className="space-y-3 border-t border-slate-100 pt-5">
            <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Campaign Performance
            </h4>

            {totalOutreachEvents === 0 && (campaign.metrics.simulated ?? 0) === 0 ? (
              <div className="p-4 rounded-lg border border-dashed border-slate-200 text-center space-y-1 bg-slate-50/30">
                <p className="text-xs font-medium text-slate-500">
                  No emails sent yet.
                </p>
                <p className="text-[11px] text-slate-400">
                  Delivery and engagement metrics strictly reflect verified send events from backend.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="grid grid-cols-3 gap-2">
                  <div className="p-2.5 rounded-lg border border-slate-200 bg-white">
                    <span className="text-[10px] text-slate-400 uppercase font-semibold block">
                      Sent (Live)
                    </span>
                    <span className="text-sm font-bold text-header">
                      {campaign.metrics.sent}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-lg border border-slate-200 bg-white">
                    <span className="text-[10px] text-slate-400 uppercase font-semibold block">
                      Delivered (Verified)
                    </span>
                    <span className="text-sm font-bold text-header">
                      {campaign.metrics.delivered}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-lg border border-slate-200 bg-white">
                    <span className="text-[10px] text-slate-400 uppercase font-semibold block">
                      Simulated (Mock)
                    </span>
                    <span className="text-sm font-bold text-amber-700">
                      {campaign.metrics.simulated ?? 0}
                    </span>
                  </div>
                </div>
                {(campaign.metrics.simulated ?? 0) > 0 && (
                  <p className="text-[10.5px] text-amber-700 bg-amber-50/60 border border-amber-200/60 rounded p-2">
                    ℹ️ <strong>Mock Provider Active:</strong> Simulated sends do not transmit real emails over the network or count toward verified deliveries.
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-100 bg-slate-50/50 flex items-center justify-between gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={onClose}
            className="text-xs"
          >
            Close
          </Button>

          <span className="text-[10px] text-slate-400 font-mono">
            Tenant: {campaign.organizationId.substring(0, 8)}...
          </span>
        </div>
      </div>

      {/* ENROLL CONTACTS MODAL */}
      <Modal
        isOpen={isEnrollModalOpen}
        onClose={() => setIsEnrollModalOpen(false)}
        title="Enroll Contacts in Campaign"
        maxWidth="lg"
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600">
            Select genuine prospects from your CRM database to enroll into{" "}
            <span className="font-semibold text-header">&ldquo;{campaign.name}&rdquo;</span>.
          </p>

          {actionError && (
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-start gap-2 animate-in fade-in">
              <AlertTriangle className="w-4 h-4 shrink-0 text-rose-500 mt-0.5" />
              <span>{actionError}</span>
            </div>
          )}

          {/* Search Contacts */}
          <Input
            placeholder="Search contacts by name, email, or company..."
            value={contactSearchQuery}
            onChange={(e) => setContactSearchQuery(e.target.value)}
            icon={<Search className="w-4 h-4 text-slate-400" />}
            className="h-9 text-xs"
          />

          {/* Contacts List */}
          <div className="border border-slate-200 rounded-lg max-h-72 overflow-y-auto divide-y divide-slate-100">
            {isLoadingContacts ? (
              <div className="p-8 text-center text-xs text-slate-500">
                Loading genuine CRM contacts...
              </div>
            ) : filteredAvailableContacts.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-400">
                No matching contacts found.
              </div>
            ) : (
              filteredAvailableContacts.map((contact) => {
                const isAlreadyEnrolled = enrolledContactIdSet.has(contact.id);
                const isSelected = selectedContactIds.includes(contact.id);
                const fullName = `${contact.first_name} ${contact.last_name}`.trim() || contact.email;
                const companyName = contact.company?.name || "—";

                return (
                  <div
                    key={contact.id}
                    className={`p-3 flex items-center justify-between gap-3 text-xs transition-colors ${
                      isAlreadyEnrolled
                        ? "bg-slate-50 opacity-60 cursor-not-allowed"
                        : isSelected
                        ? "bg-agile-lightorange/30 cursor-pointer"
                        : "hover:bg-slate-50 cursor-pointer"
                    }`}
                    onClick={() => {
                      if (isAlreadyEnrolled) return;
                      setSelectedContactIds((prev) =>
                        isSelected ? prev.filter((id) => id !== contact.id) : [...prev, contact.id]
                      );
                    }}
                  >
                    <div className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        checked={isSelected || isAlreadyEnrolled}
                        disabled={isAlreadyEnrolled}
                        onChange={() => {}} // handled by row onClick
                        className="rounded border-slate-300 text-agile-red focus:ring-agile-red"
                      />
                      <div>
                        <span className="font-semibold text-slate-800 block">
                          {fullName}
                        </span>
                        <span className="text-[11px] text-slate-500 font-mono">
                          {contact.email} • {companyName}
                        </span>
                      </div>
                    </div>

                    {isAlreadyEnrolled && (
                      <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                        Already Enrolled
                      </span>
                    )}
                  </div>
                );
              })
            )}
          </div>

          {/* Modal Footer Actions */}
          <div className="flex items-center justify-between pt-2">
            <span className="text-xs text-slate-500">
              {selectedContactIds.length} contact{selectedContactIds.length === 1 ? "" : "s"} selected
            </span>

            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIsEnrollModalOpen(false)}
                className="text-xs"
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                disabled={isEnrolling || selectedContactIds.length === 0}
                onClick={handleConfirmEnrollment}
                className="text-xs"
              >
                {isEnrolling ? "Enrolling..." : `Enroll ${selectedContactIds.length} Contacts`}
              </Button>
            </div>
          </div>
        </div>
      </Modal>

      {/* Modal: Remove Contact from Campaign Confirmation */}
      <Modal
        isOpen={contactToRemove !== null}
        onClose={() => {
          if (!isRemovingContact) {
            setContactToRemove(null);
            setRemoveContactError(null);
          }
        }}
        title={`Remove ${contactToRemove?.contactName || "Contact"} from ${campaign.name}?`}
        description="This will remove the contact's membership in this campaign only. The lead and CRM Contact will remain in the platform."
        footer={
          <>
            <Button
              variant="secondary"
              disabled={isRemovingContact}
              onClick={() => {
                setContactToRemove(null);
                setRemoveContactError(null);
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={isRemovingContact}
              onClick={handleConfirmRemoveContact}
              className="bg-rose-600 hover:bg-rose-700 text-white border-rose-600"
            >
              {isRemovingContact ? "Removing..." : "Remove Contact"}
            </Button>
          </>
        }
      >
        {contactToRemove && (
          <div className="space-y-3">
            {removeContactError && (
              <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-rose-500" />
                <span>{removeContactError}</span>
              </div>
            )}
            <div className="rounded-lg bg-slate-50 border border-slate-200 p-3.5 space-y-2 text-xs">
              <div className="flex justify-between items-center">
                <span className="text-slate-500 font-medium">Contact:</span>
                <span className="text-slate-900 font-semibold">{contactToRemove.contactName}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-500 font-medium">Email:</span>
                <span className="text-slate-900 font-mono">{contactToRemove.contactEmail}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-500 font-medium">Company:</span>
                <span className="text-slate-900">{contactToRemove.companyName}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-500 font-medium">Enrollment Status:</span>
                <span className="text-slate-900 font-semibold uppercase tracking-wider">{contactToRemove.enrollmentStatus}</span>
              </div>
            </div>
            <div className="space-y-1.5 text-xs text-slate-500 leading-relaxed">
              <p>Other campaign memberships will not be affected.</p>
              <p>No email or call will be initiated by this operation.</p>
            </div>
          </div>
        )}
      </Modal>

      {/* Modal: Delete Campaign Confirmation */}
      <Modal
        isOpen={isDeleteCampaignModalOpen}
        onClose={() => {
          if (!isDeletingCampaign) {
            setIsDeleteCampaignModalOpen(false);
            setDeleteCampaignError(null);
          }
        }}
        title={`Delete Campaign: ${campaign.name}?`}
        description="This permanently removes the campaign from the active campaign list. Associated enrollment and historical records may be retained where required for audit and data integrity."
        footer={
          <>
            <Button
              variant="secondary"
              disabled={isDeletingCampaign}
              onClick={() => {
                setIsDeleteCampaignModalOpen(false);
                setDeleteCampaignError(null);
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={isDeletingCampaign}
              onClick={handleConfirmDeleteCampaign}
              className="bg-rose-600 hover:bg-rose-700 text-white border-rose-600"
            >
              {isDeletingCampaign ? "Deleting Campaign..." : "Delete Campaign"}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {deleteCampaignError && (
            <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-500" />
              <span>{deleteCampaignError}</span>
            </div>
          )}
          <div className="rounded-lg bg-slate-50 border border-slate-200 p-3.5 space-y-2 text-xs">
            <div className="flex justify-between items-center">
              <span className="text-slate-500 font-medium">Campaign Name:</span>
              <span className="text-slate-900 font-semibold">{campaign.name}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-500 font-medium">Type:</span>
              <span className="text-slate-900">{CAMPAIGN_TYPE_LABELS[campaign.type]}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-500 font-medium">Enrolled Contacts:</span>
              <span className="text-slate-900 font-semibold">{campaign.contacts.length}</span>
            </div>
          </div>
          <p className="text-xs text-rose-600 font-medium leading-relaxed">
            This action cannot be undone from the UI.
          </p>
        </div>
      </Modal>

      {/* Modal: Attach Contact List to Campaign */}
      <Modal
        isOpen={isAttachListModalOpen}
        onClose={() => {
          if (!isAttachingList) {
            setIsAttachListModalOpen(false);
            setAttachListError(null);
          }
        }}
        title="Attach List to Campaign"
        description="Select a named contact list to associate with this campaign."
        footer={
          <>
            <Button
              variant="secondary"
              disabled={isAttachingList}
              onClick={() => {
                setIsAttachListModalOpen(false);
                setAttachListError(null);
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={isAttachingList || availableListsToAttach.length === 0 || !selectedListIdToAttach}
              onClick={handleAttachList}
            >
              {isAttachingList ? "Attaching & Enrolling..." : "Attach and Sync List"}
            </Button>
          </>
        }
      >
        <div className="space-y-4 pt-1">
          {attachListError && (
            <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-500" />
              <span>{attachListError}</span>
            </div>
          )}

          {isLoadingAvailableLists ? (
            <div className="p-6 text-center text-xs text-slate-500">
              Loading available contact lists...
            </div>
          ) : availableListsToAttach.length === 0 ? (
            <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-600 text-center">
              No additional contact lists available to attach. All existing lists are already linked to this campaign, or no lists have been created yet.
            </div>
          ) : (
            <div className="space-y-3">
              <label className="text-xs font-semibold text-slate-700 block">
                Choose Contact List
              </label>
              <select
                value={selectedListIdToAttach}
                onChange={(e) => setSelectedListIdToAttach(e.target.value)}
                className="w-full text-xs rounded-md border border-slate-200 p-2.5 bg-white text-slate-900 focus:outline-none focus:ring-1 focus:ring-agile-red"
              >
                {availableListsToAttach.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name} ({l.member_count} members)
                  </option>
                ))}
              </select>

              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-600 space-y-1">
                <p className="font-semibold text-slate-700">Safety &amp; Deduplication Rule</p>
                <p className="text-[11px] text-slate-500 leading-relaxed">
                  Attaching this list will queue its eligible contacts without duplicating members already in the campaign. Contacts without emails or who have opted out will be safely skipped. No live emails or calls are triggered.
                </p>
              </div>
            </div>
          )}
        </div>
      </Modal>
      {/* Modal: Direct Mail Pre-Flight & Test Dispatch */}
      <PhysicalMailPreflightModal
        isOpen={isPhysicalMailModalOpen}
        onClose={() => setIsPhysicalMailModalOpen(false)}
        campaignId={campaign.id}
        campaignName={campaign.name}
        onCompleted={async () => {
          if (campaign) await refreshCampaign(campaign.id);
          onCampaignUpdated?.();
        }}
      />
    </div>
  );
};
