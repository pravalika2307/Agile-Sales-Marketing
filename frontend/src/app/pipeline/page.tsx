"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { DealDetailDrawer } from "@/components/pipeline/deal-detail-drawer";
import { CreateDealModal } from "@/components/pipeline/create-deal-modal";
import {
  DealItem,
  PipelineStageItem,
  PipelineItem,
  DealStatus,
  AvailableContact,
  computePipelineMetrics,
  formatCurrency,
  DealCreatePayload,
  fetchPipelines,
  fetchDeals,
  createDeal,
  moveDealStage,
  updateDealStatus,
  deleteDeal,
  fetchAvailableContacts,
} from "@/services/pipelineService";
import {
  Plus,
  Search,
  RotateCcw,
  Layers,
  KanbanSquare,
  Calendar,
  User,
  Building2,
  RefreshCw,
} from "lucide-react";

export default function PipelinePage() {
  // Pipelines & Stages state
  const [pipelines, setPipelines] = React.useState<PipelineItem[]>([]);
  const [selectedPipelineId, setSelectedPipelineId] = React.useState<string>("");
  const [deals, setDeals] = React.useState<DealItem[]>([]);
  const [availableContacts, setAvailableContacts] = React.useState<AvailableContact[]>([]);
  const [isLoading, setIsLoading] = React.useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = React.useState<boolean>(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  // Active pipeline object and stages
  const activePipeline = React.useMemo(() => {
    return pipelines.find((p) => p.id === selectedPipelineId) || pipelines[0] || null;
  }, [pipelines, selectedPipelineId]);

  const stages = React.useMemo(() => {
    return activePipeline?.stages || [];
  }, [activePipeline]);

  // Filters & Search
  const [searchQuery, setSearchQuery] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState<string>("ALL");

  // Drawer & Modal state
  const [inspectedDeal, setInspectedDeal] = React.useState<DealItem | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = React.useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = React.useState(false);

  // Drag and drop state
  const [draggingDealId, setDraggingDealId] = React.useState<string | null>(null);

  // Load pipelines, contacts, and initial deals from live API
  const loadInitialData = React.useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const [pipelinesData, contactsData] = await Promise.all([
        fetchPipelines(),
        fetchAvailableContacts(),
      ]);

      setPipelines(pipelinesData);
      setAvailableContacts(contactsData);

      const defaultPipe = pipelinesData.find((p) => p.isDefault) || pipelinesData[0] || null;
      if (defaultPipe) {
        setSelectedPipelineId(defaultPipe.id);
        const dealsData = await fetchDeals({ pipelineId: defaultPipe.id });
        setDeals(dealsData);
      } else {
        const dealsData = await fetchDeals();
        setDeals(dealsData);
      }
    } catch (err: unknown) {
      console.error("PipelinePage: Error loading initial data:", err);
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to load pipeline data from backend."
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  // Refresh deals for active pipeline
  const refreshDeals = async () => {
    if (!activePipeline) return;
    setIsRefreshing(true);
    try {
      const dealsData = await fetchDeals({ pipelineId: activePipeline.id });
      setDeals(dealsData);
    } catch (err) {
      console.error("Error refreshing deals:", err);
    } finally {
      setIsRefreshing(false);
    }
  };

  // Pipeline selection switch
  const handlePipelineChange = async (newPipelineId: string) => {
    setSelectedPipelineId(newPipelineId);
    setIsRefreshing(true);
    try {
      const dealsData = await fetchDeals({ pipelineId: newPipelineId });
      setDeals(dealsData);
    } catch (err) {
      console.error("Error switching pipeline:", err);
    } finally {
      setIsRefreshing(false);
    }
  };

  // Calculate factual pipeline operational metrics
  const metrics = React.useMemo(() => {
    return computePipelineMetrics(deals);
  }, [deals]);

  // Filter deals
  const filteredDeals = React.useMemo(() => {
    return deals.filter((d) => {
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchName = d.name.toLowerCase().includes(q);
        const matchContact = (d.contactName || "").toLowerCase().includes(q);
        const matchCompany = (d.companyName || "").toLowerCase().includes(q);
        if (!matchName && !matchContact && !matchCompany) return false;
      }
      if (statusFilter !== "ALL") {
        if (d.status !== statusFilter) return false;
      }
      return true;
    });
  }, [deals, searchQuery, statusFilter]);

  // Handlers for Deal Actions with live API persistence
  const handleOpenDetail = (deal: DealItem) => {
    setInspectedDeal(deal);
    setIsDrawerOpen(true);
  };

  const handleStageMove = async (dealId: string, targetStageId: string) => {
    // Optimistic UI update
    setDeals((prev) =>
      prev.map((d) => {
        if (d.id === dealId) {
          const updated = {
            ...d,
            pipelineStageId: targetStageId,
            updatedAt: new Date().toISOString(),
          };
          if (inspectedDeal && inspectedDeal.id === dealId) {
            setInspectedDeal(updated);
          }
          return updated;
        }
        return d;
      })
    );

    try {
      const persisted = await moveDealStage(dealId, targetStageId);
      setDeals((prev) =>
        prev.map((d) => (d.id === dealId ? persisted : d))
      );
      if (inspectedDeal && inspectedDeal.id === dealId) {
        setInspectedDeal(persisted);
      }
    } catch (err) {
      console.error("Failed to persist deal stage move:", err);
      // Re-sync with backend
      refreshDeals();
    }
  };

  const handleStatusChange = async (dealId: string, newStatus: DealStatus) => {
    // Optimistic UI update
    setDeals((prev) =>
      prev.map((d) => {
        if (d.id === dealId) {
          const updated = {
            ...d,
            status: newStatus,
            updatedAt: new Date().toISOString(),
          };
          if (inspectedDeal && inspectedDeal.id === dealId) {
            setInspectedDeal(updated);
          }
          return updated;
        }
        return d;
      })
    );

    try {
      const persisted = await updateDealStatus(dealId, newStatus);
      setDeals((prev) =>
        prev.map((d) => (d.id === dealId ? persisted : d))
      );
      if (inspectedDeal && inspectedDeal.id === dealId) {
        setInspectedDeal(persisted);
      }
    } catch (err) {
      console.error("Failed to persist deal status update:", err);
      refreshDeals();
    }
  };

  const handleDeleteDeal = async (dealId: string) => {
    try {
      await deleteDeal(dealId);
      setDeals((prev) => prev.filter((d) => d.id !== dealId));
      setIsDrawerOpen(false);
      setInspectedDeal(null);
    } catch (err) {
      console.error("Failed to delete deal:", err);
      alert("Failed to delete deal from backend.");
    }
  };

  const handleCreateDeal = async (payload: DealCreatePayload) => {
    try {
      const created = await createDeal(payload);
      setDeals((prev) => [created, ...prev]);
      setIsCreateModalOpen(false);
    } catch (err: unknown) {
      console.error("Failed to create deal:", err);
      alert(err instanceof Error ? err.message : "Failed to create deal.");
    }
  };

  const handleResetFilters = () => {
    setSearchQuery("");
    setStatusFilter("ALL");
  };

  // Drag and Drop handlers
  const handleDragStart = (e: React.DragEvent, dealId: string) => {
    setDraggingDealId(dealId);
    e.dataTransfer.setData("text/plain", dealId);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent, stageId: string) => {
    e.preventDefault();
    const dealId = e.dataTransfer.getData("text/plain") || draggingDealId;
    if (dealId) {
      handleStageMove(dealId, stageId);
    }
    setDraggingDealId(null);
  };

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl font-bold tracking-tight text-header">
                Pipeline
              </h1>
              {pipelines.length > 1 ? (
                <div className="w-56">
                  <Select
                    value={activePipeline?.id || ""}
                    onChange={(e) => handlePipelineChange(e.target.value)}
                    className="text-xs h-7 py-0"
                  >
                    {pipelines.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} {p.isDefault ? "(Default)" : ""}
                      </option>
                    ))}
                  </Select>
                </div>
              ) : (
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-agile-lightorange text-agile-red border border-agile-outlinered/30 flex items-center gap-1.5">
                  <Layers className="w-3 h-3 text-agile-red" />
                  {activePipeline?.name || "Default Sales Pipeline"}
                </span>
              )}
            </div>
            <p className="text-sm text-secondary-text mt-1">
              Track and manage commercial sales opportunities through live pipeline stages.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={refreshDeals}
              disabled={isRefreshing}
              className="border-slate-200 text-slate-700 hover:bg-slate-50 text-xs h-8"
              title="Refresh deals"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1 ${isRefreshing ? "animate-spin" : ""}`} />
              Refresh
            </Button>
            <Button
              onClick={() => setIsCreateModalOpen(true)}
              className="bg-agile-red hover:bg-agile-red/90 text-white font-medium text-xs shadow-xs h-8"
            >
              <Plus className="w-3.5 h-3.5 mr-1.5" />
              + Create Deal
            </Button>
          </div>
        </div>

        {errorMessage && (
          <div className="bg-rose-50 border border-rose-200 text-rose-700 text-xs p-3 rounded-lg flex items-center justify-between">
            <span>{errorMessage}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={loadInitialData}
              className="text-rose-700 hover:text-rose-900 text-xs h-6 px-2"
            >
              Retry
            </Button>
          </div>
        )}

        {/* Factual Pipeline Summary Cards (Strict Zero-Fabrication Policy) */}
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <Card className="border-slate-200 shadow-xs bg-white">
            <CardContent className="p-3.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
                Total Deals
              </span>
              <div className="text-xl font-bold text-header mt-1">
                {metrics.totalDeals}
              </div>
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                Factual opportunity records
              </span>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-xs bg-white">
            <CardContent className="p-3.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
                Open Deals
              </span>
              <div className="text-xl font-bold text-sky-700 mt-1">
                {metrics.openDeals}
              </div>
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                Active in pipeline
              </span>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-xs bg-white">
            <CardContent className="p-3.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
                Won Deals
              </span>
              <div className="text-xl font-bold text-emerald-700 mt-1">
                {metrics.wonDeals}
              </div>
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                Closed won
              </span>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-xs bg-white">
            <CardContent className="p-3.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
                Lost Deals
              </span>
              <div className="text-xl font-bold text-slate-700 mt-1">
                {metrics.lostDeals}
              </div>
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                Closed lost
              </span>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-xs bg-white">
            <CardContent className="p-3.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
                Open Pipeline
              </span>
              <div className="text-xl font-bold text-header mt-1">
                {formatCurrency(metrics.totalPipelineValue)}
              </div>
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                Active opportunities
              </span>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-xs bg-white">
            <CardContent className="p-3.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-600 block">
                Closed-Won Revenue
              </span>
              <div className="text-xl font-bold text-emerald-700 mt-1">
                {formatCurrency(metrics.wonRevenue)}
              </div>
              <span className="text-[11px] text-slate-400 mt-0.5 block">
                Verified won deals
              </span>
            </CardContent>
          </Card>
        </div>

        {/* Global Empty State Banner: Displayed when 0 deals exist in the database */}
        {!isLoading && deals.length === 0 && (
          <Card className="border-slate-200 shadow-xs bg-white text-center py-12 px-6">
            <div className="max-w-md mx-auto space-y-3.5">
              <div className="w-12 h-12 rounded-full bg-agile-lightorange text-agile-red flex items-center justify-center mx-auto border border-agile-outlinered/30">
                <KanbanSquare className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-header">
                  No opportunities yet
                </h3>
                <p className="text-xs text-secondary-text mt-1 leading-relaxed">
                  Deals will appear here when prospects are converted into opportunities.
                  Use the pipeline stages below to track commercial deals.
                </p>
              </div>
              <div className="flex items-center justify-center gap-3 pt-1">
                <Button
                  onClick={() => setIsCreateModalOpen(true)}
                  className="bg-agile-red hover:bg-agile-red/90 text-white font-medium text-xs h-8 px-3"
                >
                  <Plus className="w-3.5 h-3.5 mr-1" />
                  + Create Deal
                </Button>
                <Link href="/leads">
                  <Button
                    variant="outline"
                    className="border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-medium h-8 px-3"
                  >
                    Go to Leads
                  </Button>
                </Link>
              </div>
            </div>
          </Card>
        )}

        {/* Filter Controls Bar (Visible when deals exist) */}
        {deals.length > 0 && (
          <Card className="border-slate-200 shadow-xs bg-white">
            <CardContent className="p-3.5">
              <div className="flex flex-col sm:flex-row gap-3 items-center">
                <div className="relative flex-1 w-full">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <Input
                    type="text"
                    placeholder="Search opportunity by name or contact..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9 text-xs h-9"
                  />
                </div>

                <div className="w-full sm:w-48">
                  <Select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="text-xs h-9"
                  >
                    <option value="ALL">All Statuses</option>
                    <option value="open">Open Deals</option>
                    <option value="won">Won Deals</option>
                    <option value="lost">Lost Deals</option>
                  </Select>
                </div>

                {(searchQuery || statusFilter !== "ALL") && (
                  <Button
                    variant="ghost"
                    onClick={handleResetFilters}
                    className="text-xs text-slate-500 hover:text-slate-800 h-9 px-2.5 shrink-0"
                  >
                    <RotateCcw className="w-3.5 h-3.5 mr-1" />
                    Reset
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Kanban Board Container */}
        <div className="overflow-x-auto pb-4">
          <div className="min-w-[1000px] grid grid-cols-5 gap-3.5 items-start">
            {stages.map((stage) => {
              const stageDeals = filteredDeals.filter(
                (d) => d.pipelineStageId === stage.id
              );
              const stageTotalAmount = stageDeals
                .filter((d) => d.status !== "lost")
                .reduce((acc, d) => acc + (d.amount || 0), 0);

              return (
                <div
                  key={stage.id}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, stage.id)}
                  className="bg-slate-50/70 border border-slate-200 rounded-xl p-3 flex flex-col min-h-[480px] transition-colors hover:border-slate-300"
                >
                  {/* Stage Header */}
                  <div className="pb-3 border-b border-slate-200/80 mb-3">
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <div className="flex items-center gap-1.5 truncate">
                        <span className="w-2 h-2 rounded-full bg-agile-red shrink-0" />
                        <h3 className="text-xs font-bold text-header truncate" title={stage.name}>
                          {stage.name}
                        </h3>
                      </div>
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-white border border-slate-200 text-slate-600 shrink-0">
                        {stage.probabilityPct}%
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1">
                      <span>{stageDeals.length} deals</span>
                      <span className="font-semibold text-slate-700">
                        {formatCurrency(stageTotalAmount)}
                      </span>
                    </div>
                  </div>

                  {/* Deals List */}
                  <div className="space-y-2.5 flex-1">
                    {stageDeals.length === 0 ? (
                      <div className="h-32 border border-dashed border-slate-200 rounded-lg flex flex-col items-center justify-center p-3 text-center">
                        <p className="text-[11px] text-slate-400">
                          No deals in {stage.name}
                        </p>
                        <p className="text-[10px] text-slate-300 mt-0.5">
                          Drag opportunities here
                        </p>
                      </div>
                    ) : (
                      stageDeals.map((deal) => (
                        <div
                          key={deal.id}
                          draggable
                          onDragStart={(e) => handleDragStart(e, deal.id)}
                          onClick={() => handleOpenDetail(deal)}
                          className="bg-white border border-slate-200 rounded-lg p-3 shadow-xs hover:shadow-sm hover:border-agile-red/50 transition-all cursor-pointer group space-y-2 select-none"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <h4 className="text-xs font-semibold text-header group-hover:text-agile-red transition-colors leading-tight">
                              {deal.name}
                            </h4>
                            {deal.status === "won" && (
                              <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px] px-1.5 py-0">
                                Won
                              </Badge>
                            )}
                            {deal.status === "lost" && (
                              <Badge className="bg-rose-50 text-rose-700 border-rose-200 text-[10px] px-1.5 py-0">
                                Lost
                              </Badge>
                            )}
                          </div>

                          <div className="text-sm font-bold text-header">
                            {formatCurrency(deal.amount)}
                          </div>

                          <div className="pt-1 border-t border-slate-100 space-y-1 text-[11px] text-slate-500">
                            {deal.contactName && (
                              <div className="flex items-center gap-1.5 truncate">
                                <User className="w-3 h-3 text-slate-400 shrink-0" />
                                <span className="truncate">{deal.contactName}</span>
                              </div>
                            )}
                            {deal.companyName && (
                              <div className="flex items-center gap-1.5 truncate">
                                <Building2 className="w-3 h-3 text-slate-400 shrink-0" />
                                <span className="truncate">{deal.companyName}</span>
                              </div>
                            )}
                            {deal.expectedCloseDate && (
                              <div className="flex items-center gap-1.5 text-slate-400">
                                <Calendar className="w-3 h-3 text-slate-400 shrink-0" />
                                <span>{deal.expectedCloseDate}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Deal Detail Drawer */}
      <DealDetailDrawer
        deal={inspectedDeal}
        stages={stages}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        onStageChange={handleStageMove}
        onStatusChange={handleStatusChange}
        onDeleteDeal={handleDeleteDeal}
      />

      {/* Create Deal Modal */}
      <CreateDealModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        stages={stages}
        contacts={availableContacts}
        onCreateDeal={handleCreateDeal}
      />
    </AppShell>
  );
}
