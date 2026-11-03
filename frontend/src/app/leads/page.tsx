"use client";
import { PhysicalMailPreflightModal } from "@/components/campaigns/physical-mail-preflight-modal";

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
  TableLoadingRow,
  TableEmptyRow,
} from "@/components/ui/table";
import { Pagination } from "@/components/ui/pagination";
import { Modal, ConfirmModal } from "@/components/ui/modal";
import { FormSection } from "@/components/ui/form-section";
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
  fetchCRMLeadById,
  fetchCRMLeads,
  filterCRMLeads,
  importLeadsBatch,
  LeadImportRow,
  LeadImportResponse,
  updateBackendLead,
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
  AlertTriangle,
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
  Edit,
} from "lucide-react";
import { useAppMode } from "@/contexts/AppModeContext";

function LeadsPageContent() {
  const { mode } = useAppMode();
  const isMarketing = mode === "marketing";

  const searchParams = useSearchParams();
  const router = useRouter();

  // Active view: List detail if listId is present in URL or state
  const urlListId = searchParams.get("listId");
  const urlLeadId = searchParams.get("leadId");
  const [selectedListId, setSelectedListId] = React.useState<string | null>(urlListId);
  const [viewMode, setViewMode] = React.useState<"lists" | "all_leads">("lists");

  // Keep state synced with URL parameter
  React.useEffect(() => {
    setSelectedListId(urlListId);
    if (urlListId) {
      setViewMode("lists");
    }
  }, [urlListId]);

  // Open lead detail drawer if leadId is passed in URL
  React.useEffect(() => {
    if (urlLeadId) {
      setViewMode("all_leads");
      fetchCRMLeadById(urlLeadId)
        .then((lead) => {
          if (lead) {
            setInspectedLead(lead);
          }
        })
        .catch((err) => {
          console.error("Failed to load lead by ID from URL parameter:", err);
        });
    }
  }, [urlLeadId]);

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
  const [isDirectMailModalOpen, setIsDirectMailModalOpen] = React.useState(false);
  const [directMailCampaign, setDirectMailCampaign] = React.useState<CampaignItem | null>(null);

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
  const [newListNameError, setNewListNameError] = React.useState<string | null>(null);

  // Field-level errors for manual lead creation
  const [firstNameError, setFirstNameError] = React.useState<string | null>(null);
  const [companyNameError, setCompanyNameError] = React.useState<string | null>(null);

  // Edit Lead Modal State
  const [isEditLeadModalOpen, setIsEditLeadModalOpen] = React.useState(false);
  const [leadToEdit, setLeadToEdit] = React.useState<CRMLead | null>(null);
  const [editLeadForm, setEditLeadForm] = React.useState({
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
    companyName: "",
    companyDomain: "",
    jobTitle: "",
    industry: "",
    companySize: "",
    city: "",
    state: "",
    country: "",
    linkedinProfileUrl: "",
    temperature: "UNASSESSED" as CRMLeadTemperature,
    qualificationStatus: "new" as "new" | "qualified" | "disqualified" | "reviewed",
    qualificationReason: "",
  });
  const [isSavingLead, setIsSavingLead] = React.useState(false);
  const [editLeadError, setEditLeadError] = React.useState<string | null>(null);

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

  // Selection and Direct Mail Handlers
  const handleToggleSelectAll = () => {
    if (selectedIds.size === leadsList.length && leadsList.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(leadsList.map((l) => l.id)));
    }
  };

  const handleToggleSelectLead = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleOpenEnrollModal = async () => {
    setIsCampaignModalOpen(true);
    setIsLoadingCampaigns(true);
    try {
      const res = await fetchCampaigns();
      setAvailableCampaigns(res.campaigns);
      if (res.campaigns.length > 0) {
        setSelectedCampaignId(res.campaigns[0].id);
      }
    } catch (err) {
      console.error("Failed to load campaigns:", err);
    } finally {
      setIsLoadingCampaigns(false);
    }
  };

  const handleEnrollSelectedLeads = async (launchDirectMail: boolean = false) => {
    if (!selectedCampaignId || selectedIds.size === 0) return;
    setIsEnrollingInCampaign(true);
    try {
      await enrollContactsInCampaign(selectedCampaignId, Array.from(selectedIds));
      setSuccessToast(`Successfully enrolled ${selectedIds.size} lead(s) into campaign.`);
      setIsCampaignModalOpen(false);
      if (launchDirectMail) {
        const camp = availableCampaigns.find((c) => c.id === selectedCampaignId) || null;
        setDirectMailCampaign(camp);
        setIsDirectMailModalOpen(true);
      }
    } catch (err: any) {
      console.error("Enrollment error:", err);
      setCreateLeadError(err.message || "Failed to enroll leads in campaign.");
    } finally {
      setIsEnrollingInCampaign(false);
    }
  };

  const handleLaunchDirectMailFromSelection = async () => {
    if (selectedIds.size === 0) return;
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
        setIsCampaignModalOpen(true);
      }
    } catch (err) {
      console.error("Error launching direct mail:", err);
    } finally {
      setIsLoadingCampaigns(false);
    }
  };

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
    linkedinProfileUrl: "",
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
      setNewListNameError("Please enter a list name to continue.");
      return;
    }
    setNewListNameError(null);
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
    setFirstNameError(null);
    setCompanyNameError(null);
    setCreateLeadError(null);

    let hasError = false;
    if (!newLeadForm.firstName.trim()) {
      setFirstNameError("First name is required.");
      hasError = true;
    }
    if (!newLeadForm.companyName.trim()) {
      setCompanyNameError("Company name is required.");
      hasError = true;
    }
    if (hasError) return;

    // Contact fields (email, phone, linkedinProfileUrl) are optional to support minimal creation
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
        linkedinProfileUrl: "",
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

  // ── Edit Lead Handlers ─────────────────────────────────────────────────────
  const handleOpenEditLeadModal = (lead: CRMLead) => {
    setLeadToEdit(lead);
    setEditLeadForm({
      firstName: lead.firstName || "",
      lastName: lead.lastName || "",
      email: lead.email === "—" ? "" : lead.email,
      phone: lead.phone || "",
      companyName: lead.companyName === "—" ? "" : lead.companyName,
      companyDomain: lead.companyDomain || "",
      jobTitle: lead.jobTitle === "—" ? "" : lead.jobTitle,
      industry: lead.industry === "—" ? "" : lead.industry,
      companySize: lead.companySize === "—" ? "" : lead.companySize,
      city: lead.city || "",
      state: lead.state || "",
      country: lead.country || "",
      linkedinProfileUrl: lead.linkedinProfileUrl || "",
      temperature: lead.temperature || "UNASSESSED",
      qualificationStatus: lead.qualificationStatus || "new",
      qualificationReason: lead.qualificationReason === "—" ? "" : lead.qualificationReason,
    });
    setEditLeadError(null);
    setIsEditLeadModalOpen(true);
  };

  const handleSaveEditedLead = async () => {
    if (!leadToEdit) return;
    if (!editLeadForm.companyName.trim() && !editLeadForm.firstName.trim()) {
      setEditLeadError("At least a company name or lead name is required.");
      return;
    }

    setIsSavingLead(true);
    setEditLeadError(null);
    try {
      // Safe delta payload: only include actively updated fields to avoid overwriting unchanged values
      const payload: Record<string, any> = {};

      const trimmedFirst = editLeadForm.firstName.trim();
      if (trimmedFirst !== (leadToEdit.firstName || "")) payload.firstName = trimmedFirst;

      const trimmedLast = editLeadForm.lastName.trim();
      if (trimmedLast !== (leadToEdit.lastName || "")) payload.lastName = trimmedLast;

      const trimmedEmail = editLeadForm.email.trim();
      const existingEmail = leadToEdit.email === "—" ? "" : leadToEdit.email;
      if (trimmedEmail !== existingEmail) payload.email = trimmedEmail || undefined;

      const trimmedPhone = editLeadForm.phone.trim();
      if (trimmedPhone !== (leadToEdit.phone || "")) payload.phone = trimmedPhone || undefined;

      const trimmedComp = editLeadForm.companyName.trim();
      const existingComp = leadToEdit.companyName === "—" ? "" : leadToEdit.companyName;
      if (trimmedComp && trimmedComp !== existingComp) payload.companyName = trimmedComp;

      const trimmedDomain = editLeadForm.companyDomain.trim();
      if (trimmedDomain !== (leadToEdit.companyDomain || "")) payload.companyDomain = trimmedDomain || undefined;

      const trimmedTitle = editLeadForm.jobTitle.trim();
      const existingTitle = leadToEdit.jobTitle === "—" ? "" : leadToEdit.jobTitle;
      if (trimmedTitle !== existingTitle) payload.jobTitle = trimmedTitle || undefined;

      const trimmedInd = editLeadForm.industry.trim();
      const existingInd = leadToEdit.industry === "—" ? "" : leadToEdit.industry;
      if (trimmedInd !== existingInd) payload.industry = trimmedInd || undefined;

      const trimmedCity = editLeadForm.city.trim();
      if (trimmedCity !== (leadToEdit.city || "")) payload.city = trimmedCity || undefined;

      const trimmedState = editLeadForm.state.trim();
      if (trimmedState !== (leadToEdit.state || "")) payload.state = trimmedState || undefined;

      const trimmedCountry = editLeadForm.country.trim();
      if (trimmedCountry !== (leadToEdit.country || "")) payload.country = trimmedCountry || undefined;

      const trimmedLi = editLeadForm.linkedinProfileUrl.trim();
      const existingLi = leadToEdit.linkedinProfileUrl || "";
      if (trimmedLi !== existingLi) payload.linkedinProfileUrl = trimmedLi || null;

      if (editLeadForm.temperature !== leadToEdit.temperature) {
        payload.temperature = editLeadForm.temperature;
      }

      if (editLeadForm.qualificationStatus !== leadToEdit.qualificationStatus) {
        payload.qualificationStatus = editLeadForm.qualificationStatus;
      }

      const trimmedReason = editLeadForm.qualificationReason.trim();
      const existingReason = leadToEdit.qualificationReason === "—" ? "" : leadToEdit.qualificationReason;
      if (trimmedReason !== existingReason) payload.qualificationReason = trimmedReason || undefined;

      const updatedLead = await updateBackendLead(leadToEdit.id, payload);

      // Refresh local leads list
      setLeadsList((prev) => prev.map((l) => (l.id === updatedLead.id ? updatedLead : l)));

      // If drawer is open with this lead, refresh drawer data immediately
      if (inspectedLead && inspectedLead.id === updatedLead.id) {
        setInspectedLead(updatedLead);
      }

      setSuccessToast(`Lead "${updatedLead.fullName}" updated successfully.`);
      setIsEditLeadModalOpen(false);
      setLeadToEdit(null);

      // Refresh lists to update member and valid email counts
      loadLists();
    } catch (err: unknown) {
      setEditLeadError(err instanceof Error ? err.message : "Failed to update lead.");
    } finally {
      setIsSavingLead(false);
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
        linkedin_profile_url: getVal(columnMapping.linkedin_profile_url) || undefined,
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
          onEditLead={handleOpenEditLeadModal}
        />
      ) : viewMode === "all_leads" ? (
        /* Raw All-Leads View */
        <div className="space-y-4 max-w-7xl mx-auto pb-16">
          <div className="flex items-center justify-between pb-3 border-b border-slate-200/80">
            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setViewMode("lists")}
                className="text-xs inline-flex items-center gap-1.5"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Back to Lists</span>
              </Button>
              <h2 className="text-lg font-bold text-header">
                {isMarketing ? "All Contacts & Audience" : "All Prospect Leads"} ({totalLeads})
              </h2>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
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
                className="text-xs inline-flex items-center gap-1.5 shadow-xs"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>{isMarketing ? "Add Contact" : "Add Lead"}</span>
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

                    {/* Bulk Selection Bar */}
          {selectedIds.size > 0 && (
            <div className="p-3 bg-slate-900 text-white rounded-xl shadow-lg flex items-center justify-between text-xs animate-in fade-in">
              <div className="flex items-center gap-2">
                <span className="font-semibold">{selectedIds.size} lead(s) selected</span>
                <button
                  onClick={() => setSelectedIds(new Set())}
                  className="text-slate-400 hover:text-white underline text-[11px] ml-2"
                >
                  Clear selection
                </button>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleOpenEnrollModal}
                  className="text-xs bg-white/10 hover:bg-white/20 text-white border-white/20"
                >
                  <UserCheck className="w-3.5 h-3.5 mr-1" />
                  Add to Campaign
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleLaunchDirectMailFromSelection}
                  className="text-xs bg-agile-red hover:bg-agile-red/90 text-white"
                >
                  <Send className="w-3.5 h-3.5 mr-1" />
                  Direct Mail Test Dispatch
                </Button>
              </div>
            </div>
          )}

          {/* Leads Table */}
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
            <Table>
              <TableHeader className="bg-slate-50">
                <TableRow>
                  <TableHead className="w-10">
                    <button
                      type="button"
                      onClick={handleToggleSelectAll}
                      className="text-slate-400 hover:text-slate-700"
                    >
                      {selectedIds.size === leadsList.length && leadsList.length > 0 ? (
                        <CheckSquare className="w-4 h-4 text-agile-red" />
                      ) : selectedIds.size > 0 ? (
                        <MinusSquare className="w-4 h-4 text-agile-red" />
                      ) : (
                        <Square className="w-4 h-4" />
                      )}
                    </button>
                  </TableHead>
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
                  <TableLoadingRow colSpan={8} rows={4} />
                ) : leadsList.length === 0 ? (
                  <TableEmptyRow
                    colSpan={8}
                    title="No prospect leads found"
                    description={
                      searchQuery
                        ? `No leads match "${searchQuery}". Try adjusting your search query.`
                        : "No leads found in this view. Import leads or create a new prospect to begin."
                    }
                    action={
                      <div className="flex items-center gap-2 pt-1">
                        <Button
                          variant="secondary"
                          size="xs"
                          onClick={() => setIsImportModalOpen(true)}
                          className="text-xs"
                        >
                          <Download className="w-3.5 h-3.5 mr-1" />
                          Import CSV
                        </Button>
                        <Button
                          variant="primary"
                          size="xs"
                          onClick={() => setIsAddLeadModalOpen(true)}
                          className="text-xs"
                        >
                          <Plus className="w-3.5 h-3.5 mr-1" />
                          {isMarketing ? "Add Contact" : "Add Lead"}
                        </Button>
                      </div>
                    }
                  />
                ) : (
                  leadsList.map((lead) => (
                    <TableRow key={lead.id} className={`hover:bg-slate-50/50 ${selectedIds.has(lead.id) ? "bg-rose-50/30" : ""}`}>
                      <TableCell className="py-2.5">
                        <button
                          type="button"
                          onClick={() => handleToggleSelectLead(lead.id)}
                          className="text-slate-400 hover:text-slate-700"
                        >
                          {selectedIds.has(lead.id) ? (
                            <CheckSquare className="w-4 h-4 text-agile-red" />
                          ) : (
                            <Square className="w-4 h-4" />
                          )}
                        </button>
                      </TableCell>
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
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleOpenEditLeadModal(lead)}
                            className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                            title="Edit Lead Details"
                          >
                            <Edit className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => setInspectedLead(lead)}
                            className="p-1 rounded text-slate-400 hover:text-slate-600 hover:bg-slate-100"
                            title="Inspect Lead"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                        </div>
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
        onClose={() => {
          setIsCreateListModalOpen(false);
          setNewListNameError(null);
        }}
        title={isMarketing ? "Create New Audience List" : "Create New Lead List"}
        description={
          isMarketing
            ? "Create a static audience list to organize members for marketing campaigns or segmented broadcasts."
            : "Create a static prospect list to organize leads for outbound sequences or sales calls."
        }
        footer={
          <>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setIsCreateListModalOpen(false)}
              className="text-xs"
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={handleCreateList}
              isLoading={isCreatingList}
              disabled={isCreatingList || !newListName.trim()}
              className="text-xs shadow-xs"
            >
              Create List
            </Button>
          </>
        }
      >
        <div className="space-y-3.5">
          {createListError && (
            <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{createListError}</span>
            </div>
          )}

          <Input
            label="List Name"
            required
            placeholder="e.g. Q4 FinTech Founders"
            value={newListName}
            error={newListNameError || undefined}
            onChange={(e) => {
              setNewListName(e.target.value);
              if (newListNameError) setNewListNameError(null);
            }}
            helperText="A descriptive name to easily identify this group across your CRM."
            autoFocus
          />

          <Input
            label="Description"
            optional
            placeholder="e.g. High intent prospects targeting enterprise sales"
            value={newListDesc}
            onChange={(e) => setNewListDesc(e.target.value)}
            helperText="Internal notes on audience criteria or lead source."
          />
        </div>
      </Modal>

      {/* ── MODAL: Edit List ── */}
      <Modal
        isOpen={Boolean(listToEdit)}
        onClose={() => setListToEdit(null)}
        title="Edit List Details"
        description="Update the name and notes for this static lead list."
        footer={
          <>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setListToEdit(null)}
              className="text-xs"
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={handleUpdateList}
              isLoading={isUpdatingList}
              disabled={isUpdatingList || !editListName.trim()}
              className="text-xs shadow-xs"
            >
              Save Changes
            </Button>
          </>
        }
      >
        <div className="space-y-3.5">
          <Input
            label="List Name"
            required
            value={editListName}
            onChange={(e) => setEditListName(e.target.value)}
          />
          <Input
            label="Description"
            optional
            value={editListDesc}
            onChange={(e) => setEditListDesc(e.target.value)}
            helperText="Notes on the audience criteria or campaign target."
          />
        </div>
      </Modal>

      {/* ── MODAL: Confirm Delete List ── */}
      <ConfirmModal
        isOpen={Boolean(listToDelete)}
        onClose={() => setListToDelete(null)}
        onConfirm={handleDeleteList}
        title={listToDelete ? `Delete List "${listToDelete.name}"?` : "Delete List"}
        description={`Are you sure you want to delete "${listToDelete?.name}"? This removes the static list grouping.`}
        consequenceNotice="Underlying CRM Contacts, Leads, Companies, and Campaigns will never be deleted. Historical outreach events and activity metrics remain completely intact."
        confirmText="Delete List"
        variant="danger"
        isLoading={isDeletingList}
      />

      {/* ── MODAL: Add Lead Manually ── */}
      <Modal
        isOpen={isAddLeadModalOpen}
        onClose={() => {
          setIsAddLeadModalOpen(false);
          setFirstNameError(null);
          setCompanyNameError(null);
        }}
        title={isMarketing ? "Add Audience Contact" : "Add Prospect Lead"}
        description="Enter prospect details to add a new record to your CRM database."
        footer={
          <>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setIsAddLeadModalOpen(false)}
              className="text-xs"
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={handleCreateManualLead}
              isLoading={isCreatingLead}
              disabled={isCreatingLead || !newLeadForm.firstName.trim() || !newLeadForm.companyName.trim()}
              className="text-xs shadow-xs"
            >
              Save Lead
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {createLeadError && (
            <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{createLeadError}</span>
            </div>
          )}

          <FormSection title="Contact Information">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Input
                label="First Name"
                required
                placeholder="Jane"
                value={newLeadForm.firstName}
                error={firstNameError || undefined}
                onChange={(e) => {
                  setNewLeadForm({ ...newLeadForm, firstName: e.target.value });
                  if (firstNameError) setFirstNameError(null);
                }}
              />
              <Input
                label="Last Name"
                optional
                placeholder="Doe"
                value={newLeadForm.lastName}
                onChange={(e) => setNewLeadForm({ ...newLeadForm, lastName: e.target.value })}
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Input
                label="Email Address"
                optional
                placeholder="jane@company.com"
                value={newLeadForm.email}
                onChange={(e) => setNewLeadForm({ ...newLeadForm, email: e.target.value })}
                helperText="Required for automated email cadences."
              />
              <Input
                label="Phone Number"
                optional
                placeholder="+1 555-0100"
                value={newLeadForm.phone}
                onChange={(e) => setNewLeadForm({ ...newLeadForm, phone: e.target.value })}
                helperText="E.164 format for SMS / Voice."
              />
            </div>
          </FormSection>

          <FormSection title="Company & Employment">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Input
                label="Company Name"
                required
                placeholder="Acme Corp"
                value={newLeadForm.companyName}
                error={companyNameError || undefined}
                onChange={(e) => {
                  setNewLeadForm({ ...newLeadForm, companyName: e.target.value });
                  if (companyNameError) setCompanyNameError(null);
                }}
              />
              <Input
                label="Job Title"
                optional
                placeholder="VP of Growth"
                value={newLeadForm.jobTitle}
                onChange={(e) => setNewLeadForm({ ...newLeadForm, jobTitle: e.target.value })}
              />
            </div>

            <Input
              label="Industry"
              optional
              placeholder="e.g. Financial Services"
              value={newLeadForm.industry}
              onChange={(e) => setNewLeadForm({ ...newLeadForm, industry: e.target.value })}
            />
          </FormSection>

          <FormSection
            title="Social & Outreach Profiles"
            description="Add social networking profiles for multi-touch outreach."
            collapsible
            defaultOpen={Boolean(newLeadForm.linkedinProfileUrl)}
          >
            <Input
              label="LinkedIn Profile URL"
              optional
              placeholder="https://www.linkedin.com/in/username"
              value={newLeadForm.linkedinProfileUrl || ""}
              onChange={(e) => setNewLeadForm({ ...newLeadForm, linkedinProfileUrl: e.target.value })}
              helperText="Personal profile link used in assisted LinkedIn outreach sequences."
            />
          </FormSection>
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

              {/* Column Mapping for LinkedIn Profile URL */}
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-2">
                <div className="flex items-center justify-between text-xs font-semibold text-slate-700">
                  <span>LinkedIn Profile Column Mapping</span>
                  <span className="text-[11px] text-slate-500 font-normal">
                    {columnMapping.linkedin_profile_url !== -1
                      ? `Mapped to: "${csvHeaders[columnMapping.linkedin_profile_url]}"`
                      : "(Auto-detect: Not detected)"}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <select
                      value={columnMapping.linkedin_profile_url}
                      onChange={(e) =>
                        setColumnMapping({
                          ...columnMapping,
                          linkedin_profile_url: parseInt(e.target.value, 10),
                        })
                      }
                      className="w-full text-xs p-1.5 rounded border border-slate-200 bg-white"
                    >
                      <option value={-1}>-- Not Mapped (Optional) --</option>
                      {csvHeaders.map((header, idx) => (
                        <option key={idx} value={idx}>
                          Col {idx + 1}: {header}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="text-[11px] text-slate-500 flex items-center">
                    URLs are automatically validated and normalized to canonical format.
                  </div>
                </div>
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

            {/* ── MODAL: Add Selected Leads to Campaign ── */}
      <Modal
        isOpen={isCampaignModalOpen}
        onClose={() => setIsCampaignModalOpen(false)}
        title={`Add ${selectedIds.size || "Selected"} Leads to Campaign`}
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600">
            Select an outreach sequence to enroll the selected leads.
          </p>
          {isLoadingCampaigns ? (
            <div className="py-6 text-center text-xs text-slate-400">Loading campaigns...</div>
          ) : availableCampaigns.length === 0 ? (
            <p className="text-xs text-slate-500">No campaigns found. Create a campaign first.</p>
          ) : (
            <div className="space-y-3">
              <Select
                label="Target Campaign"
                helperText="Choose an outreach campaign to enroll the selected leads."
                value={selectedCampaignId}
                onChange={(e) => setSelectedCampaignId(e.target.value)}
                options={availableCampaigns.map((camp) => ({
                  value: camp.id,
                  label: `${camp.name} (${camp.type}) — ${camp.status}`,
                }))}
              />

              {/* LinkedIn URL Availability Warning for Target Campaign */}
              {(() => {
                const targetCampaign = availableCampaigns.find((c) => c.id === selectedCampaignId) || availableCampaigns[0];
                const isLinkedIn =
                  (targetCampaign?.type as string) === "linkedin" ||
                  targetCampaign?.channels?.includes("linkedin") ||
                  targetCampaign?.steps?.some((s) => s.stepType === "linkedin") ||
                  targetCampaign?.workflowConfig?.nodes?.some((n: any) => n.type === "linkedin");
                if (!isLinkedIn) return null;

                const selectedList = leadsList.filter((l) => selectedIds.has(l.id));
                const missingUrlCount = selectedList.filter((l) => !l.linkedinProfileUrl).length;

                if (missingUrlCount === 0) {
                  return (
                    <div className="p-2.5 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                      <span>All {selectedList.length} selected leads have LinkedIn profile URLs recorded.</span>
                    </div>
                  );
                }

                return (
                  <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold block">
                        ⚠️ {missingUrlCount} of {selectedList.length} selected leads do not have a LinkedIn profile URL recorded.
                      </span>
                      <span className="text-[11px] text-amber-700">
                        They will still be enrolled safely with auto-generated LinkedIn Search links, and you can record their profile URLs directly in the LinkedIn Outreach workspace.
                      </span>
                    </div>
                  </div>
                );
              })()}
            </div>
          )}
          <div className="flex justify-between items-center pt-2 border-t border-slate-100">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsCampaignModalOpen(false)}
              disabled={isEnrollingInCampaign}
              className="text-xs"
            >
              Cancel
            </Button>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleEnrollSelectedLeads(true)}
                disabled={isEnrollingInCampaign || availableCampaigns.length === 0 || selectedIds.size === 0}
                isLoading={isEnrollingInCampaign}
                className="text-xs border-rose-300 text-rose-700 hover:bg-rose-50"
              >
                <Send className="w-3 h-3 mr-1 text-rose-600" />
                Enroll & Open Direct Mail
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => handleEnrollSelectedLeads(false)}
                disabled={isEnrollingInCampaign || availableCampaigns.length === 0 || selectedIds.size === 0}
                isLoading={isEnrollingInCampaign}
                className="text-xs bg-agile-red hover:bg-agile-red/90 text-white"
              >
                Enroll Selected
              </Button>
            </div>
          </div>
        </div>
      </Modal>

      {/* ── MODAL: Direct Mail Pre-Flight & Test Dispatch ── */}
      {directMailCampaign && (
        <PhysicalMailPreflightModal
          isOpen={isDirectMailModalOpen}
          onClose={() => setIsDirectMailModalOpen(false)}
          campaignId={directMailCampaign.id}
          campaignName={directMailCampaign.name}
          recipientIds={selectedIds.size > 0 ? Array.from(selectedIds) : undefined}
          onCompleted={() => {
            setSelectedIds(new Set());
          }}
        />
      )}

      {/* ── MODAL: Edit Lead Details ── */}
      <Modal
        isOpen={isEditLeadModalOpen}
        onClose={() => {
          if (!isSavingLead) {
            setIsEditLeadModalOpen(false);
            setLeadToEdit(null);
          }
        }}
        title="Edit Lead Details"
        description="Update prospect details, contact channels, company profile, or qualification status."
      >
        <div className="space-y-4 max-h-[75vh] overflow-y-auto pr-1">
          {editLeadError && (
            <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2" role="alert">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{editLeadError}</span>
            </div>
          )}

          {/* Section: Contact Information */}
          <FormSection
            title="Contact Information"
            description="Personal details and communication channels for this prospect."
          >
            <div className="grid grid-cols-2 gap-2.5">
              <Input
                label="First Name"
                placeholder="First name"
                value={editLeadForm.firstName}
                onChange={(e) => setEditLeadForm({ ...editLeadForm, firstName: e.target.value })}
                className="h-8 text-xs"
              />
              <Input
                label="Last Name"
                placeholder="Last name"
                value={editLeadForm.lastName}
                onChange={(e) => setEditLeadForm({ ...editLeadForm, lastName: e.target.value })}
                className="h-8 text-xs"
              />
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <Input
                label="Email Address"
                optional
                type="email"
                placeholder="email@example.com"
                value={editLeadForm.email}
                onChange={(e) => setEditLeadForm({ ...editLeadForm, email: e.target.value })}
                className="h-8 text-xs font-mono"
              />
              <Input
                label="Phone Number"
                optional
                type="tel"
                placeholder="+1 555-0100"
                value={editLeadForm.phone}
                onChange={(e) => setEditLeadForm({ ...editLeadForm, phone: e.target.value })}
                className="h-8 text-xs font-mono"
              />
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <Input
                label="Job Title"
                optional
                placeholder="e.g. VP of Sales"
                value={editLeadForm.jobTitle}
                onChange={(e) => setEditLeadForm({ ...editLeadForm, jobTitle: e.target.value })}
                className="h-8 text-xs"
              />
              <Input
                label="LinkedIn Profile URL"
                optional
                placeholder="https://www.linkedin.com/in/username"
                value={editLeadForm.linkedinProfileUrl}
                onChange={(e) => setEditLeadForm({ ...editLeadForm, linkedinProfileUrl: e.target.value })}
                className="h-8 text-xs font-mono"
              />
            </div>
          </FormSection>

          {/* Section: Company & Organization */}
          <FormSection
            title="Company & Organization"
            description="Employer, industry sector, and geographic location."
          >
            <div className="grid grid-cols-2 gap-2.5">
              <Input
                label="Company Name"
                placeholder="Company name"
                value={editLeadForm.companyName}
                onChange={(e) => setEditLeadForm({ ...editLeadForm, companyName: e.target.value })}
                className="h-8 text-xs"
              />
              <Input
                label="Company Domain"
                optional
                placeholder="company.com"
                value={editLeadForm.companyDomain}
                onChange={(e) => setEditLeadForm({ ...editLeadForm, companyDomain: e.target.value })}
                className="h-8 text-xs font-mono"
              />
            </div>

            <Input
              label="Industry"
              optional
              placeholder="e.g. Financial Services"
              value={editLeadForm.industry}
              onChange={(e) => setEditLeadForm({ ...editLeadForm, industry: e.target.value })}
              className="h-8 text-xs"
            />

            <div className="grid grid-cols-3 gap-2.5">
              <Input
                label="City"
                optional
                placeholder="City"
                value={editLeadForm.city}
                onChange={(e) => setEditLeadForm({ ...editLeadForm, city: e.target.value })}
                className="h-8 text-xs"
              />
              <Input
                label="State / Region"
                optional
                placeholder="State"
                value={editLeadForm.state}
                onChange={(e) => setEditLeadForm({ ...editLeadForm, state: e.target.value })}
                className="h-8 text-xs"
              />
              <Input
                label="Country"
                optional
                placeholder="Country"
                value={editLeadForm.country}
                onChange={(e) => setEditLeadForm({ ...editLeadForm, country: e.target.value })}
                className="h-8 text-xs"
              />
            </div>
          </FormSection>

          {/* Section: Temperature & Qualification */}
          <FormSection
            title="Temperature & Qualification"
            description="Assess sales engagement temperature and pipeline qualification status."
          >
            <div className="grid grid-cols-2 gap-2.5">
              <Select
                label="Lead Temperature"
                value={editLeadForm.temperature}
                onChange={(e) => setEditLeadForm({ ...editLeadForm, temperature: e.target.value as CRMLeadTemperature })}
                options={[
                  { value: "HOT", label: "🔥 Hot (Active buying intent)" },
                  { value: "WARM", label: "☀️ Warm (Engaged / interested)" },
                  { value: "COLD", label: "❄️ Cold (Unresponsive)" },
                  { value: "UNASSESSED", label: "⚪ Unassessed" },
                ]}
              />
              <Select
                label="Qualification Status"
                value={editLeadForm.qualificationStatus}
                onChange={(e) => setEditLeadForm({ ...editLeadForm, qualificationStatus: e.target.value as any })}
                options={[
                  { value: "new", label: "New / Unassessed" },
                  { value: "qualified", label: "Qualified" },
                  { value: "disqualified", label: "Disqualified" },
                  { value: "reviewed", label: "Reviewed" },
                ]}
              />
            </div>

            <Input
              label="Qualification Notes"
              optional
              placeholder="e.g. Meets ICP criteria or notes from initial assessment"
              value={editLeadForm.qualificationReason}
              onChange={(e) => setEditLeadForm({ ...editLeadForm, qualificationReason: e.target.value })}
              className="h-8 text-xs"
            />
          </FormSection>

          <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
            <Button
              variant="outline"
              size="sm"
              disabled={isSavingLead}
              onClick={() => {
                setIsEditLeadModalOpen(false);
                setLeadToEdit(null);
              }}
              className="text-xs"
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleSaveEditedLead}
              disabled={isSavingLead}
              isLoading={isSavingLead}
              className="text-xs bg-agile-red hover:bg-agile-red/90 text-white"
            >
              Save Changes
            </Button>
          </div>
        </div>
      </Modal>

      {/* ── Lead Detail Drawer ── */}
      <LeadDetailDrawer
        lead={inspectedLead}
        isOpen={Boolean(inspectedLead)}
        onClose={() => setInspectedLead(null)}
        onEditLead={handleOpenEditLeadModal}
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
