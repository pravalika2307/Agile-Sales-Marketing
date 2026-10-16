"use client";

import * as React from "react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
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
  onCreateDeal: (payload: DealCreatePayload) => void;
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
  const [formError, setFormError] = React.useState("");

  React.useEffect(() => {
    if (stages.length > 0 && !stageId) {
      setStageId(stages[0].id);
    }
  }, [stages, stageId]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!dealName.trim()) {
      setFormError("Deal name is required.");
      return;
    }
    if (!stageId) {
      setFormError("Pipeline stage is required.");
      return;
    }

    const numericAmount = parseFloat(amount);
    if (isNaN(numericAmount) || numericAmount < 0) {
      setFormError("Amount must be a non-negative number.");
      return;
    }

    onCreateDeal({
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
    setFormError("");
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create New Opportunity"
      description="Add a deal opportunity to your sales pipeline. Strictly mapped to backend Deal schema."
      maxWidth="md"
    >
      <form onSubmit={handleSubmit} className="space-y-4 pt-2">
        {formError && (
          <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
            {formError}
          </div>
        )}

        {/* Deal Name */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-700 block">
            Deal Name <span className="text-agile-red">*</span>
          </label>
          <Input
            type="text"
            placeholder="e.g., Accounts Operations Contract Renewal"
            value={dealName}
            onChange={(e) => {
              setDealName(e.target.value);
              if (formError) setFormError("");
            }}
            className="text-xs h-9"
            autoFocus
          />
        </div>

        {/* Pipeline Stage */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-700 block">
            Pipeline Stage <span className="text-agile-red">*</span>
          </label>
          <Select
            value={stageId}
            onChange={(e) => setStageId(e.target.value)}
            className="text-xs h-9"
          >
            {stages.map((stage) => (
              <option key={stage.id} value={stage.id}>
                {stage.orderIndex}. {stage.name} ({stage.probabilityPct}% win probability)
              </option>
            ))}
          </Select>
        </div>

        {/* Deal Value Amount */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-700 block">
            Deal Amount (USD)
          </label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-xs">
              $
            </span>
            <Input
              type="number"
              min="0"
              step="any"
              placeholder="0.00"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="text-xs h-9 pl-7"
            />
          </div>
        </div>

        {/* Expected Close Date */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-700 block">
            Expected Close Date
          </label>
          <Input
            type="date"
            value={closeDate}
            onChange={(e) => setCloseDate(e.target.value)}
            className="text-xs h-9"
          />
        </div>

        {/* Associated Contact */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-700 block">
            Associated CRM Contact (Optional)
          </label>
          <Select
            value={contactId}
            onChange={(e) => setContactId(e.target.value)}
            className="text-xs h-9"
          >
            <option value="">No Contact Linked</option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.email})
              </option>
            ))}
          </Select>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-2.5 pt-4 border-t border-slate-100">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            className="text-xs h-9 border-slate-200"
          >
            Cancel
          </Button>
          <Button
            type="submit"
            className="text-xs h-9 bg-agile-red hover:bg-agile-red/90 text-white font-medium"
          >
            Create Deal
          </Button>
        </div>
      </form>
    </Modal>
  );
};
