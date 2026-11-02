"use client";

import * as React from "react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { FormSection } from "@/components/ui/form-section";
import {
  PipelineStageItem,
  AvailableContact,
  DealCreatePayload,
} from "@/services/pipelineService";

export interface CreateDealModalProps {
  isOpen: boolean;
  onClose: () => void;
  stages: PipelineStageItem[];
  contacts: AvailableContact[];
  onCreateDeal: (payload: DealCreatePayload) => void | Promise<void>;
}

export const CreateDealModal: React.FC<CreateDealModalProps> = ({
  isOpen,
  onClose,
  stages,
  contacts,
  onCreateDeal,
}) => {
  const [dealName, setDealName] = React.useState("");
  const [stageId, setStageId] = React.useState(stages[0]?.id || "");
  const [amount, setAmount] = React.useState<string>("0");
  const [closeDate, setCloseDate] = React.useState("");
  const [contactId, setContactId] = React.useState("");
  const [nameError, setNameError] = React.useState<string | null>(null);
  const [amountError, setAmountError] = React.useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  React.useEffect(() => {
    if (stages.length > 0 && !stageId) {
      setStageId(stages[0].id);
    }
  }, [stages, stageId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setNameError(null);
    setAmountError(null);

    let hasError = false;
    if (!dealName.trim()) {
      setNameError("Please enter a deal or opportunity title.");
      hasError = true;
    }

    const numericAmount = parseFloat(amount);
    if (isNaN(numericAmount) || numericAmount < 0) {
      setAmountError("Please enter a valid non-negative number.");
      hasError = true;
    }

    if (hasError) return;

    setIsSubmitting(true);
    try {
      await onCreateDeal({
        name: dealName.trim(),
        pipeline_stage_id: stageId,
        amount: numericAmount,
        contact_id: contactId ? contactId : undefined,
        expected_close_date: closeDate ? closeDate : undefined,
        status: "open",
      });

      // Reset form
      setDealName("");
      setAmount("0");
      setCloseDate("");
      setContactId("");
      setNameError(null);
      setAmountError(null);
      onClose();
    } catch {
      // Keep entered values so user does not lose input
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={isSubmitting ? () => {} : onClose}
      title="Create New Opportunity"
      description="Add a deal opportunity to track revenue, win probability, and stage progression in your pipeline."
      maxWidth="md"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Section 1: Opportunity Information */}
        <FormSection title="Deal Overview">
          <Input
            label="Deal Name"
            required
            placeholder="e.g. Accounts Operations Contract Renewal"
            value={dealName}
            error={nameError || undefined}
            onChange={(e) => {
              setDealName(e.target.value);
              if (nameError) setNameError(null);
            }}
            helperText="A clear title identifying the deal, company, or renewal opportunity."
            autoFocus
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Select
              label="Pipeline Stage"
              required
              value={stageId}
              onChange={(e) => setStageId(e.target.value)}
              helperText="Initial stage in your pipeline."
            >
              {stages.map((stage) => (
                <option key={stage.id} value={stage.id}>
                  {stage.orderIndex}. {stage.name} ({stage.probabilityPct}% win probability)
                </option>
              ))}
            </Select>

            <Input
              label="Deal Value ($ USD)"
              type="number"
              min="0"
              step="any"
              placeholder="0.00"
              value={amount}
              error={amountError || undefined}
              onChange={(e) => {
                setAmount(e.target.value);
                if (amountError) setAmountError(null);
              }}
              helperText="Estimated deal value or expected contract total."
            />
          </div>
        </FormSection>

        {/* Section 2: Timeline & Contact Linkage (Progressive Disclosure) */}
        <FormSection
          title="Timeline & Contact Linkage"
          description="Link an associated prospect or target close date."
          collapsible
          defaultOpen={false}
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input
              label="Expected Close Date"
              optional
              type="date"
              value={closeDate}
              onChange={(e) => setCloseDate(e.target.value)}
              helperText="Target date for finalizing the contract."
            />

            <Select
              label="Associated CRM Contact"
              optional
              value={contactId}
              onChange={(e) => setContactId(e.target.value)}
              helperText="Primary point of contact for this deal."
            >
              <option value="">No Contact Linked</option>
              {contacts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.email})
                </option>
              ))}
            </Select>
          </div>
        </FormSection>

        {/* Actions */}
        <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-slate-100">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={isSubmitting}
            onClick={onClose}
            className="text-xs"
          >
            Cancel
          </Button>
          <Button
            type="submit"
            size="sm"
            isLoading={isSubmitting}
            disabled={isSubmitting || !dealName.trim()}
            className="text-xs shadow-xs"
          >
            Create Opportunity
          </Button>
        </div>
      </form>
    </Modal>
  );
};
