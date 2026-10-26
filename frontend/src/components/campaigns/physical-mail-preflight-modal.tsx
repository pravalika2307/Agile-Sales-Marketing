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
  XCircle,
} from "lucide-react";
import {
  approveAndSubmitPhysicalMail,
  getPhysicalMailStatus,
  previewCampaignPhysicalMail,
  syncCampaignPhysicalMail,
  validateCampaignPhysicalMail,
  type PhysicalMailPreviewResponse,
  type PhysicalMailStatus,
  type PhysicalMailSubmissionResponse,
  type PhysicalMailValidateResponse,
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
  // Step state: "validate" | "preview" | "submitted"
  const [activeStep, setActiveStep] = useState<"validate" | "preview" | "submitted">("validate");

  // Config & Provider Status
  const [poplarStatus, setPoplarStatus] = useState<PhysicalMailStatus | null>(null);
  const [poplarCampaignId, setPoplarCampaignId] = useState<string>("");
  const [poplarCreativeId, setPoplarCreativeId] = useState<string>("");

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

  // Load config on open
  useEffect(() => {
    if (isOpen) {
      setErrorMessage(null);
      setSyncMessage(null);
      getPhysicalMailStatus()
        .then((status) => {
          setPoplarStatus(status);
          if (status.default_campaign_id) setPoplarCampaignId(status.default_campaign_id);
          if (status.default_creative_id) setPoplarCreativeId(status.default_creative_id);
        })
        .catch(() => {
          // If status endpoint fails, allow manual ID entry
        });
    }
  }, [isOpen]);

  // Step 1: Validate Addresses
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

  // Step 2: Fetch Preview & Budget
  const handleProceedToPreview = async () => {
    setIsPreviewing(true);
    setErrorMessage(null);
    try {
      const res = await previewCampaignPhysicalMail(campaignId, {
        poplar_campaign_id: poplarCampaignId.trim() || undefined,
        poplar_creative_id: poplarCreativeId.trim() || undefined,
      });
      setPreviewResult(res);
      setActiveStep("preview");
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to generate mail preview and cost calculation.");
    } finally {
      setIsPreviewing(false);
    }
  };

  // Step 3: Approve and Submit to Poplar (Test Environment)
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
      title={`Direct Mail Pre-Flight & Test Dispatch — ${campaignName}`}
    >
      <div className="space-y-4 max-h-[78vh] overflow-y-auto pr-1">
        {/* Environment Safety Notice */}
        <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-lg flex items-start gap-2.5 text-xs text-amber-900">
          <ShieldCheck className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <span className="font-semibold">Poplar Test Environment Active</span>
            <p className="text-[11px] text-amber-800">
              Dispatches execute against Poplar’s test API sandbox or safe simulation mode. Digital proof URLs will be
              generated, zero commercial print orders will be submitted, and no billing charges will occur.
            </p>
          </div>
        </div>

        {/* Global Error Alert */}
        {errorMessage && (
          <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-800 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <div className="flex-1">{errorMessage}</div>
          </div>
        )}

        {/* Workflow Progression Tabs */}
        <div className="flex border-b border-slate-200 text-xs font-medium">
          <button
            onClick={() => setActiveStep("validate")}
            className={`py-2 px-3 border-b-2 transition-colors ${
              activeStep === "validate"
                ? "border-agile-red text-agile-red font-semibold"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            1. Address Verification
          </button>
          <button
            onClick={() => {
              if (validationReport) setActiveStep("preview");
            }}
            disabled={!validationReport}
            className={`py-2 px-3 border-b-2 transition-colors ${
              activeStep === "preview"
                ? "border-agile-red text-agile-red font-semibold"
                : "border-transparent text-slate-400 disabled:opacity-50"
            }`}
          >
            2. Preview & Budget
          </button>
          <button
            onClick={() => {
              if (submissionResult) setActiveStep("submitted");
            }}
            disabled={!submissionResult}
            className={`py-2 px-3 border-b-2 transition-colors ${
              activeStep === "submitted"
                ? "border-agile-red text-agile-red font-semibold"
                : "border-transparent text-slate-400 disabled:opacity-50"
            }`}
          >
            3. Submission Results
          </button>
        </div>

        {/* ── STEP 1: ADDRESS VALIDATION ── */}
        {activeStep === "validate" && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 border border-slate-200 rounded-lg">
              <div>
                <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                  Poplar Campaign ID *
                </label>
                <Input
                  placeholder="e.g. cmp_01h8abcdef..."
                  value={poplarCampaignId}
                  onChange={(e) => setPoplarCampaignId(e.target.value)}
                  className="h-8 text-xs font-mono"
                />
              </div>
              <div>
                <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                  Poplar Creative ID (Optional)
                </label>
                <Input
                  placeholder="e.g. crt_01h8abcdef..."
                  value={poplarCreativeId}
                  onChange={(e) => setPoplarCreativeId(e.target.value)}
                  className="h-8 text-xs font-mono"
                />
              </div>
            </div>

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
                      Validating Addresses...
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
                    <span className="text-[10px] text-rose-700 uppercase font-semibold">Invalid / Missing</span>
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
                  <Button variant="outline" size="sm" onClick={handleValidateAddresses} className="text-xs">
                    Re-Audit
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

        {/* ── STEP 2: PREVIEW & BUDGET AUTHORIZATION ── */}
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
                  USPS First Class Standard
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
                    <span className="font-medium text-slate-700">Poplar Campaign: {previewResult.poplar_campaign_id}</span>
                  </div>
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
                Test Mode (Free)
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
                  for <strong>{previewResult.valid_count}</strong> valid recipient(s). I understand this executes in
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
                Back to Validation
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

        {/* ── STEP 3: SUBMISSION RESULTS & TRACKING ── */}
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
    </Modal>
  );
}
