"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/app-shell";
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
  ContactListDetail,
  ContactListMember,
  deleteContactList,
  fetchContactListMembers,
  getContactList,
  removeMemberFromList,
  syncCampaignList,
  updateContactList,
} from "@/services/contactListService";
import {
  ArrowLeft,
  Users,
  Mail,
  AlertTriangle,
  Send,
  Calendar,
  Search,
  Trash2,
  Edit2,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  ShieldAlert,
  X,
  UserX,
  Phone,
  Building2,
  Layers,
} from "lucide-react";

export default function ListDetailPage() {
  const params = useParams();
  const router = useRouter();
  const listId = params.id as string;

  React.useEffect(() => {
    if (listId) {
      router.replace(`/leads?listId=${listId}`);
    }
  }, [listId, router]);

  // Detail State
  const [listDetail, setListDetail] = React.useState<ContactListDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = React.useState(true);
  const [detailError, setDetailError] = React.useState<string | null>(null);

  // Members State
  const [members, setMembers] = React.useState<ContactListMember[]>([]);
  const [membersTotal, setMembersTotal] = React.useState(0);
  const [isLoadingMembers, setIsLoadingMembers] = React.useState(true);
  const [memberSearchQuery, setMemberSearchQuery] = React.useState("");
  const [emailFilter, setEmailFilter] = React.useState<"ALL" | "VALID" | "UNRESOLVED">("ALL");

  // Notifications
  const [successBanner, setSuccessBanner] = React.useState<string | null>(null);
  const [errorBanner, setErrorBanner] = React.useState<string | null>(null);

  // Edit List Modal
  const [isEditModalOpen, setIsEditModalOpen] = React.useState(false);
  const [editName, setEditName] = React.useState("");
  const [editDescription, setEditDescription] = React.useState("");
  const [isUpdating, setIsUpdating] = React.useState(false);

  // Delete List Modal
  const [isDeleteModalOpen, setIsDeleteModalOpen] = React.useState(false);
  const [isDeleting, setIsDeleting] = React.useState(false);

  // Remove Member Modal
  const [memberToRemove, setMemberToRemove] = React.useState<ContactListMember | null>(null);
  const [isRemovingMember, setIsRemovingMember] = React.useState(false);

  // Syncing State for Campaign Links
  const [syncingCampaignId, setSyncingCampaignId] = React.useState<string | null>(null);

  // Load List Detail
  const loadDetail = React.useCallback(async () => {
    if (!listId) return;
    setIsLoadingDetail(true);
    setDetailError(null);
    try {
      const data = await getContactList(listId);
      setListDetail(data);
      setEditName(data.name);
      setEditDescription(data.description || "");
    } catch (err: unknown) {
      setDetailError(err instanceof Error ? err.message : "Failed to load list details.");
    } finally {
      setIsLoadingDetail(false);
    }
  }, [listId]);

  // Load Members
  const loadMembers = React.useCallback(async () => {
    if (!listId) return;
    setIsLoadingMembers(true);
    try {
      const hasUnresolved =
        emailFilter === "UNRESOLVED" ? true : emailFilter === "VALID" ? false : undefined;
      const res = await fetchContactListMembers(listId, {
        search: memberSearchQuery || undefined,
        has_unresolved_email: hasUnresolved,
      });
      setMembers(res.items);
      setMembersTotal(res.total);
    } catch (err: unknown) {
      console.error("Error loading members:", err);
    } finally {
      setIsLoadingMembers(false);
    }
  }, [listId, memberSearchQuery, emailFilter]);

  React.useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  React.useEffect(() => {
    loadMembers();
  }, [loadMembers]);

  // Handle Update List
  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editName.trim()) return;
    setIsUpdating(true);
    try {
      await updateContactList(listId, {
        name: editName.trim(),
        description: editDescription.trim() || undefined,
      });
      setIsEditModalOpen(false);
      setSuccessBanner("List details updated successfully.");
      await loadDetail();
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Failed to update list.");
    } finally {
      setIsUpdating(false);
    }
  };

  // Handle Delete List
  const handleDeleteList = async () => {
    setIsDeleting(true);
    try {
      await deleteContactList(listId);
      router.push("/lists");
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Failed to delete list.");
      setIsDeleting(false);
    }
  };

  // Handle Remove Member
  const handleRemoveMember = async () => {
    if (!memberToRemove) return;
    setIsRemovingMember(true);
    try {
      await removeMemberFromList(listId, memberToRemove.id);
      setSuccessBanner(`Removed "${memberToRemove.full_name}" from this list. CRM contact was not deleted.`);
      setMemberToRemove(null);
      await Promise.all([loadDetail(), loadMembers()]);
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Failed to remove member.");
    } finally {
      setIsRemovingMember(false);
    }
  };

  // Handle Campaign Sync
  const handleSyncCampaign = async (campaignId: string) => {
    setSyncingCampaignId(campaignId);
    try {
      const res = await syncCampaignList(campaignId, listId);
      const msg = `Sync complete: ${res.newly_enrolled_count} newly enrolled, ${res.already_enrolled_count} already enrolled.${
        res.unresolved_email_count > 0 ? ` ${res.unresolved_email_count} skipped (unresolved email).` : ""
      }${res.suppressed_opt_out_count > 0 ? ` ${res.suppressed_opt_out_count} skipped (opted out).` : ""}`;
      setSuccessBanner(msg);
      await loadDetail();
    } catch (err: unknown) {
      setErrorBanner(err instanceof Error ? err.message : "Failed to sync campaign.");
    } finally {
      setSyncingCampaignId(null);
    }
  };

  if (isLoadingDetail && !listDetail) {
    return (
      <AppShell>
        <div className="space-y-4 max-w-7xl mx-auto p-6 animate-pulse">
          <div className="h-6 w-32 bg-slate-200 rounded" />
          <div className="h-10 w-96 bg-slate-200 rounded" />
          <div className="grid grid-cols-4 gap-4 pt-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-24 bg-slate-100 rounded-lg" />
            ))}
          </div>
        </div>
      </AppShell>
    );
  }

  if (detailError || !listDetail) {
    return (
      <AppShell>
        <div className="max-w-2xl mx-auto py-12 text-center space-y-4">
          <AlertCircle className="w-12 h-12 text-rose-500 mx-auto" />
          <h2 className="text-lg font-bold text-header">List Not Found</h2>
          <p className="text-sm text-slate-500">
            {detailError || "This contact list does not exist or you do not have permission to view it."}
          </p>
          <Link href="/lists">
            <Button variant="secondary" size="sm" className="text-xs">
              Back to Lists
            </Button>
          </Link>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="space-y-6 max-w-7xl mx-auto pb-16">
        {/* Navigation Breadcrumb */}
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Link
            href="/lists"
            className="hover:text-header transition-colors inline-flex items-center gap-1 font-medium"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Lists</span>
          </Link>
          <span>/</span>
          <span className="text-slate-800 font-semibold">{listDetail.name}</span>
        </div>

        {/* 1. List Header & Action Toolbar */}
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

          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                loadDetail();
                loadMembers();
              }}
              className="text-xs inline-flex items-center gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5 text-slate-500" />
              <span>Refresh</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsEditModalOpen(true)}
              className="text-xs inline-flex items-center gap-1.5"
            >
              <Edit2 className="w-3.5 h-3.5 text-slate-500" />
              <span>Edit List</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsDeleteModalOpen(true)}
              className="text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50 border-rose-200"
            >
              <Trash2 className="w-3.5 h-3.5 mr-1" />
              <span>Delete</span>
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

        {/* 2. Unresolved Email Protective Warning Banner */}
        {listDetail.unresolved_email_count > 0 && (
          <div className="p-3.5 rounded-xl bg-amber-50/70 border border-amber-200 text-amber-900 text-xs flex items-start gap-3">
            <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <p className="font-semibold">
                Unresolved Email Warning ({listDetail.unresolved_email_count} lead{listDetail.unresolved_email_count > 1 ? "s" : ""})
              </p>
              <p className="text-[11px] text-amber-800 leading-relaxed">
                Leads without valid email addresses can be organized in this list, but they <strong>will not be enrolled in automated email outreach</strong> when synchronizing with campaigns until an email address is provided and verified.
              </p>
            </div>
          </div>
        )}

        {/* 3. Stat Cards Breakdown */}
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
                Campaign outreach eligible
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
                Outbound workflows linked
              </p>
            </CardContent>
          </Card>
        </div>

        {/* 4. Associated Campaigns Section */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4 shadow-xs">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-header flex items-center gap-2">
                <Send className="w-4 h-4 text-agile-red" />
                <span>Associated Campaigns ({listDetail.associated_campaigns.length})</span>
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Campaigns configured to receive audience members from this list.
              </p>
            </div>
            <Link href="/campaigns">
              <Button variant="ghost" size="sm" className="text-xs text-slate-600">
                <span>View All Campaigns</span>
                <ExternalLink className="w-3 h-3 ml-1" />
              </Button>
            </Link>
          </div>

          {listDetail.associated_campaigns.length === 0 ? (
            <div className="p-6 rounded-lg border border-dashed border-slate-200 text-center space-y-1 bg-slate-50/50">
              <p className="text-xs font-medium text-slate-600">
                This list is not yet associated with any campaigns.
              </p>
              <p className="text-[11px] text-slate-400">
                Open any campaign in the Campaigns section and attach this list to use it as an audience source.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {listDetail.associated_campaigns.map((camp) => (
                <div
                  key={camp.id}
                  className="p-3.5 rounded-lg border border-slate-200/90 bg-white hover:border-slate-300 transition-colors space-y-2.5 flex flex-col justify-between"
                >
                  <div className="space-y-1">
                    <div className="flex items-center justify-between gap-1">
                      <span className="font-semibold text-xs text-header truncate">
                        {camp.name}
                      </span>
                      <Badge variant="neutral" className="capitalize text-[10px] shrink-0">
                        {camp.status}
                      </Badge>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Linked {new Date(camp.associated_at).toLocaleDateString()}
                    </p>
                  </div>

                  <div className="pt-2 border-t border-slate-100 flex items-center justify-between gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={syncingCampaignId === camp.id}
                      onClick={() => handleSyncCampaign(camp.id)}
                      className="text-xs h-7 px-2 inline-flex items-center gap-1 text-agile-red hover:bg-agile-lightorange border-agile-red/20"
                      title="Sync newly added list members into this campaign"
                    >
                      <RefreshCw className={`w-3 h-3 ${syncingCampaignId === camp.id ? "animate-spin" : ""}`} />
                      <span>{syncingCampaignId === camp.id ? "Syncing..." : "Sync New Members"}</span>
                    </Button>

                    <Link href={`/campaigns`}>
                      <Button variant="ghost" size="sm" className="text-xs h-7 px-2 text-slate-500">
                        <span>Open</span>
                      </Button>
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 5. Members Section */}
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h2 className="text-base font-bold text-header flex items-center gap-2">
                <Users className="w-4 h-4 text-header" />
                <span>List Members ({membersTotal})</span>
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Review, filter, and manage prospect leads and contacts in this list.
              </p>
            </div>

            {/* Email Status Filter Pills */}
            <div className="flex items-center gap-1.5 text-xs">
              <button
                type="button"
                onClick={() => setEmailFilter("ALL")}
                className={`px-2.5 py-1 rounded-md font-medium text-xs transition-colors border ${
                  emailFilter === "ALL"
                    ? "bg-header text-white border-header"
                    : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
                }`}
              >
                All ({listDetail.member_count})
              </button>
              <button
                type="button"
                onClick={() => setEmailFilter("VALID")}
                className={`px-2.5 py-1 rounded-md font-medium text-xs transition-colors border ${
                  emailFilter === "VALID"
                    ? "bg-emerald-600 text-white border-emerald-600 font-semibold"
                    : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
                }`}
              >
                Valid Email ({listDetail.valid_email_count})
              </button>
              <button
                type="button"
                onClick={() => setEmailFilter("UNRESOLVED")}
                className={`px-2.5 py-1 rounded-md font-medium text-xs transition-colors border ${
                  emailFilter === "UNRESOLVED"
                    ? "bg-amber-600 text-white border-amber-600 font-semibold"
                    : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
                }`}
              >
                Unresolved Email ({listDetail.unresolved_email_count})
              </button>
            </div>
          </div>

          {/* Search Bar for Members */}
          <div className="relative w-full sm:w-96">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <Input
              type="text"
              placeholder="Search members by name, company, or email..."
              value={memberSearchQuery}
              onChange={(e) => setMemberSearchQuery(e.target.value)}
              className="pl-9 text-xs h-9"
            />
          </div>

          {/* Members Table */}
          {isLoadingMembers ? (
            <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-12 bg-slate-100/70 rounded-md animate-pulse" />
              ))}
            </div>
          ) : members.length === 0 ? (
            <div className="rounded-xl border border-slate-200 bg-white p-12 text-center flex flex-col items-center justify-center space-y-2">
              <Users className="w-10 h-10 text-slate-300" />
              <h3 className="text-sm font-semibold text-header">No members found</h3>
              <p className="text-xs text-slate-500 max-w-sm">
                {memberSearchQuery || emailFilter !== "ALL"
                  ? "No members match your current search and email status filters."
                  : "This list has no members yet. Add leads from the Leads page using 'Save to List'."}
              </p>
              {memberSearchQuery && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setMemberSearchQuery("")}
                  className="text-xs mt-2"
                >
                  Clear Search
                </Button>
              )}
            </div>
          ) : (
            <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-xs">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Prospect</TableHead>
                    <TableHead>Company</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Phone</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead>Added Date</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {members.map((m) => (
                    <TableRow key={m.id} className="hover:bg-slate-50/70 transition-colors">
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="font-semibold text-xs text-header">
                            {m.full_name}
                          </span>
                          {m.job_title && (
                            <span className="text-[11px] text-slate-400">
                              {m.job_title}
                            </span>
                          )}
                        </div>
                      </TableCell>

                      <TableCell>
                        <div className="flex items-center gap-1.5 text-xs text-slate-700">
                          <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                          <span>{m.company_name || "—"}</span>
                        </div>
                      </TableCell>

                      <TableCell>
                        {m.has_valid_email ? (
                          <div className="flex items-center gap-1.5 text-xs text-slate-700 font-mono">
                            <Mail className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                            <span>{m.email}</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5">
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-800 border border-amber-200 inline-flex items-center gap-1">
                              <AlertTriangle className="w-3 h-3 text-amber-600" />
                              <span>Unresolved Email</span>
                            </span>
                            {m.email && (
                              <span className="text-[11px] text-slate-400 font-mono">
                                ({m.email})
                              </span>
                            )}
                          </div>
                        )}
                      </TableCell>

                      <TableCell>
                        <div className="text-xs text-slate-600 font-mono">
                          {m.phone || "—"}
                        </div>
                      </TableCell>

                      <TableCell>
                        <Badge variant="neutral" className="text-[10px] uppercase tracking-wider">
                          {m.source || "lead"}
                        </Badge>
                      </TableCell>

                      <TableCell>
                        <span className="text-xs text-slate-400">
                          {new Date(m.added_at).toLocaleDateString()}
                        </span>
                      </TableCell>

                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setMemberToRemove(m)}
                          className="h-7 w-7 p-0 text-slate-400 hover:text-rose-600 hover:bg-rose-50"
                          title="Remove from list"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>

        {/* 6. Edit Modal */}
        <Modal
          isOpen={isEditModalOpen}
          onClose={() => setIsEditModalOpen(false)}
          title="Edit List Details"
          description="Update the name and description of this contact list."
        >
          <form onSubmit={handleUpdate} className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 block">
                List Name <span className="text-rose-500">*</span>
              </label>
              <Input
                type="text"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                required
                maxLength={255}
                className="text-xs h-9"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 block">
                Description (Optional)
              </label>
              <textarea
                rows={3}
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                maxLength={2000}
                className="w-full text-xs rounded-md border border-slate-200 p-2.5 focus:outline-none focus:ring-1 focus:ring-agile-red"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsEditModalOpen(false)}
                disabled={isUpdating}
                className="text-xs"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="sm"
                disabled={isUpdating || !editName.trim()}
                className="text-xs shadow-xs"
              >
                {isUpdating ? "Saving..." : "Save Changes"}
              </Button>
            </div>
          </form>
        </Modal>

        {/* 7. Delete List Modal */}
        <Modal
          isOpen={isDeleteModalOpen}
          onClose={() => setIsDeleteModalOpen(false)}
          title="Delete Contact List"
          description={`Are you sure you want to delete "${listDetail.name}"?`}
        >
          <div className="space-y-4 pt-2">
            <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs space-y-1.5">
              <p className="font-semibold flex items-center gap-1.5 text-amber-900">
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
                <span>Underlying CRM Records Preserved</span>
              </p>
              <p className="text-[11px] leading-relaxed">
                Deleting this list removes the list definition and membership. It will <strong>NEVER</strong> delete your CRM contacts, leads, companies, campaign enrollments, or historical outreach activity.
              </p>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsDeleteModalOpen(false)}
                disabled={isDeleting}
                className="text-xs"
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                onClick={handleDeleteList}
                disabled={isDeleting}
                className="text-xs"
              >
                {isDeleting ? "Deleting..." : "Delete List"}
              </Button>
            </div>
          </div>
        </Modal>

        {/* 8. Remove Member Modal */}
        <Modal
          isOpen={!!memberToRemove}
          onClose={() => setMemberToRemove(null)}
          title="Remove Member from List"
          description={`Remove "${memberToRemove?.full_name}" from this list?`}
        >
          <div className="space-y-4 pt-2">
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-slate-700 text-xs space-y-1">
              <p className="font-semibold text-slate-800">
                List Membership Independence Rule
              </p>
              <p className="text-[11px] text-slate-500 leading-relaxed">
                Removing this member only removes them from this list. It does not delete the CRM lead or contact, and will not unenroll them from any currently running campaigns.
              </p>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setMemberToRemove(null)}
                disabled={isRemovingMember}
                className="text-xs"
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                onClick={handleRemoveMember}
                disabled={isRemovingMember}
                className="text-xs"
              >
                {isRemovingMember ? "Removing..." : "Remove Member"}
              </Button>
            </div>
          </div>
        </Modal>
      </div>
    </AppShell>
  );
}
