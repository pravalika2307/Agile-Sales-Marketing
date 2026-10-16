"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
  ContactListItem,
  createContactList,
  deleteContactList,
  fetchContactLists,
  updateContactList,
} from "@/services/contactListService";
import {
  ListOrdered,
  Plus,
  Search,
  Users,
  Send,
  Calendar,
  AlertCircle,
  CheckCircle2,
  Trash2,
  Edit2,
  ExternalLink,
  RefreshCw,
  FolderOpen,
  X,
} from "lucide-react";

export default function ListsPage() {
  const router = useRouter();

  React.useEffect(() => {
    router.replace("/leads");
  }, [router]);

  // State
  const [lists, setLists] = React.useState<ContactListItem[]>([]);
  const [totalCount, setTotalCount] = React.useState(0);
  const [isLoading, setIsLoading] = React.useState(true);
  const [hasError, setHasError] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [searchQuery, setSearchQuery] = React.useState("");

  // Feedback notifications
  const [successBanner, setSuccessBanner] = React.useState<string | null>(null);
  const [errorBanner, setErrorBanner] = React.useState<string | null>(null);

  // Create List Modal State
  const [isCreateModalOpen, setIsCreateModalOpen] = React.useState(false);
  const [newListName, setNewListName] = React.useState("");
  const [newListDescription, setNewListDescription] = React.useState("");
  const [isCreating, setIsCreating] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);

  // Edit List Modal State
  const [listToEdit, setListToEdit] = React.useState<ContactListItem | null>(null);
  const [editName, setEditName] = React.useState("");
  const [editDescription, setEditDescription] = React.useState("");
  const [isUpdating, setIsUpdating] = React.useState(false);
  const [editError, setEditError] = React.useState<string | null>(null);

  // Delete List Modal State
  const [listToDelete, setListToDelete] = React.useState<ContactListItem | null>(null);
  const [isDeleting, setIsDeleting] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState<string | null>(null);

  // Load lists from backend
  const loadLists = React.useCallback(async (search?: string) => {
    setIsLoading(true);
    setHasError(false);
    setErrorMessage(null);
    try {
      const res = await fetchContactLists({ search: search ?? searchQuery });
      setLists(res.items);
      setTotalCount(res.total);
    } catch (err: unknown) {
      setHasError(true);
      setErrorMessage(err instanceof Error ? err.message : "Failed to load lists.");
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery]);

  React.useEffect(() => {
    loadLists();
  }, [loadLists]);

  // Aggregate stats
  const totalMembers = React.useMemo(() => {
    return lists.reduce((sum, item) => sum + item.member_count, 0);
  }, [lists]);

  const totalCampaignLinks = React.useMemo(() => {
    return lists.reduce((sum, item) => sum + item.campaigns_count, 0);
  }, [lists]);

  // Handle Search
  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadLists(searchQuery);
  };

  // Handle Create List
  const handleCreateList = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newListName.trim();
    if (!trimmed) {
      setCreateError("Please enter a list name.");
      return;
    }

    setIsCreating(true);
    setCreateError(null);
    try {
      const created = await createContactList({
        name: trimmed,
        description: newListDescription.trim() || undefined,
        type: "static",
      });
      setIsCreateModalOpen(false);
      setNewListName("");
      setNewListDescription("");
      setSuccessBanner(`List "${created.name}" created successfully.`);
      await loadLists();
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : "Failed to create list.");
    } finally {
      setIsCreating(false);
    }
  };

  // Handle Edit List
  const handleOpenEdit = (list: ContactListItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setListToEdit(list);
    setEditName(list.name);
    setEditDescription(list.description || "");
    setEditError(null);
  };

  const handleUpdateList = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!listToEdit) return;
    const trimmed = editName.trim();
    if (!trimmed) {
      setEditError("List name cannot be empty.");
      return;
    }

    setIsUpdating(true);
    setEditError(null);
    try {
      await updateContactList(listToEdit.id, {
        name: trimmed,
        description: editDescription.trim() || undefined,
      });
      setListToEdit(null);
      setSuccessBanner(`List updated successfully.`);
      await loadLists();
    } catch (err: unknown) {
      setEditError(err instanceof Error ? err.message : "Failed to update list.");
    } finally {
      setIsUpdating(false);
    }
  };

  // Handle Delete List
  const handleOpenDelete = (list: ContactListItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setListToDelete(list);
    setDeleteError(null);
  };

  const handleDeleteList = async () => {
    if (!listToDelete) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deleteContactList(listToDelete.id);
      setSuccessBanner(`List "${listToDelete.name}" deleted. Contacts and campaign records preserved.`);
      setListToDelete(null);
      await loadLists();
    } catch (err: unknown) {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete list.");
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <AppShell>
      <div className="space-y-6 max-w-7xl mx-auto pb-12">
        {/* 1. Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight text-header">
                Lists
              </h1>
              <Badge variant="neutral" className="text-xs">
                Static Lists
              </Badge>
            </div>
            <p className="text-sm text-slate-500 mt-1">
              Organize leads into reusable target audiences. Associate lists with campaigns and sync newly discovered members on demand.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => loadLists()}
              disabled={isLoading}
              className="text-xs inline-flex items-center gap-1.5"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-agile-red" : ""}`} />
              <span>Refresh</span>
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setCreateError(null);
                setNewListName("");
                setNewListDescription("");
                setIsCreateModalOpen(true);
              }}
              className="text-xs shadow-xs inline-flex items-center gap-1.5"
            >
              <Plus className="w-4 h-4" />
              <span>Create List</span>
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

        {/* 2. Top Metric Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card className="border-slate-200 shadow-xs">
            <CardContent className="p-5 flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Total Lists
                </p>
                <p className="text-2xl font-bold text-header mt-1">
                  {totalCount}
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Named audience segments
                </p>
              </div>
              <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-slate-600">
                <ListOrdered className="w-5 h-5 text-agile-red" />
              </div>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-xs">
            <CardContent className="p-5 flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Total Members
                </p>
                <p className="text-2xl font-bold text-header mt-1">
                  {totalMembers}
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Leads and contacts organized
                </p>
              </div>
              <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-slate-600">
                <Users className="w-5 h-5 text-blue-600" />
              </div>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-xs">
            <CardContent className="p-5 flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Associated Campaigns
                </p>
                <p className="text-2xl font-bold text-header mt-1">
                  {totalCampaignLinks}
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Outreach workflow connections
                </p>
              </div>
              <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-slate-600">
                <Send className="w-5 h-5 text-emerald-600" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* 3. Search Bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white p-3 rounded-xl border border-slate-200">
          <form onSubmit={handleSearchSubmit} className="relative w-full sm:w-96">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <Input
              type="text"
              placeholder="Search lists by name or description..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 text-xs h-9"
            />
          </form>
          <div className="flex items-center gap-2 self-end sm:self-auto text-xs text-slate-500">
            <span>Showing {lists.length} of {totalCount} lists</span>
          </div>
        </div>

        {/* 4. Main Lists Content */}
        {hasError ? (
          <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-8 text-center flex flex-col items-center justify-center space-y-3">
            <AlertCircle className="w-8 h-8 text-rose-500" />
            <div>
              <h3 className="text-sm font-semibold text-rose-900">
                Unable to load contact lists
              </h3>
              <p className="text-xs text-rose-700 mt-0.5">
                {errorMessage || "Please check your network connection and server status."}
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => loadLists()}
              className="text-xs bg-white"
            >
              Try again
            </Button>
          </div>
        ) : isLoading ? (
          <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-14 bg-slate-100/70 rounded-md animate-pulse" />
            ))}
          </div>
        ) : lists.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-200 bg-white p-12 text-center flex flex-col items-center justify-center space-y-3">
            <div className="w-12 h-12 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-400">
              <FolderOpen className="w-6 h-6 text-slate-400" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-header">
                {searchQuery ? "No matching lists found" : "No lists yet"}
              </h3>
              <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                {searchQuery
                  ? "Try searching with different keywords or clear your query."
                  : "Named lists allow you to save prospect segments and associate them with multiple outbound campaigns."}
              </p>
            </div>
            <div className="flex items-center gap-2 pt-2">
              {searchQuery ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setSearchQuery("");
                    loadLists("");
                  }}
                  className="text-xs"
                >
                  Clear Search
                </Button>
              ) : (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => setIsCreateModalOpen(true)}
                  className="text-xs shadow-xs inline-flex items-center gap-1.5"
                >
                  <Plus className="w-4 h-4" />
                  <span>Create Your First List</span>
                </Button>
              )}
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-xs">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-1/3">List Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Members</TableHead>
                  <TableHead>Campaigns</TableHead>
                  <TableHead>Created Date</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lists.map((list) => (
                  <TableRow
                    key={list.id}
                    onClick={() => router.push(`/lists/${list.id}`)}
                    className="cursor-pointer hover:bg-slate-50/80 transition-colors"
                  >
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-semibold text-header text-sm flex items-center gap-1.5">
                          {list.name}
                        </span>
                        {list.description && (
                          <span className="text-xs text-slate-500 truncate max-w-md mt-0.5">
                            {list.description}
                          </span>
                        )}
                      </div>
                    </TableCell>

                    <TableCell>
                      <Badge variant="neutral" className="capitalize text-[11px]">
                        {list.type}
                      </Badge>
                    </TableCell>

                    <TableCell>
                      <div className="flex items-center gap-1.5 text-xs text-slate-700 font-medium">
                        <Users className="w-3.5 h-3.5 text-slate-400" />
                        <span>{list.member_count}</span>
                      </div>
                    </TableCell>

                    <TableCell>
                      <div className="flex items-center gap-1.5 text-xs text-slate-700 font-medium">
                        <Send className="w-3.5 h-3.5 text-slate-400" />
                        <span>{list.campaigns_count}</span>
                      </div>
                    </TableCell>

                    <TableCell>
                      <div className="flex items-center gap-1.5 text-xs text-slate-500">
                        <Calendar className="w-3.5 h-3.5 text-slate-400" />
                        <span>{new Date(list.created_at).toLocaleDateString()}</span>
                      </div>
                    </TableCell>

                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => router.push(`/lists/${list.id}`)}
                          className="h-8 px-2 text-xs text-slate-600 hover:text-header"
                          title="Open list details"
                        >
                          <ExternalLink className="w-3.5 h-3.5 mr-1" />
                          <span>View</span>
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => handleOpenEdit(list, e)}
                          className="h-8 w-8 p-0 text-slate-500 hover:text-slate-800"
                          title="Edit name and description"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => handleOpenDelete(list, e)}
                          className="h-8 w-8 p-0 text-slate-400 hover:text-rose-600 hover:bg-rose-50"
                          title="Delete list"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {/* 5. Create List Modal */}
        <Modal
          isOpen={isCreateModalOpen}
          onClose={() => setIsCreateModalOpen(false)}
          title="Create New List"
          description="Create a named static list to organize prospects and contacts."
        >
          <form onSubmit={handleCreateList} className="space-y-4 pt-2">
            {createError && (
              <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-rose-500" />
                <span>{createError}</span>
              </div>
            )}

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 block">
                List Name <span className="text-rose-500">*</span>
              </label>
              <Input
                type="text"
                placeholder="e.g. Q4 FinTech VPs, Enterprise Healthcare"
                value={newListName}
                onChange={(e) => setNewListName(e.target.value)}
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
                placeholder="Context or notes about this lead audience..."
                value={newListDescription}
                onChange={(e) => setNewListDescription(e.target.value)}
                maxLength={2000}
                className="w-full text-xs rounded-md border border-slate-200 p-2.5 focus:outline-none focus:ring-1 focus:ring-agile-red"
              />
            </div>

            <div className="p-3 rounded-lg bg-slate-50 border border-slate-100 text-[11px] text-slate-500">
              <p className="font-semibold text-slate-700 mb-0.5">Static List Rules</p>
              <ul className="list-disc pl-4 space-y-0.5">
                <li>Membership is managed deliberately by adding or removing leads.</li>
                <li>Leads without email addresses are allowed (marked as &quot;Unresolved Email&quot;).</li>
                <li>Associating a list with a campaign never automatically sends emails or makes calls.</li>
              </ul>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsCreateModalOpen(false)}
                disabled={isCreating}
                className="text-xs"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="sm"
                disabled={isCreating || !newListName.trim()}
                className="text-xs shadow-xs"
              >
                {isCreating ? "Creating..." : "Create List"}
              </Button>
            </div>
          </form>
        </Modal>

        {/* 6. Edit List Modal */}
        <Modal
          isOpen={!!listToEdit}
          onClose={() => setListToEdit(null)}
          title="Edit List"
          description="Update the name and description of this contact list."
        >
          <form onSubmit={handleUpdateList} className="space-y-4 pt-2">
            {editError && (
              <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-rose-500" />
                <span>{editError}</span>
              </div>
            )}

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
                onClick={() => setListToEdit(null)}
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
          isOpen={!!listToDelete}
          onClose={() => setListToDelete(null)}
          title="Delete Contact List"
          description={`Are you sure you want to delete "${listToDelete?.name}"?`}
        >
          <div className="space-y-4 pt-2">
            {deleteError && (
              <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-rose-500" />
                <span>{deleteError}</span>
              </div>
            )}

            <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs space-y-1.5">
              <p className="font-semibold flex items-center gap-1.5 text-amber-900">
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
                <span>Data Preservation Invariant</span>
              </p>
              <p className="text-[11px] leading-relaxed">
                Deleting this list removes the list and its membership links only. It will <strong>NEVER</strong> delete your CRM contacts, leads, companies, campaign enrollments, or historical outreach activity records.
              </p>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setListToDelete(null)}
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
      </div>
    </AppShell>
  );
}
