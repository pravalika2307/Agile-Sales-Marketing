"use client";

import React, { useEffect, useState } from "react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  FileText,
  Mail,
  RefreshCw,
  Send,
  ShieldCheck,
  Truck,
  Layers,
  Link2,
  PlusCircle,
  Sparkles,
  Clock,
  DollarSign,
  Palette,
  Check,
} from "lucide-react";
import {
  approveAndSubmitPhysicalMail,
  configurePhysicalMailCampaign,
  getCampaignPhysicalMailConfig,
  getPhysicalMailOptions,
  getPhysicalMailStatus,
  getPoplarCampaigns,
  getPoplarCreatives,
  type PoplarCampaignItem,
  validateCreativeAsset,
  previewCampaignPhysicalMail,
  syncCampaignPhysicalMail,
  validateCampaignPhysicalMail,
  type PhysicalMailOptions,
  type PhysicalMailPreviewResponse,
  type PhysicalMailStatus,
  type PhysicalMailSubmissionResponse,
  type PhysicalMailValidateResponse,
  type PoplarCreativeItem,
  type CreativeValidateResponse,
} from "@/services/physicalMailService";

interface PhysicalMailPreflightModalProps {
  isOpen: boolean;
  onClose: () => void;
  campaignId: string;
  campaignName: string;
  recipientIds?: string[];
  onCompleted?: () => void;
}

export function PhysicalMailPreflightModal({
  isOpen,
  onClose,
  campaignId,
  campaignName,
  recipientIds,
  onCompleted,
}: PhysicalMailPreflightModalProps) {
  // Step state: "configure" | "validate" | "preview" | "submitted"
  const [activeStep, setActiveStep] = useState<"configure" | "validate" | "preview" | "submitted">("configure");

  // Config & Provider Status
  const [poplarStatus, setPoplarStatus] = useState<PhysicalMailStatus | null>(null);
  const [optionsData, setOptionsData] = useState<PhysicalMailOptions | null>(null);

  // Mailpiece Form State
  const [mailpieceSize, setMailpieceSize] = useState<string>("4x6");
  const [formatType, setFormatType] = useState<string>("postcard");
  const [paperType, setPaperType] = useState<string>("premium_coated");
  const [postageClass, setPostageClass] = useState<string>("usps_first_class");
  const [designName, setDesignName] = useState<string>("Agile Direct Mail Creative");
  const [designUrl, setDesignUrl] = useState<string>("https://assets.heypoplar.com/templates/sample-postcard-proof.pdf");

  // Poplar Remote Resource State
  const [workflowMode, setWorkflowMode] = useState<"connect" | "create">("connect");
  const [newCampaignName, setNewCampaignName] = useState<string>(() => `Agile - ${campaignName || "Campaign"}`);
  const [newCampaignPurpose, setNewCampaignPurpose] = useState<string>("retention");
  const [newCampaignSubPurpose, setNewCampaignSubPurpose] = useState<string>("reactivation");
  const [newCampaignDescription, setNewCampaignDescription] = useState<string>("");
  const [showConfirmCreate, setShowConfirmCreate] = useState<boolean>(false);
  const [recoveryCampaignId, setRecoveryCampaignId] = useState<string | null>(null);
  const [poplarCampaignId, setPoplarCampaignId] = useState<string>("");
  const [poplarCreativeId, setPoplarCreativeId] = useState<string>("");
  const [poplarRemoteName, setPoplarRemoteName] = useState<string>("");
  const [isConfiguring, setIsConfiguring] = useState<boolean>(false);
  const [isConfigured, setIsConfigured] = useState<boolean>(false);

  // Poplar Account Campaigns Discovery State
  const [poplarCampaigns, setPoplarCampaigns] = useState<PoplarCampaignItem[]>([]);
  const [isLoadingCampaigns, setIsLoadingCampaigns] = useState<boolean>(false);
  const [campaignsError, setCampaignsError] = useState<string | null>(null);

  // Poplar Creative Library State
  const [creatives, setCreatives] = useState<PoplarCreativeItem[]>([]);
  const [isLoadingCreatives, setIsLoadingCreatives] = useState<boolean>(false);
  const [customFileName, setCustomFileName] = useState<string>("agile-mailpiece.pdf");
  const [artworkValidation, setArtworkValidation] = useState<CreativeValidateResponse | null>(null);
  const [isValidatingArtwork, setIsValidatingArtwork] = useState<boolean>(false);

  // Validation State
  const [isValidating, setIsValidating] = useState<boolean>(false);
  const [validationReport, setValidationReport] = useState<PhysicalMailValidateResponse | null>(null);
  const [activeRecipientTab, setActiveRecipientTab] = useState<"valid" | "invalid">("valid");

  // Preview State
  const [isPreviewing, setIsPreviewing] = useState<boolean>(false);
  const [previewResult, setPreviewResult] = useState<PhysicalMailPreviewResponse | null>(null);
  const [isExplicitlyApproved, setIsExplicitlyApproved] = useState<boolean>(false);
  const [approvalToken, setApprovalToken] = useState<string>(() => `apr_${Math.random().toString(36).substring(2, 10)}`);

  // Submission State
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submissionResult, setSubmissionResult] = useState<PhysicalMailSubmissionResponse | null>(null);

  // Sync State
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  // Global Error state
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successNotice, setSuccessNotice] = useState<string | null>(null);

  // Load provider options and existing campaign configuration on open
  useEffect(() => {
    if (isOpen) {
      setErrorMessage(null);
      setSuccessNotice(null);
      setSyncMessage(null);
      setRecoveryCampaignId(null);
      setShowConfirmCreate(false);
      setNewCampaignName(`Agile - ${campaignName || "Campaign"}`);

      // Load Poplar status
      getPhysicalMailStatus()
        .then((status) => {
          setPoplarStatus(status);
        })
        .catch(() => {});

      // Load supported options
      getPhysicalMailOptions()
        .then((opts) => setOptionsData(opts))
        .catch(() => {});

      // Load existing Poplar Campaigns (read-only discovery)
      loadPoplarCampaigns();

      // Load Poplar Account Creatives
      setIsLoadingCreatives(true);
      getPoplarCreatives()
        .then((res) => {
          if (res?.creatives) {
            setCreatives(res.creatives);
          }
        })
        .catch((e) => console.warn("Failed to load Poplar creatives:", e))
        .finally(() => setIsLoadingCreatives(false));

      // Load existing campaign configuration if already set
      getCampaignPhysicalMailConfig(campaignId)
        .then((details) => {
          if (details.configured && details.config) {
            setIsConfigured(true);
            const cfg = details.config;
            if (cfg.campaign_id) setPoplarCampaignId(cfg.campaign_id);
            if (cfg.creative_id) setPoplarCreativeId(cfg.creative_id);
            if (cfg.name) setPoplarRemoteName(cfg.name);
            if (cfg.mailpiece) {
              if (cfg.mailpiece.size) setMailpieceSize(cfg.mailpiece.size);
              if (cfg.mailpiece.format) setFormatType(cfg.mailpiece.format);
              if (cfg.mailpiece.paper) setPaperType(cfg.mailpiece.paper);
              if (cfg.mailpiece.postage) setPostageClass(cfg.mailpiece.postage);
            }
            if (cfg.design) {
              if (cfg.design.name) setDesignName(cfg.design.name);
              if (cfg.design.url) setDesignUrl(cfg.design.url);
            }
          }
        })
        .catch(() => {});
    }
  }, [isOpen, campaignId]);

  // Fetch existing Poplar campaigns via read-only GET /v1/campaigns
  const loadPoplarCampaigns = async () => {
    setIsLoadingCampaigns(true);
    setCampaignsError(null);
    try {
      const res = await getPoplarCampaigns();
      const list = res.campaigns || [];
      setPoplarCampaigns(list);
    } catch (err: any) {
      console.warn("Failed to load Poplar campaigns:", err);
      setCampaignsError(err.message || "Failed to load Poplar campaigns.");
    } finally {
      setIsLoadingCampaigns(false);
    }
  };

  const handleSelectPoplarCampaign = (selectedId: string) => {
    setPoplarCampaignId(selectedId);
    setIsConfigured(false);
    const matched = poplarCampaigns.find((c) => c.id === selectedId);
    if (matched) {
      setPoplarRemoteName(matched.name);
      setSuccessNotice(`Selected Poplar Campaign: "${matched.name}" (${matched.id})`);
      setIsLoadingCreatives(true);
      getPoplarCreatives(matched.id)
        .then((res) => {
          if (res?.creatives && res.creatives.length > 0) {
            setCreatives(res.creatives);
          }
        })
        .catch(() => {})
        .finally(() => setIsLoadingCreatives(false));
    } else {
      setPoplarRemoteName("");
      setSuccessNotice(null);
    }
  };

  // Handle selecting an existing Poplar library creative
  const handleSelectCreative = (creative: PoplarCreativeItem) => {
    setPoplarCreativeId(creative.id);
    setDesignName(creative.name);
    if (creative.thumbnail_url) {
      setDesignUrl(creative.thumbnail_url);
    }
    if (creative.associated_campaign_id && !poplarCampaignId) {
      setPoplarCampaignId(creative.associated_campaign_id);
    }
    const cType = (creative.creative_type || "").toLowerCase();
    const mType = (creative.mail_type || "").toLowerCase();
    const cName = (creative.name || "").toLowerCase();
    const combined = `${cType} ${mType} ${cName}`;

    if (combined.includes("postcard")) {
      setFormatType("postcard");
      if (combined.includes("6x11") || combined.includes("6 x 11")) {
        setMailpieceSize("6x11");
      } else if (combined.includes("6x9") || combined.includes("6 x 9")) {
        setMailpieceSize("6x9");
      } else if (combined.includes("4x6") || combined.includes("4 x 6")) {
        setMailpieceSize("4x6");
      }
    } else if (combined.includes("bifold")) {
      setFormatType("bifold");
    } else if (combined.includes("trifold")) {
      setFormatType("trifold");
    } else if (combined.includes("color letter") || combined.includes("full-color")) {
      setFormatType("color_envelope");
    } else if (combined.includes("letter") || combined.includes("bw") || combined.includes("black")) {
      setFormatType("bw_envelope");
    }
    setSuccessNotice(`Selected Poplar Creative: ${creative.name} (${creative.id})`);
  };

  // Handle artwork specification check
  const handleValidateCustomArtwork = async () => {
    if (!customFileName.trim()) return;
    setIsValidatingArtwork(true);
    setArtworkValidation(null);
    try {
      const res = await validateCreativeAsset({
        file_name: customFileName.trim(),
        mailpiece_size: mailpieceSize,
      });
      setArtworkValidation(res);
    } catch (e: any) {
      console.warn("Creative validation error:", e);
    } finally {
      setIsValidatingArtwork(false);
    }
  };

  // Dynamic estimated unit cost calculation
  const getEstimatedUnitCost = (): number => {
    if (optionsData?.cost_estimates) {
      if (formatType === "postcard") {
        const key1 = `${mailpieceSize}:${postageClass}`;
        if (optionsData.cost_estimates[key1]) return optionsData.cost_estimates[key1];
        if (optionsData.cost_estimates[`postcard:${postageClass}`]) return optionsData.cost_estimates[`postcard:${postageClass}`];
      } else {
        const key2 = `${formatType}:${postageClass}`;
        if (optionsData.cost_estimates[key2]) return optionsData.cost_estimates[key2];
      }
    }
    return postageClass === "usps_standard" ? 0.95 : 1.15;
  };

  // Step 1 Action: Configure / Connect Poplar Campaign
  const handleConfigurePoplar = async () => {
    if (workflowMode === "create") {
      if (!newCampaignName.trim()) {
        setErrorMessage("Poplar campaign name cannot be blank.");
        return;
      }
      setShowConfirmCreate(true);
      return;
    }

    if (!poplarCampaignId.trim()) {
      setErrorMessage("Please select or specify an existing Poplar Campaign ID from your Poplar dashboard.");
      return;
    }
    setIsConfiguring(true);
    setErrorMessage(null);
    setSuccessNotice(null);
    setRecoveryCampaignId(null);
    try {
      const res = await configurePhysicalMailCampaign(campaignId, {
        workflow_mode: "connect",
        mailpiece_size: mailpieceSize,
        format_type: formatType,
        paper_type: paperType,
        postage_class: postageClass,
        design_name: designName.trim() || undefined,
        design_url: designUrl.trim() || undefined,
        poplar_campaign_id: poplarCampaignId.trim() || undefined,
        creative_id: poplarCreativeId.trim() || undefined,
        recipient_ids: recipientIds,
      });

      if (res.poplar_campaign_id) {
        setPoplarCampaignId(res.poplar_campaign_id);
        setPoplarRemoteName(res.poplar_name || campaignName);
        setIsConfigured(true);
        setSuccessNotice(
          `Campaign resource confirmed in Poplar TEST account: ${res.poplar_campaign_id} (${res.poplar_status})`
        );
      }
      // Auto-populate recipient count if returned
      if (res.recipient_summary) {
        setActiveStep("validate");
        handleValidateAddresses();
      }
    } catch (err: any) {
      setIsConfigured(false);
      setSuccessNotice(null);
      setErrorMessage(err.message || "Failed to configure Poplar campaign resource.");
    } finally {
      setIsConfiguring(false);
    }
  };

  // Step 1 Action (Create Mode): Execute remote creation after user confirmation
  const handleExecuteCreatePoplar = async () => {
    setShowConfirmCreate(false);
    if (!newCampaignName.trim()) {
      setErrorMessage("Poplar campaign name cannot be blank.");
      return;
    }
    setIsConfiguring(true);
    setErrorMessage(null);
    setSuccessNotice(null);
    setRecoveryCampaignId(null);
    try {
      const res = await configurePhysicalMailCampaign(campaignId, {
        workflow_mode: "create",
        new_campaign_name: newCampaignName.trim(),
        purpose: newCampaignPurpose,
        sub_purpose: newCampaignSubPurpose,
        description: newCampaignDescription.trim() || undefined,
        mailpiece_size: mailpieceSize,
        format_type: formatType,
        paper_type: paperType,
        postage_class: postageClass,
        design_name: designName.trim() || undefined,
        design_url: designUrl.trim() || undefined,
        creative_id: poplarCreativeId.trim() || undefined,
        recipient_ids: recipientIds,
      });

      if (res.poplar_campaign_id) {
        setPoplarCampaignId(res.poplar_campaign_id);
        setPoplarRemoteName(res.poplar_name || newCampaignName.trim());
        setIsConfigured(true);
        setSuccessNotice(
          `New Poplar campaign created & linked successfully: "${res.poplar_name || newCampaignName.trim()}" (${res.poplar_campaign_id})`
        );
        // Refresh list so it now appears in existing dropdown
        loadPoplarCampaigns();
      }
      if (res.recipient_summary) {
        setActiveStep("validate");
        handleValidateAddresses();
      }
    } catch (err: any) {
      setIsConfigured(false);
      setSuccessNotice(null);
      if (err.poplar_campaign_id) {
        setRecoveryCampaignId(err.poplar_campaign_id);
      }
      setErrorMessage(err.message || "Failed to create remote Poplar campaign.");
    } finally {
      setIsConfiguring(false);
    }
  };

  // Step 2 Action: Validate Addresses
  const handleValidateAddresses = async () => {
    setIsValidating(true);
    setErrorMessage(null);
    try {
      const res = await validateCampaignPhysicalMail(campaignId, recipientIds);
      setValidationReport(res);
      if (res.invalid_count > 0 && res.valid_count === 0) {
        setActiveRecipientTab("invalid");
      } else {
        setActiveRecipientTab("valid");
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to validate recipient addresses.");
    } finally {
      setIsValidating(false);
    }
  };

  // Step 3 Action: Fetch Preview & Budget
  const handleProceedToPreview = async () => {
    setIsPreviewing(true);
    setErrorMessage(null);
    try {
      const res = await previewCampaignPhysicalMail(campaignId, {
        poplar_campaign_id: poplarCampaignId.trim() || undefined,
        poplar_creative_id: poplarCreativeId.trim() || undefined,
        unit_cost: getEstimatedUnitCost(),
      });
      setPreviewResult(res);
      setActiveStep("preview");
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to generate mail preview and cost calculation.");
    } finally {
      setIsPreviewing(false);
    }
  };

  // Step 4 Action: Approve and Submit to Poplar (Test Environment)
  const handleSubmitCampaign = async () => {
    if (!isExplicitlyApproved) {
      setErrorMessage("You must explicitly authorize the submission before dispatching mail.");
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const res = await approveAndSubmitPhysicalMail(campaignId, {
        approved: true,
        approval_token: approvalToken,
        poplar_campaign_id: poplarCampaignId.trim() || undefined,
        poplar_creative_id: poplarCreativeId.trim() || undefined,
        recipient_ids: recipientIds,
      });
      setSubmissionResult(res);
      setActiveStep("submitted");
      if (onCompleted) onCompleted();
    } catch (err: any) {
      setErrorMessage(err.message || "Physical mail submission failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Tracking Sync
  const handleSyncTracking = async () => {
    setIsSyncing(true);
    setSyncMessage(null);
    try {
      const res = await syncCampaignPhysicalMail(campaignId);
      setSyncMessage(
        `Tracking synced: ${res.total_checked} checked, ${res.total_updated} updated, ${res.total_delivered} delivered.`
      );
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to sync tracking status.");
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Direct Mail Pre-Flight & Poplar Dispatch — ${campaignName}`}
    >
      <div className="space-y-4 max-h-[78vh] overflow-y-auto pr-1">
        {/* Environment Safety Notice */}
        <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-lg flex items-start gap-2.5 text-xs text-amber-900">
          <ShieldCheck className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <span className="font-semibold">Poplar Test Environment Active (Agile Receivables Inc)</span>
            <p className="text-[11px] text-amber-800">
              Dispatches execute against Poplar’s test API sandbox. Campaign resources are verified directly with Poplar.
              Digital proof URLs are generated, zero physical commercial mailings are printed, and no billing charges occur.
            </p>
          </div>
        </div>

        {/* Global Alerts */}
        {errorMessage && (
          <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-800 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <div className="flex-1">{errorMessage}</div>
          </div>
        )}

        {successNotice && (
          <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800 flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
            <div className="flex-1 font-medium">{successNotice}</div>
          </div>
        )}

        {/* Workflow Progression Tabs */}
        <div className="flex border-b border-slate-200 text-xs font-medium">
          <button
            onClick={() => setActiveStep("configure")}
            className={`py-2 px-3 border-b-2 transition-colors flex items-center gap-1.5 ${
              activeStep === "configure"
                ? "border-agile-red text-agile-red font-semibold"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <Palette className="w-3.5 h-3.5" />
            <span>1. Mailpiece & Poplar</span>
          </button>
          <button
            onClick={() => setActiveStep("validate")}
            className={`py-2 px-3 border-b-2 transition-colors flex items-center gap-1.5 ${
              activeStep === "validate"
                ? "border-agile-red text-agile-red font-semibold"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <Mail className="w-3.5 h-3.5" />
            <span>2. Recipient Audit</span>
          </button>
          <button
            onClick={() => {
              if (validationReport) setActiveStep("preview");
            }}
            disabled={!validationReport}
            className={`py-2 px-3 border-b-2 transition-colors flex items-center gap-1.5 ${
              activeStep === "preview"
                ? "border-agile-red text-agile-red font-semibold"
                : "border-transparent text-slate-400 disabled:opacity-50"
            }`}
          >
            <DollarSign className="w-3.5 h-3.5" />
            <span>3. Preflight & Preview</span>
          </button>
          <button
            onClick={() => {
              if (submissionResult) setActiveStep("submitted");
            }}
            disabled={!submissionResult}
            className={`py-2 px-3 border-b-2 transition-colors flex items-center gap-1.5 ${
              activeStep === "submitted"
                ? "border-agile-red text-agile-red font-semibold"
                : "border-transparent text-slate-400 disabled:opacity-50"
            }`}
          >
            <Truck className="w-3.5 h-3.5" />
            <span>4. Poplar Tracking</span>
          </button>
        </div>

        {/* ── STEP 1: MAILPIECE SPECIFICATIONS & POPLAR RESOURCE ── */}
        {activeStep === "configure" && (
          <div className="space-y-4">
            {/* Poplar Dual Workflow Switcher */}
            <div className="flex items-center gap-2 p-1 bg-slate-100 rounded-lg border border-slate-200">
              <button
                type="button"
                onClick={() => {
                  setWorkflowMode("connect");
                  setErrorMessage(null);
                }}
                className={`flex-1 text-xs font-semibold py-2 px-3 rounded-md flex items-center justify-center gap-1.5 transition-all ${
                  workflowMode === "connect"
                    ? "bg-white text-slate-900 shadow-xs border border-slate-200/80 font-bold"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <Link2 className="w-3.5 h-3.5 text-slate-600" />
                Connect Existing Poplar Campaign
              </button>
              <button
                type="button"
                onClick={() => {
                  setWorkflowMode("create");
                  setErrorMessage(null);
                }}
                className={`flex-1 text-xs font-semibold py-2 px-3 rounded-md flex items-center justify-center gap-1.5 transition-all ${
                  workflowMode === "create"
                    ? "bg-agile-red text-white shadow-xs font-bold"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <PlusCircle className="w-3.5 h-3.5" />
                Create New Poplar Campaign
              </button>
            </div>

            {/* Partial Failure Recovery Notice */}
            {recoveryCampaignId && (
              <div className="p-3 bg-amber-50 border border-amber-300 rounded-lg text-xs text-amber-900 space-y-2">
                <div className="flex items-center gap-1.5 font-semibold text-amber-950">
                  <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
                  <span>Remote Campaign Created, Local Save Incomplete</span>
                </div>
                <p className="text-[11px] text-amber-800">
                  Poplar successfully created campaign <code className="bg-amber-100 px-1 py-0.5 rounded font-mono font-bold text-amber-900">{recoveryCampaignId}</code>, but local persistence encountered an error. You can link this campaign directly without creating a duplicate.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setWorkflowMode("connect");
                    setPoplarCampaignId(recoveryCampaignId);
                    setRecoveryCampaignId(null);
                    setErrorMessage(null);
                    setSuccessNotice(`Switched to Connect Existing with Poplar ID: ${recoveryCampaignId}. Click 'Verify & Bind' to finish linking.`);
                  }}
                  className="text-xs border-amber-300 bg-white hover:bg-amber-100/50 text-amber-900"
                >
                  <Link2 className="w-3.5 h-3.5 mr-1" />
                  Switch to Connect Existing with this ID
                </Button>
              </div>
            )}

            {/* Poplar Resource Linkage Card */}
            <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-lg space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-agile-red" />
                  {workflowMode === "connect" ? "Poplar Account & Campaign Binding" : "Create New Poplar Campaign Container"}
                </span>
                <div className="flex items-center gap-2">
                  {workflowMode === "connect" && (
                    <button
                      type="button"
                      onClick={loadPoplarCampaigns}
                      disabled={isLoadingCampaigns}
                      className="text-[11px] text-slate-500 hover:text-agile-red flex items-center gap-1 px-1.5 py-0.5 rounded border border-slate-200 bg-white hover:bg-slate-50 transition-colors"
                      title="Refresh campaigns list from Poplar account"
                    >
                      <RefreshCw className={`w-3 h-3 ${isLoadingCampaigns ? "animate-spin" : ""}`} />
                      <span>Refresh</span>
                    </button>
                  )}
                  {isConfigured && poplarCampaignId ? (
                    <Badge variant="neutral" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px]">
                      <Check className="w-3 h-3 mr-1 inline" />
                      {poplarRemoteName ? poplarRemoteName : "Verified Poplar Campaign"}
                    </Badge>
                  ) : (
                    <Badge variant="neutral" className="text-amber-700 bg-amber-50 border-amber-200 text-[10px]">
                      Unlinked
                    </Badge>
                  )}
                </div>
              </div>

              {/* Workflow Option A: Connect Existing */}
              {workflowMode === "connect" ? (
                <>
                  {/* Poplar Campaign Dropdown Selection */}
                  <div>
                    <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                      Select Existing Poplar Campaign *
                    </label>
                    {isLoadingCampaigns ? (
                      <div className="p-2 bg-white rounded border border-slate-200 text-xs text-slate-400 flex items-center gap-2">
                        <RefreshCw className="w-3.5 h-3.5 animate-spin text-slate-400" />
                        <span>Fetching campaigns from Poplar account...</span>
                      </div>
                    ) : campaignsError ? (
                      <div className="p-2 bg-rose-50 rounded border border-rose-200 text-xs text-rose-700 space-y-1">
                        <div className="flex items-center gap-1.5">
                          <AlertCircle className="w-3.5 h-3.5 text-rose-600 shrink-0" />
                          <span>{campaignsError}</span>
                        </div>
                        <p className="text-[10px] text-rose-600">You can also paste a Campaign ID manually below.</p>
                      </div>
                    ) : poplarCampaigns.length === 0 ? (
                      <div className="p-2.5 bg-amber-50 rounded border border-amber-200 text-xs text-amber-800 space-y-1">
                        <p className="font-semibold">No Poplar campaigns found in account.</p>
                        <p className="text-[11px] text-amber-700">
                          Create an empty test campaign in your Poplar dashboard or switch to &quot;Create New Poplar Campaign&quot; above.
                        </p>
                      </div>
                    ) : (
                      <select
                        value={poplarCampaignId}
                        onChange={(e) => handleSelectPoplarCampaign(e.target.value)}
                        className="w-full text-xs rounded border border-slate-200 p-2 bg-white text-slate-800 focus:outline-none focus:border-agile-red font-mono"
                      >
                        <option value="">-- Select an existing Poplar campaign --</option>
                        {poplarCampaigns.map((camp) => (
                          <option key={camp.id} value={camp.id}>
                            {camp.name} ({camp.id})
                          </option>
                        ))}
                      </select>
                    )}
                    <p className="text-[10px] text-slate-500 mt-1">
                      Connects to an existing campaign created in Poplar. Never creates remote campaigns.
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-3 text-xs pt-1">
                    <div>
                      <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                        Poplar Campaign ID (Manual / Verified)
                      </label>
                      <Input
                        placeholder="e.g. bc748442-baae-48b3-87c1-..."
                        value={poplarCampaignId}
                        onChange={(e) => {
                          const val = e.target.value;
                          setPoplarCampaignId(val);
                          setIsConfigured(false);
                          const matched = poplarCampaigns.find((c) => c.id === val.trim());
                          if (matched) {
                            setPoplarRemoteName(matched.name);
                          } else {
                            setPoplarRemoteName("");
                          }
                        }}
                        className="h-8 text-xs font-mono"
                      />
                      <p className="text-[10px] text-slate-500 mt-1">
                        Poplar Campaign UUID from your dashboard URL or API
                      </p>
                    </div>
                    <div>
                      <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                        Poplar Creative ID (Optional)
                      </label>
                      <Input
                        placeholder="e.g. 0d5926c2-c7a3-4962-ad72-... (optional)"
                        value={poplarCreativeId}
                        onChange={(e) => setPoplarCreativeId(e.target.value)}
                        className="h-8 text-xs font-mono"
                      />
                      <p className="text-[10px] text-slate-500 mt-1">
                        Specific Creative asset ID if configured in dashboard
                      </p>
                    </div>
                  </div>
                </>
              ) : (
                /* Workflow Option B: Create New Poplar Campaign */
                <div className="space-y-3">
                  <div>
                    <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                      New Poplar Campaign Name *
                    </label>
                    <Input
                      placeholder="e.g. Agile - Customer Winback"
                      value={newCampaignName}
                      onChange={(e) => {
                        setNewCampaignName(e.target.value);
                        setIsConfigured(false);
                      }}
                      className="h-8 text-xs font-medium"
                    />
                    <p className="text-[10px] text-slate-500 mt-1">
                      Prefilled with &quot;Agile - {campaignName}&quot;. You can edit before creating.
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                        Campaign Purpose
                      </label>
                      <select
                        value={newCampaignPurpose}
                        onChange={(e) => setNewCampaignPurpose(e.target.value)}
                        className="w-full text-xs rounded border border-slate-200 p-2 bg-white text-slate-800 focus:outline-none focus:border-agile-red"
                      >
                        <option value="retention">Retention (Winback, Lapsed, Reactivation)</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                        Sub-Purpose
                      </label>
                      <select
                        value={newCampaignSubPurpose}
                        onChange={(e) => setNewCampaignSubPurpose(e.target.value)}
                        className="w-full text-xs rounded border border-slate-200 p-2 bg-white text-slate-800 focus:outline-none focus:border-agile-red"
                      >
                        <option value="reactivation">Reactivation (Customer Winback / Re-engagement)</option>
                      </select>
                    </div>
                    <div className="col-span-2">
                      <p className="text-[10px] text-slate-500">
                        Poplar API campaign containers require verified Retention &amp; Reactivation parameters.
                      </p>
                    </div>
                  </div>

                  <div>
                    <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                      Description (Optional)
                    </label>
                    <Input
                      placeholder="e.g. Automated direct mail cadence for sales leads"
                      value={newCampaignDescription}
                      onChange={(e) => setNewCampaignDescription(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3 text-xs pt-1">
                    <div>
                      <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                        Attach Creative Asset ID (Optional)
                      </label>
                      <Input
                        placeholder="e.g. 0d5926c2-c7a3-4962-ad72-... (optional)"
                        value={poplarCreativeId}
                        onChange={(e) => setPoplarCreativeId(e.target.value)}
                        className="h-8 text-xs font-mono"
                      />
                      <p className="text-[10px] text-slate-500 mt-1">
                        Creative selection is optional during creation.
                      </p>
                    </div>
                    <div className="flex flex-col justify-end">
                      <div className="p-2 bg-emerald-50 border border-emerald-200 rounded text-[10px] text-emerald-800">
                        <span className="font-semibold block flex items-center gap-1">
                          <ShieldCheck className="w-3 h-3 text-emerald-600" /> Safe Container Setup
                        </span>
                        Creates an organizational campaign container. Never purchases postage or triggers fulfillment.
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Creative Guidance Notice */}
            {isConfigured && poplarCampaignId && !poplarCreativeId && (
              <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-800 space-y-1">
                <div className="flex items-center gap-1.5 font-semibold text-blue-900">
                  <Sparkles className="w-3.5 h-3.5 text-blue-600 shrink-0" />
                  <span>Campaign Linked — Creative Asset Optional</span>
                </div>
                <p className="text-[11px] text-blue-700">
                  Poplar campaign <strong>&quot;{poplarRemoteName || poplarCampaignId}&quot;</strong> is linked, but does not have a creative template assigned yet. You may select an existing template from the library below, or proceed with standard custom artwork. (No artwork is uploaded automatically, and no mail is sent).
                </p>
              </div>
            )}

            {/* Poplar Creative Library Card */}
            <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-lg space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                  <Palette className="w-4 h-4 text-agile-red" />
                  Poplar Account Creative Library
                </span>
                <span className="text-[10px] text-slate-500">
                  {isLoadingCreatives ? "Loading templates..." : `${creatives.length} templates available`}
                </span>
              </div>

              {creatives.length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                  {creatives.map((c) => {
                    const isSelected = poplarCreativeId === c.id;
                    return (
                      <div
                        key={c.id}
                        onClick={() => handleSelectCreative(c)}
                        className={`p-2.5 rounded-lg border text-left cursor-pointer transition-all ${
                          isSelected
                            ? "border-agile-red bg-white ring-1 ring-agile-red shadow-xs"
                            : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/50"
                        }`}
                      >
                        {c.thumbnail_url ? (
                          <img
                            src={c.thumbnail_url}
                            alt={c.name}
                            className="w-full h-16 object-cover rounded mb-1.5 border border-slate-100"
                          />
                        ) : (
                          <div className="w-full h-16 bg-slate-100 rounded mb-1.5 flex items-center justify-center text-slate-400">
                            <FileText className="w-6 h-6" />
                          </div>
                        )}
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-xs text-slate-900 truncate">{c.name}</span>
                          {isSelected && (
                            <span className="text-[10px] text-emerald-600 font-semibold flex items-center">
                              <Check className="w-3 h-3" />
                            </span>
                          )}
                        </div>
                        <p className="text-[10px] text-slate-500 capitalize">{c.mail_type || "Postcard"} &bull; {c.format || "Print Ready"}</p>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-[11px] text-slate-500">
                  {isLoadingCreatives ? "Fetching templates from Poplar TEST account..." : "No existing templates found in Poplar sandbox. You can enter an artwork URL below."}
                </p>
              )}
            </div>

            {/* Mailpiece Configurations */}
            <div className="p-4 bg-white border border-slate-200 rounded-lg space-y-4">
              <span className="text-xs font-bold text-slate-800 block">Mailpiece Specifications</span>

              <div className="grid grid-cols-2 gap-4">
                {/* Mailpiece Size */}
                <div>
                  <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                    Dimensions / Size
                  </label>
                  <select
                    value={mailpieceSize}
                    onChange={(e) => setMailpieceSize(e.target.value)}
                    className="w-full text-xs rounded-md border border-slate-200 p-2 bg-white text-slate-800 focus:outline-none focus:border-agile-red"
                  >
                    <option value="4x6">4x6 Postcard (Compact, Cost-Effective)</option>
                    <option value="6x9">6x9 Postcard (Medium Oversized, High Visibility)</option>
                    <option value="6x11">6x11 Postcard (Maximum Impact Panorama)</option>
                  </select>
                </div>

                {/* Format Type */}
                <div>
                  <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                    Format & Envelope
                  </label>
                  <select
                    value={formatType}
                    onChange={(e) => setFormatType(e.target.value)}
                    className="w-full text-xs rounded-md border border-slate-200 p-2 bg-white text-slate-800 focus:outline-none focus:border-agile-red"
                  >
                    <option value="postcard">Postcard (No Envelope - Flat Card)</option>
                    <option value="bw_envelope">Black & White Letter (#10 Envelope)</option>
                    <option value="color_envelope">Full-Color Letter (#10 Double Window)</option>
                    <option value="bifold">Bifold Self-Mailer (4 Printable Panels)</option>
                    <option value="trifold">Trifold Self-Mailer (6 Printable Panels)</option>
                  </select>
                </div>

                {/* Postage Class */}
                <div>
                  <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                    Postage Tier
                  </label>
                  <select
                    value={postageClass}
                    onChange={(e) => setPostageClass(e.target.value)}
                    className="w-full text-xs rounded-md border border-slate-200 p-2 bg-white text-slate-800 focus:outline-none focus:border-agile-red"
                  >
                    <option value="usps_first_class">USPS First Class (3–5 business days, Forwarding)</option>
                    <option value="usps_standard">USPS Standard (5–15 business days, Bulk Rate)</option>
                  </select>
                </div>

                {/* Paper Quality */}
                <div>
                  <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                    Paper Stock & Coating
                  </label>
                  <select
                    value={paperType}
                    onChange={(e) => setPaperType(e.target.value)}
                    className="w-full text-xs rounded-md border border-slate-200 p-2 bg-white text-slate-800 focus:outline-none focus:border-agile-red"
                  >
                    <option value="premium_coated">Premium Coated (UV gloss protective finish)</option>
                    <option value="premium_uncoated">Premium Uncoated (Matte natural tactile feel)</option>
                  </select>
                </div>
              </div>

              {/* Design Upload / URL */}
              <div className="pt-2 border-t border-slate-100 grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                    Artwork / Template Name
                  </label>
                  <Input
                    value={designName}
                    onChange={(e) => setDesignName(e.target.value)}
                    placeholder="e.g. Agile Receivables Notice"
                    className="h-8 text-xs"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                    Artwork Proof URL (PDF / PNG)
                  </label>
                  <Input
                    value={designUrl}
                    onChange={(e) => setDesignUrl(e.target.value)}
                    placeholder="https://..."
                    className="h-8 text-xs font-mono"
                  />
                </div>
              </div>

              {/* Artwork Validation Tool */}
              <div className="p-3 bg-slate-50 rounded-lg space-y-2 border border-slate-200/80">
                <span className="text-[11px] font-semibold text-slate-700 block">
                  Artwork Specification &amp; Bleed Verification
                </span>
                <div className="flex gap-2">
                  <Input
                    value={customFileName}
                    onChange={(e) => setCustomFileName(e.target.value)}
                    placeholder="e.g. proof-creative.pdf"
                    className="h-8 text-xs font-mono flex-1"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleValidateCustomArtwork}
                    disabled={isValidatingArtwork || !customFileName.trim()}
                    className="text-xs h-8"
                  >
                    {isValidatingArtwork ? <RefreshCw className="w-3 h-3 animate-spin" /> : "Verify File Specs"}
                  </Button>
                </div>
                {artworkValidation && (
                  <div
                    className={`p-2 rounded text-[11px] ${
                      artworkValidation.is_valid
                        ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                        : "bg-rose-50 text-rose-800 border border-rose-200"
                    }`}
                  >
                    <div className="flex items-center justify-between font-semibold">
                      <span>{artworkValidation.is_valid ? "Artwork Validated for Print" : "Specification Notice"}</span>
                      <span className="font-mono text-[10px]">{artworkValidation.spec?.pixel_bleed_width}x{artworkValidation.spec?.pixel_bleed_height}px @ 300 DPI</span>
                    </div>
                    {artworkValidation.errors?.length > 0 && (
                      <p className="mt-0.5">{artworkValidation.errors.join("; ")}</p>
                    )}
                    {artworkValidation.warnings?.length > 0 && (
                      <p className="mt-0.5 text-amber-700">{artworkValidation.warnings.join("; ")}</p>
                    )}
                  </div>
                )}
              </div>

              {/* Live Cost Preview Card */}
              <div className="p-3 bg-slate-50 rounded-lg flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-agile-red" />
                  <span className="text-slate-600">Calculated Rate per Piece:</span>
                  <span className="font-bold text-slate-900">${getEstimatedUnitCost().toFixed(2)}</span>
                </div>
                <span className="text-[11px] text-slate-500">
                  Includes full-color print, stock coating & USPS postage
                </span>
              </div>
            </div>

            {/* Action Bar */}
            <div className="flex justify-between items-center pt-2">
              <Button variant="outline" size="sm" onClick={onClose} className="text-xs">
                Cancel
              </Button>
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleConfigurePoplar}
                  disabled={
                    isConfiguring ||
                    (workflowMode === "connect" && !poplarCampaignId.trim()) ||
                    (workflowMode === "create" && !newCampaignName.trim())
                  }
                  className="text-xs bg-agile-red hover:bg-agile-red/90 text-white"
                >
                  {isConfiguring ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                      {workflowMode === "create" ? "Creating in Poplar..." : "Verifying with Poplar..."}
                    </>
                  ) : workflowMode === "create" ? (
                    <>
                      <PlusCircle className="w-3.5 h-3.5 mr-1.5" />
                      Create &amp; Bind Poplar Campaign
                    </>
                  ) : (
                    <>
                      <Layers className="w-3.5 h-3.5 mr-1.5" />
                      Verify &amp; Bind Poplar Campaign
                    </>
                  )}
                </Button>
                {poplarCampaignId && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setActiveStep("validate");
                      if (!validationReport) handleValidateAddresses();
                    }}
                    className="text-xs"
                  >
                    Next: Audit Recipients &rarr;
                  </Button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── STEP 2: ADDRESS AUDIT & RECIPIENT SELECTION ── */}
        {activeStep === "validate" && (
          <div className="space-y-4">
            {!validationReport ? (
              <div className="py-8 text-center border-2 border-dashed border-slate-200 rounded-xl space-y-3">
                <Mail className="w-10 h-10 text-slate-400 mx-auto" />
                <div className="space-y-1">
                  <p className="text-xs font-semibold text-slate-800">Pre-Flight Postal Address Audit</p>
                  <p className="text-[11px] text-slate-500 max-w-sm mx-auto">
                    Verify all enrolled campaign prospects against USPS domestic address standards (valid street line,
                    2-letter state code, and 5-digit ZIP) before generating mail pieces.
                  </p>
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleValidateAddresses}
                  disabled={isValidating}
                  className="text-xs bg-agile-red hover:bg-agile-red/90 text-white"
                >
                  {isValidating ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 mr-1 animate-spin" />
                      Auditing Addresses...
                    </>
                  ) : (
                    "Audit Recipient Addresses"
                  )}
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                {/* Metric Summary Cards */}
                <div className="grid grid-cols-3 gap-2">
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-center">
                    <span className="text-[10px] text-slate-500 uppercase font-semibold">Total Audience</span>
                    <p className="text-lg font-bold text-slate-900">{validationReport.total_recipients}</p>
                  </div>
                  <div className="p-3 bg-emerald-50/60 border border-emerald-200 rounded-lg text-center">
                    <span className="text-[10px] text-emerald-700 uppercase font-semibold">Valid Addresses</span>
                    <p className="text-lg font-bold text-emerald-700">{validationReport.valid_count}</p>
                  </div>
                  <div className="p-3 bg-rose-50/60 border border-rose-200 rounded-lg text-center">
                    <span className="text-[10px] text-rose-700 uppercase font-semibold">Invalid / Incomplete</span>
                    <p className="text-lg font-bold text-rose-700">{validationReport.invalid_count}</p>
                  </div>
                </div>

                {/* Sub-tab selection */}
                <div className="flex gap-2 text-xs">
                  <button
                    onClick={() => setActiveRecipientTab("valid")}
                    className={`px-3 py-1 rounded-md transition-colors ${
                      activeRecipientTab === "valid"
                        ? "bg-emerald-100 text-emerald-800 font-semibold"
                        : "text-slate-500 hover:bg-slate-100"
                    }`}
                  >
                    Valid ({validationReport.valid_count})
                  </button>
                  <button
                    onClick={() => setActiveRecipientTab("invalid")}
                    className={`px-3 py-1 rounded-md transition-colors ${
                      activeRecipientTab === "invalid"
                        ? "bg-rose-100 text-rose-800 font-semibold"
                        : "text-slate-500 hover:bg-slate-100"
                    }`}
                  >
                    Incomplete / Errors ({validationReport.invalid_count})
                  </button>
                </div>

                {/* Recipient Tables */}
                <div className="border border-slate-200 rounded-lg max-h-48 overflow-y-auto">
                  {activeRecipientTab === "valid" ? (
                    validationReport.valid_recipients.length === 0 ? (
                      <p className="p-4 text-center text-xs text-slate-400">No valid postal addresses found.</p>
                    ) : (
                      <table className="w-full text-left text-[11px]">
                        <thead className="bg-slate-50 text-slate-500 border-b border-slate-200 sticky top-0">
                          <tr>
                            <th className="p-2 font-medium">Recipient</th>
                            <th className="p-2 font-medium">Company</th>
                            <th className="p-2 font-medium">Standardized Address</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {validationReport.valid_recipients.map((rec) => (
                            <tr key={rec.recipient_id} className="hover:bg-slate-50/60">
                              <td className="p-2 font-medium text-slate-900">{rec.full_name}</td>
                              <td className="p-2 text-slate-600">{rec.company_name || "—"}</td>
                              <td className="p-2 text-slate-600 font-mono text-[10px]">
                                {rec.address
                                  ? `${rec.address.address_1}, ${rec.address.city}, ${rec.address.state} ${rec.address.postal_code}`
                                  : "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )
                  ) : validationReport.invalid_recipients.length === 0 ? (
                    <p className="p-4 text-center text-xs text-emerald-600">All recipient addresses are valid!</p>
                  ) : (
                    <table className="w-full text-left text-[11px]">
                      <thead className="bg-rose-50 text-rose-700 border-b border-rose-200 sticky top-0">
                        <tr>
                          <th className="p-2 font-medium">Recipient</th>
                          <th className="p-2 font-medium">Company</th>
                          <th className="p-2 font-medium">Missing / Invalid Fields</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {validationReport.invalid_recipients.map((rec) => (
                          <tr key={rec.recipient_id} className="hover:bg-rose-50/30">
                            <td className="p-2 font-medium text-slate-900">{rec.full_name}</td>
                            <td className="p-2 text-slate-600">{rec.company_name || "—"}</td>
                            <td className="p-2 text-rose-600">
                              {rec.errors && rec.errors.length > 0 ? rec.errors.join("; ") : "Invalid address"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>

                <div className="flex justify-between items-center pt-2">
                  <Button variant="outline" size="sm" onClick={() => setActiveStep("configure")} className="text-xs">
                    &larr; Back to Mailpiece
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleProceedToPreview}
                    disabled={validationReport.valid_count === 0 || isPreviewing}
                    className="text-xs bg-agile-red hover:bg-agile-red/90 text-white"
                  >
                    {isPreviewing ? "Calculating Budget..." : `Proceed to Preview (${validationReport.valid_count} Valid)`}
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── STEP 3: PREVIEW & BUDGET AUTHORIZATION ── */}
        {activeStep === "preview" && previewResult && (
          <div className="space-y-4">
            {/* Sample Layout Card */}
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                  <FileText className="w-4 h-4 text-agile-red" />
                  Sample Direct Mail Preview (1st Recipient)
                </span>
                <Badge variant="neutral" className="text-[10px]">
                  {postageClass === "usps_first_class" ? "USPS First Class" : "USPS Standard"} &bull; {mailpieceSize}
                </Badge>
              </div>

              {previewResult.sample_preview ? (
                <div className="p-3 bg-white border border-slate-200 rounded-lg space-y-2 text-xs">
                  <div className="space-y-0.5">
                    <span className="text-[10px] text-slate-400 uppercase font-semibold">Delivery Address</span>
                    <p className="font-semibold text-slate-900">{previewResult.sample_preview.merge_tags.full_name}</p>
                    {previewResult.sample_preview.merge_tags.company && (
                      <p className="text-slate-600 text-[11px]">{previewResult.sample_preview.merge_tags.company}</p>
                    )}
                    <p className="text-slate-700 font-mono text-[11px]">
                      {previewResult.sample_preview.recipient?.address_1}
                    </p>
                    <p className="text-slate-700 font-mono text-[11px]">
                      {previewResult.sample_preview.recipient?.city}, {previewResult.sample_preview.recipient?.state}{" "}
                      {previewResult.sample_preview.recipient?.postal_code}
                    </p>
                  </div>
                  <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
                    <span>Estimated transit: {previewResult.sample_preview.estimated_delivery_days}</span>
                    <span className="font-mono text-slate-700">Poplar Campaign: {poplarCampaignId || previewResult.poplar_campaign_id}</span>
                  </div>

                  {/* Visual Creative Thumbnail if available */}
                  {designUrl && (
                    <div className="pt-2 border-t border-slate-100 flex items-center gap-3">
                      {(designUrl.includes(".png") || designUrl.includes(".jpg") || designUrl.includes("s3.") || designUrl.includes("heypoplar")) && (
                        <img
                          src={designUrl}
                          alt="Creative Proof"
                          className="w-20 h-14 object-cover rounded border border-slate-200"
                          onError={(e) => {
                            (e.target as HTMLElement).style.display = "none";
                          }}
                        />
                      )}
                      <div className="text-[11px] text-slate-600">
                        <span className="font-semibold block text-slate-800">{designName || "Selected Template"}</span>
                        <a href={designUrl} target="_blank" rel="noopener noreferrer" className="text-agile-red hover:underline flex items-center gap-1 font-mono text-[10px]">
                          <span>View Artwork Asset</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-xs text-slate-500">No sample preview available.</p>
              )}
            </div>

            {/* Budget & Cost Summary */}
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between text-xs">
              <div className="space-y-0.5">
                <span className="text-[10px] uppercase font-semibold text-slate-500">Production Cost Estimate</span>
                <p className="text-sm font-bold text-slate-900">
                  ${previewResult.estimated_total_cost.toFixed(2)}{" "}
                  <span className="text-[11px] font-normal text-slate-500">
                    (${previewResult.unit_cost.toFixed(2)}/piece × {previewResult.valid_count} recipients)
                  </span>
                </p>
              </div>
              <Badge variant="neutral" className="text-emerald-700 bg-emerald-50 border-emerald-200">
                Poplar Test Mode (Free)
              </Badge>
            </div>

            {/* Explicit Approval Gate */}
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-2">
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={isExplicitlyApproved}
                  onChange={(e) => setIsExplicitlyApproved(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 text-agile-red focus:ring-agile-red"
                />
                <span className="text-xs text-slate-700">
                  <strong>Explicit User Authorization:</strong> I authorize the test submission of direct mail pieces
                  for <strong>{previewResult.valid_count}</strong> valid recipient(s). I understand this executes against
                  the Poplar TEST environment to generate proof previews.
                </span>
              </label>

              <div className="flex items-center gap-2 pt-1 text-[11px] text-slate-500">
                <span>Idempotency Approval Token:</span>
                <code className="bg-white px-2 py-0.5 rounded border border-slate-200 font-mono text-[10px]">
                  {approvalToken}
                </code>
              </div>
            </div>

            <div className="flex justify-between items-center pt-2">
              <Button variant="outline" size="sm" onClick={() => setActiveStep("validate")} className="text-xs">
                &larr; Back to Validation
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleSubmitCampaign}
                disabled={!isExplicitlyApproved || isSubmitting}
                className="text-xs bg-agile-red hover:bg-agile-red/90 text-white"
              >
                {isSubmitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 mr-1 animate-spin" />
                    Submitting to Poplar...
                  </>
                ) : (
                  `Authorize & Submit (${previewResult.valid_count} Mailings)`
                )}
              </Button>
            </div>
          </div>
        )}

        {/* ── STEP 4: SUBMISSION RESULTS & TRACKING ── */}
        {activeStep === "submitted" && submissionResult && (
          <div className="space-y-4">
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg flex items-center justify-between text-xs text-emerald-900">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
                <div>
                  <span className="font-bold">Submission Complete</span>
                  <p className="text-[11px] text-emerald-800">
                    {submissionResult.total_submitted} mailing(s) dispatched to Poplar test pipeline.
                  </p>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={handleSyncTracking}
                disabled={isSyncing}
                className="text-xs bg-white text-emerald-900"
              >
                {isSyncing ? (
                  <RefreshCw className="w-3 h-3 animate-spin mr-1" />
                ) : (
                  <Truck className="w-3.5 h-3.5 mr-1" />
                )}
                Sync USPS Tracking
              </Button>
            </div>

            {syncMessage && (
              <div className="p-2 bg-blue-50 border border-blue-200 text-blue-800 text-[11px] rounded-lg">
                {syncMessage}
              </div>
            )}

            {/* Per-Recipient Outcomes Table */}
            <div className="border border-slate-200 rounded-lg max-h-56 overflow-y-auto">
              <table className="w-full text-left text-[11px]">
                <thead className="bg-slate-50 text-slate-500 border-b border-slate-200 sticky top-0">
                  <tr>
                    <th className="p-2 font-medium">Recipient ID</th>
                    <th className="p-2 font-medium">Status</th>
                    <th className="p-2 font-medium">Mailing ID</th>
                    <th className="p-2 font-medium text-right">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {submissionResult.outcomes.map((outcome, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/60">
                      <td className="p-2 font-mono text-[10px] text-slate-700">
                        {outcome.recipient_id.substring(0, 8)}...
                      </td>
                      <td className="p-2">
                        {outcome.success ? (
                          <Badge variant="neutral" className="text-emerald-700 bg-emerald-50 border-emerald-200 text-[10px]">
                            {outcome.simulated ? "Simulated Test" : outcome.status}
                          </Badge>
                        ) : (
                          <Badge variant="neutral" className="text-rose-700 bg-rose-50 border-rose-200 text-[10px]">
                            {outcome.status}
                          </Badge>
                        )}
                      </td>
                      <td className="p-2 font-mono text-[10px] text-slate-600">
                        {outcome.mailing_id || "—"}
                      </td>
                      <td className="p-2 text-right">
                        {outcome.error ? (
                          <span className="text-rose-600 text-[10px]">{outcome.error}</span>
                        ) : outcome.proof_url ? (
                          <a
                            href={outcome.proof_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-[10px] font-medium text-agile-red hover:underline"
                          >
                            <span>View Proof</span>
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        ) : (
                          <span className="text-slate-400 text-[10px]">Proof queued</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex justify-end pt-2">
              <Button variant="primary" size="sm" onClick={onClose} className="text-xs bg-agile-red text-white">
                Done
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Confirmation Dialog for Remote Campaign Creation */}
      {showConfirmCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-lg max-w-md w-full p-5 space-y-4 shadow-xl border border-slate-200 animate-in fade-in zoom-in-95">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-full bg-agile-red/10 text-agile-red shrink-0">
                <PlusCircle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-900">Confirm Remote Poplar Campaign Creation</h3>
                <p className="text-xs text-slate-600 mt-1">
                  You are about to create a new campaign container in your Poplar account.
                </p>
              </div>
            </div>

            <div className="p-3 bg-slate-50 rounded border border-slate-200 text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-slate-500">Campaign Name:</span>
                <span className="font-semibold text-slate-800 text-right">{newCampaignName.trim()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Purpose / Sub-Purpose:</span>
                <span className="font-mono text-slate-800">{newCampaignPurpose} / {newCampaignSubPurpose}</span>
              </div>
              {newCampaignDescription && (
                <div className="flex justify-between">
                  <span className="text-slate-500">Description:</span>
                  <span className="text-slate-700 italic truncate max-w-[200px]">{newCampaignDescription}</span>
                </div>
              )}
            </div>

            <div className="p-2.5 bg-emerald-50 rounded border border-emerald-200 text-[11px] text-emerald-800 space-y-0.5">
              <p className="font-semibold flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" /> Safe Container Operation
              </p>
              <p className="text-emerald-700">
                This creates only an organizational container in Poplar. It will <strong>not</strong> purchase postage, print pieces, or charge your account.
              </p>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setShowConfirmCreate(false)}
                className="text-xs"
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="primary"
                size="sm"
                onClick={handleExecuteCreatePoplar}
                className="text-xs bg-agile-red hover:bg-agile-red/90 text-white font-semibold"
              >
                Confirm &amp; Create in Poplar
              </Button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
