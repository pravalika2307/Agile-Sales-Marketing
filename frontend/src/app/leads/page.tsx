"use client";

import * as React from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
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
import { Pagination } from "@/components/ui/pagination";
import { Modal } from "@/components/ui/modal";
import { LeadDetailDrawer } from "@/components/leads/lead-detail-drawer";
import { LeadListsView } from "@/components/leads/lead-lists-view";
import { LeadListDetailView } from "@/components/leads/lead-list-detail-view";
import {
  CRMLead,
  CRMLeadFilterOptions,
  CRMLeadStatus,
  CRMLeadTemperature,
  bulkUpdateLeadStatus,
  createBackendLead,
  deleteLead,
  fetchCRMLeads,
  filterCRMLeads,
  importLeadsBatch,
  LeadImportRow,
  LeadImportResponse,
} from "@/services/crmLeadService";
import {
  fetchCampaigns,
  enrollContactsInCampaign,
  CampaignItem,
} from "@/services/campaignService";
import {
  parseCSV,
  autoDetectColumnMapping,
  ColumnMapping,
  DEFAULT_COLUMN_MAPPING,
} from "@/lib/csvParser";
import {
  ContactListItem,
  fetchContactLists,
  createContactList,
  updateContactList,
  deleteContactList,
  addMembersToList,
  syncSourceLists,
} from "@/services/contactListService";
import {
  Search,
  Plus,
  Download,
  Filter,
  RotateCcw,
  CheckSquare,
  Square,
  MinusSquare,
  Send,
  Eye,
  AlertCircle,
  CheckCircle2,
  FileSpreadsheet,
  FileCheck,
  UserCheck,
  Loader2,
  UploadCloud,
  Check,
  Trash2,
  X,
  RefreshCw,
  ArrowLeft,
  ListOrdered,
} from "lucide-react";

function LeadsPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  // Active view: List detail if listId is present in URL or state
  const urlListId = searchParams.get("listId");
  const [selectedListId, setSelectedListId] = React.useState<string | null>(urlListId);
  const [viewMode, setViewMode] = React.useState<"lists" | "all_leads">("lists");

  // Keep state synced with URL parameter
  React.useEffect(() => {
    setSelectedListId(urlListId);
    if (urlListId) {
      setViewMode("lists");
    }
  }, [urlListId]);

  // Lists state
  const [lists, setLists] = React.useState<ContactListItem[]>([]);
  const [isLoadingLists, setIsLoadingLists] = React.useState(true);
  const [isSyncingSources, setIsSyncingSources] = React.useState(false);

  // Global Leads table state (for "Browse All Leads" view)
  const [leadsList, setLeadsList] = React.useState<CRMLead[]>([]);
  const [isLoadingLeads, setIsLoadingLeads] = React.useState(false);
  const [hasError, setHasError] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const [searchQuery, setSearchQuery] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState("ALL");
  const [qualificationFilter, setQualificationFilter] = React.useState("ALL");
  const [temperatureFilter, setTemperatureFilter] = React.useState("ALL");
  const [sourceFilter, setSourceFilter] = React.useState("ALL");
  const [campaignFilter, setCampaignFilter] = React.useState("ALL");
  const [sortBy, setSortBy] = React.useState<"newest" | "score_desc">("newest");

  // Selection
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());

  // UI Drawer & Modals
  const [inspectedLead, setInspectedLead] = React.useState<CRMLead | null>(null);
  const [isCampaignModalOpen, setIsCampaignModalOpen] = React.useState(false);
  const [isAddLeadModalOpen, setIsAddLeadModalOpen] = React.useState(false);
  const [isCreatingLead, setIsCreatingLead] = React.useState(false);
  const [createLeadError, setCreateLeadError] = React.useState<string | null>(null);
  const [isImportModalOpen, setIsImportModalOpen] = React.useState(false);

  // Create List Modal State
  const [isCreateListModalOpen, setIsCreateListModalOpen] = React.useState(false);
  const [newListName, setNewListName] = React.useState("");
  const [newListDesc, setNewListDesc] = React.useState("");
  const [isCreatingList, setIsCreatingList] = React.useState(false);
  const [createListError, setCreateListError] = React.useState<string | null>(null);

  // Edit List Modal State
  const [listToEdit, setListToEdit] = React.useState<ContactListItem | null>(null);
  const [editListName, setEditListName] = React.useState("");
  const [editListDesc, setEditListDesc] = React.useState("");
  const [isUpdatingList, setIsUpdatingList] = React.useState(false);

  // Delete List Modal State
  const [listToDelete, setListToDelete] = React.useState<ContactListItem | null>(null);
  const [isDeletingList, setIsDeletingList] = React.useState(false);

  // Campaign Enrollment State
  const [availableCampaigns, setAvailableCampaigns] = React.useState<CampaignItem[]>([]);
  const [isLoadingCampaigns, setIsLoadingCampaigns] = React.useState(false);
  const [selectedCampaignId, setSelectedCampaignId] = React.useState<string>("");
  const [isEnrollingInCampaign, setIsEnrollingInCampaign] = React.useState(false);

  // CSV Import State
  const [csvFile, setCsvFile] = React.useState<File | null>(null);
  const [csvHeaders, setCsvHeaders] = React.useState<string[]>([]);
  const [csvRawRows, setCsvRawRows] = React.useState<string[][]>([]);
  const [columnMapping, setColumnMapping] = React.useState<ColumnMapping>(DEFAULT_COLUMN_MAPPING);
  const [isParsingCsv, setIsParsingCsv] = React.useState(false);
  const [csvParseError, setCsvParseError] = React.useState<string | null>(null);
  const [isImportingLeads, setIsImportingLeads] = React.useState(false);
  const [importResult, setImportResult] = React.useState<LeadImportResponse | null>(null);
  const [targetListNameForImport, setTargetListNameForImport] = React.useState("");

  // Pagination & Total State for All Leads
  const [currentPage, setCurrentPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(10);
  const [totalLeads, setTotalLeads] = React.useState(0);

  // New Lead Form State
  const [newLeadForm, setNewLeadForm] = React.useState({
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
    companyName: "",
    jobTitle: "",
    industry: "Financial Services",
    temperature: "UNASSESSED" as CRMLeadTemperature,
  });

  // Global Notification Banners
  const [successToast, setSuccessToast] = React.useState<string | null>(null);
  const [errorToast, setErrorToast] = React.useState<string | null>(null);

  // ── 1. Load Contact Lists ──────────────────────────────────────────────────
  const loadLists = React.useCallback(async () => {
    setIsLoadingLists(true);
    try {
      const res = await fetchContactLists({ limit: 100 });
      setLists(res.items);
    } catch (err: unknown) {
      console.error("Failed to load contact lists:", err);
    } finally {
      setIsLoadingLists(false);
    }
  }, []);

  React.useEffect(() => {
    loadLists();
  }, [loadLists]);

  // ── 2. Sync Source and Industry Lists Automatically or on Button ──────────
  const handleSyncSources = async () => {
    setIsSyncingSources(true);
    try {
      const res = await syncSourceLists();
      await loadLists();
      setSuccessToast(
        `Synchronized ${res.total_lists_synced} source & industry lists. (${res.total_new_memberships} newly added memberships)`
      );
    } catch (err: unknown) {
      setErrorToast(err instanceof Error ? err.message : "Failed to sync source lists.");
    } finally {
      setIsSyncingSources(false);
    }
  };

  // ── 3. Load Raw Leads (for "All Leads" view) ───────────────────────────────
  const loadLeads = React.useCallback(async (page: number = currentPage) => {
    setIsLoadingLeads(true);
    setHasError(false);
    setErrorMessage(null);
    try {
      const data = await fetchCRMLeads({
        page,
        pageSize,
        search: searchQuery.trim() || undefined,
        status: statusFilter !== "ALL" ? statusFilter : undefined,
        qualificationStatus: qualificationFilter !== "ALL" ? qualificationFilter : undefined,
        leadTemperature: temperatureFilter !== "ALL" ? temperatureFilter : undefined,
        source: sourceFilter !== "ALL" ? sourceFilter : undefined,
        excludeTest: true,
      });
      setLeadsList(data.items);
      setTotalLeads(data.total);
    } catch (err: unknown) {
      setHasError(true);
      setErrorMessage(err instanceof Error ? err.message : "Failed to load leads from server.");
    } finally {
      setIsLoadingLeads(false);
    }
  }, [pageSize, searchQuery, statusFilter, qualificationFilter, temperatureFilter, sourceFilter, currentPage]);

  React.useEffect(() => {
    if (viewMode === "all_leads") {
      loadLeads(currentPage);
    }
  }, [viewMode, loadLeads, currentPage]);

  // ── Navigation between Lists and Opened List ───────────────────────────────
  const handleOpenList = (listId: string) => {
    setSelectedListId(listId);
    router.push(`/leads?listId=${listId}`);
  };

  const handleBackToLists = () => {
    setSelectedListId(null);
    router.push("/leads");
    loadLists();
  };

  // ── Create List Handler ───────────────────────────────────────────────────
  const handleCreateList = async () => {
    const trimmed = newListName.trim();
    if (!trimmed) {
      setCreateListError("Please enter a list name.");
      return;
    }
    setIsCreatingList(true);
    setCreateListError(null);
    try {
      const created = await createContactList({
        name: trimmed,
        description: newListDesc.trim() || undefined,
        type: "static",
      });
      setSuccessToast(`Created list "${created.name}".`);
      setIsCreateListModalOpen(false);
      setNewListName("");
      setNewListDesc("");
      await loadLists();
      // Optionally open the newly created list
      handleOpenList(created.id);
    } catch (err: unknown) {
      setCreateListError(err instanceof Error ? err.message : "Failed to create list.");
    } finally {
      setIsCreatingList(false);
    }
  };

  // ── Edit List Handler ─────────────────────────────────────────────────────
  const handleOpenEditList = (list: ContactListItem) => {
    setListToEdit(list);
    setEditListName(list.name);
    setEditListDesc(list.description || "");
  };

  const handleUpdateList = async () => {
    if (!listToEdit) return;
    setIsUpdatingList(true);
    try {
      await updateContactList(listToEdit.id, {
        name: editListName.trim() || undefined,
        description: editListDesc.trim() || undefined,
      });
      setSuccessToast(`Updated list "${editListName}".`);
      setListToEdit(null);
      await loadLists();
    } catch (err: unknown) {
      setErrorToast(err instanceof Error ? err.message : "Failed to update list.");
    } finally {
      setIsUpdatingList(false);
    }
  };

  // ── Delete List Handler ───────────────────────────────────────────────────
  const handleDeleteList = async () => {
    if (!listToDelete) return;
    setIsDeletingList(true);
    try {
      await deleteContactList(listToDelete.id);
      setSuccessToast(`Deleted list "${listToDelete.name}".`);
      setListToDelete(null);
      await loadLists();
    } catch (err: unknown) {
      setErrorToast(err instanceof Error ? err.message : "Failed to delete list.");
    } finally {
      setIsDeletingList(false);
    }
  };

  // ── Create Lead Handler ───────────────────────────────────────────────────
  const handleCreateManualLead = async () => {
    if (!newLeadForm.firstName.trim() || !newLeadForm.companyName.trim()) {
      setCreateLeadError("First name and Company name are required.");
      return;
    }
    setIsCreatingLead(true);
    setCreateLeadError(null);
    try {
      const created = await createBackendLead(newLeadForm);
      setSuccessToast(`Lead "${created.fullName}" created successfully.`);
      setIsAddLeadModalOpen(false);
      setNewLeadForm({
        firstName: "",
        lastName: "",
        email: "",
        phone: "",
        companyName: "",
        jobTitle: "",
        industry: "Financial Services",
        temperature: "UNASSESSED",
      });
      // Re-sync sources to organize into "Manually Added Leads"
      await syncSourceLists();
      await loadLists();
    } catch (err: unknown) {
      setCreateLeadError(err instanceof Error ? err.message : "Failed to create lead.");
    } finally {
      setIsCreatingLead(false);
    }
  };

  // ── CSV Import Handlers ────────────────────────────────────────────────────
  const handleCsvFileSelected = async (file: File) => {
    setCsvFile(file);
    setIsParsingCsv(true);
    setCsvParseError(null);
    try {
      const text = await file.text();
      const parsed = parseCSV(text);
      if (parsed.headers.length === 0 || parsed.rows.length === 0) {
        throw new Error("The selected CSV file appears to be empty or invalid.");
      }
      setCsvHeaders(parsed.headers);
      setCsvRawRows(parsed.rows);
      const autoMap = autoDetectColumnMapping(parsed.headers);
      setColumnMapping(autoMap);
      setTargetListNameForImport(`CSV Import — ${new Date().toLocaleDateString()}`);
    } catch (err: unknown) {
      setCsvParseError(err instanceof Error ? err.message : "Failed to parse CSV file.");
    } finally {
      setIsParsingCsv(false);
    }
  };

  const mappedPreviewRows = React.useMemo(() => {
    return csvRawRows.map((row) => {
      const getVal = (colIdx: number) => (colIdx >= 0 && colIdx < row.length ? row[colIdx]?.trim() : "");
      return {
        first_name: getVal(columnMapping.first_name) || undefined,
        last_name: getVal(columnMapping.last_name) || undefined,
        email: getVal(columnMapping.email) || undefined,
        company_name: getVal(columnMapping.company_name) || undefined,
        phone: getVal(columnMapping.phone) || undefined,
        job_title: getVal(columnMapping.job_title) || undefined,
        industry: getVal(columnMapping.industry) || undefined,
        city: getVal(columnMapping.city) || undefined,
        country: getVal(columnMapping.country) || undefined,
      };
    });
  }, [csvRawRows, columnMapping]);

  const handleExecuteImport = async () => {
    if (mappedPreviewRows.length === 0) return;
    setIsImportingLeads(true);
    setCsvParseError(null);
    try {
      const result = await importLeadsBatch(mappedPreviewRows);
      setImportResult(result);

      // If imported leads exist, save to the designated list
      if (result.imported_ids && result.imported_ids.length > 0) {
        const listName = targetListNameForImport.trim() || `CSV Import — ${new Date().toLocaleDateString()}`;
        // Create new list for this import batch
        const list = await createContactList({
          name: listName,
          description: `Imported from CSV file "${csvFile?.name || "import"}" on ${new Date().toLocaleDateString()}.`,
          type: "source",
        });
        await addMembersToList(list.id, { leadIds: result.imported_ids });
      }

      await syncSourceLists();
      await loadLists();
      setSuccessToast(`Imported ${result.imported_count} leads successfully!`);
    } catch (err: unknown) {
      setCsvParseError(err instanceof Error ? err.message : "Failed to import leads batch.");
    } finally {
      setIsImportingLeads(false);
    }
  };

  const handleResetImportModal = () => {
    setCsvFile(null);
    setCsvHeaders([]);
    setCsvRawRows([]);
    setColumnMapping(DEFAULT_COLUMN_MAPPING);
    setCsvParseError(null);
    setImportResult(null);
    setIsImportModalOpen(false);
  };

  return (
    <AppShell onNewCampaignClick={() => setIsCampaignModalOpen(true)}>
      {/* Toast Notifications */}
      {successToast && (
        <div className="mb-4 p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center justify-between gap-2 max-w-7xl mx-auto">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{successToast}</span>
          </div>
          <button onClick={() => setSuccessToast(null)} className="text-emerald-500 hover:text-emerald-700">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {errorToast && (
        <div className="mb-4 p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between gap-2 max-w-7xl mx-auto">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{errorToast}</span>
          </div>
          <button onClick={() => setErrorToast(null)} className="text-rose-500 hover:text-rose-700">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* ── VIEW ROUTING: Opened List View vs. List-First Landing vs. All Leads ── */}
      {selectedListId ? (
        <LeadListDetailView
          listId={selectedListId}
          onBackToLists={handleBackToLists}
          onInspectLead={(lead) => setInspectedLead(lead)}
        />
      ) : viewMode === "all_leads" ? (
        /* Raw All-Leads View */
        <div className="space-y-4 max-w-7xl mx-auto pb-16">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setViewMode("lists")}
                className="text-xs inline-flex items-center gap-1.5"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Back to Lists</span>
              </Button>
              <h2 className="text-lg font-bold text-header">All Prospect Leads ({totalLeads})</h2>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsImportModalOpen(true)}
                className="text-xs inline-flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Import CSV</span>
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => setIsAddLeadModalOpen(true)}
                className="text-xs inline-flex items-center gap-1.5 bg-agile-red hover:bg-agile-red/90 text-white"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add Lead</span>
              </Button>
            </div>
          </div>

          {/* Search bar & filter pills */}
          <div className="flex items-center gap-2">
            <div className="relative w-64">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input
                placeholder="Search leads..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 h-8 text-xs"
              />
            </div>
            <Button variant="ghost" size="sm" onClick={() => loadLeads(1)} className="text-xs h-8">
              <RefreshCw className="w-3.5 h-3.5 text-slate-500 mr-1" />
              Refresh
            </Button>
          </div>

          {/* Leads Table */}
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
            <Table>
              <TableHeader className="bg-slate-50">
                <TableRow>
                  <TableHead className="text-xs font-semibold">Lead</TableHead>
                  <TableHead className="text-xs font-semibold">Email</TableHead>
                  <TableHead className="text-xs font-semibold">Phone</TableHead>
                  <TableHead className="text-xs font-semibold">Company</TableHead>
                  <TableHead className="text-xs font-semibold">Industry</TableHead>
                  <TableHead className="text-xs font-semibold">Source</TableHead>
                  <TableHead className="text-xs font-semibold text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoadingLeads ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8 text-xs text-slate-400">
                      Loading leads...
                    </TableCell>
                  </TableRow>
                ) : leadsList.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8 text-xs text-slate-400">
                      No leads found.
                    </TableCell>
                  </TableRow>
                ) : (
                  leadsList.map((lead) => (
                    <TableRow key={lead.id} className="hover:bg-slate-50/50">
                      <TableCell className="py-2.5">
                        <button
                          onClick={() => setInspectedLead(lead)}
                          className="text-left font-medium text-xs text-header hover:text-agile-red transition-colors"
                        >
                          {lead.fullName}
                        </button>
                      </TableCell>
                      <TableCell className="py-2.5 text-xs font-mono text-[11px] text-slate-600">
                        {lead.email}
                      </TableCell>
                      <TableCell className="py-2.5 text-xs text-slate-500 font-mono text-[11px]">
                        {lead.phone || "—"}
                      </TableCell>
                      <TableCell className="py-2.5 text-xs text-slate-700">
                        {lead.companyName}
                      </TableCell>
                      <TableCell className="py-2.5 text-xs text-slate-500">
                        {lead.industry || "—"}
                      </TableCell>
                      <TableCell className="py-2.5">
                        <Badge variant="neutral" className="text-[10px] capitalize">
                          {lead.source}
                        </Badge>
                      </TableCell>
                      <TableCell className="py-2.5 text-right">
                        <button
                          onClick={() => setInspectedLead(lead)}
                          className="p-1 rounded text-slate-400 hover:text-slate-600 hover:bg-slate-100"
                          title="Inspect Lead"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between pt-2">
            <span className="text-xs text-slate-500">
              Showing page {currentPage} of {Math.max(1, Math.ceil(totalLeads / pageSize))} ({totalLeads} total leads)
            </span>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                className="text-xs h-7"
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={currentPage >= Math.ceil(totalLeads / pageSize)}
                onClick={() => setCurrentPage((p) => p + 1)}
                className="text-xs h-7"
              >
                Next
              </Button>
            </div>
          </div>
        </div>
      ) : (
        /* Default: List-First Landing View */
        <LeadListsView
          lists={lists}
          isLoading={isLoadingLists}
          onOpenList={handleOpenList}
          onSyncSources={handleSyncSources}
          isSyncingSources={isSyncingSources}
          onCreateListOpen={() => setIsCreateListModalOpen(true)}
          onImportCsvOpen={() => setIsImportModalOpen(true)}
          onAddLeadOpen={() => setIsAddLeadModalOpen(true)}
          onBrowseAllLeads={() => setViewMode("all_leads")}
          onEditList={handleOpenEditList}
          onDeleteList={(list) => setListToDelete(list)}
        />
      )}

      {/* ── MODAL: Create Custom List ── */}
      <Modal
        isOpen={isCreateListModalOpen}
        onClose={() => setIsCreateListModalOpen(false)}
        title="Create New Lead List"
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600">
            Create a static list to organize prospects for campaigns, sales calls, or segmented outreach.
          </p>

          {createListError && (
            <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{createListError}</span>
            </div>
          )}

          <div className="space-y-3">
            <div>
              <label className="text-xs font-semibold text-slate-700">List Name *</label>
              <Input
                placeholder="e.g. Q4 FinTech Founders"
                value={newListName}
                onChange={(e) => setNewListName(e.target.value)}
                className="mt-1 h-8 text-xs"
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700">Description (Optional)</label>
              <Input
                placeholder="e.g. High intent prospects targeting enterprise sales"
                value={newListDesc}
                onChange={(e) => setNewListDesc(e.target.value)}
                className="mt-1 h-8 text-xs"
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
            <Button variant="outline" size="sm" onClick={() => setIsCreateListModalOpen(false)} className="text-xs">
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleCreateList}
              disabled={isCreatingList || !newListName.trim()}
              className="text-xs bg-agile-red hover:bg-agile-red/90 text-white"
            >
              {isCreatingList ? "Creating..." : "Create List"}
            </Button>
          </div>
        </div>
      </Modal>

      {/* ── MODAL: Edit List ── */}
      <Modal
        isOpen={Boolean(listToEdit)}
        onClose={() => setListToEdit(null)}
        title="Edit List Details"
      >
        <div className="space-y-4">
          <div className="space-y-3">
            <div>
              <label className="text-xs font-semibold text-slate-700">List Name</label>
              <Input
                value={editListName}
                onChange={(e) => setEditListName(e.target.value)}
                className="mt-1 h-8 text-xs"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700">Description</label>
              <Input
                value={editListDesc}
                onChange={(e) => setEditListDesc(e.target.value)}
                className="mt-1 h-8 text-xs"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
            <Button variant="outline" size="sm" onClick={() => setListToEdit(null)} className="text-xs">
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleUpdateList}
              disabled={isUpdatingList}
              className="text-xs bg-agile-red hover:bg-agile-red/90 text-white"
            >
              {isUpdatingList ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </div>
      </Modal>

      {/* ── MODAL: Confirm Delete List ── */}
      <Modal
        isOpen={Boolean(listToDelete)}
        onClose={() => setListToDelete(null)}
        title="Delete Lead List"
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600 leading-relaxed">
            Are you sure you want to delete the list <strong>"{listToDelete?.name}"</strong>?
          </p>
          <div className="p-3 bg-slate-50 rounded-lg text-[11px] text-slate-500 space-y-1 border border-slate-100">
            <p>• Underlying CRM Contacts, Leads, Companies, and Campaigns will <strong>never</strong> be deleted.</p>
            <p>• Historical outreach events and activity metrics remain completely intact.</p>
          </div>
          <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
            <Button variant="outline" size="sm" onClick={() => setListToDelete(null)} className="text-xs">
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleDeleteList}
              disabled={isDeletingList}
              className="text-xs bg-rose-600 hover:bg-rose-700 text-white"
            >
              {isDeletingList ? "Deleting..." : "Delete List"}
            </Button>
          </div>
        </div>
      </Modal>

      {/* ── MODAL: Add Lead Manually ── */}
      <Modal
        isOpen={isAddLeadModalOpen}
        onClose={() => setIsAddLeadModalOpen(false)}
        title="Add Prospect Lead"
      >
        <div className="space-y-3.5">
          {createLeadError && (
            <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs">
              {createLeadError}
            </div>
          )}

          <div className="grid grid-cols-2 gap-2.5">
            <div>
              <label className="text-xs font-semibold text-slate-700">First Name *</label>
              <Input
                placeholder="Jane"
                value={newLeadForm.firstName}
                onChange={(e) => setNewLeadForm({ ...newLeadForm, firstName: e.target.value })}
                className="mt-1 h-8 text-xs"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700">Last Name</label>
              <Input
                placeholder="Doe"
                value={newLeadForm.lastName}
                onChange={(e) => setNewLeadForm({ ...newLeadForm, lastName: e.target.value })}
                className="mt-1 h-8 text-xs"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            <div>
              <label className="text-xs font-semibold text-slate-700">Email</label>
              <Input
                placeholder="jane@company.com"
                value={newLeadForm.email}
                onChange={(e) => setNewLeadForm({ ...newLeadForm, email: e.target.value })}
                className="mt-1 h-8 text-xs"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700">Phone</label>
              <Input
                placeholder="+1 555-0100"
                value={newLeadForm.phone}
                onChange={(e) => setNewLeadForm({ ...newLeadForm, phone: e.target.value })}
                className="mt-1 h-8 text-xs"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            <div>
              <label className="text-xs font-semibold text-slate-700">Company Name *</label>
              <Input
                placeholder="Acme Corp"
                value={newLeadForm.companyName}
                onChange={(e) => setNewLeadForm({ ...newLeadForm, companyName: e.target.value })}
                className="mt-1 h-8 text-xs"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700">Job Title</label>
              <Input
                placeholder="VP of Growth"
                value={newLeadForm.jobTitle}
                onChange={(e) => setNewLeadForm({ ...newLeadForm, jobTitle: e.target.value })}
                className="mt-1 h-8 text-xs"
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700">Industry</label>
            <Input
              placeholder="e.g. Financial Services"
              value={newLeadForm.industry}
              onChange={(e) => setNewLeadForm({ ...newLeadForm, industry: e.target.value })}
              className="mt-1 h-8 text-xs"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
            <Button variant="outline" size="sm" onClick={() => setIsAddLeadModalOpen(false)} className="text-xs">
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleCreateManualLead}
              disabled={isCreatingLead || !newLeadForm.firstName.trim() || !newLeadForm.companyName.trim()}
              className="text-xs bg-agile-red hover:bg-agile-red/90 text-white"
            >
              {isCreatingLead ? "Creating..." : "Save Lead"}
            </Button>
          </div>
        </div>
      </Modal>

      {/* ── MODAL: CSV Import with Auto List Creation ── */}
      <Modal
        isOpen={isImportModalOpen}
        onClose={handleResetImportModal}
        title="Import Leads from CSV"
      >
        <div className="space-y-4">
          {!csvFile ? (
            <div className="border-2 border-dashed border-slate-200 rounded-xl p-8 text-center space-y-3 hover:border-agile-red/40 transition-colors">
              <UploadCloud className="w-10 h-10 text-slate-400 mx-auto" />
              <div className="space-y-1">
                <p className="text-xs font-semibold text-header">Choose a CSV file to upload</p>
                <p className="text-[11px] text-slate-400">Supports standard CSV exports with header rows</p>
              </div>
              <input
                type="file"
                accept=".csv"
                id="csv-file-input"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleCsvFileSelected(f);
                }}
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => document.getElementById("csv-file-input")?.click()}
                className="text-xs mt-2"
              >
                Browse CSV File
              </Button>
            </div>
          ) : importResult ? (
            <div className="space-y-4 py-4 text-center">
              <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
              <h3 className="text-sm font-bold text-header">Import Complete!</h3>
              <p className="text-xs text-slate-600">
                Successfully imported <strong>{importResult.imported_count}</strong> leads.
                {importResult.skipped_duplicate_count > 0 && (
                  <span> ({importResult.skipped_duplicate_count} skipped as duplicates)</span>
                )}
              </p>
              <Button variant="primary" size="sm" onClick={handleResetImportModal} className="text-xs">
                Done
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="p-3 bg-slate-50 rounded-lg text-xs flex items-center justify-between">
                <span className="font-medium text-slate-700">{csvFile.name}</span>
                <span className="text-slate-400 text-[11px]">{csvRawRows.length} rows found</span>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700">Organize in List</label>
                <Input
                  value={targetListNameForImport}
                  onChange={(e) => setTargetListNameForImport(e.target.value)}
                  placeholder="e.g. CSV Import — [Date]"
                  className="mt-1 h-8 text-xs"
                />
                <p className="text-[10px] text-slate-400 mt-1">
                  A named list will be created automatically to organize these imported leads.
                </p>
              </div>

              {csvParseError && (
                <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs">
                  {csvParseError}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <Button variant="outline" size="sm" onClick={handleResetImportModal} className="text-xs">
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleExecuteImport}
                  disabled={isImportingLeads}
                  className="text-xs bg-agile-red hover:bg-agile-red/90 text-white"
                >
                  {isImportingLeads ? "Importing..." : `Import ${csvRawRows.length} Leads`}
                </Button>
              </div>
            </div>
          )}
        </div>
      </Modal>

      {/* ── Lead Detail Drawer ── */}
      <LeadDetailDrawer
        lead={inspectedLead}
        isOpen={Boolean(inspectedLead)}
        onClose={() => setInspectedLead(null)}
        onLeadUpdated={() => {
          loadLists();
          if (viewMode === "all_leads") loadLeads(currentPage);
        }}
      />
    </AppShell>
  );
}

export default function LeadsPage() {
  return (
    <React.Suspense fallback={<div className="p-8 text-center text-xs text-slate-400">Loading Leads...</div>}>
      <LeadsPageContent />
    </React.Suspense>
  );
}
