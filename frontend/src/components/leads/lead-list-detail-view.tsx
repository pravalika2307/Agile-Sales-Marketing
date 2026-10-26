"use client";
import { PhysicalMailPreflightModal } from "@/components/campaigns/physical-mail-preflight-modal";

import * as React from "react";
import Link from "next/link";
import {
  ContactListDetail,
  ContactListMember,
  deleteContactList,
  fetchContactListMembers,
  getContactList,
  removeMemberFromList,
  syncCampaignList,
  attachListToCampaign,
} from "@/services/contactListService";
import {
  fetchCampaigns,
  CampaignItem,
  enrollContactsInCampaign,
} from "@/services/campaignService";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Modal } from "@/components/ui/modal";
import {
  ArrowLeft,
  Users,
  Mail,
  AlertTriangle,
  Send,
  Calendar,
  Search,
  Trash2,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  ShieldAlert,
  X,
  Phone,
  Building2,
  CheckSquare,
  Square,
  MinusSquare,
  Eye,
  Check,
  Plus,
  Activity,
  Clock,
} from "lucide-react";
import { CRMLead, fetchCRMLeadById } from "@/services/crmLeadService";
import {
  fetchUnifiedActivities,
  UnifiedActivityItem,
} from "@/services/analyticsService";

export interface LeadListDetailViewProps {
  listId: string;
  onBackToLists: () => void;
  onInspectLead: (lead: CRMLead) => void;
}

export const LeadListDetailView: React.FC<LeadListDetailViewProps> = ({
  listId,
  onBackToLists,
  onInspectLead,
}) => {
  // Detail State
  const [listDetail, setListDetail] = React.useState<ContactListDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = React.useState(true);
  const [detailError, setDetailError] = React.useState<string | null>(null);

  // Members State
  const [members, setMembers] = React.useState<ContactListMember[]>([]);
  const [membersTotal, setMembersTotal] = React.useState(0);
  const [isLoadingMembers, setIsLoadingMembers] = React.useState(true);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [emailFilter, setEmailFilter] = React.useState<"ALL" | "VALID" | "UNRESOLVED">("ALL");

  // Selection
  const [selectedMemberIds, setSelectedMemberIds] = React.useState<Set<string>>(new Set());
  const [isDirectMailModalOpen, setIsDirectMailModalOpen] = React.useState(false);
  const [directMailCampaign, setDirectMailCampaign] = React.useState<CampaignItem | null>(null);

  // Notifications
  const [successBanner, setSuccessBanner] = React.useState<string | null>(null);
  const [errorBanner, setErrorBanner] = React.useState<string | null>(null);

  // Remove Member State
  const [memberToRemove, setMemberToRemove] = React.useState<ContactListMember | null>(null);
  const [isRemovingMember, setIsRemovingMember] = React.useState(false);

  // Campaign Association Modal State
  const [isAttachModalOpen, setIsAttachModalOpen] = React.useState(false);
  const [availableCampaigns, setAvailableCampaigns] = React.useState<CampaignItem[]>([]);
  const [isLoadingCampaigns, setIsLoadingCampaigns] = React.useState(false);
  const [selectedCampaignId, setSelectedCampaignId] = React.useState("");
  const [isAttaching, setIsAttaching] = React.useState(false);

  // Add Selected to Campaign Modal State
  const [isAddSelectedModalOpen, setIsAddSelectedModalOpen] = React.useState(false);
  const [selectedEnrollCampaignId, setSelectedEnrollCampaignId] = React.useState("");
  const [isEnrollingSelected, setIsEnrollingSelected] = React.useState(false);

  // Syncing State
  const [syncingCampaignId, setSyncingCampaignId] = React.useState<string | null>(null);

  // Load List Detail
  const loadDetail = React.useCallback(async () => {
    if (!listId) return;
    setIsLoadingDetail(true);
    setDetailError(null);
    try {
      const data = await getContactList(listId);
      setListDetail(data);
    } catch (err: unknown) {
      setDetailError(err instanceof Error ? err.message : "Failed to load list details.");
    } finally {
      setIsLoadingDetail(false);
    }
  }, [listId]);

  // Load List Members
  const loadMembers = React.useCallback(async () => {
    if (!listId) return;
    setIsLoadingMembers(true);
    try {
      const hasUnresolved =
        emailFilter === "UNRESOLVED" ? true : emailFilter === "VALID" ? false : undefined;
      const res = await fetchContactListMembers(listId, {
        search: searchQuery,
        has_unresolved_email: hasUnresolved,
        limit: 100,
      });
      setMembers(res.items);
      setMembersTotal(res.total);
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Failed to load list members.");
    } finally {
      setIsLoadingMembers(false);
    }
  }, [listId, searchQuery, emailFilter]);

  // List Activity State
  const [listActivities, setListActivities] = React.useState<UnifiedActivityItem[]>([]);
  const [isLoadingActivities, setIsLoadingActivities] = React.useState(false);
  const [activitiesTotal, setActivitiesTotal] = React.useState(0);

  const loadActivities = React.useCallback(async () => {
    if (!listId) return;
    setIsLoadingActivities(true);
    try {
      const res = await fetchUnifiedActivities({ list_id: listId, limit: 5 });
      setListActivities(res.items);
      setActivitiesTotal(res.total);
    } catch {
      // ignore non-critical list activity fetch failure
    } finally {
      setIsLoadingActivities(false);
    }
  }, [listId]);

  React.useEffect(() => {
    loadDetail();
    loadMembers();
    loadActivities();
  }, [loadDetail, loadMembers, loadActivities]);

  // Fetch campaigns for modals
  const loadCampaigns = async () => {
    setIsLoadingCampaigns(true);
    try {
      const res = await fetchCampaigns();
      setAvailableCampaigns(res.campaigns);
      if (res.campaigns.length > 0) {
        setSelectedCampaignId(res.campaigns[0].id);
        setSelectedEnrollCampaignId(res.campaigns[0].id);
      }
    } catch (err) {
      console.error("Failed to fetch campaigns:", err);
    } finally {
      setIsLoadingCampaigns(false);
    }
  };

  // Selection helpers
  const handleToggleSelectAll = () => {
    if (selectedMemberIds.size === members.length) {
      setSelectedMemberIds(new Set());
    } else {
      setSelectedMemberIds(new Set(members.map((m) => m.id)));
    }
  };

  const handleSelectEligibleOnly = () => {
    const eligible = members.filter((m) => m.has_valid_email).map((m) => m.id);
    setSelectedMemberIds(new Set(eligible));
  };

  const handleToggleSelectOne = (id: string) => {
    setSelectedMemberIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Remove single member
  const handleConfirmRemoveMember = async () => {
    if (!memberToRemove || !listDetail) return;
    setIsRemovingMember(true);
    try {
      await removeMemberFromList(listDetail.id, memberToRemove.id);
      setSuccessBanner(`Removed "${memberToRemove.full_name}" from list.`);
      setMemberToRemove(null);
      setSelectedMemberIds((prev) => {
        const next = new Set(prev);
        next.delete(memberToRemove.id);
        return next;
      });
      await Promise.all([loadDetail(), loadMembers()]);
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Failed to remove member.");
    } finally {
      setIsRemovingMember(false);
    }
  };

  const handleLaunchDirectMailFromList = async () => {
    if (selectedMemberIds.size === 0) return;
    setIsLoadingCampaigns(true);
    try {
      const res = await fetchCampaigns();
      setAvailableCampaigns(res.campaigns);
      const mailCamp = res.campaigns.find(
        (c) => c.channels?.includes("physical_mail") || c.steps?.some((s) => s.stepType === "physical_mail")
      ) || res.campaigns[0];
      if (mailCamp) {
        setDirectMailCampaign(mailCamp);
        setIsDirectMailModalOpen(true);
      } else {
        setIsAddSelectedModalOpen(true);
      }
    } catch (err) {
      console.error("Error launching direct mail from list:", err);
    } finally {
      setIsLoadingCampaigns(false);
    }
  };

  // Bulk remove selected members
  const handleRemoveSelectedMembers = async () => {
    if (selectedMemberIds.size === 0 || !listDetail) return;
    try {
      let count = 0;
      for (const mid of Array.from(selectedMemberIds)) {
        await removeMemberFromList(listDetail.id, mid);
        count++;
      }
      setSuccessBanner(`Removed ${count} member(s) from list.`);
      setSelectedMemberIds(new Set());
      await Promise.all([loadDetail(), loadMembers()]);
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Failed to remove selected members.");
    }
  };

  // Attach List to Campaign
  const handleAttachListToCampaign = async () => {
    if (!selectedCampaignId || !listDetail) return;
    setIsAttaching(true);
    try {
      const res = await attachListToCampaign(selectedCampaignId, listDetail.id, true);
      let msg = `Attached to campaign! ${res.newly_enrolled_count} newly enrolled.`;
      if (res.unresolved_email_count > 0) {
        msg += ` (${res.unresolved_email_count} skipped due to missing email)`;
      }
      if (res.suppressed_opt_out_count > 0) {
        msg += ` (${res.suppressed_opt_out_count} suppressed)`;
      }
      setSuccessBanner(msg);
      setIsAttachModalOpen(false);
      await loadDetail();
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Failed to attach list to campaign.");
    } finally {
      setIsAttaching(false);
    }
  };

  // Explicit Campaign Sync
  const handleSyncCampaign = async (campaignId: string) => {
    if (!listDetail) return;
    setSyncingCampaignId(campaignId);
    try {
      const res = await syncCampaignList(campaignId, listDetail.id);
      let msg = `Sync complete: ${res.newly_enrolled_count} newly enrolled.`;
      if (res.unresolved_email_count > 0) {
        msg += ` (${res.unresolved_email_count} unresolved skipped)`;
      }
      setSuccessBanner(msg);
      await loadDetail();
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Failed to sync campaign.");
    } finally {
      setSyncingCampaignId(null);
    }
  };

  // Add Selected Leads to Campaign
  const handleEnrollSelectedToCampaign = async () => {
    if (!selectedEnrollCampaignId || selectedMemberIds.size === 0) return;
    setIsEnrollingSelected(true);
    try {
      // Find contact IDs for selected members
      const selectedMembers = members.filter((m) => selectedMemberIds.has(m.id));
      const contactIds = selectedMembers
        .map((m) => m.contact_id)
        .filter((cid): cid is string => Boolean(cid));

      if (contactIds.length === 0) {
        throw new Error("None of the selected leads have a valid CRM contact record. Provide valid emails first.");
      }

      const res = await enrollContactsInCampaign(selectedEnrollCampaignId, contactIds);
      setSuccessBanner(
        `Enrolled ${res.enrolledContactIds.length} contact(s) into campaign. (${res.alreadyEnrolledContactIds.length} already enrolled, ${res.rejectedContactIds.length} rejected/suppressed)`
      );
      setIsAddSelectedModalOpen(false);
      setSelectedMemberIds(new Set());
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Failed to enroll selected leads.");
    } finally {
      setIsEnrollingSelected(false);
    }
  };

  // Handle lead click to open drawer
  const handleLeadClick = async (member: ContactListMember) => {
    if (member.lead_id) {
      try {
        const lead = await fetchCRMLeadById(member.lead_id);
        onInspectLead(lead);
      } catch (err) {
        console.error("Failed to fetch lead for drawer:", err);
      }
    }
  };

  if (isLoadingDetail && !listDetail) {
    return (
      <div className="space-y-4 max-w-7xl mx-auto p-6 animate-pulse">
        <div className="h-6 w-32 bg-slate-200 rounded" />
        <div className="h-10 w-96 bg-slate-200 rounded" />
        <div className="grid grid-cols-4 gap-4 pt-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 bg-slate-100 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (detailError || !listDetail) {
    return (
      <div className="max-w-2xl mx-auto py-12 text-center space-y-4">
        <AlertCircle className="w-12 h-12 text-rose-500 mx-auto" />
        <h2 className="text-lg font-bold text-header">List Not Found</h2>
        <p className="text-sm text-slate-500">
          {detailError || "This contact list does not exist or you do not have permission to view it."}
        </p>
        <Button variant="secondary" size="sm" onClick={onBackToLists} className="text-xs">
          Back to Lists
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-16">
      {/* 1. Navigation Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <button
          onClick={onBackToLists}
          className="hover:text-header transition-colors inline-flex items-center gap-1 font-medium text-slate-600"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>All Lists</span>
        </button>
        <span>/</span>
        <span className="text-slate-800 font-semibold">{listDetail.name}</span>
      </div>

      {/* 2. List Header & Action Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 pb-4 border-b border-slate-100">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-2xl font-bold tracking-tight text-header">
              {listDetail.name}
            </h1>
            <Badge variant="neutral" className="text-xs capitalize">
              {listDetail.type} List
            </Badge>
            {listDetail.unresolved_email_count > 0 && (
              <Badge variant="warning" dot className="text-xs">
                {listDetail.unresolved_email_count} Unresolved Email{listDetail.unresolved_email_count > 1 ? "s" : ""}
              </Badge>
            )}
          </div>
          {listDetail.description ? (
            <p className="text-sm text-slate-600 max-w-2xl mt-1">
              {listDetail.description}
            </p>
          ) : (
            <p className="text-xs text-slate-400 italic">No description provided.</p>
          )}
          <div className="flex items-center gap-3 text-xs text-slate-400 pt-1">
            <span>Created {new Date(listDetail.created_at).toLocaleDateString()}</span>
            <span>•</span>
            <span>Last updated {new Date(listDetail.updated_at).toLocaleDateString()}</span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              loadDetail();
              loadMembers();
              loadActivities();
            }}
            className="text-xs inline-flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5 text-slate-500" />
            <span>Refresh</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              loadCampaigns();
              setIsAttachModalOpen(true);
            }}
            className="text-xs inline-flex items-center gap-1.5 border-blue-200 text-blue-700 hover:bg-blue-50"
          >
            <Send className="w-3.5 h-3.5" />
            <span>Attach to Campaign</span>
          </Button>
        </div>
      </div>

      {/* Feedback Banners */}
      {successBanner && (
        <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{successBanner}</span>
          </div>
          <button
            onClick={() => setSuccessBanner(null)}
            className="text-emerald-500 hover:text-emerald-700"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {errorBanner && (
        <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{errorBanner}</span>
          </div>
          <button
            onClick={() => setErrorBanner(null)}
            className="text-rose-500 hover:text-rose-700"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* 3. Unresolved Email Protective Warning Banner */}
      {listDetail.unresolved_email_count > 0 && (
        <div className="p-3.5 rounded-xl bg-amber-50/70 border border-amber-200 text-amber-900 text-xs flex items-start gap-3">
          <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <p className="font-semibold">
              Unresolved Email Warning ({listDetail.unresolved_email_count} lead{listDetail.unresolved_email_count > 1 ? "s" : ""})
            </p>
            <p className="text-[11px] text-amber-800 leading-relaxed">
              Leads without valid email addresses can be organized in this list for phone calls or manual enrichment, but they <strong>will NOT be enrolled in automated email outreach</strong> when synchronizing with campaigns until an email address is provided and verified.
            </p>
          </div>
        </div>
      )}

      {/* 4. Stat Cards Breakdown */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card className="border-slate-200 shadow-xs">
          <CardContent className="p-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              Total Members
            </p>
            <p className="text-2xl font-bold text-header mt-1">
              {listDetail.member_count}
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Organized contacts & leads
            </p>
          </CardContent>
        </Card>

        <Card className="border-slate-200 shadow-xs">
          <CardContent className="p-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              Valid Email
            </p>
            <p className="text-2xl font-bold text-emerald-600 mt-1">
              {listDetail.valid_email_count}
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Outreach eligible
            </p>
          </CardContent>
        </Card>

        <Card className="border-slate-200 shadow-xs">
          <CardContent className="p-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              Unresolved Email
            </p>
            <p className="text-2xl font-bold text-amber-600 mt-1">
              {listDetail.unresolved_email_count}
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Email outreach suppressed
            </p>
          </CardContent>
        </Card>

        <Card className="border-slate-200 shadow-xs">
          <CardContent className="p-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              Associated Campaigns
            </p>
            <p className="text-2xl font-bold text-blue-600 mt-1">
              {listDetail.campaigns_count}
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Outbound sequences linked
            </p>
          </CardContent>
        </Card>
      </div>

      {/* 5. Associated Campaigns Accordion / Section */}
      {listDetail.associated_campaigns.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-3 shadow-xs">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-header flex items-center gap-2">
              <Send className="w-3.5 h-3.5 text-agile-red" />
              <span>Associated Campaigns ({listDetail.associated_campaigns.length})</span>
            </h3>
            <span className="text-[11px] text-slate-400">
              Synchronizing will enroll new eligible members without resetting existing progress.
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {listDetail.associated_campaigns.map((camp) => (
              <div
                key={camp.id}
                className="p-3 rounded-lg border border-slate-100 bg-slate-50/50 flex items-center justify-between gap-2"
              >
                <div className="space-y-0.5 truncate">
                  <p className="text-xs font-semibold text-header truncate">{camp.name}</p>
                  <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
                    <span className="capitalize">{camp.status}</span>
                    <span>•</span>
                    <span className="capitalize">{camp.type.replace("_", " ")}</span>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleSyncCampaign(camp.id)}
                  disabled={syncingCampaignId === camp.id}
                  className="text-xs h-7 px-2 shrink-0 inline-flex items-center gap-1"
                >
                  <RefreshCw
                    className={`w-3 h-3 text-slate-500 ${
                      syncingCampaignId === camp.id ? "animate-spin" : ""
                    }`}
                  />
                  <span>{syncingCampaignId === camp.id ? "Syncing..." : "Sync"}</span>
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 5b. List Activity Summary Section */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-3 shadow-xs">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold text-header flex items-center gap-2">
            <Activity className="w-3.5 h-3.5 text-blue-600" />
            <span>List Outreach & Activity ({activitiesTotal})</span>
          </h3>
          <span className="text-[11px] text-slate-400">
            Verified email and voice interactions with members of this list.
          </span>
        </div>

        {isLoadingActivities && (
          <div className="py-4 text-center text-xs text-slate-400 flex items-center justify-center gap-2">
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-slate-400" />
            <span>Loading recent activity...</span>
          </div>
        )}

        {!isLoadingActivities && listActivities.length === 0 && (
          <div className="p-4 rounded-lg bg-slate-50 border border-slate-100 text-center text-xs text-slate-500">
            No outreach or call activity recorded for members of this list yet.
          </div>
        )}

        {!isLoadingActivities && listActivities.length > 0 && (
          <div className="space-y-2">
            {listActivities.map((act) => {
              const isEmail = act.channel === "email";
              const isVoice = act.channel === "voice";

              return (
                <div
                  key={act.id}
                  className="p-2.5 rounded-lg border border-slate-100 bg-slate-50/50 flex items-center justify-between gap-3 text-xs"
                >
                  <div className="flex items-center gap-2.5 truncate">
                    <div
                      className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${
                        isEmail
                          ? "bg-blue-100 text-blue-600"
                          : isVoice
                          ? "bg-purple-100 text-purple-600"
                          : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {isEmail && <Mail className="w-3 h-3" />}
                      {isVoice && <Phone className="w-3 h-3" />}
                    </div>

                    <div className="space-y-0.5 truncate">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-header truncate">{act.title}</span>
                        {act.contact_name && (
                          <span className="text-[11px] text-slate-500 truncate">
                            • {act.contact_name}
                          </span>
                        )}
                        {act.company_name && (
                          <span className="text-[11px] text-slate-400 truncate">
                            ({act.company_name})
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-slate-400">
                        {act.campaign_name && <span>Campaign: {act.campaign_name}</span>}
                        {isEmail && act.email_details && (
                          <>
                            {act.email_details.is_replied ? (
                              <span className="text-purple-600 font-semibold">• Replied</span>
                            ) : act.email_details.is_delivered ? (
                              <span className="text-emerald-600 font-semibold">• Delivered</span>
                            ) : act.email_details.status === "sent" ? (
                              <span className="text-slate-500">• Submitted</span>
                            ) : null}
                          </>
                        )}
                        {isVoice && act.voice_details && (
                          <>
                            <span className={act.voice_details.is_connected ? "text-emerald-600 font-semibold" : "text-slate-500"}>
                              • {act.voice_details.is_connected ? "Connected" : "No Answer"}
                            </span>
                            {act.voice_details.call_outcome && (
                              <span className="text-indigo-600 font-semibold">• {act.voice_details.call_outcome}</span>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  <span className="text-[11px] font-mono text-slate-400 shrink-0">
                    {new Date(act.occurred_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 6. Members Table Controls: Search, Email Status Filter, Bulk Actions */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            {/* Search Input */}
            <div className="relative w-full sm:w-64">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                type="text"
                placeholder="Search leads in this list..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 h-9 text-xs"
              />
            </div>

            {/* Email Filter Pills */}
            <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg text-xs font-medium">
              <button
                onClick={() => setEmailFilter("ALL")}
                className={`px-2.5 py-1 rounded-md transition-all ${
                  emailFilter === "ALL"
                    ? "bg-white text-header shadow-xs font-semibold"
                    : "text-slate-600 hover:text-header"
                }`}
              >
                All ({membersTotal})
              </button>
              <button
                onClick={() => setEmailFilter("VALID")}
                className={`px-2.5 py-1 rounded-md transition-all ${
                  emailFilter === "VALID"
                    ? "bg-white text-header shadow-xs font-semibold"
                    : "text-slate-600 hover:text-header"
                }`}
              >
                Valid Email
              </button>
              <button
                onClick={() => setEmailFilter("UNRESOLVED")}
                className={`px-2.5 py-1 rounded-md transition-all ${
                  emailFilter === "UNRESOLVED"
                    ? "bg-white text-header shadow-xs font-semibold"
                    : "text-slate-600 hover:text-header"
                }`}
              >
                Unresolved
              </button>
            </div>
          </div>

          {/* Quick Selection Shortcuts */}
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleSelectEligibleOnly}
              className="text-xs text-emerald-700 hover:text-emerald-800 hover:bg-emerald-50 h-8"
              title="Select all members with valid email addresses"
            >
              <span>Select All Eligible</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleToggleSelectAll}
              className="text-xs text-slate-600 hover:text-header h-8"
            >
              <span>{selectedMemberIds.size === members.length ? "Deselect All" : "Select All"}</span>
            </Button>
          </div>
        </div>

        {/* Bulk Action Bar (when leads are selected) */}
        {selectedMemberIds.size > 0 && (
          <div className="p-3 bg-slate-900 text-white rounded-xl shadow-lg flex items-center justify-between gap-4 animate-in fade-in slide-in-from-top-1">
            <div className="flex items-center gap-2.5 pl-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-xs font-semibold">
                {selectedMemberIds.size} lead{selectedMemberIds.size > 1 ? "s" : ""} selected
              </span>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  loadCampaigns();
                  setIsAddSelectedModalOpen(true);
                }}
                className="text-xs bg-white text-slate-900 hover:bg-slate-100 border-none h-8 font-medium inline-flex items-center gap-1.5"
              >
                <Send className="w-3.5 h-3.5 text-agile-red" />
                <span>Add to Campaign</span>
              </Button>

              <Button
                variant="outline"
                size="sm"
                onClick={handleLaunchDirectMailFromList}
                className="text-xs bg-rose-600 hover:bg-rose-700 text-white border-none h-8 font-medium inline-flex items-center gap-1.5"
                title="Direct Mail Pre-Flight & Test Dispatch"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Direct Mail</span>
              </Button>

              <Button
                variant="outline"
                size="sm"
                onClick={handleRemoveSelectedMembers}
                className="text-xs bg-rose-600 hover:bg-rose-700 text-white border-none h-8 font-medium inline-flex items-center gap-1.5"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Remove from List</span>
              </Button>

              <button
                onClick={() => setSelectedMemberIds(new Set())}
                className="text-slate-400 hover:text-white p-1"
                title="Clear selection"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 7. Members Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
        {isLoadingMembers ? (
          <div className="p-12 text-center text-xs text-slate-400 space-y-2">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto text-slate-300" />
            <p>Loading list members...</p>
          </div>
        ) : members.length === 0 ? (
          <div className="p-12 text-center text-xs text-slate-400 space-y-2">
            <Users className="w-8 h-8 text-slate-300 mx-auto" />
            <p className="font-medium text-slate-600">No members found in this list.</p>
            <p className="text-[11px] text-slate-400">
              {searchQuery ? "Try adjusting your search criteria." : "Add leads or contacts to this list to begin."}
            </p>
          </div>
        ) : (
          <Table>
            <TableHeader className="bg-slate-50/75 border-b border-slate-100">
              <TableRow>
                <TableHead className="w-10">
                  <button
                    onClick={handleToggleSelectAll}
                    className="p-1 rounded text-slate-400 hover:text-header"
                  >
                    {selectedMemberIds.size === members.length ? (
                      <CheckSquare className="w-4 h-4 text-agile-red" />
                    ) : selectedMemberIds.size > 0 ? (
                      <MinusSquare className="w-4 h-4 text-agile-red" />
                    ) : (
                      <Square className="w-4 h-4" />
                    )}
                  </button>
                </TableHead>
                <TableHead className="text-xs font-semibold text-slate-600">Lead / Contact</TableHead>
                <TableHead className="text-xs font-semibold text-slate-600">Email Address</TableHead>
                <TableHead className="text-xs font-semibold text-slate-600">Phone</TableHead>
                <TableHead className="text-xs font-semibold text-slate-600">Company</TableHead>
                <TableHead className="text-xs font-semibold text-slate-600">Job Title</TableHead>
                <TableHead className="text-xs font-semibold text-slate-600">Source</TableHead>
                <TableHead className="text-xs font-semibold text-slate-600">Added</TableHead>
                <TableHead className="text-xs font-semibold text-slate-600 text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((member) => {
                const isSelected = selectedMemberIds.has(member.id);

                return (
                  <TableRow
                    key={member.id}
                    className={`hover:bg-slate-50/50 transition-colors ${
                      isSelected ? "bg-rose-50/30" : ""
                    }`}
                  >
                    {/* Checkbox */}
                    <TableCell className="w-10 py-3">
                      <button
                        onClick={() => handleToggleSelectOne(member.id)}
                        className="p-1 rounded text-slate-400 hover:text-header"
                      >
                        {isSelected ? (
                          <CheckSquare className="w-4 h-4 text-agile-red" />
                        ) : (
                          <Square className="w-4 h-4" />
                        )}
                      </button>
                    </TableCell>

                    {/* Name */}
                    <TableCell className="py-3">
                      <button
                        onClick={() => handleLeadClick(member)}
                        className="text-left group font-medium text-xs text-header hover:text-agile-red transition-colors"
                      >
                        <span className="group-hover:underline">{member.full_name}</span>
                      </button>
                    </TableCell>

                    {/* Email with Validity Indicator */}
                    <TableCell className="py-3">
                      {member.has_valid_email ? (
                        <div className="flex items-center gap-1.5 text-xs text-slate-700">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                          <span className="font-mono text-[11px]">{member.email}</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 text-xs text-amber-700">
                          <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                          <Badge variant="warning" className="text-[10px] px-1.5 py-0 font-normal">
                            Unresolved
                          </Badge>
                        </div>
                      )}
                    </TableCell>

                    {/* Phone */}
                    <TableCell className="py-3 text-xs text-slate-500">
                      {member.phone ? (
                        <span className="font-mono text-[11px]">{member.phone}</span>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </TableCell>

                    {/* Company */}
                    <TableCell className="py-3 text-xs text-slate-600">
                      {member.company_name || <span className="text-slate-300">—</span>}
                    </TableCell>

                    {/* Job Title */}
                    <TableCell className="py-3 text-xs text-slate-500 truncate max-w-[150px]">
                      {member.job_title || <span className="text-slate-300">—</span>}
                    </TableCell>

                    {/* Source */}
                    <TableCell className="py-3">
                      <Badge variant="neutral" className="text-[10px] capitalize">
                        {member.source || "CRM"}
                      </Badge>
                    </TableCell>

                    {/* Added At */}
                    <TableCell className="py-3 text-xs text-slate-400">
                      {new Date(member.added_at).toLocaleDateString()}
                    </TableCell>

                    {/* Actions */}
                    <TableCell className="py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleLeadClick(member)}
                          className="p-1 rounded text-slate-400 hover:text-slate-600 hover:bg-slate-100"
                          title="View lead details"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => setMemberToRemove(member)}
                          className="p-1 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-50"
                          title="Remove from this list"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>

      {/* 8. Modal: Attach List to Campaign */}
      <Modal
        isOpen={isAttachModalOpen}
        onClose={() => setIsAttachModalOpen(false)}
        title={`Attach "${listDetail.name}" to Campaign`}
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600">
            Select an outreach campaign to associate with this list. Newly added eligible members will be synchronized to the campaign audience without resetting existing outreach steps.
          </p>

          {isLoadingCampaigns ? (
            <div className="py-6 text-center text-xs text-slate-400">
              <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-slate-300" />
              Loading campaigns...
            </div>
          ) : availableCampaigns.length === 0 ? (
            <div className="p-4 rounded-lg bg-slate-50 text-center text-xs text-slate-500">
              No campaigns available. Create a campaign first.
            </div>
          ) : (
            <div className="space-y-3">
              <label className="text-xs font-semibold text-slate-700">Campaign</label>
              <select
                value={selectedCampaignId}
                onChange={(e) => setSelectedCampaignId(e.target.value)}
                className="w-full text-xs p-2 rounded-lg border border-slate-200 bg-white"
              >
                {availableCampaigns.map((camp) => (
                  <option key={camp.id} value={camp.id}>
                    {camp.name} ({camp.type}) — {camp.status}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsAttachModalOpen(false)}
              className="text-xs"
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleAttachListToCampaign}
              disabled={isAttaching || availableCampaigns.length === 0}
              className="text-xs bg-agile-red hover:bg-agile-red/90 text-white"
            >
              {isAttaching ? "Attaching..." : "Attach and Sync"}
            </Button>
          </div>
        </div>
      </Modal>

      {/* 9. Modal: Add Selected Leads to Campaign */}
      <Modal
        isOpen={isAddSelectedModalOpen}
        onClose={() => setIsAddSelectedModalOpen(false)}
        title={`Add ${selectedMemberIds.size} Selected Lead(s) to Campaign`}
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600">
            Enroll the selected leads directly into an active or draft campaign. Unresolved leads without emails will be skipped.
          </p>

          {isLoadingCampaigns ? (
            <div className="py-6 text-center text-xs text-slate-400">
              <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-slate-300" />
              Loading campaigns...
            </div>
          ) : (
            <div className="space-y-3">
              <label className="text-xs font-semibold text-slate-700">Target Campaign</label>
              <select
                value={selectedEnrollCampaignId}
                onChange={(e) => setSelectedEnrollCampaignId(e.target.value)}
                className="w-full text-xs p-2 rounded-lg border border-slate-200 bg-white"
              >
                {availableCampaigns.map((camp) => (
                  <option key={camp.id} value={camp.id}>
                    {camp.name} ({camp.type}) — {camp.status}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="flex justify-between items-center pt-2 border-t border-slate-100">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsAddSelectedModalOpen(false)}
              className="text-xs"
            >
              Cancel
            </Button>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={async () => {
                  const camp = availableCampaigns.find((c) => c.id === selectedEnrollCampaignId);
                  await handleEnrollSelectedToCampaign();
                  if (camp) {
                    setDirectMailCampaign(camp);
                    setIsDirectMailModalOpen(true);
                  }
                }}
                disabled={isEnrollingSelected || availableCampaigns.length === 0}
                className="text-xs border-rose-300 text-rose-700 hover:bg-rose-50"
              >
                <Send className="w-3 h-3 mr-1 text-rose-600" />
                Enroll & Open Direct Mail
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleEnrollSelectedToCampaign}
                disabled={isEnrollingSelected || availableCampaigns.length === 0}
                className="text-xs bg-agile-red hover:bg-agile-red/90 text-white"
              >
                {isEnrollingSelected ? "Enrolling..." : "Enroll Selected"}
              </Button>
            </div>
          </div>
        </div>
      </Modal>

      {/* 10. Modal: Confirm Remove Single Member */}
      <Modal
        isOpen={Boolean(memberToRemove)}
        onClose={() => setMemberToRemove(null)}
        title="Remove Member from List"
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600 leading-relaxed">
            Are you sure you want to remove <strong>{memberToRemove?.full_name}</strong> from{" "}
            <strong>{listDetail.name}</strong>?
          </p>
          <div className="p-3 bg-slate-50 rounded-lg text-[11px] text-slate-500 space-y-1 border border-slate-100">
            <p>
              • The underlying CRM Contact and Lead records will <strong>not</strong> be deleted.
            </p>
            <p>
              • Any existing campaign enrollment or outreach history remains completely intact.
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setMemberToRemove(null)}
              className="text-xs"
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleConfirmRemoveMember}
              disabled={isRemovingMember}
              className="text-xs bg-rose-600 hover:bg-rose-700 text-white"
            >
              {isRemovingMember ? "Removing..." : "Remove Member"}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Direct Mail Preflight Modal */}
      {directMailCampaign && (
        <PhysicalMailPreflightModal
          isOpen={isDirectMailModalOpen}
          onClose={() => setIsDirectMailModalOpen(false)}
          campaignId={directMailCampaign.id}
          campaignName={directMailCampaign.name}
          recipientIds={
            selectedMemberIds.size > 0
              ? members
                  .filter((m) => selectedMemberIds.has(m.id))
                  .map((m) => m.lead_id)
                  .filter((id): id is string => Boolean(id))
              : undefined
          }
          onCompleted={() => {
            setSelectedMemberIds(new Set());
          }}
        />
      )}
    </div>
  );
};
