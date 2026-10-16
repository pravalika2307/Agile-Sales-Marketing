"use client";

import * as React from "react";
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
import Link from "next/link";
import {
  LeadItem,
  LeadFilterCriteria,
  filterLeads,
  searchProspects,
} from "@/services/leadService";
import {
  Search,
  Filter,
  RotateCcw,
  Plus,
  Send,
  Building,
  MapPin,
  Mail,
  Phone,
  CheckSquare,
  Square,
  MinusSquare,
  ExternalLink,
  ChevronRight,
  UserPlus,
  AlertCircle,
  Info,
} from "lucide-react";

export default function FindLeadsPage() {
  // Prospects State (Strict Data Integrity: No fabricated leads)
  const [prospectsList, setProspectsList] = React.useState<LeadItem[]>([]);
  const [searchMessage, setSearchMessage] = React.useState<string | null>(
    "No external B2B lead discovery provider is currently configured (e.g. Apollo, ZoomInfo). In production integrity mode, synthetic leads are never fabricated."
  );
  const [searchError, setSearchError] = React.useState<string | null>(null);

  // Search & Filter State
  const [naturalQuery, setNaturalQuery] = React.useState("");
  const [industry, setIndustry] = React.useState("ALL");
  const [location, setLocation] = React.useState("ALL");
  const [companySize, setCompanySize] = React.useState("ALL");
  const [jobTitle, setJobTitle] = React.useState("");
  const [seniority, setSeniority] = React.useState("ALL");
  const [department, setDepartment] = React.useState("ALL");
  const [technology, setTechnology] = React.useState("ALL");
  const [keywords, setKeywords] = React.useState("");

  // UI States
  const [isLoading, setIsLoading] = React.useState(false);
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());
  const [currentPage, setCurrentPage] = React.useState(1);
  const [pageSize] = React.useState(10);
  const [activeTabFilter, setActiveTabFilter] = React.useState<"ALL" | "HOT" | "WARM" | "COLD">("ALL");
  const [isCampaignModalOpen, setIsCampaignModalOpen] = React.useState(false);

  // Filter computation
  const filteredProspects = React.useMemo(() => {
    const criteria: LeadFilterCriteria = {
      naturalQuery: naturalQuery.trim() ? naturalQuery : undefined,
      industry: industry !== "ALL" ? industry : undefined,
      location: location !== "ALL" ? location : undefined,
      companySize: companySize !== "ALL" ? companySize : undefined,
      seniority: seniority !== "ALL" ? seniority : undefined,
      department: department !== "ALL" ? department : undefined,
      keywords: keywords.trim() ? keywords : undefined,
    };

    let result = filterLeads(prospectsList, criteria);

    // Secondary temperature filter
    if (activeTabFilter !== "ALL") {
      result = result.filter((l) => l.temperature === activeTabFilter);
    }

    return result;
  }, [
    prospectsList,
    naturalQuery,
    industry,
    location,
    companySize,
    seniority,
    department,
    keywords,
    activeTabFilter,
  ]);

  // Execute Search action
  const handleSearch = async () => {
    setIsLoading(true);
    setSearchError(null);
    try {
      const criteria: LeadFilterCriteria = {
        naturalQuery: naturalQuery.trim() ? naturalQuery : undefined,
        industry: industry !== "ALL" ? industry : undefined,
        location: location !== "ALL" ? location : undefined,
        companySize: companySize !== "ALL" ? companySize : undefined,
        seniority: seniority !== "ALL" ? seniority : undefined,
        department: department !== "ALL" ? department : undefined,
        keywords: keywords.trim() ? keywords : undefined,
      };

      const result = await searchProspects(criteria);
      setProspectsList(result.leads);
      if (result.message) {
        setSearchMessage(result.message);
      }
      setCurrentPage(1);
    } catch (err: unknown) {
      console.error("Search failed:", err);
      setSearchError(
        err instanceof Error ? err.message : "Lead search provider request failed."
      );
    } finally {
      setIsLoading(false);
    }
  };

  // Reset Filters
  const handleResetFilters = () => {
    setNaturalQuery("");
    setIndustry("ALL");
    setLocation("ALL");
    setCompanySize("ALL");
    setJobTitle("");
    setSeniority("ALL");
    setDepartment("ALL");
    setTechnology("ALL");
    setKeywords("");
    setActiveTabFilter("ALL");
    setSelectedIds(new Set());
  };

  // Selection Logic
  const allCurrentIds = React.useMemo(
    () => filteredProspects.map((p) => p.id),
    [filteredProspects]
  );

  const isAllSelected =
    allCurrentIds.length > 0 &&
    allCurrentIds.every((id) => selectedIds.has(id));

  const isSomeSelected =
    allCurrentIds.some((id) => selectedIds.has(id)) && !isAllSelected;

  const toggleSelectAll = () => {
    if (isAllSelected) {
      const next = new Set(selectedIds);
      allCurrentIds.forEach((id) => next.delete(id));
      setSelectedIds(next);
    } else {
      const next = new Set(selectedIds);
      allCurrentIds.forEach((id) => next.add(id));
      setSelectedIds(next);
    }
  };

  const toggleSelectRow = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelectedIds(next);
  };

  return (
    <AppShell onNewCampaignClick={() => setIsCampaignModalOpen(true)}>
      {/* 1. Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-1">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-header">
            Find Leads
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
            Discover and qualify prospects for your sales campaigns.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleResetFilters}
            className="text-xs inline-flex items-center gap-1.5"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset Search</span>
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={handleSearch}
            className="text-xs inline-flex items-center gap-1.5 shadow-xs"
          >
            <Search className="w-3.5 h-3.5" />
            <span>Run Search</span>
          </Button>
        </div>
      </div>

      {/* 2. Natural-Language Lead Search Area */}
      <Card className="border border-slate-200 shadow-[0_1px_3px_rgba(0,0,0,0.03)] bg-white">
        <CardContent className="p-4 sm:p-5 space-y-4">
          <div className="space-y-1.5">
            <label
              htmlFor="natural-search-input"
              className="block text-xs font-semibold text-slate-700"
            >
              Describe who you&apos;re looking for
            </label>
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              <div className="relative flex-1">
                <Input
                  id="natural-search-input"
                  value={naturalQuery}
                  onChange={(e) => setNaturalQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                  placeholder='e.g. "Find sales directors at SaaS companies in California with 50–500 employees"'
                  icon={<Search className="w-4 h-4 text-slate-400" />}
                  className="h-10 text-xs sm:text-sm bg-white border-slate-200 focus:border-agile-red"
                />
              </div>

              <Button
                variant="primary"
                onClick={handleSearch}
                className="h-10 px-5 text-xs sm:text-sm font-semibold shrink-0 shadow-xs inline-flex items-center justify-center gap-2"
              >
                <Search className="w-4 h-4" />
                <span>Find Leads</span>
              </Button>
            </div>
          </div>

          {/* 3. Structured Filters Grid */}
          <div className="pt-3 border-t border-slate-100">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-700 uppercase tracking-wider">
                <Filter className="w-3.5 h-3.5 text-slate-400" />
                <span>Structured Filters</span>
              </div>
              <span className="text-[11px] text-slate-400 font-normal">
                Refine by exact firmographic and contact parameters
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
              <Select
                label="Industry"
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                options={[
                  { value: "ALL", label: "All Industries" },
                  { value: "Financial Services", label: "Financial Services" },
                  { value: "Healthcare", label: "Healthcare" },
                  { value: "Logistics & Supply Chain", label: "Logistics & Supply Chain" },
                  { value: "Energy & Utilities", label: "Energy & Utilities" },
                  { value: "Technology", label: "Technology" },
                  { value: "Legal Services", label: "Legal Services" },
                  { value: "Construction & Building", label: "Construction & Building" },
                ]}
              />

              <Select
                label="Location"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                options={[
                  { value: "ALL", label: "All Locations" },
                  { value: "Texas", label: "Texas (All)" },
                  { value: "Dallas", label: "Dallas, TX" },
                  { value: "Houston", label: "Houston, TX" },
                  { value: "Austin", label: "Austin, TX" },
                  { value: "Fort Worth", label: "Fort Worth, TX" },
                  { value: "San Antonio", label: "San Antonio, TX" },
                  { value: "El Paso", label: "El Paso, TX" },
                  { value: "California", label: "California" },
                  { value: "New York", label: "New York" },
                ]}
              />

              <Select
                label="Company Size"
                value={companySize}
                onChange={(e) => setCompanySize(e.target.value)}
                options={[
                  { value: "ALL", label: "All Sizes" },
                  { value: "10-50", label: "10–50 Employees" },
                  { value: "50-200", label: "50–200 Employees" },
                  { value: "201-500", label: "201–500 Employees" },
                  { value: "500-1000", label: "500–1000 Employees" },
                ]}
              />

              <Select
                label="Seniority"
                value={seniority}
                onChange={(e) => setSeniority(e.target.value)}
                options={[
                  { value: "ALL", label: "All Seniorities" },
                  { value: "C-Level", label: "C-Level" },
                  { value: "VP", label: "VP" },
                  { value: "Director", label: "Director" },
                  { value: "Head", label: "Head of Dept" },
                  { value: "Manager", label: "Manager" },
                  { value: "Individual Contributor", label: "Individual Contributor" },
                ]}
              />

              <Select
                label="Department"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                options={[
                  { value: "ALL", label: "All Departments" },
                  { value: "Operations", label: "Operations" },
                  { value: "Finance", label: "Finance / Accounts Receivable" },
                  { value: "Revenue Operations", label: "Revenue Operations" },
                  { value: "Executive", label: "Executive" },
                ]}
              />

              <Select
                label="Technology"
                value={technology}
                onChange={(e) => setTechnology(e.target.value)}
                options={[
                  { value: "ALL", label: "All Technologies" },
                  { value: "Salesforce", label: "Salesforce" },
                  { value: "Workday", label: "Workday" },
                  { value: "NetSuite", label: "NetSuite" },
                  { value: "SAP", label: "SAP" },
                  { value: "Retell AI", label: "Retell AI" },
                  { value: "Epic", label: "Epic Systems" },
                ]}
              />

              <Input
                label="Job Title Query"
                placeholder="e.g. Operations, Credit"
                value={jobTitle}
                onChange={(e) => setJobTitle(e.target.value)}
                className="h-9 text-xs"
              />

              <Input
                label="Keywords"
                placeholder="e.g. sales, b2b, saas"
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                className="h-9 text-xs"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 4. Selection Action Floating / Prominent Bar */}
      {selectedIds.size > 0 && (
        <div className="rounded-xl border border-agile-outlinered/40 bg-agile-lightorange/90 p-3.5 px-4 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-3 animate-in fade-in duration-150">
          <div className="flex items-center gap-3">
            <span className="w-2 h-2 rounded-full bg-agile-red" />
            <span className="text-xs font-semibold text-header">
              <strong className="text-agile-red">{selectedIds.size}</strong>{" "}
              {selectedIds.size === 1 ? "lead" : "leads"} selected for action
            </span>
            <span className="text-slate-300 hidden sm:inline">|</span>
            <span className="text-[11px] text-slate-500 hidden sm:inline">
              Selected prospects will be queued for automated Voice SDR qualification and email campaigns.
            </span>
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSelectedIds(new Set())}
              className="text-xs bg-white text-slate-600 hover:text-slate-800"
            >
              Deselect All
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => setIsCampaignModalOpen(true)}
              className="text-xs shadow-xs inline-flex items-center gap-1.5"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add to Campaign</span>
            </Button>
          </div>
        </div>
      )}

      {/* 5. Search Results Header & Quick Temperature Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-1">
        <div className="flex items-center gap-3">
          <h2 className="text-base sm:text-lg font-bold text-header">
            Prospects
          </h2>
          <span className="px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600 font-semibold text-xs border border-slate-200">
            {filteredProspects.length} prospects found
          </span>
        </div>

        {/* Temperature Quick Pills */}
        <div className="flex items-center gap-1 text-xs">
          <span className="text-slate-400 font-medium mr-1 text-[11px]">
            Filter:
          </span>
          <button
            type="button"
            onClick={() => setActiveTabFilter("ALL")}
            className={`px-2.5 py-1 rounded-md font-medium text-xs transition-colors border ${
              activeTabFilter === "ALL"
                ? "bg-header text-white border-header"
                : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
            }`}
          >
            All
          </button>
          <button
            type="button"
            onClick={() => setActiveTabFilter("HOT")}
            className={`px-2.5 py-1 rounded-md font-medium text-xs transition-colors border ${
              activeTabFilter === "HOT"
                ? "bg-agile-red text-white border-agile-red"
                : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
            }`}
          >
            HOT (Score 85+)
          </button>
          <button
            type="button"
            onClick={() => setActiveTabFilter("WARM")}
            className={`px-2.5 py-1 rounded-md font-medium text-xs transition-colors border ${
              activeTabFilter === "WARM"
                ? "bg-agile-orange text-slate-900 border-agile-orange font-semibold"
                : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
            }`}
          >
            WARM (Score 65–84)
          </button>
          <button
            type="button"
            onClick={() => setActiveTabFilter("COLD")}
            className={`px-2.5 py-1 rounded-md font-medium text-xs transition-colors border ${
              activeTabFilter === "COLD"
                ? "bg-slate-600 text-white border-slate-600"
                : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
            }`}
          >
            COLD (&lt;65)
          </button>
        </div>
      </div>

      {/* 6. Lead Results Table or Empty / Loading State */}
      <div className="space-y-3">
        {searchError ? (
          /* Error State */
          <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-8 text-center flex flex-col items-center justify-center space-y-3">
            <AlertCircle className="w-8 h-8 text-rose-500" />
            <div>
              <h3 className="text-sm font-semibold text-rose-900">
                Lead Search Failed
              </h3>
              <p className="text-xs text-rose-700 mt-0.5 max-w-md">
                {searchError}
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleSearch}
              className="text-xs bg-white"
            >
              Try Again
            </Button>
          </div>
        ) : isLoading ? (
          /* Subtle skeleton loading state */
          <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className="h-10 bg-slate-100/70 rounded-md animate-pulse flex items-center px-4"
              />
            ))}
          </div>
        ) : filteredProspects.length === 0 ? (
          /* Honest Empty State */
          <div className="rounded-xl border border-slate-200 bg-white p-12 text-center flex flex-col items-center justify-center space-y-3">
            <div className="w-10 h-10 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-400">
              <Search className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-header">
                No external lead provider connected
              </h3>
              <p className="text-xs text-slate-500 mt-1 max-w-md leading-relaxed">
                Agile Sales & Marketing is running in production data-integrity mode. No live B2B discovery provider is configured (e.g. Apollo, ZoomInfo), and synthetic records are never fabricated. You can manage genuine leads directly in the CRM.
              </p>
            </div>
            <div className="flex items-center gap-2 pt-2">
              <Link href="/leads">
                <Button
                  variant="primary"
                  size="sm"
                  className="text-xs shadow-xs"
                >
                  View Leads CRM
                </Button>
              </Link>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleResetFilters}
                className="text-xs"
              >
                Reset Search
              </Button>
            </div>
          </div>
        ) : (
          /* Responsive Lead Results Table */
          <div className="space-y-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10 text-center">
                    <button
                      type="button"
                      onClick={toggleSelectAll}
                      className="p-1 rounded text-slate-500 hover:text-slate-800"
                      aria-label="Select all prospects"
                    >
                      {isAllSelected ? (
                        <CheckSquare className="w-4 h-4 text-agile-red" />
                      ) : isSomeSelected ? (
                        <MinusSquare className="w-4 h-4 text-agile-red" />
                      ) : (
                        <Square className="w-4 h-4 text-slate-400" />
                      )}
                    </button>
                  </TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Job Title</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Location</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Lead Score</TableHead>
                  <TableHead>Temperature</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredProspects.map((lead) => {
                  const isSelected = selectedIds.has(lead.id);

                  return (
                    <TableRow
                      key={lead.id}
                      className={
                        isSelected
                          ? "bg-agile-lightorange/30 border-agile-outlinered/20"
                          : ""
                      }
                    >
                      {/* Select Checkbox */}
                      <TableCell className="text-center">
                        <button
                          type="button"
                          onClick={() => toggleSelectRow(lead.id)}
                          className="p-1 rounded text-slate-500 hover:text-slate-800"
                          aria-label={`Select ${lead.name}`}
                        >
                          {isSelected ? (
                            <CheckSquare className="w-4 h-4 text-agile-red" />
                          ) : (
                            <Square className="w-4 h-4 text-slate-300" />
                          )}
                        </button>
                      </TableCell>

                      {/* Name */}
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="font-semibold text-header text-sm">
                            {lead.name}
                          </span>
                          <span className="text-[11px] text-slate-400">
                            {lead.seniority} • {lead.department}
                          </span>
                        </div>
                      </TableCell>

                      {/* Job Title */}
                      <TableCell className="font-medium text-slate-700 text-xs sm:text-sm">
                        {lead.jobTitle}
                      </TableCell>

                      {/* Company */}
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="font-semibold text-slate-800 text-xs sm:text-sm flex items-center gap-1.5">
                            <Building className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                            {lead.company}
                          </span>
                          <span className="text-[11px] text-slate-400">
                            {lead.industry} • {lead.companySize} emp
                          </span>
                        </div>
                      </TableCell>

                      {/* Location */}
                      <TableCell>
                        <span className="text-xs text-slate-600 flex items-center gap-1">
                          <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                          {lead.location}
                        </span>
                      </TableCell>

                      {/* Email */}
                      <TableCell>
                        <span className="font-mono text-xs text-slate-600 select-all">
                          {lead.email}
                        </span>
                      </TableCell>

                      {/* Lead Score */}
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {lead.leadScore !== null ? (
                            <span
                              className={`text-xs font-bold px-2 py-0.5 rounded border ${
                                lead.leadScore >= 85
                                  ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                  : lead.leadScore >= 65
                                  ? "bg-amber-50 text-amber-700 border-amber-200"
                                  : "bg-slate-100 text-slate-600 border-slate-200"
                              }`}
                            >
                              {lead.leadScore}
                            </span>
                          ) : (
                            <span className="text-xs font-medium px-2 py-0.5 rounded border bg-slate-50 text-slate-400 border-slate-200">
                              Unscored
                            </span>
                          )}
                        </div>
                      </TableCell>

                      {/* Temperature Badge */}
                      <TableCell>
                        {lead.temperature === "HOT" && (
                          <Badge variant="coral" dot>
                            HOT
                          </Badge>
                        )}
                        {lead.temperature === "WARM" && (
                          <Badge variant="peach" dot>
                            WARM
                          </Badge>
                        )}
                        {lead.temperature === "COLD" && (
                          <Badge variant="neutral">COLD</Badge>
                        )}
                        {lead.temperature === "UNASSESSED" && (
                          <span className="text-xs text-slate-400 font-mono">—</span>
                        )}
                      </TableCell>

                      {/* Row Action */}
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setSelectedIds(new Set([lead.id]));
                            setIsCampaignModalOpen(true);
                          }}
                          className="h-7 text-xs text-agile-red hover:bg-agile-lightorange hover:text-agile-red"
                        >
                          Enroll
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>

            <Pagination
              currentPage={currentPage}
              totalPages={Math.ceil(filteredProspects.length / pageSize) || 1}
              onPageChange={setCurrentPage}
            />
          </div>
        )}
      </div>

      {/* 7. Add to Campaign Modal Dialog */}
      <Modal
        isOpen={isCampaignModalOpen}
        onClose={() => setIsCampaignModalOpen(false)}
        title="Add Selected Leads to Campaign"
        description={`You have ${selectedIds.size || 1} lead(s) selected for enrollment.`}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setIsCampaignModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                setIsCampaignModalOpen(false);
                setSelectedIds(new Set());
              }}
              className="inline-flex items-center gap-1.5"
            >
              <Send className="w-3.5 h-3.5" />
              <span>Enroll In Campaign</span>
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Select
            label="Target Outreach Campaign"
            options={[
              {
                value: "illinois-midmarket-sdr",
                label: "Illinois Mid-Market, Voice SDR Follow-Up (Active)",
              },
              {
                value: "enterprise-ar-execs",
                label: "Enterprise AR Executives Outbound SDR",
              },
            ]}
          />

          <Select
            label="Channel Cadence"
            options={[
              {
                value: "voice-sdr-ses",
                label: "Retell Voice SDR + Instant Amazon SES Email Follow-Up",
              },
              {
                value: "ses-email-first",
                label: "Amazon SES Email First, Voice SDR Escalation",
              },
            ]}
          />

          <div className="rounded-lg bg-slate-50 p-3 border border-slate-200 text-xs text-slate-600">
            <strong>Source of Truth Protection:</strong> All prospect email addresses and contact names will be preserved as primary record identifiers during voice webhook synchronization.
          </div>
        </div>
      </Modal>
    </AppShell>
  );
}
