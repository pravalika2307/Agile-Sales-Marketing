"use client";

import * as React from "react";
import { ContactListItem } from "@/services/contactListService";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Users,
  Building2,
  FileSpreadsheet,
  UserCheck,
  FolderOpen,
  Search,
  Plus,
  RefreshCw,
  Send,
  Calendar,
  ArrowRight,
  Filter,
  Layers,
  Sparkles,
  Edit2,
  Trash2,
  TableProperties,
} from "lucide-react";

export interface LeadListsViewProps {
  lists: ContactListItem[];
  isLoading: boolean;
  onOpenList: (listId: string) => void;
  onSyncSources: () => Promise<void>;
  isSyncingSources: boolean;
  onCreateListOpen: () => void;
  onImportCsvOpen: () => void;
  onAddLeadOpen: () => void;
  onBrowseAllLeads: () => void;
  onEditList: (list: ContactListItem) => void;
  onDeleteList: (list: ContactListItem) => void;
}

export const LeadListsView: React.FC<LeadListsViewProps> = ({
  lists,
  isLoading,
  onOpenList,
  onSyncSources,
  isSyncingSources,
  onCreateListOpen,
  onImportCsvOpen,
  onAddLeadOpen,
  onBrowseAllLeads,
  onEditList,
  onDeleteList,
}) => {
  const [searchQuery, setSearchQuery] = React.useState("");
  const [activeCategory, setActiveCategory] = React.useState<"ALL" | "source" | "industry" | "custom">("ALL");

  // Filter lists
  const filteredLists = React.useMemo(() => {
    return lists.filter((item) => {
      // Category filter
      if (activeCategory === "source" && item.type !== "source") return false;
      if (activeCategory === "industry" && item.type !== "industry") return false;
      if (activeCategory === "custom" && (item.type === "source" || item.type === "industry")) return false;

      // Search filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchName = item.name.toLowerCase().includes(q);
        const matchDesc = item.description?.toLowerCase().includes(q) ?? false;
        if (!matchName && !matchDesc) return false;
      }

      return true;
    });
  }, [lists, activeCategory, searchQuery]);

  // Aggregate metrics
  const totalMembers = React.useMemo(() => {
    return lists.reduce((sum, item) => sum + (item.member_count || 0), 0);
  }, [lists]);

  const sourceListsCount = React.useMemo(() => {
    return lists.filter((l) => l.type === "source").length;
  }, [lists]);

  const industryListsCount = React.useMemo(() => {
    return lists.filter((l) => l.type === "industry").length;
  }, [lists]);

  const customListsCount = React.useMemo(() => {
    return lists.filter((l) => l.type !== "source" && l.type !== "industry").length;
  }, [lists]);

  // Helper for list styling & icons
  const getListMeta = (item: ContactListItem) => {
    const lowerName = item.name.toLowerCase();
    if (lowerName.includes("hubspot")) {
      return {
        badgeVariant: "warning" as const,
        badgeText: "HubSpot CRM",
        icon: Users,
        iconBg: "bg-amber-50 text-amber-600 border-amber-200",
        borderHighlight: "hover:border-amber-300",
      };
    }
    if (lowerName.includes("csv") || lowerName.includes("import")) {
      return {
        badgeVariant: "peach" as const,
        badgeText: "CSV Import",
        icon: FileSpreadsheet,
        iconBg: "bg-purple-50 text-purple-600 border-purple-200",
        borderHighlight: "hover:border-purple-300",
      };
    }
    if (lowerName.includes("manual")) {
      return {
        badgeVariant: "info" as const,
        badgeText: "Manual CRM",
        icon: UserCheck,
        iconBg: "bg-blue-50 text-blue-600 border-blue-200",
        borderHighlight: "hover:border-blue-300",
      };
    }
    if (item.type === "industry") {
      return {
        badgeVariant: "success" as const,
        badgeText: "Industry Segment",
        icon: Building2,
        iconBg: "bg-emerald-50 text-emerald-600 border-emerald-200",
        borderHighlight: "hover:border-emerald-300",
      };
    }
    return {
      badgeVariant: "neutral" as const,
      badgeText: "Custom List",
      icon: FolderOpen,
      iconBg: "bg-slate-100 text-slate-700 border-slate-200",
      borderHighlight: "hover:border-slate-300",
    };
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-16">
      {/* 1. Header Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-100">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-header">
            Leads
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Review and organize prospect leads by verified sources, industry segments, and targeted lists.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            onClick={onSyncSources}
            disabled={isSyncingSources}
            className="text-xs inline-flex items-center gap-1.5 border-slate-200 hover:bg-slate-50"
            title="Automatically group existing CRM leads into their respective source and industry lists"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-slate-600 ${isSyncingSources ? "animate-spin" : ""}`} />
            <span>{isSyncingSources ? "Syncing..." : "Sync Sources"}</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={onImportCsvOpen}
            className="text-xs inline-flex items-center gap-1.5 border-slate-200 hover:bg-slate-50"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-slate-600" />
            <span>Import CSV</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={onAddLeadOpen}
            className="text-xs inline-flex items-center gap-1.5 border-slate-200 hover:bg-slate-50"
          >
            <Plus className="w-3.5 h-3.5 text-slate-600" />
            <span>Add Lead</span>
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={onCreateListOpen}
            className="text-xs inline-flex items-center gap-1.5 bg-agile-red hover:bg-agile-red/90 text-white shadow-xs"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Create List</span>
          </Button>
        </div>
      </div>

      {/* 2. KPI Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card className="border-slate-200 shadow-xs">
          <CardContent className="p-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              Total Lists
            </p>
            <p className="text-2xl font-bold text-header mt-1">
              {lists.length}
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Organized lead groups
            </p>
          </CardContent>
        </Card>

        <Card className="border-slate-200 shadow-xs">
          <CardContent className="p-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              Source Lists
            </p>
            <p className="text-2xl font-bold text-amber-600 mt-1">
              {sourceListsCount}
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              HubSpot, CSV, & Manual leads
            </p>
          </CardContent>
        </Card>

        <Card className="border-slate-200 shadow-xs">
          <CardContent className="p-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              Industry Segments
            </p>
            <p className="text-2xl font-bold text-emerald-600 mt-1">
              {industryListsCount}
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Verified domain categories
            </p>
          </CardContent>
        </Card>

        <Card className="border-slate-200 shadow-xs">
          <CardContent className="p-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              Custom Lists
            </p>
            <p className="text-2xl font-bold text-blue-600 mt-1">
              {customListsCount}
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Targeted campaign lists
            </p>
          </CardContent>
        </Card>
      </div>

      {/* 3. Search and Category Filter Tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Category Tabs */}
        <div className="flex items-center gap-1.5 p-1 bg-slate-100 rounded-lg text-xs font-medium overflow-x-auto">
          <button
            onClick={() => setActiveCategory("ALL")}
            className={`px-3 py-1.5 rounded-md transition-all ${
              activeCategory === "ALL"
                ? "bg-white text-header shadow-xs font-semibold"
                : "text-slate-600 hover:text-header"
            }`}
          >
            All Lists ({lists.length})
          </button>
          <button
            onClick={() => setActiveCategory("source")}
            className={`px-3 py-1.5 rounded-md transition-all ${
              activeCategory === "source"
                ? "bg-white text-header shadow-xs font-semibold"
                : "text-slate-600 hover:text-header"
            }`}
          >
            Source Lists ({sourceListsCount})
          </button>
          <button
            onClick={() => setActiveCategory("industry")}
            className={`px-3 py-1.5 rounded-md transition-all ${
              activeCategory === "industry"
                ? "bg-white text-header shadow-xs font-semibold"
                : "text-slate-600 hover:text-header"
            }`}
          >
            Industry Lists ({industryListsCount})
          </button>
          <button
            onClick={() => setActiveCategory("custom")}
            className={`px-3 py-1.5 rounded-md transition-all ${
              activeCategory === "custom"
                ? "bg-white text-header shadow-xs font-semibold"
                : "text-slate-600 hover:text-header"
            }`}
          >
            Custom Lists ({customListsCount})
          </button>
        </div>

        {/* Search Input & Browse All Leads link */}
        <div className="flex items-center gap-2">
          <div className="relative w-full sm:w-64">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input
              type="text"
              placeholder="Search lists..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 h-9 text-xs"
            />
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={onBrowseAllLeads}
            className="text-xs text-slate-600 hover:text-header shrink-0 hidden md:inline-flex items-center gap-1"
            title="Switch to unorganized individual leads view"
          >
            <TableProperties className="w-3.5 h-3.5 text-slate-500" />
            <span>All Leads Table</span>
          </Button>
        </div>
      </div>

      {/* 4. Lists Vertical Row Display */}
      {isLoading ? (
        <div className="bg-white rounded-xl border border-slate-200 divide-y divide-slate-100 shadow-xs overflow-hidden">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="p-4 flex items-center justify-between animate-pulse">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-slate-200" />
                <div className="space-y-1.5">
                  <div className="h-4 w-40 bg-slate-200 rounded" />
                  <div className="h-3 w-24 bg-slate-100 rounded" />
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="h-4 w-16 bg-slate-100 rounded" />
                <div className="h-8 w-24 bg-slate-100 rounded" />
              </div>
            </div>
          ))}
        </div>
      ) : filteredLists.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center space-y-4 shadow-xs">
          <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mx-auto text-slate-400">
            <Filter className="w-6 h-6" />
          </div>
          <div className="space-y-1 max-w-md mx-auto">
            <h3 className="text-sm font-bold text-header">No lead lists found</h3>
            <p className="text-xs text-slate-500">
              {searchQuery
                ? `No lists matched "${searchQuery}". Try adjusting your search query.`
                : "Sync your sources or create your first targeted list to organize your prospect audience."}
            </p>
          </div>
          <div className="flex items-center justify-center gap-2 pt-2">
            <Button
              variant="outline"
              size="sm"
              onClick={onSyncSources}
              disabled={isSyncingSources}
              className="text-xs inline-flex items-center gap-1.5"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-slate-600 ${isSyncingSources ? "animate-spin" : ""}`} />
              <span>Sync Sources</span>
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={onCreateListOpen}
              className="text-xs bg-agile-red hover:bg-agile-red/90 text-white"
            >
              <Plus className="w-3.5 h-3.5 mr-1" />
              <span>Create List</span>
            </Button>
          </div>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 divide-y divide-slate-100 shadow-xs overflow-hidden">
          {filteredLists.map((item, index) => {
            const meta = getListMeta(item);
            const IconComponent = meta.icon;

            return (
              <div
                key={item.id}
                onClick={() => onOpenList(item.id)}
                className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/80 transition-colors cursor-pointer group"
              >
                {/* Left: Index, Icon, Name, Badge, Description */}
                <div className="flex items-start sm:items-center gap-3 min-w-0">
                  <span className="text-xs font-mono text-slate-400 w-5 shrink-0 hidden sm:inline-block">
                    {index + 1}.
                  </span>
                  <div className={`w-9 h-9 rounded-lg border flex items-center justify-center shrink-0 ${meta.iconBg}`}>
                    <IconComponent className="w-4 h-4" />
                  </div>
                  <div className="min-w-0 space-y-0.5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-sm text-header group-hover:text-agile-red transition-colors truncate">
                        {item.name}
                      </span>
                      <Badge variant={meta.badgeVariant} className="text-[10px] shrink-0">
                        {meta.badgeText}
                      </Badge>
                    </div>
                    {item.description && (
                      <p className="text-xs text-slate-500 truncate max-w-xl">
                        {item.description}
                      </p>
                    )}
                  </div>
                </div>

                {/* Right: Member count, Campaigns, Edit/Delete, Open List */}
                <div className="flex items-center gap-3 sm:gap-5 shrink-0 self-end sm:self-center">
                  <div className="flex items-center gap-3 text-xs text-slate-600 font-medium">
                    <div className="flex items-center gap-1.5" title="List members">
                      <Users className="w-3.5 h-3.5 text-slate-400" />
                      <span className="font-semibold text-slate-700">
                        {item.member_count.toLocaleString()}
                      </span>
                      <span className="text-slate-400 font-normal">
                        {item.member_count === 1 ? "lead" : "leads"}
                      </span>
                    </div>

                    {item.campaigns_count > 0 && (
                      <div className="flex items-center gap-1 text-blue-600 bg-blue-50 px-2 py-0.5 rounded text-[11px]" title="Associated campaigns">
                        <Send className="w-3 h-3" />
                        <span>{item.campaigns_count}</span>
                      </div>
                    )}
                  </div>

                  {/* Actions for custom lists */}
                  {item.type !== "source" && item.type !== "industry" && (
                    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => onEditList(item)}
                        className="p-1 rounded text-slate-400 hover:text-slate-600 hover:bg-slate-100"
                        title="Edit List"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => onDeleteList(item)}
                        className="p-1 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-50"
                        title="Delete List"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenList(item.id);
                    }}
                    className="text-xs font-semibold text-agile-red hover:text-agile-red hover:bg-rose-50/50 inline-flex items-center gap-1 px-3 h-8 shrink-0"
                  >
                    <span>Open List</span>
                    <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
