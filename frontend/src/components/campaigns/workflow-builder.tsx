"use client";

import * as React from "react";
import {
  WorkflowConfig,
  WorkflowNode,
  WorkflowEdge,
  WorkflowValidationResult,
  TemplatePreviewResponse,
  fetchCampaignWorkflow,
  saveCampaignWorkflow,
  validateWorkflow,
  previewStepTemplate,
  CampaignItem,
} from "@/services/campaignService";
import {
  EmailTemplateItem,
  fetchEmailTemplates,
  createEmailTemplate,
  updateEmailTemplate,
  generateAIEmail,
  TEMPLATE_CATEGORIES,
} from "@/services/templateService";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import {
  Mail,
  Clock,
  PhoneCall,
  MessageSquare,
  GitBranch,
  Play,
  Plus,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Eye,
  Save,
  RefreshCw,
  User,
  Building2,
  ArrowDown,
  X,
  ExternalLink,
  Zap,
  Info,
  Sparkles,
  BookOpen,
  Bookmark,
  Search,
  Check,
  Smartphone,
  ShieldCheck,
} from "lucide-react";
import { estimateSMSSegments } from "@/services/smsService";

export interface WorkflowBuilderProps {
  campaignId: string;
  campaignName: string;
  campaignStatus: string;
  initialWorkflow?: WorkflowConfig | null;
  initialDescription?: string | null;
  onSaveSuccess?: () => void;
  onSaved?: () => void;
  onClose?: () => void;
}

const VARIABLE_TAGS = [
  { tag: "{contact.first_name}", label: "First Name" },
  { tag: "{contact.last_name}", label: "Last Name" },
  { tag: "{contact.email}", label: "Email" },
  { tag: "{contact.company}", label: "Company" },
  { tag: "{contact.job_title}", label: "Job Title" },
  { tag: "{contact.phone}", label: "Phone" },
  { tag: "{sender.name}", label: "Sender Name" },
  { tag: "{sender.company_name}", label: "Sender Company" },
  { tag: "{booking_link}", label: "Booking Link" },
];

export const WorkflowBuilder: React.FC<WorkflowBuilderProps> = ({
  campaignId,
  campaignName,
  campaignStatus,
  initialWorkflow,
  initialDescription,
  onSaveSuccess,
  onSaved,
  onClose,
}) => {
  const [workflow, setWorkflow] = React.useState<WorkflowConfig>(
    initialWorkflow || {
      nodes: [{ id: "start", type: "start", title: "Campaign Trigger", config: {} }],
      edges: [],
    }
  );
  const [description, setDescription] = React.useState(initialDescription || "");
  const [isLoadingWorkflow, setIsLoadingWorkflow] = React.useState(!initialWorkflow);
  const [selectedNodeId, setSelectedNodeId] = React.useState<string | null>(null);
  const [isSaving, setIsSaving] = React.useState(false);
  const [saveMessage, setSaveMessage] = React.useState<{ type: "success" | "error"; text: string } | null>(null);
  const [validation, setValidation] = React.useState<WorkflowValidationResult | null>(null);

  // Load existing saved workflow if not provided initially
  React.useEffect(() => {
    if (!initialWorkflow && campaignId) {
      setIsLoadingWorkflow(true);
      fetchCampaignWorkflow(campaignId)
        .then((wf) => {
          if (wf && wf.nodes && wf.nodes.length > 0) {
            setWorkflow(wf);
          }
        })
        .catch((err) => {
          console.error("Failed to recover campaign workflow:", err);
        })
        .finally(() => {
          setIsLoadingWorkflow(false);
        });
    }
  }, [campaignId, initialWorkflow]);

  // Template preview state
  const [isPreviewOpen, setIsPreviewOpen] = React.useState(false);
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [previewResult, setPreviewResult] = React.useState<TemplatePreviewResponse | null>(null);
  const [previewContactId, setPreviewContactId] = React.useState<string>("");
  const [previewMode, setPreviewMode] = React.useState<"text" | "html">("text");
  const [campaignContacts, setCampaignContacts] = React.useState<
    Array<{ id: string; name: string; email: string; phone?: string | null; companyName?: string | null }>
  >([]);
  const [allOrgContacts, setAllOrgContacts] = React.useState<
    Array<{ id: string; name: string; email: string; phone?: string | null; companyName?: string | null }>
  >([]);

  // Load available contacts for live preview (prioritize campaign-enrolled contacts)
  React.useEffect(() => {
    async function loadContacts() {
      try {
        const [campRes, orgRes] = await Promise.all([
          campaignId
            ? fetch(`/api/campaigns/${campaignId}/contacts?limit=100`, { cache: "no-store" }).catch(() => null)
            : null,
          fetch("/api/contacts?limit=100", { cache: "no-store" }).catch(() => null),
        ]);

        let enrolledList: Array<{ id: string; name: string; email: string; phone?: string | null; companyName?: string | null }> = [];
        if (campRes && campRes.ok) {
          const rawCamp = await campRes.json();
          enrolledList = (rawCamp || []).map((c: any) => {
            const inner = c.contact || c;
            const firstName = inner.first_name || c.first_name || "";
            const lastName = inner.last_name || c.last_name || "";
            const fullName = `${firstName} ${lastName}`.trim() || inner.name || c.contactName || inner.email || c.email || "Contact";
            const email = inner.email || c.contactEmail || c.email || "";
            const phone = inner.phone || c.phone || null;
            const companyName = inner.company?.name || inner.company_name || c.companyName || c.company_name || null;
            return {
              id: c.contact_id || c.contactId || inner.id || c.id,
              name: fullName,
              email: email,
              phone: phone,
              companyName: companyName,
            };
          });
          setCampaignContacts(enrolledList);
        }

        let orgList: Array<{ id: string; name: string; email: string; phone?: string | null; companyName?: string | null }> = [];
        if (orgRes && orgRes.ok) {
          const rawOrg = await orgRes.json();
          orgList = (rawOrg || []).map((c: any) => ({
            id: c.id,
            name: `${c.first_name || ""} ${c.last_name || ""}`.trim() || c.email,
            email: c.email,
            phone: c.phone || null,
            companyName: c.company?.name || c.company_name || null,
          }));
          setAllOrgContacts(orgList);
        }

        // Initialize previewContactId: prioritize enrolled contact, then org contact
        if (enrolledList.length > 0) {
          setPreviewContactId(enrolledList[0].id);
        } else if (orgList.length > 0) {
          setPreviewContactId(orgList[0].id);
        } else {
          setPreviewContactId("__sample__");
        }
      } catch (err) {
        console.error("Failed to load contacts for preview:", err);
      }
    }
    loadContacts();
  }, [campaignId]);

  // ── AI Email Generation State ──────────────────────────────────────────────
  const [isAIGenOpen, setIsAIGenOpen] = React.useState(false);
  const [aiObjective, setAiObjective] = React.useState("");
  const [aiAudience, setAiAudience] = React.useState("");
  const [aiTone, setAiTone] = React.useState("professional");
  const [aiCta, setAiCta] = React.useState("");
  const [aiLoading, setAiLoading] = React.useState(false);
  const [aiError, setAiError] = React.useState<string | null>(null);
  const [aiGeneratedSubject, setAiGeneratedSubject] = React.useState("");
  const [aiGeneratedBody, setAiGeneratedBody] = React.useState("");
  const [aiHasGenerated, setAiHasGenerated] = React.useState(false);

  // ── Reusable Saved Templates State ─────────────────────────────────────────
  const [isTemplatePickerOpen, setIsTemplatePickerOpen] = React.useState(false);
  const [savedTemplates, setSavedTemplates] = React.useState<EmailTemplateItem[]>([]);
  const [isLoadingTemplates, setIsLoadingTemplates] = React.useState(false);
  const [templateSearch, setTemplateSearch] = React.useState("");
  const [templateCategory, setTemplateCategory] = React.useState("all");
  const [selectedTemplateForPreview, setSelectedTemplateForPreview] = React.useState<EmailTemplateItem | null>(null);

  // ── Save As Template State ────────────────────────────────────────────────
  const [isSaveTemplateOpen, setIsSaveTemplateOpen] = React.useState(false);
  const [newTemplateName, setNewTemplateName] = React.useState("");
  const [newTemplateDescription, setNewTemplateDescription] = React.useState("");
  const [newTemplateCategory, setNewTemplateCategory] = React.useState("outbound");
  const [isSavingTemplate, setIsSavingTemplate] = React.useState(false);
  const [saveTemplateError, setSaveTemplateError] = React.useState<string | null>(null);

  // ── Update Master Template State ──────────────────────────────────────────
  const [isUpdateTemplateOpen, setIsUpdateTemplateOpen] = React.useState(false);
  const [isUpdatingTemplate, setIsUpdatingTemplate] = React.useState(false);
  const [updateTemplateError, setUpdateTemplateError] = React.useState<string | null>(null);

  // Open AI Generator modal pre-populated
  const handleOpenAIGenerator = () => {
    setAiObjective("");
    setAiAudience("");
    setAiTone("professional");
    setAiCta("");
    setAiError(null);
    setAiGeneratedSubject("");
    setAiGeneratedBody("");
    setAiHasGenerated(false);
    setIsAIGenOpen(true);
  };

  // Run AI Generation
  const handleRunAIGeneration = async () => {
    if (!aiObjective.trim()) {
      setAiError("Please provide an email objective or purpose.");
      return;
    }
    setAiLoading(true);
    setAiError(null);
    try {
      const result = await generateAIEmail({
        campaign_name: campaignName,
        email_objective: aiObjective,
        target_audience: aiAudience || undefined,
        tone: aiTone,
        call_to_action: aiCta || undefined,
      });
      setAiGeneratedSubject(result.subject);
      setAiGeneratedBody(result.body);
      setAiHasGenerated(true);
    } catch (err: unknown) {
      setAiError(err instanceof Error ? err.message : "AI generation failed. Your existing text was preserved.");
    } finally {
      setAiLoading(false);
    }
  };

  // Apply AI Generated Content to Selected Step
  const handleApplyAIGeneration = () => {
    if (!selectedNodeId) return;
    updateSelectedNodeConfig("subject", aiGeneratedSubject);
    updateSelectedNodeConfig("body", aiGeneratedBody);
    setIsAIGenOpen(false);
  };

  // Open Template Picker & load templates
  const handleOpenTemplatePicker = async () => {
    setIsTemplatePickerOpen(true);
    setIsLoadingTemplates(true);
    try {
      const templates = await fetchEmailTemplates();
      setSavedTemplates(templates);
      if (templates.length > 0) {
        setSelectedTemplateForPreview(templates[0]);
      } else {
        setSelectedTemplateForPreview(null);
      }
    } catch (err) {
      console.error("Failed to fetch templates:", err);
    } finally {
      setIsLoadingTemplates(false);
    }
  };

  // Apply selected saved template to current step
  const handleApplyTemplate = (tmpl: EmailTemplateItem) => {
    if (!selectedNodeId) return;
    updateSelectedNodeConfig("subject", tmpl.subject_template);
    updateSelectedNodeConfig("body", tmpl.body_template);
    updateSelectedNodeConfig("applied_template_id", tmpl.id);
    updateSelectedNodeConfig("applied_template_name", tmpl.name);
    setIsTemplatePickerOpen(false);
  };

  // Open Save As Template modal
  const handleOpenSaveTemplate = () => {
    if (!selectedNode) return;
    setNewTemplateName(selectedNode.title || "Custom Template");
    setNewTemplateDescription("");
    setNewTemplateCategory("outbound");
    setSaveTemplateError(null);
    setIsSaveTemplateOpen(true);
  };

  // Submit Save As Template
  const handleSaveAsTemplate = async () => {
    if (!selectedNode) return;
    if (!newTemplateName.trim()) {
      setSaveTemplateError("Template name is required.");
      return;
    }
    const currentSubject = selectedNode.config.subject || "";
    const currentBody = selectedNode.config.body || "";
    if (!currentSubject.trim() || !currentBody.trim()) {
      setSaveTemplateError("Subject line and email body cannot be empty.");
      return;
    }

    setIsSavingTemplate(true);
    setSaveTemplateError(null);
    try {
      const created = await createEmailTemplate({
        name: newTemplateName.trim(),
        description: newTemplateDescription.trim() || undefined,
        category: newTemplateCategory,
        subject_template: currentSubject,
        body_template: currentBody,
      });
      // Link applied template reference to the node
      updateSelectedNodeConfig("applied_template_id", created.id);
      updateSelectedNodeConfig("applied_template_name", created.name);
      setIsSaveTemplateOpen(false);
      setSaveMessage({ type: "success", text: `Template "${created.name}" saved successfully and ready for reuse across campaigns.` });
    } catch (err: unknown) {
      setSaveTemplateError(err instanceof Error ? err.message : "Failed to save template.");
    } finally {
      setIsSavingTemplate(false);
    }
  };

  // Submit Update Master Template
  const handleUpdateMasterTemplate = async () => {
    if (!selectedNode || !selectedNode.config.applied_template_id) return;
    const templateId = selectedNode.config.applied_template_id;
    const currentSubject = selectedNode.config.subject || "";
    const currentBody = selectedNode.config.body || "";

    setIsUpdatingTemplate(true);
    setUpdateTemplateError(null);
    try {
      const updated = await updateEmailTemplate(templateId, {
        subject_template: currentSubject,
        body_template: currentBody,
      });
      setIsUpdateTemplateOpen(false);
      setSaveMessage({ type: "success", text: `Master template "${updated.name}" updated successfully.` });
    } catch (err: unknown) {
      setUpdateTemplateError(err instanceof Error ? err.message : "Failed to update master template.");
    } finally {
      setIsUpdatingTemplate(false);
    }
  };

  const selectedNode = workflow.nodes.find((n) => n.id === selectedNodeId) || null;

  // Add a new step after a specific node index
  const handleAddStep = (afterIndex: number, type: "email" | "wait" | "voice" | "sms" | "condition") => {
    const newId = `node-${type}-${Date.now()}`;
    let title = "";
    let defaultConfig: Record<string, any> = {};

    if (type === "email") {
      title = `Email Step`;
      defaultConfig = {
        subject: "Introducing Agile Sales & Marketing for {contact.company}",
        body: "Hi {contact.first_name},\n\nI noticed your role as {contact.job_title} at {contact.company}.\n\nWould you have 10 minutes next week for a brief briefing?\n\nBest regards,\n{sender_name}\n{sender_company_name}",
        delay_days: 0,
        delay_hours: 0,
        is_active: true,
      };
    } else if (type === "wait") {
      title = "Wait Delay";
      defaultConfig = { duration: 2, unit: "days" };
    } else if (type === "voice") {
      title = "AI Voice SDR Call";
      defaultConfig = { agent_type: "outbound_sdr", phone_required: true };
    } else if (type === "sms") {
      title = "SMS Outreach";
      defaultConfig = {
        body: "Hi {contact.first_name}, this is {sender_name} from {sender_company}. Are you available for a brief 10-minute briefing next week? Let me know or book directly: {booking_link}",
        delay_days: 0,
        delay_hours: 0,
        is_active: true,
      };
    } else if (type === "condition") {
      title = "Outcome Branch";
      defaultConfig = { condition_type: "email_replied" };
    }

    const newNode: WorkflowNode = {
      id: newId,
      type,
      title,
      config: defaultConfig,
    };

    const newNodes = [...workflow.nodes];
    newNodes.splice(afterIndex + 1, 0, newNode);

    // Rebuild simple sequential edges
    const newEdges: WorkflowEdge[] = [];
    for (let i = 0; i < newNodes.length - 1; i++) {
      newEdges.push({
        id: `e-${newNodes[i].id}-${newNodes[i + 1].id}`,
        source: newNodes[i].id,
        target: newNodes[i + 1].id,
        label: newNodes[i].type === "condition" ? "Branch" : "Next",
      });
    }

    setWorkflow({ nodes: newNodes, edges: newEdges });
    setSelectedNodeId(newId);
  };

  // Remove a step
  const handleRemoveNode = (nodeId: string) => {
    if (workflow.nodes.find((n) => n.id === nodeId)?.type === "start") {
      alert("The Campaign Start node cannot be removed.");
      return;
    }

    const newNodes = workflow.nodes.filter((n) => n.id !== nodeId);
    const newEdges: WorkflowEdge[] = [];
    for (let i = 0; i < newNodes.length - 1; i++) {
      newEdges.push({
        id: `e-${newNodes[i].id}-${newNodes[i + 1].id}`,
        source: newNodes[i].id,
        target: newNodes[i + 1].id,
        label: newNodes[i].type === "condition" ? "Branch" : "Next",
      });
    }

    setWorkflow({ nodes: newNodes, edges: newEdges });
    if (selectedNodeId === nodeId) {
      setSelectedNodeId(null);
    }
  };

  // Update selected node config
  const updateSelectedNodeConfig = (key: string, value: any) => {
    if (!selectedNodeId) return;
    setWorkflow((prev) => ({
      ...prev,
      nodes: prev.nodes.map((n) => {
        if (n.id === selectedNodeId) {
          return {
            ...n,
            config: { ...n.config, [key]: value },
          };
        }
        return n;
      }),
    }));
  };

  const updateSelectedNodeTitle = (title: string) => {
    if (!selectedNodeId) return;
    setWorkflow((prev) => ({
      ...prev,
      nodes: prev.nodes.map((n) => (n.id === selectedNodeId ? { ...n, title } : n)),
    }));
  };

  // Insert personalization variable
  const insertVariable = (field: "subject" | "body", tag: string) => {
    if (!selectedNode) return;
    const currentVal = selectedNode.config[field] || "";
    updateSelectedNodeConfig(field, currentVal + (currentVal ? " " : "") + tag);
  };

  // Run validation
  const handleValidate = async () => {
    try {
      const result = await validateWorkflow(campaignId, workflow);
      setValidation(result);
    } catch (err: unknown) {
      console.error("Validation error:", err);
      setValidation({
        is_valid: false,
        errors: [err instanceof Error ? err.message : "Validation failed"],
        warnings: [],
        supported_step_types: ["email", "wait", "voice", "sms", "condition"],
        unavailable_step_types: [],
      });
    }
  };

  // Save workflow
  const handleSave = async () => {
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const resp = await saveCampaignWorkflow(campaignId, workflow, description);
      setValidation(resp.validation);
      if (resp.validation.is_valid) {
        setSaveMessage({ type: "success", text: "Workflow and sequence steps saved successfully." });
      } else {
        setSaveMessage({
          type: "error",
          text: `Workflow saved as draft with ${resp.validation.errors.length} validation item(s) to resolve before activation.`,
        });
      }
      onSaveSuccess?.();
      onSaved?.();
    } catch (err: unknown) {
      setSaveMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to persist workflow.",
      });
    } finally {
      setIsSaving(false);
    }
  };

  // Preview Email Step
  const handlePreview = async () => {
    if (!selectedNode || selectedNode.type !== "email") return;
    setIsPreviewOpen(true);
    setPreviewLoading(true);

    let targetId = previewContactId;
    if (!targetId) {
      if (campaignContacts.length > 0) {
        targetId = campaignContacts[0].id;
      } else if (allOrgContacts.length > 0) {
        targetId = allOrgContacts[0].id;
      } else {
        targetId = "__sample__";
      }
      setPreviewContactId(targetId);
    }

    const isSample = targetId === "__sample__";
    try {
      const res = await previewStepTemplate(campaignId, {
        subject_template: selectedNode.config.subject,
        body_template: selectedNode.config.body,
        contact_id: isSample ? undefined : targetId,
        use_sample: isSample,
        sender_name: "Agile Sales Team",
        sender_company_name: "Agile Sales & Marketing",
      });
      setPreviewResult(res);
    } catch (err) {
      console.error("Preview failed:", err);
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-150">
      <div className="flex flex-col w-full max-w-7xl h-[92vh] bg-slate-50/90 rounded-xl border border-slate-200 overflow-hidden shadow-2xl">
        {/* Top Action Bar */}
      <div className="flex items-center justify-between px-6 py-3.5 bg-white border-b border-slate-200">
        <div className="flex items-center gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-header">{campaignName}</h2>
              <Badge
                variant={
                  campaignStatus === "active"
                    ? "coral"
                    : campaignStatus === "completed"
                    ? "success"
                    : campaignStatus === "paused"
                    ? "warning"
                    : "neutral"
                }
                className="text-[10px] capitalize font-medium"
              >
                {campaignStatus}
              </Badge>
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Visual Workflow Builder • {workflow.nodes.length} nodes configured
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleValidate}
            className="text-xs h-8 flex items-center gap-1.5"
          >
            <CheckCircle2 className="w-3.5 h-3.5 text-slate-500" />
            <span>Validate</span>
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={handleSave}
            disabled={isSaving}
            className="text-xs h-8 flex items-center gap-1.5 shadow-xs"
          >
            <Save className="w-3.5 h-3.5" />
            <span>{isSaving ? "Saving..." : "Save Workflow"}</span>
          </Button>

          {onClose && (
            <Button variant="ghost" size="sm" onClick={onClose} className="h-8 w-8 p-0 text-slate-400 hover:text-slate-700">
              <X className="w-4 h-4" />
            </Button>
          )}
        </div>
      </div>

      {/* Save Notification Banner */}
      {saveMessage && (
        <div
          className={`px-6 py-2.5 text-xs flex items-center justify-between ${
            saveMessage.type === "success"
              ? "bg-emerald-50 text-emerald-800 border-b border-emerald-200"
              : "bg-amber-50 text-amber-800 border-b border-amber-200"
          }`}
        >
          <div className="flex items-center gap-2">
            {saveMessage.type === "success" ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            )}
            <span>{saveMessage.text}</span>
          </div>
          <button onClick={() => setSaveMessage(null)} className="text-slate-400 hover:text-slate-600">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Validation Issues Alert */}
      {validation && !validation.is_valid && (
        <div className="px-6 py-2.5 bg-rose-50 border-b border-rose-200 text-xs text-rose-700">
          <p className="font-semibold flex items-center gap-1.5 mb-1">
            <AlertCircle className="w-4 h-4 text-rose-500" />
            Configuration Requirements ({validation.errors.length}):
          </p>
          <ul className="list-disc pl-5 space-y-0.5 text-[11px]">
            {validation.errors.map((e, idx) => (
              <li key={idx}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Main Workspace: Left Canvas, Right Config Drawer */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Interactive Workflow Flowchart */}
        <div className="flex-1 overflow-y-auto p-8 flex flex-col items-center space-y-4">
          {workflow.nodes.map((node, index) => {
            const isSelected = node.id === selectedNodeId;
            const isStart = node.type === "start";

            return (
              <React.Fragment key={node.id}>
                {/* Node Card */}
                <div
                  onClick={() => setSelectedNodeId(node.id)}
                  className={`w-80 p-4 rounded-xl border transition-all cursor-pointer select-none relative ${
                    isSelected
                      ? "border-agile-red ring-2 ring-agile-red/20 bg-white shadow-md"
                      : "border-slate-200 bg-white hover:border-slate-300 shadow-xs"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                          node.type === "start"
                            ? "bg-slate-900 text-white"
                            : node.type === "email"
                            ? "bg-agile-red text-white"
                            : node.type === "wait"
                            ? "bg-amber-500 text-white"
                            : node.type === "voice"
                            ? "bg-blue-600 text-white"
                            : node.type === "sms"
                            ? "bg-emerald-600 text-white"
                            : node.type === "condition"
                            ? "bg-purple-600 text-white"
                            : "bg-slate-300 text-slate-700"
                        }`}
                      >
                        {node.type === "start" && <Play className="w-4 h-4 fill-current" />}
                        {node.type === "email" && <Mail className="w-4 h-4" />}
                        {node.type === "wait" && <Clock className="w-4 h-4" />}
                        {node.type === "voice" && <PhoneCall className="w-4 h-4" />}
                        {node.type === "sms" && <Smartphone className="w-4 h-4" />}
                        {node.type === "condition" && <GitBranch className="w-4 h-4" />}
                      </div>

                      <div>
                        <h4 className="text-xs font-bold text-header">{node.title}</h4>
                        <span className="text-[10px] text-slate-400 capitalize">
                          {node.type === "voice" ? "Retell AI Voice SDR" : node.type === "sms" ? "Twilio SMS" : node.type} Step
                        </span>
                      </div>
                    </div>

                    {!isStart && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRemoveNode(node.id);
                        }}
                        className="text-slate-300 hover:text-rose-500 transition-colors p-1"
                        title="Remove Step"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>

                  {/* Step Summary Details */}
                  <div className="mt-2.5 pt-2 border-t border-slate-100 text-[11px] text-slate-600">
                    {node.type === "start" && (
                      <p className="text-slate-400 italic">Campaign enrolls eligible CRM contacts.</p>
                    )}
                    {node.type === "email" && (
                      <div className="space-y-0.5 truncate">
                        <p className="font-mono text-[10px] text-slate-500 truncate">
                          Subject: {node.config.subject || "(Empty subject)"}
                        </p>
                      </div>
                    )}
                    {node.type === "wait" && (
                      <p className="text-slate-700 font-medium">
                        Delay: {node.config.duration || 1} {node.config.unit || "days"}
                      </p>
                    )}
                    {node.type === "voice" && (
                      <p className="text-blue-700 font-medium">Outbound SDR • Verified Agent</p>
                    )}
                    {node.type === "sms" && (
                      <p className="text-emerald-700 font-medium">
                        {node.config.body
                          ? `${estimateSMSSegments(node.config.body).characterCount} chars • ${estimateSMSSegments(node.config.body).segmentCount} seg`
                          : "Twilio SMS (Safe Mode)"}
                      </p>
                    )}
                    {node.type === "condition" && (
                      <p className="text-purple-700 font-medium">
                        Check: {node.config.condition_type || "email_replied"}
                      </p>
                    )}
                  </div>
                </div>

                {/* Connector Line & "Add Step" Intermediary Button */}
                {index < workflow.nodes.length - 1 && (
                  <div className="flex flex-col items-center my-0.5 relative group">
                    <div className="w-0.5 h-6 bg-slate-300" />
                    <div className="relative">
                      <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-full px-2 py-0.5 shadow-xs text-[10px] text-slate-500">
                        <ArrowDown className="w-3 h-3 text-slate-400" />
                        <span>Add Next</span>
                        <div className="flex items-center gap-1 pl-1">
                          <button
                            onClick={() => handleAddStep(index, "email")}
                            className="p-1 hover:bg-slate-100 rounded text-agile-red"
                            title="Add Email Step"
                          >
                            <Mail className="w-3 h-3" />
                          </button>
                          <button
                            onClick={() => handleAddStep(index, "wait")}
                            className="p-1 hover:bg-slate-100 rounded text-amber-600"
                            title="Add Wait Delay"
                          >
                            <Clock className="w-3 h-3" />
                          </button>
                          <button
                            onClick={() => handleAddStep(index, "voice")}
                            className="p-1 hover:bg-slate-100 rounded text-blue-600"
                            title="Add AI Voice Call"
                          >
                            <PhoneCall className="w-3 h-3" />
                          </button>
                          <button
                            onClick={() => handleAddStep(index, "sms")}
                            className="p-1 hover:bg-slate-100 rounded text-emerald-600"
                            title="Add SMS Message"
                          >
                            <Smartphone className="w-3 h-3" />
                          </button>
                          <button
                            onClick={() => handleAddStep(index, "condition")}
                            className="p-1 hover:bg-slate-100 rounded text-purple-600"
                            title="Add Condition Branch"
                          >
                            <GitBranch className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    </div>
                    <div className="w-0.5 h-6 bg-slate-300" />
                  </div>
                )}
              </React.Fragment>
            );
          })}

          {/* End of Sequence Adder */}
          <div className="pt-2 flex items-center gap-2">
            <span className="text-xs text-slate-400 font-medium">Append step:</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleAddStep(workflow.nodes.length - 1, "email")}
              className="text-xs h-7 gap-1"
            >
              <Mail className="w-3 h-3 text-agile-red" />
              <span>Email</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleAddStep(workflow.nodes.length - 1, "wait")}
              className="text-xs h-7 gap-1"
            >
              <Clock className="w-3 h-3 text-amber-500" />
              <span>Wait</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleAddStep(workflow.nodes.length - 1, "voice")}
              className="text-xs h-7 gap-1"
            >
              <PhoneCall className="w-3 h-3 text-blue-600" />
              <span>Voice SDR</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleAddStep(workflow.nodes.length - 1, "sms")}
              className="text-xs h-7 gap-1"
            >
              <Smartphone className="w-3 h-3 text-emerald-600" />
              <span>SMS</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleAddStep(workflow.nodes.length - 1, "condition")}
              className="text-xs h-7 gap-1"
            >
              <GitBranch className="w-3 h-3 text-purple-600" />
              <span>Condition</span>
            </Button>
          </div>
        </div>

        {/* Right: Step Configuration Panel */}
        <div className="w-96 bg-white border-l border-slate-200 overflow-y-auto p-5 flex flex-col justify-between">
          {selectedNode ? (
            <div className="space-y-5">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                    Step Configuration
                  </h3>
                  <p className="text-xs font-semibold text-header mt-0.5">{selectedNode.title}</p>
                </div>
                <Badge variant="neutral" className="text-[10px] capitalize">
                  {selectedNode.type}
                </Badge>
              </div>

              {/* Title input */}
              <Input
                label="Step Title"
                value={selectedNode.title}
                onChange={(e) => updateSelectedNodeTitle(e.target.value)}
              />

              {/* 1. EMAIL STEP CONFIG */}
              {selectedNode.type === "email" && (
                <div className="space-y-4">
                  {/* Template Tools Action Bar */}
                  <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                        Template Tools
                      </span>
                      {selectedNode.config.applied_template_id && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200 font-medium">
                          Saved Template Applied
                        </span>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handleOpenAIGenerator}
                        className="text-xs h-8 flex items-center justify-center gap-1.5 bg-indigo-50/70 border-indigo-200 text-indigo-700 hover:bg-indigo-100 font-medium"
                      >
                        <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                        <span>Generate with AI</span>
                      </Button>

                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handleOpenTemplatePicker}
                        className="text-xs h-8 flex items-center justify-center gap-1.5 bg-white border-slate-200 text-slate-700 hover:bg-slate-100"
                      >
                        <BookOpen className="w-3.5 h-3.5 text-slate-500" />
                        <span>Saved Templates</span>
                      </Button>
                    </div>

                    {selectedNode.config.applied_template_id && (
                      <div className="pt-2 border-t border-slate-200/80 flex items-center justify-between text-[11px] text-slate-600">
                        <span className="truncate max-w-[190px]" title={selectedNode.config.applied_template_name}>
                          Master: <strong>{selectedNode.config.applied_template_name || "Saved Template"}</strong>
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => setIsUpdateTemplateOpen(true)}
                            className="text-indigo-600 hover:text-indigo-800 font-semibold underline text-[10px]"
                          >
                            Update Master
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              updateSelectedNodeConfig("applied_template_id", null);
                              updateSelectedNodeConfig("applied_template_name", null);
                            }}
                            className="text-slate-400 hover:text-slate-600 text-[10px]"
                            title="Unlink from master template"
                          >
                            Unlink
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  <div>
                    <Input
                      label="Subject Line *"
                      required
                      placeholder="e.g. Briefing for {contact.company}"
                      value={selectedNode.config.subject || ""}
                      onChange={(e) => updateSelectedNodeConfig("subject", e.target.value)}
                    />
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      <span className="text-[10px] text-slate-400 self-center mr-1">Insert:</span>
                      {VARIABLE_TAGS.slice(0, 4).map((v) => (
                        <button
                          key={v.tag}
                          type="button"
                          onClick={() => insertVariable("subject", v.tag)}
                          className="px-1.5 py-0.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-[10px] rounded border border-slate-200 font-mono"
                        >
                          {v.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Email Body Template *
                    </label>
                    <textarea
                      rows={6}
                      className="w-full text-xs font-mono p-2.5 rounded-lg border border-slate-200 focus:outline-none focus:ring-1 focus:ring-agile-red focus:border-agile-red"
                      placeholder="Write your email body template..."
                      value={selectedNode.config.body || ""}
                      onChange={(e) => updateSelectedNodeConfig("body", e.target.value)}
                    />
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      <span className="text-[10px] text-slate-400 self-center mr-1">Variables:</span>
                      {VARIABLE_TAGS.map((v) => (
                        <button
                          key={v.tag}
                          type="button"
                          onClick={() => insertVariable("body", v.tag)}
                          className="px-1.5 py-0.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-[10px] rounded border border-slate-200 font-mono"
                        >
                          {v.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3 pt-1">
                    <Input
                      label="Delay (Days)"
                      type="number"
                      min={0}
                      value={String(selectedNode.config.delay_days ?? 0)}
                      onChange={(e) => updateSelectedNodeConfig("delay_days", parseInt(e.target.value) || 0)}
                    />
                    <Input
                      label="Delay (Hours)"
                      type="number"
                      min={0}
                      max={23}
                      value={String(selectedNode.config.delay_hours ?? 0)}
                      onChange={(e) => updateSelectedNodeConfig("delay_hours", parseInt(e.target.value) || 0)}
                    />
                  </div>

                  <div className="pt-2 space-y-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handlePreview}
                      className="w-full text-xs flex items-center justify-center gap-1.5"
                    >
                      <Eye className="w-3.5 h-3.5 text-slate-500" />
                      <span>Live Contact Preview</span>
                    </Button>

                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={handleOpenSaveTemplate}
                      className="w-full text-xs h-8 flex items-center justify-center gap-1.5 text-slate-600 hover:text-slate-900 border border-slate-200/80 bg-white hover:bg-slate-50"
                    >
                      <Bookmark className="w-3.5 h-3.5 text-slate-400" />
                      <span>Save as Reusable Template</span>
                    </Button>
                  </div>
                </div>
              )}

              {/* 2. WAIT STEP CONFIG */}
              {selectedNode.type === "wait" && (
                <div className="space-y-4">
                  <Input
                    label="Delay Duration *"
                    type="number"
                    min={1}
                    value={String(selectedNode.config.duration || 1)}
                    onChange={(e) => updateSelectedNodeConfig("duration", parseInt(e.target.value) || 1)}
                  />
                  <Select
                    label="Time Unit"
                    value={selectedNode.config.unit || "days"}
                    onChange={(e) => updateSelectedNodeConfig("unit", e.target.value)}
                    options={[
                      { value: "minutes", label: "Minutes" },
                      { value: "hours", label: "Hours" },
                      { value: "days", label: "Days" },
                    ]}
                  />
                  <div className="rounded-lg bg-amber-50 p-3 border border-amber-200 text-[11px] text-amber-800 space-y-1">
                    <p className="font-semibold flex items-center gap-1">
                      <Clock className="w-3 h-3 text-amber-600" />
                      Durable Scheduling
                    </p>
                    <p>
                      Delays are persisted in the database with timestamps. The web request is never blocked while waiting.
                    </p>
                  </div>
                </div>
              )}

              {/* 3. VOICE SDR STEP CONFIG */}
              {selectedNode.type === "voice" && (
                <div className="space-y-4">
                  <div className="rounded-lg bg-blue-50 p-3 border border-blue-200 text-[11px] text-blue-800 space-y-1">
                    <p className="font-semibold flex items-center gap-1">
                      <PhoneCall className="w-3 h-3 text-blue-600" />
                      Retell AI Outbound Sales SDR
                    </p>
                    <p>
                      Connects prospect with configured Agile Sales & Marketing SDR agent. Automatically honors suppression and phone availability.
                    </p>
                  </div>
                  <div className="text-xs text-slate-500 space-y-2">
                    <p><strong>Agent Model:</strong> Outbound B2B Sales Prospector</p>
                    <p><strong>Consent Rule:</strong> Strict CRM phone presence verified.</p>
                    <p className="text-[10px] text-slate-400">
                      * Test executions use mocked call webhook responses and never dial live telephone numbers.
                    </p>
                  </div>
                </div>
              )}

              {/* 4. SMS STEP CONFIG */}
              {selectedNode.type === "sms" && (() => {
                const smsBody = selectedNode.config.body || "";
                const seg = estimateSMSSegments(smsBody);

                // Find active preview contact
                const selectedContact =
                  previewContactId === "__sample__" || !previewContactId
                    ? null
                    : campaignContacts.find((c) => c.id === previewContactId) ||
                      allOrgContacts.find((c) => c.id === previewContactId) ||
                      null;

                const contactData = selectedContact
                  ? {
                      first_name: selectedContact.name.split(" ")[0] || "Prospect",
                      last_name: selectedContact.name.split(" ").slice(1).join(" ") || "",
                      email: selectedContact.email || "prospect@example.com",
                      phone: selectedContact.phone || null,
                      company: selectedContact.companyName || "Acme Corp",
                    }
                  : {
                      first_name: "Alex",
                      last_name: "Taylor",
                      email: "alex.taylor@example.com",
                      phone: "+1 (555) 234-5678",
                      company: "Acme Corp",
                    };

                // Render preview text
                const renderedSMS = smsBody
                  .replace(/\{contact\.first_name\}/g, contactData.first_name)
                  .replace(/\{contact\.last_name\}/g, contactData.last_name)
                  .replace(/\{contact\.email\}/g, contactData.email)
                  .replace(/\{contact\.phone\}/g, contactData.phone || "[No Phone]")
                  .replace(/\{contact\.company\}/g, contactData.company)
                  .replace(/\{contact\.job_title\}/g, "VP of Growth")
                  .replace(/\{sender\.name\}/g, "Agile Sales Team")
                  .replace(/\{sender_name\}/g, "Agile Sales Team")
                  .replace(/\{sender\.company_name\}/g, "Agile Sales & Marketing")
                  .replace(/\{sender_company\}/g, "Agile Sales & Marketing")
                  .replace(/\{booking_link\}/g, "https://cal.com/agilereceivables/30min");

                const renderedSeg = estimateSMSSegments(renderedSMS);
                const unresolvedPlaceholders = Array.from(new Set(renderedSMS.match(/\{[^}]+\}/g) || []));

                return (
                  <div className="space-y-4">
                    {/* Safe Simulation Mode Banner */}
                    <div className="rounded-lg bg-emerald-50 p-3 border border-emerald-200 text-[11px] text-emerald-900 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <p className="font-semibold flex items-center gap-1.5 text-emerald-800">
                          <Smartphone className="w-3.5 h-3.5 text-emerald-600" />
                          Twilio SMS Step
                        </p>
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
                          <ShieldCheck className="w-3 h-3 text-emerald-600" />
                          Safe Simulation Mode
                        </span>
                      </div>
                      <p className="text-emerald-700 leading-relaxed text-[11px]">
                        Fail-closed safety active (<code>TWILIO_ALLOW_LIVE_SENDING=false</code>). Campaign runs generate realistic mock dispatch IDs (<code>mock-sms-...</code>). Zero live SMS credits are consumed.
                      </p>
                    </div>

                    {/* SMS Body Editor */}
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="text-xs font-semibold text-slate-700">
                          SMS Message Body *
                        </label>
                        <span
                          className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                            seg.characterCount > 1600
                              ? "bg-rose-100 text-rose-700 font-semibold"
                              : seg.segmentCount > 1
                              ? "bg-amber-100 text-amber-700 font-medium"
                              : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {seg.characterCount} chars • {seg.segmentCount} {seg.segmentCount === 1 ? "segment" : "segments"} ({seg.encoding})
                        </span>
                      </div>
                      <textarea
                        rows={4}
                        className="w-full text-xs font-mono p-2.5 rounded-lg border border-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500"
                        placeholder="Type your SMS message template..."
                        value={smsBody}
                        onChange={(e) => updateSelectedNodeConfig("body", e.target.value)}
                      />
                      <div className="flex items-center justify-between mt-1 text-[10px] text-slate-400">
                        <span>{seg.remainingInSegment} chars left in segment {seg.segmentCount || 1}</span>
                        <span>Max per segment: {seg.maxPerSegment}</span>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-2">
                        <span className="text-[10px] text-slate-400 self-center mr-1">Variables:</span>
                        {VARIABLE_TAGS.map((v) => (
                          <button
                            key={v.tag}
                            type="button"
                            onClick={() => insertVariable("body", v.tag)}
                            className="px-1.5 py-0.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-[10px] rounded border border-slate-200 font-mono"
                          >
                            {v.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Step Delays */}
                    <div className="grid grid-cols-2 gap-3 pt-1">
                      <Input
                        label="Delay (Days)"
                        type="number"
                        min={0}
                        value={String(selectedNode.config.delay_days ?? 0)}
                        onChange={(e) => updateSelectedNodeConfig("delay_days", parseInt(e.target.value) || 0)}
                      />
                      <Input
                        label="Delay (Hours)"
                        type="number"
                        min={0}
                        max={23}
                        value={String(selectedNode.config.delay_hours ?? 0)}
                        onChange={(e) => updateSelectedNodeConfig("delay_hours", parseInt(e.target.value) || 0)}
                      />
                    </div>

                    {/* Recipient Phone Normalization & Consent Guard */}
                    <div className="rounded-lg bg-slate-50 p-2.5 border border-slate-200 space-y-1">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="font-semibold text-slate-700 flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                          E.164 & Consent Protection
                        </span>
                        <span className="text-[10px] font-mono text-slate-500">Auto-Filtered</span>
                      </div>
                      <p className="text-[10px] text-slate-500 leading-normal">
                        Phone numbers are normalized to E.164 international format (+1...). Contacts lacking phone numbers or with opt-out keywords (<code>STOP</code>, <code>UNSUBSCRIBE</code>) are safely skipped during campaign dispatch.
                      </p>
                    </div>

                    {/* Live Mobile SMS Device Preview */}
                    <div className="rounded-xl border border-slate-200 bg-slate-100/70 p-3 space-y-2.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1 text-[11px] font-semibold text-slate-700">
                          <Eye className="w-3 h-3 text-slate-500" />
                          <span>Live Mobile Preview</span>
                        </div>
                        <select
                          className="text-[10px] bg-white border border-slate-200 rounded px-1.5 py-0.5 text-slate-600 focus:outline-none max-w-[150px] truncate"
                          value={previewContactId}
                          onChange={(e) => setPreviewContactId(e.target.value)}
                        >
                          <option value="__sample__">Sample Contact</option>
                          {campaignContacts.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name} {c.phone ? `(${c.phone})` : "(No phone)"}
                            </option>
                          ))}
                          {allOrgContacts
                            .filter((oc) => !campaignContacts.some((cc) => cc.id === oc.id))
                            .map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.name} {c.phone ? `(${c.phone})` : "(No phone)"}
                              </option>
                            ))}
                        </select>
                      </div>

                      {/* Contact Phone Status Pill */}
                      <div className="flex items-center gap-1.5 text-[10px]">
                        {contactData.phone ? (
                          <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                            <CheckCircle2 className="w-2.5 h-2.5" />
                            Recipient: {contactData.phone}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                            <AlertTriangle className="w-2.5 h-2.5" />
                            No phone on record (Step skipped)
                          </span>
                        )}
                      </div>

                      {/* Unresolved Placeholders Warning */}
                      {unresolvedPlaceholders.length > 0 && (
                        <div className="text-[10px] text-amber-800 bg-amber-50 p-1.5 rounded border border-amber-200 flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3 shrink-0 text-amber-600" />
                          <span>Unresolved: {unresolvedPlaceholders.join(", ")}</span>
                        </div>
                      )}

                      {/* Phone SMS Bubble Frame */}
                      <div className="bg-slate-200/80 rounded-2xl p-2.5 space-y-1.5">
                        <div className="text-center text-[9px] font-medium text-slate-500 uppercase tracking-wider">
                          SMS Message • Today 10:00 AM
                        </div>
                        <div className="flex justify-start">
                          <div className="max-w-[90%] bg-emerald-600 text-white text-[11px] leading-relaxed rounded-2xl rounded-tl-xs px-3 py-2 shadow-xs whitespace-pre-wrap break-words font-sans">
                            {renderedSMS || <span className="opacity-60 italic">No SMS body template defined</span>}
                          </div>
                        </div>
                        <div className="text-right text-[9px] text-slate-400 pr-1">
                          {renderedSeg.characterCount} chars • {renderedSeg.segmentCount} {renderedSeg.segmentCount === 1 ? "seg" : "segs"} ({renderedSeg.encoding})
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* 5. CONDITION BRANCH CONFIG */}
              {selectedNode.type === "condition" && (
                <div className="space-y-4">
                  <Select
                    label="Condition Trigger"
                    value={selectedNode.config.condition_type || "email_replied"}
                    onChange={(e) => updateSelectedNodeConfig("condition_type", e.target.value)}
                    options={[
                      { value: "email_replied", label: "Email: Contact Replied (Halt Sequence)" },
                      { value: "email_not_replied", label: "Email: No Reply After Delay (Proceed to Next Step)" },
                      { value: "email_opened", label: "Email: Contact Opened Email" },
                      { value: "meeting_requested", label: "Voice SDR: Meeting Requested (Halt Sequence)" },
                      { value: "call_completed", label: "Voice SDR: Call Ended" },
                      { value: "contact_opted_out", label: "Suppression: Contact Opted Out (Halt Sequence)" },
                      { value: "email_bounced", label: "Delivery: Email Bounced (Halt Sequence)" },
                    ]}
                  />
                  <div className="rounded-lg bg-purple-50 p-3 border border-purple-200 text-[11px] text-purple-800">
                    Branches are evaluated strictly against verified CRM interaction events.
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-6 text-slate-400">
              <GitBranch className="w-8 h-8 text-slate-300 mb-2" />
              <p className="text-xs font-medium text-slate-600">Select a step node</p>
              <p className="text-[11px] text-slate-400 mt-1">
                Click any step on the left canvas to configure subject, body, variables, delays, or conditions.
              </p>
            </div>
          )}

          {/* Description field at bottom of panel */}
          <div className="pt-4 border-t border-slate-100">
            <label className="block text-[11px] font-semibold text-slate-600 mb-1">
              Campaign Workflow Notes
            </label>
            <textarea
              rows={2}
              className="w-full text-xs p-2 rounded border border-slate-200 text-slate-700"
              placeholder="Internal campaign description or strategy notes..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* LIVE TEMPLATE PREVIEW MODAL */}
      <Modal
        isOpen={isPreviewOpen}
        onClose={() => setIsPreviewOpen(false)}
        title="Email Step Live Preview"
        description="Rendered with genuine persisted CRM contact data using identical sending logic."
        footer={
          <Button variant="secondary" onClick={() => setIsPreviewOpen(false)}>
            Close Preview
          </Button>
        }
      >
        <div className="space-y-4 text-xs">
          {/* Contact selector */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-semibold text-slate-700">
                Preview with Contact:
              </label>
              {campaignContacts.length > 0 && (
                <span className="text-[10px] text-slate-500">
                  {campaignContacts.length} enrolled in this campaign
                </span>
              )}
            </div>
            <select
              className="w-full h-9 text-xs rounded-lg border border-slate-200 px-3 bg-white focus:outline-none focus:ring-1 focus:ring-agile-red"
              value={previewContactId}
              onChange={(e) => {
                const newId = e.target.value;
                setPreviewContactId(newId);
                if (selectedNode && selectedNode.type === "email") {
                  setPreviewLoading(true);
                  const isSample = newId === "__sample__";
                  previewStepTemplate(campaignId, {
                    subject_template: selectedNode.config.subject,
                    body_template: selectedNode.config.body,
                    contact_id: isSample ? undefined : newId,
                    use_sample: isSample,
                    sender_name: "Agile Sales Team",
                    sender_company_name: "Agile Sales & Marketing",
                  })
                    .then(setPreviewResult)
                    .catch((err) => console.error("Preview failed:", err))
                    .finally(() => setPreviewLoading(false));
                }
              }}
            >
              {campaignContacts.length > 0 && (
                <optgroup label="Campaign Enrolled Contacts">
                  {campaignContacts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.email}){c.companyName ? ` • ${c.companyName}` : " • (No Company)"}
                    </option>
                  ))}
                </optgroup>
              )}
              {allOrgContacts.filter((c) => !campaignContacts.some((ec) => ec.id === c.id)).length > 0 && (
                <optgroup label="Other CRM Contacts">
                  {allOrgContacts
                    .filter((c) => !campaignContacts.some((ec) => ec.id === c.id))
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.email}){c.companyName ? ` • ${c.companyName}` : " • (No Company)"}
                      </option>
                    ))}
                </optgroup>
              )}
              <optgroup label="Sample Fallback">
                <option value="__sample__">
                  Default Sample Contact (Jordan Taylor • Acme Global Solutions)
                </option>
              </optgroup>
            </select>
          </div>

          {previewLoading ? (
            <div className="p-8 text-center text-slate-400 flex items-center justify-center gap-2">
              <RefreshCw className="w-4 h-4 animate-spin text-agile-red" />
              <span>Rendering template...</span>
            </div>
          ) : previewResult ? (
            <div className="space-y-3">
              {/* Fallback alerts if any */}
              {previewResult.safe_fallbacks_applied.length > 0 && (
                <div className="p-2.5 rounded bg-amber-50 border border-amber-200 text-[11px] text-amber-800">
                  <span className="font-semibold">Safe Fallbacks Applied:</span>
                  <ul className="list-disc pl-4 mt-0.5">
                    {previewResult.safe_fallbacks_applied.map((f, i) => (
                      <li key={i}>{f}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Unresolved variable error if any */}
              {previewResult.unresolved_placeholders.length > 0 && (
                <div className="p-2.5 rounded bg-rose-50 border border-rose-200 text-[11px] text-rose-700">
                  <span className="font-semibold">Unresolved Placeholders (Would Block Send):</span>
                  <ul className="list-disc pl-4 mt-0.5">
                    {previewResult.unresolved_placeholders.map((u, i) => (
                      <li key={i} className="font-mono">{u}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Rendered Email Card */}
              <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-3 shadow-xs">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-400">Subject:</span>
                    <p className="text-xs font-semibold text-header font-mono">
                      {previewResult.rendered_subject || "(Empty subject)"}
                    </p>
                  </div>
                  {previewResult.rendered_html && (
                    <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded text-[11px]">
                      <button
                        type="button"
                        onClick={() => setPreviewMode("text")}
                        className={`px-2 py-0.5 rounded font-medium transition-colors ${
                          previewMode === "text"
                            ? "bg-white text-slate-800 shadow-xs"
                            : "text-slate-500 hover:text-slate-700"
                        }`}
                      >
                        Text View
                      </button>
                      <button
                        type="button"
                        onClick={() => setPreviewMode("html")}
                        className={`px-2 py-0.5 rounded font-medium transition-colors ${
                          previewMode === "html"
                            ? "bg-white text-slate-800 shadow-xs"
                            : "text-slate-500 hover:text-slate-700"
                        }`}
                      >
                        HTML Email
                      </button>
                    </div>
                  )}
                </div>

                <div className="pt-2 border-t border-slate-100">
                  <span className="text-[10px] uppercase font-bold text-slate-400">Body:</span>
                  {previewMode === "html" && previewResult.rendered_html ? (
                    <div className="mt-2 border border-slate-200 rounded-md overflow-hidden bg-slate-50">
                      <iframe
                        srcDoc={previewResult.rendered_html}
                        title="HTML Email Preview"
                        className="w-full h-64 border-0 bg-white"
                        sandbox="allow-popups allow-popups-to-escape-sandbox"
                      />
                    </div>
                  ) : (
                    <div className="text-xs text-slate-700 whitespace-pre-wrap font-sans mt-1 leading-relaxed">
                      {previewResult.rendered_body ? (
                        previewResult.rendered_body.split(/(https?:\/\/[^\s]+)/g).map((part, idx) =>
                          part.match(/^https?:\/\//) ? (
                            <a
                              key={idx}
                              href={part}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-600 underline font-medium hover:text-blue-800 break-all"
                            >
                              {part}
                            </a>
                          ) : (
                            part
                          )
                        )
                      ) : (
                        "(Empty body)"
                      )}
                    </div>
                  )}
                </div>

                {previewResult.booking_url && (
                  <div className="pt-3 border-t border-slate-100 flex items-center justify-between bg-blue-50/50 -mx-4 -mb-4 p-3 rounded-b-lg">
                    <div className="flex items-center gap-1.5 text-xs text-blue-900 font-medium">
                      <span>Booking CTA Destination:</span>
                      <span className="text-slate-500 font-mono text-[11px] truncate max-w-xs">
                        {previewResult.booking_url}
                      </span>
                    </div>
                    <a
                      href={previewResult.booking_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-md shadow-xs transition-colors shrink-0"
                    >
                      <span>Book a Meeting</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>
                )}
              </div>

              {previewResult.contact_used && (
                <div className="flex items-center justify-between text-[11px] bg-slate-50 border border-slate-200 rounded p-2.5 text-slate-600">
                  <div>
                    Rendered for: <strong className="text-slate-800">{previewResult.contact_used.first_name} {previewResult.contact_used.last_name}</strong>
                    {previewResult.contact_used.company_name ? (
                      <span> at <strong className="text-slate-800">{previewResult.contact_used.company_name}</strong></span>
                    ) : (
                      <span className="text-amber-600 font-medium"> at No Company Association</span>
                    )}
                    <span className="text-slate-400 ml-1.5 font-mono text-[10px]">({previewResult.contact_used.email})</span>
                  </div>
                  {previewResult.is_sample && (
                    <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                      Sample Contact
                    </span>
                  )}
                </div>
              )}
            </div>
          ) : null}
        </div>
      </Modal>

      {/* 1. AI EMAIL GENERATOR MODAL */}
      <Modal
        isOpen={isAIGenOpen}
        onClose={() => setIsAIGenOpen(false)}
        title="AI-Assisted Email Creation"
        description="Generates high-converting subject and body copy powered by AWS Bedrock (Claude Sonnet 4.5)."
        footer={
          <div className="flex items-center justify-between w-full">
            <span className="text-[11px] text-slate-400">
              * Applying updates this step editor without auto-saving the campaign.
            </span>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => setIsAIGenOpen(false)}>
                Cancel
              </Button>
              {aiHasGenerated && (
                <Button
                  variant="primary"
                  onClick={handleApplyAIGeneration}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white gap-1.5"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>Apply to Step</span>
                </Button>
              )}
            </div>
          </div>
        }
      >
        <div className="space-y-4 text-xs">
          {aiError && (
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Generation Issue</p>
                <p className="text-[11px] mt-0.5">{aiError}</p>
                <p className="text-[10px] text-rose-500 mt-1">Your existing email step content was not changed.</p>
              </div>
            </div>
          )}

          {/* Form Inputs */}
          <div className="space-y-3 bg-slate-50 p-3.5 rounded-lg border border-slate-200">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Campaign</label>
                <input
                  type="text"
                  disabled
                  value={campaignName}
                  className="w-full h-8 px-2.5 rounded border border-slate-200 bg-slate-100 text-slate-500 text-xs font-medium cursor-not-allowed"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Tone of Voice</label>
                <select
                  value={aiTone}
                  onChange={(e) => setAiTone(e.target.value)}
                  className="w-full h-8 px-2 rounded border border-slate-200 bg-white text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="professional">Professional & Consultative</option>
                  <option value="conversational">Casual & Conversational</option>
                  <option value="direct">Direct & Concise</option>
                  <option value="urgent">Time-Sensitive / Urgent</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Email Objective / Purpose *
              </label>
              <textarea
                rows={2}
                placeholder="e.g. Introduce our outbound sales platform and book a 15-minute briefing..."
                value={aiObjective}
                onChange={(e) => setAiObjective(e.target.value)}
                className="w-full text-xs p-2.5 rounded-md border border-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Target Audience (Optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. VP of Sales, Operations Directors"
                  value={aiAudience}
                  onChange={(e) => setAiAudience(e.target.value)}
                  className="w-full h-8 px-2.5 rounded border border-slate-200 bg-white text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Call to Action (Optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. Ask for availability next Tuesday"
                  value={aiCta}
                  onChange={(e) => setAiCta(e.target.value)}
                  className="w-full h-8 px-2.5 rounded border border-slate-200 bg-white text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>

            <div className="pt-1 flex justify-end">
              <Button
                variant="primary"
                size="sm"
                onClick={handleRunAIGeneration}
                disabled={aiLoading || !aiObjective.trim()}
                className="text-xs h-8 bg-indigo-600 hover:bg-indigo-700 text-white gap-1.5 shadow-xs"
              >
                {aiLoading ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Generating with Bedrock...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>{aiHasGenerated ? "Regenerate Content" : "Generate Email Draft"}</span>
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Generated Result Output */}
          {aiHasGenerated && (
            <div className="space-y-3 pt-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Generated Draft (Editable)
                </span>
                <span className="text-[10px] text-indigo-600 font-medium bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                  Claude Sonnet 4.5
                </span>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Subject</label>
                <input
                  type="text"
                  value={aiGeneratedSubject}
                  onChange={(e) => setAiGeneratedSubject(e.target.value)}
                  className="w-full h-8 px-2.5 font-mono text-xs rounded border border-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white"
                />
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-600 mb-1">Body</label>
                <textarea
                  rows={6}
                  value={aiGeneratedBody}
                  onChange={(e) => setAiGeneratedBody(e.target.value)}
                  className="w-full text-xs font-mono p-2.5 rounded border border-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white leading-relaxed"
                />
              </div>
            </div>
          )}
        </div>
      </Modal>

      {/* 2. SAVED TEMPLATE PICKER MODAL */}
      <Modal
        isOpen={isTemplatePickerOpen}
        onClose={() => setIsTemplatePickerOpen(false)}
        title="Reusable Email Templates"
        description="Select a previously saved organization template to apply to this campaign step."
        footer={
          <div className="flex items-center justify-between w-full">
            <span className="text-[11px] text-slate-400">
              * Applying copies the template without modifying the original saved master.
            </span>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => setIsTemplatePickerOpen(false)}>
                Cancel
              </Button>
              {selectedTemplateForPreview && (
                <Button
                  variant="primary"
                  onClick={() => handleApplyTemplate(selectedTemplateForPreview)}
                  className="gap-1.5"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>Apply to Step</span>
                </Button>
              )}
            </div>
          </div>
        }
      >
        <div className="space-y-3 text-xs">
          {/* Filter and Search Bar */}
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Search templates by name, subject, or description..."
                value={templateSearch}
                onChange={(e) => {
                  const val = e.target.value;
                  setTemplateSearch(val);
                  fetchEmailTemplates({ category: templateCategory, search: val })
                    .then(setSavedTemplates)
                    .catch(console.error);
                }}
                className="w-full h-8 pl-8 pr-3 text-xs rounded border border-slate-200 focus:outline-none focus:ring-1 focus:ring-agile-red"
              />
            </div>
            <select
              value={templateCategory}
              onChange={(e) => {
                const cat = e.target.value;
                setTemplateCategory(cat);
                fetchEmailTemplates({ category: cat, search: templateSearch })
                  .then(setSavedTemplates)
                  .catch(console.error);
              }}
              className="h-8 px-2.5 text-xs rounded border border-slate-200 bg-white focus:outline-none focus:ring-1 focus:ring-agile-red"
            >
              {TEMPLATE_CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          {/* Master-Detail Layout */}
          {isLoadingTemplates ? (
            <div className="p-8 text-center text-slate-400 flex items-center justify-center gap-2">
              <RefreshCw className="w-4 h-4 animate-spin text-agile-red" />
              <span>Loading saved templates...</span>
            </div>
          ) : savedTemplates.length === 0 ? (
            <div className="p-8 text-center bg-slate-50 rounded-lg border border-slate-200 text-slate-500 space-y-1">
              <BookOpen className="w-6 h-6 text-slate-300 mx-auto mb-1" />
              <p className="font-semibold text-xs">No saved templates found</p>
              <p className="text-[11px] text-slate-400">
                You can save any campaign email step as a reusable template using &quot;Save as Reusable Template&quot;.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-5 gap-3 border border-slate-200 rounded-lg overflow-hidden h-80">
              {/* Left Column: Template List */}
              <div className="col-span-2 border-r border-slate-200 overflow-y-auto bg-slate-50 divide-y divide-slate-100">
                {savedTemplates.map((t) => {
                  const isSelected = selectedTemplateForPreview?.id === t.id;
                  return (
                    <div
                      key={t.id}
                      onClick={() => setSelectedTemplateForPreview(t)}
                      className={`p-3 cursor-pointer transition-colors ${
                        isSelected ? "bg-white border-l-2 border-agile-red shadow-2xs" : "hover:bg-slate-100/70"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="font-semibold text-header truncate">{t.name}</span>
                        <span className="text-[9px] uppercase px-1.5 py-0.2 rounded bg-slate-200 text-slate-700">
                          {t.category}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500 truncate font-mono">{t.subject_template}</p>
                    </div>
                  );
                })}
              </div>

              {/* Right Column: Preview Pane */}
              <div className="col-span-3 p-3.5 overflow-y-auto space-y-3 bg-white">
                {selectedTemplateForPreview ? (
                  <>
                    <div className="pb-2 border-b border-slate-100 flex items-center justify-between">
                      <div>
                        <h4 className="font-bold text-xs text-header">{selectedTemplateForPreview.name}</h4>
                        {selectedTemplateForPreview.description && (
                          <p className="text-[10px] text-slate-400 mt-0.5">{selectedTemplateForPreview.description}</p>
                        )}
                      </div>
                      <Badge variant="neutral" className="text-[10px] capitalize">
                        {selectedTemplateForPreview.category}
                      </Badge>
                    </div>

                    <div>
                      <span className="text-[10px] uppercase font-bold text-slate-400">Subject:</span>
                      <p className="text-xs font-mono font-medium text-slate-800 mt-0.5 p-2 bg-slate-50 rounded border border-slate-100">
                        {selectedTemplateForPreview.subject_template}
                      </p>
                    </div>

                    <div>
                      <span className="text-[10px] uppercase font-bold text-slate-400">Body:</span>
                      <p className="text-xs font-mono text-slate-700 whitespace-pre-wrap mt-0.5 p-2 bg-slate-50 rounded border border-slate-100 leading-relaxed max-h-40 overflow-y-auto">
                        {selectedTemplateForPreview.body_template}
                      </p>
                    </div>
                  </>
                ) : (
                  <div className="h-full flex items-center justify-center text-slate-400 text-xs">
                    Select a template to view details
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </Modal>

      {/* 3. SAVE AS REUSABLE TEMPLATE MODAL */}
      <Modal
        isOpen={isSaveTemplateOpen}
        onClose={() => setIsSaveTemplateOpen(false)}
        title="Save as Reusable Template"
        description="Persists the current email subject and body so it can be reused across any campaign."
        footer={
          <div className="flex items-center justify-end gap-2 w-full">
            <Button variant="secondary" onClick={() => setIsSaveTemplateOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSaveAsTemplate}
              disabled={isSavingTemplate || !newTemplateName.trim()}
              className="gap-1.5"
            >
              {isSavingTemplate ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Saving...</span>
                </>
              ) : (
                <>
                  <Bookmark className="w-3.5 h-3.5" />
                  <span>Save Template</span>
                </>
              )}
            </Button>
          </div>
        }
      >
        <div className="space-y-3 text-xs">
          {saveTemplateError && (
            <div className="p-2.5 rounded bg-rose-50 border border-rose-200 text-rose-700">
              {saveTemplateError}
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Template Name *</label>
            <input
              type="text"
              placeholder="e.g. Executive Introduction Q4"
              value={newTemplateName}
              onChange={(e) => setNewTemplateName(e.target.value)}
              className="w-full h-8 px-2.5 text-xs rounded border border-slate-200 focus:outline-none focus:ring-1 focus:ring-agile-red"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Category</label>
              <select
                value={newTemplateCategory}
                onChange={(e) => setNewTemplateCategory(e.target.value)}
                className="w-full h-8 px-2.5 text-xs rounded border border-slate-200 bg-white focus:outline-none focus:ring-1 focus:ring-agile-red"
              >
                <option value="outbound">Cold Outbound</option>
                <option value="follow_up">Follow-up</option>
                <option value="nurture">Nurture</option>
                <option value="referral">Referral Request</option>
                <option value="announcement">Announcement</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Description (Optional)</label>
              <input
                type="text"
                placeholder="e.g. Best for technical founders"
                value={newTemplateDescription}
                onChange={(e) => setNewTemplateDescription(e.target.value)}
                className="w-full h-8 px-2.5 text-xs rounded border border-slate-200 focus:outline-none focus:ring-1 focus:ring-agile-red"
              />
            </div>
          </div>

          <div className="p-3 bg-slate-50 rounded border border-slate-200 space-y-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Content Snapshot</span>
            <p className="font-mono text-[11px] text-slate-700 truncate">
              <strong>Subject:</strong> {selectedNode?.config.subject || "(Empty)"}
            </p>
            <p className="font-mono text-[10px] text-slate-500 line-clamp-2">
              <strong>Body:</strong> {selectedNode?.config.body || "(Empty)"}
            </p>
          </div>
        </div>
      </Modal>

      {/* 4. UPDATE MASTER TEMPLATE MODAL */}
      <Modal
        isOpen={isUpdateTemplateOpen}
        onClose={() => setIsUpdateTemplateOpen(false)}
        title="Update Original Saved Template"
        description="Explicitly overwrite the master template record with current step modifications."
        footer={
          <div className="flex items-center justify-end gap-2 w-full">
            <Button variant="secondary" onClick={() => setIsUpdateTemplateOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleUpdateMasterTemplate}
              disabled={isUpdatingTemplate}
              className="gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white"
            >
              {isUpdatingTemplate ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Updating...</span>
                </>
              ) : (
                <>
                  <Save className="w-3.5 h-3.5" />
                  <span>Confirm Update</span>
                </>
              )}
            </Button>
          </div>
        }
      >
        <div className="space-y-3 text-xs">
          {updateTemplateError && (
            <div className="p-2.5 rounded bg-rose-50 border border-rose-200 text-rose-700">
              {updateTemplateError}
            </div>
          )}

          <div className="p-3 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg space-y-1">
            <p className="font-semibold flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
              Overwriting Master Template
            </p>
            <p className="text-[11px]">
              This will update the saved template <strong>&quot;{selectedNode?.config.applied_template_name}&quot;</strong> in your organization&apos;s library with the current step&apos;s subject and body. Other campaigns will not be affected.
            </p>
          </div>

          <div className="p-3 bg-slate-50 rounded border border-slate-200 space-y-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">New Content to Save</span>
            <p className="font-mono text-[11px] text-slate-800 truncate">
              <strong>Subject:</strong> {selectedNode?.config.subject}
            </p>
            <p className="font-mono text-[11px] text-slate-600 whitespace-pre-wrap max-h-32 overflow-y-auto">
              <strong>Body:</strong> {selectedNode?.config.body}
            </p>
          </div>
        </div>
      </Modal>
      </div>
    </div>
  );
};
