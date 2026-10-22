"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useDropzone } from "react-dropzone";
import { AppShell } from "@/components/layout/app-shell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Upload,
  Globe,
  FileText,
  Calendar,
  Sparkles,
  Bot,
  ShieldCheck,
  Check,
  Trash2,
  HelpCircle,
  Clock,
  Layers,
  Share2,
} from "lucide-react";
import {
  LinkedInIcon,
  XIcon,
  InstagramIcon,
} from "@/components/social/social-icons";
import { createMarketingCampaign } from "@/services/marketingService";

const STEPS = [
  { id: 1, title: "Campaign & Platform", desc: "Target channels & naming" },
  { id: 2, title: "Knowledge Upload", desc: "Source of truth docs" },
  { id: 3, title: "Scheduling Mode", desc: "Cadence & calendar" },
  { id: 4, title: "AI Training & Guardrails", desc: "Approval & autonomy" },
];

export default function NewMarketingCampaignPage() {
  const router = useRouter();
  const [currentStep, setCurrentStep] = React.useState(1);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [successData, setSuccessData] = React.useState<any | null>(null);

  // Form State
  const [name, setName] = React.useState("");
  const [platforms, setPlatforms] = React.useState<string[]>(["LINKEDIN"]);
  const [websiteUrl, setWebsiteUrl] = React.useState("");
  const [knowledgeFiles, setKnowledgeFiles] = React.useState<File[]>([]);
  const [schedulingMode, setSchedulingMode] = React.useState<"AI_AUTO" | "EXCEL_SYNC">("AI_AUTO");
  const [postsPerWeek, setPostsPerWeek] = React.useState<number>(3);
  const [scheduleFile, setScheduleFile] = React.useState<File | null>(null);
  const [trainingPeriodDays, setTrainingPeriodDays] = React.useState<number>(45);
  const [requireApproval, setRequireApproval] = React.useState<boolean>(true);
  const [autoPublish, setAutoPublish] = React.useState<boolean>(false);

  // Dropzone for Knowledge Base Files (Step 2)
  const onDropKnowledge = React.useCallback((acceptedFiles: File[]) => {
    setKnowledgeFiles((prev) => [...prev, ...acceptedFiles]);
  }, []);

  const {
    getRootProps: getKnowledgeRootProps,
    getInputProps: getKnowledgeInputProps,
    isDragActive: isKnowledgeDragActive,
  } = useDropzone({
    onDrop: onDropKnowledge,
    accept: {
      "application/pdf": [".pdf"],
      "text/csv": [".csv"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
      "text/plain": [".txt"],
    },
    maxSize: 25 * 1024 * 1024,
  });

  // Dropzone for Manual Schedule Calendar File (Step 3)
  const onDropSchedule = React.useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      setScheduleFile(acceptedFiles[0]);
    }
  }, []);

  const {
    getRootProps: getScheduleRootProps,
    getInputProps: getScheduleInputProps,
    isDragActive: isScheduleDragActive,
  } = useDropzone({
    onDrop: onDropSchedule,
    accept: {
      "text/csv": [".csv"],
      "application/vnd.ms-excel": [".xls"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    },
    maxFiles: 1,
  });

  const togglePlatform = (p: string) => {
    if (platforms.includes(p)) {
      if (platforms.length > 1) {
        setPlatforms(platforms.filter((item) => item !== p));
      }
    } else {
      setPlatforms([...platforms, p]);
    }
  };

  const removeKnowledgeFile = (index: number) => {
    setKnowledgeFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleNext = () => {
    setErrorMessage(null);
    if (currentStep === 1) {
      if (!name.trim()) {
        setErrorMessage("Please enter a campaign name to continue.");
        return;
      }
      if (platforms.length === 0) {
        setErrorMessage("Please select at least one distribution platform.");
        return;
      }
    }
    if (currentStep < 4) {
      setCurrentStep((prev) => prev + 1);
    }
  };

  const handleBack = () => {
    setErrorMessage(null);
    if (currentStep > 1) {
      setCurrentStep((prev) => prev - 1);
    }
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const formData = new FormData();
      formData.append("name", name.trim());
      platforms.forEach((p) => formData.append("platforms", p));
      if (websiteUrl.trim()) {
        formData.append("websiteUrl", websiteUrl.trim());
      }
      formData.append("schedulingMode", schedulingMode);
      formData.append("postsPerWeek", String(postsPerWeek));
      formData.append("trainingPeriodDays", String(trainingPeriodDays));
      formData.append("requireApprovalDuringTraining", String(requireApproval));
      formData.append("autoPublishAfterTraining", String(autoPublish));

      knowledgeFiles.forEach((file) => {
        formData.append("knowledgeFiles", file);
      });

      if (scheduleFile) {
        formData.append("scheduleFile", scheduleFile);
      }

      const res = await createMarketingCampaign(formData);
      setSuccessData(res);
    } catch (err: any) {
      setErrorMessage(err?.message || "Failed to launch campaign. Please check the inputs.");
      setIsSubmitting(false);
    }
  };

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto space-y-8 pb-16">
        {/* Breadcrumb & Navigation */}
        <div className="flex items-center justify-between pb-2 border-b border-slate-200">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
              <Link href="/marketing/campaigns" className="hover:text-slate-800 transition-colors">
                Marketing Campaigns
              </Link>
              <span>/</span>
              <span className="text-[#D7525A]">New Campaign Onboarding</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 mt-1">
              Create AI Marketing Campaign
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Set up your campaign parameters, knowledge base, and autonomous AI training guardrails.
            </p>
          </div>
          <Link href="/marketing/campaigns">
            <Button variant="outline" size="sm" className="text-xs">
              <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
              Cancel
            </Button>
          </Link>
        </div>

        {/* Stepper Header */}
        <div className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-xs">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {STEPS.map((step) => {
              const isCompleted = currentStep > step.id;
              const isActive = currentStep === step.id;
              return (
                <div
                  key={step.id}
                  onClick={() => {
                    if (isCompleted) setCurrentStep(step.id);
                  }}
                  className={`flex items-start gap-3 p-2.5 rounded-lg transition-all ${
                    isActive
                      ? "bg-rose-50/70 border border-[#D7525A]/30"
                      : isCompleted
                      ? "cursor-pointer hover:bg-slate-50"
                      : "opacity-60"
                  }`}
                >
                  <div
                    className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-bold transition-colors ${
                      isActive
                        ? "bg-[#D7525A] text-white shadow-xs"
                        : isCompleted
                        ? "bg-emerald-600 text-white"
                        : "bg-slate-100 text-slate-500 border border-slate-200"
                    }`}
                  >
                    {isCompleted ? <Check className="w-4 h-4 stroke-[2.5]" /> : step.id}
                  </div>
                  <div className="min-w-0">
                    <p
                      className={`text-xs font-bold leading-tight ${
                        isActive ? "text-[#D7525A]" : "text-slate-800"
                      }`}
                    >
                      {step.title}
                    </p>
                    <p className="text-[11px] text-slate-500 truncate mt-0.5">{step.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Error Alert */}
        {errorMessage && (
          <div className="p-4 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-sm flex items-center justify-between">
            <span>{errorMessage}</span>
            <button
              onClick={() => setErrorMessage(null)}
              className="text-xs underline font-semibold ml-3"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Success Dialog / Launch Completion */}
        {successData ? (
          <Card className="border-emerald-200 bg-emerald-50/40 p-8 text-center space-y-6">
            <div className="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto shadow-sm">
              <CheckCircle2 className="w-9 h-9" />
            </div>
            <div className="space-y-2 max-w-lg mx-auto">
              <h2 className="text-xl font-bold text-slate-900">
                Campaign Launched &amp; AI Training Active!
              </h2>
              <p className="text-sm text-slate-600">
                Your campaign <strong>&ldquo;{name}&rdquo;</strong> is now active in supervised training mode for the next{" "}
                <strong>{trainingPeriodDays} days</strong>. The initial content generation batch has been queued.
              </p>
            </div>

            <div className="bg-white rounded-lg p-4 max-w-md mx-auto border border-emerald-200/80 text-left space-y-2 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-100">
                <span className="text-slate-500">Supervised Mode:</span>
                <span className="font-semibold text-slate-800">
                  {requireApproval ? "Approval Required Before Posting" : "Autonomous Posting"}
                </span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-100">
                <span className="text-slate-500">Cadence:</span>
                <span className="font-semibold text-slate-800">
                  {schedulingMode === "AI_AUTO"
                    ? `${postsPerWeek} posts / week (AI Auto-Pilot)`
                    : "Excel Schedule Sync"}
                </span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-slate-500">Platforms:</span>
                <span className="font-semibold text-slate-800">{platforms.join(", ")}</span>
              </div>
            </div>

            <div className="flex items-center justify-center gap-3 pt-2">
              <Button
                variant="primary"
                onClick={() => router.push("/marketing/content-calendar")}
                className="bg-[#D7525A] hover:bg-[#c2434b] text-white px-6 font-semibold shadow-xs"
              >
                Go to Content Calendar Kanban
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
              <Button
                variant="outline"
                onClick={() => router.push("/marketing/campaigns")}
                className="text-slate-700 bg-white"
              >
                View All Campaigns
              </Button>
            </div>
          </Card>
        ) : (
          /* Step Contents */
          <div className="bg-white rounded-xl border border-slate-200/80 shadow-xs p-6 sm:p-8">
            {/* STEP 1: Campaign Details & Platform */}
            {currentStep === 1 && (
              <div className="space-y-8">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">Step 1: Campaign Details &amp; Platforms</h2>
                  <p className="text-xs text-slate-500 mt-1">
                    Give your marketing initiative a clear objective and choose where your AI agent should distribute content.
                  </p>
                </div>

                <div className="space-y-3">
                  <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                    Campaign Name <span className="text-[#D7525A]">*</span>
                  </label>
                  <Input
                    placeholder="e.g. Q4 B2B CFO Growth Engine &amp; Liquidity Series"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="h-11 text-sm bg-slate-50/50 focus:bg-white"
                  />
                  <p className="text-[11px] text-slate-400">
                    Used to label content pillars, target audiences, and automated reporting rollups.
                  </p>
                </div>

                <div className="space-y-3">
                  <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                    Distribution Platforms <span className="text-[#D7525A]">*</span>
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {/* LinkedIn */}
                    <div
                      onClick={() => togglePlatform("LINKEDIN")}
                      className={`cursor-pointer rounded-xl border p-4.5 transition-all text-left flex flex-col justify-between ${
                        platforms.includes("LINKEDIN")
                          ? "border-[#D7525A] bg-rose-50/30 ring-1 ring-[#D7525A]"
                          : "border-slate-200 hover:border-slate-300 bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="w-9 h-9 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                          <LinkedInIcon className="w-5 h-5 text-[#0A66C2]" />
                        </div>
                        <div
                          className={`w-5 h-5 rounded-full border flex items-center justify-center ${
                            platforms.includes("LINKEDIN")
                              ? "bg-[#D7525A] border-[#D7525A] text-white"
                              : "border-slate-300"
                          }`}
                        >
                          {platforms.includes("LINKEDIN") && <Check className="w-3.5 h-3.5 stroke-[3]" />}
                        </div>
                      </div>
                      <div className="mt-4">
                        <p className="text-sm font-bold text-slate-900">LinkedIn</p>
                        <p className="text-xs text-slate-500 mt-1">
                          B2B thought leadership, CFO benchmark carousel slides, and case study breakdowns.
                        </p>
                      </div>
                    </div>

                    {/* X / Twitter */}
                    <div
                      onClick={() => togglePlatform("X")}
                      className={`cursor-pointer rounded-xl border p-4.5 transition-all text-left flex flex-col justify-between ${
                        platforms.includes("X")
                          ? "border-[#D7525A] bg-rose-50/30 ring-1 ring-[#D7525A]"
                          : "border-slate-200 hover:border-slate-300 bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="w-9 h-9 rounded-lg bg-slate-900 text-white flex items-center justify-center">
                          <XIcon className="w-4 h-4 text-white" />
                        </div>
                        <div
                          className={`w-5 h-5 rounded-full border flex items-center justify-center ${
                            platforms.includes("X")
                              ? "bg-[#D7525A] border-[#D7525A] text-white"
                              : "border-slate-300"
                          }`}
                        >
                          {platforms.includes("X") && <Check className="w-3.5 h-3.5 stroke-[3]" />}
                        </div>
                      </div>
                      <div className="mt-4">
                        <p className="text-sm font-bold text-slate-900">X (Twitter)</p>
                        <p className="text-xs text-slate-500 mt-1">
                          Concise industry hot takes, real-time debt recovery stats, and engaging discussion threads.
                        </p>
                      </div>
                    </div>

                    {/* Meta */}
                    <div
                      onClick={() => togglePlatform("META")}
                      className={`cursor-pointer rounded-xl border p-4.5 transition-all text-left flex flex-col justify-between ${
                        platforms.includes("META")
                          ? "border-[#D7525A] bg-rose-50/30 ring-1 ring-[#D7525A]"
                          : "border-slate-200 hover:border-slate-300 bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="w-9 h-9 rounded-lg bg-pink-50 text-pink-600 flex items-center justify-center">
                          <InstagramIcon className="w-5 h-5 text-[#E4405F]" />
                        </div>
                        <div
                          className={`w-5 h-5 rounded-full border flex items-center justify-center ${
                            platforms.includes("META")
                              ? "bg-[#D7525A] border-[#D7525A] text-white"
                              : "border-slate-300"
                          }`}
                        >
                          {platforms.includes("META") && <Check className="w-3.5 h-3.5 stroke-[3]" />}
                        </div>
                      </div>
                      <div className="mt-4">
                        <p className="text-sm font-bold text-slate-900">Meta (IG &amp; FB)</p>
                        <p className="text-xs text-slate-500 mt-1">
                          Visual customer testimonials, infographic reels, and lookalike retargeting funnels.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* STEP 2: Company Context & Knowledge Upload */}
            {currentStep === 2 && (
              <div className="space-y-8">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">Step 2: Company Context &amp; Knowledge Base</h2>
                  <p className="text-xs text-slate-500 mt-1">
                    Upload your internal assets so our LLM generates factually grounded copy tailored to your value proposition.
                  </p>
                </div>

                {/* Helpful Callout */}
                <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200/80 flex items-start gap-3">
                  <Sparkles className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                  <div className="text-xs text-amber-900 leading-relaxed">
                    <strong>AI Source of Truth:</strong> Upload your company tone guidelines, past high-performing posts,
                    product one-pagers, or competitor differentiation PDFs. Our AI uses this context as its primary knowledge base to avoid generic output.
                  </div>
                </div>

                {/* Drag-and-drop dropzone */}
                <div className="space-y-3">
                  <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                    Upload Documents (PDF, DOCX, CSV)
                  </label>
                  <div
                    {...getKnowledgeRootProps()}
                    className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                      isKnowledgeDragActive
                        ? "border-[#D7525A] bg-rose-50/40"
                        : "border-slate-300 hover:border-slate-400 bg-slate-50/40"
                    }`}
                  >
                    <input {...getKnowledgeInputProps()} />
                    <div className="w-12 h-12 bg-white rounded-full flex items-center justify-center mx-auto text-slate-600 shadow-xs border border-slate-200">
                      <Upload className="w-6 h-6 text-[#D7525A]" />
                    </div>
                    <p className="text-sm font-semibold text-slate-800 mt-3">
                      Drag &amp; drop reference files here, or <span className="text-[#D7525A] underline">browse files</span>
                    </p>
                    <p className="text-xs text-slate-400 mt-1">
                      Supports PDF, DOCX, and CSV up to 25MB each
                    </p>
                  </div>

                  {/* Uploaded File List */}
                  {knowledgeFiles.length > 0 && (
                    <div className="space-y-2 mt-3">
                      <p className="text-xs font-semibold text-slate-600">
                        {knowledgeFiles.length} file{knowledgeFiles.length > 1 ? "s" : ""} selected for extraction:
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {knowledgeFiles.map((file, idx) => (
                          <div
                            key={idx}
                            className="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <FileText className="w-4 h-4 text-slate-500 shrink-0" />
                              <span className="font-medium text-slate-800 truncate">{file.name}</span>
                              <span className="text-[10px] text-slate-400 shrink-0">
                                ({(file.size / 1024).toFixed(0)} KB)
                              </span>
                            </div>
                            <button
                              type="button"
                              onClick={() => removeKnowledgeFile(idx)}
                              className="text-slate-400 hover:text-rose-600 p-1"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Website URL scraping */}
                <div className="space-y-3 pt-4 border-t border-slate-100">
                  <label className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                    <Globe className="w-3.5 h-3.5 text-slate-500" />
                    Website URL for Automated Scraping (Optional)
                  </label>
                  <Input
                    placeholder="https://www.agilereceivables.com/solutions/b2b"
                    value={websiteUrl}
                    onChange={(e) => setWebsiteUrl(e.target.value)}
                    className="h-11 text-sm bg-slate-50/50 focus:bg-white"
                  />
                  <p className="text-[11px] text-slate-400">
                    Our crawler will parse key solution pages, product feature descriptions, and FAQ schemas.
                  </p>
                </div>
              </div>
            )}

            {/* STEP 3: Scheduling Mode Selection */}
            {currentStep === 3 && (
              <div className="space-y-8">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">Step 3: Scheduling Mode Selection</h2>
                  <p className="text-xs text-slate-500 mt-1">
                    Choose whether the AI auto-schedules based on peak engagement or follows your custom spreadsheet calendar.
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* Card A: Sync with Existing Excel Schedule */}
                  <div
                    onClick={() => setSchedulingMode("EXCEL_SYNC")}
                    className={`cursor-pointer rounded-xl border p-5 transition-all text-left flex flex-col justify-between ${
                      schedulingMode === "EXCEL_SYNC"
                        ? "border-[#D7525A] bg-rose-50/30 ring-1 ring-[#D7525A]"
                        : "border-slate-200 hover:border-slate-300 bg-white"
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <div className="w-10 h-10 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center">
                          <Calendar className="w-5 h-5" />
                        </div>
                        <div
                          className={`w-5 h-5 rounded-full border flex items-center justify-center ${
                            schedulingMode === "EXCEL_SYNC"
                              ? "bg-[#D7525A] border-[#D7525A] text-white"
                              : "border-slate-300"
                          }`}
                        >
                          {schedulingMode === "EXCEL_SYNC" && <Check className="w-3.5 h-3.5 stroke-[3]" />}
                        </div>
                      </div>
                      <h3 className="text-sm font-bold text-slate-900 mt-4">Card A: Sync with Existing Excel Schedule</h3>
                      <p className="text-xs text-slate-500 mt-1">
                        Preserves your existing n8n-to-Excel workflow and scheduling dates from your spreadsheet calendar.
                      </p>
                    </div>

                    {schedulingMode === "EXCEL_SYNC" && (
                      <div className="mt-4 pt-4 border-t border-rose-200/60" onClick={(e) => e.stopPropagation()}>
                        <div
                          {...getScheduleRootProps()}
                          className={`border border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors ${
                            isScheduleDragActive
                              ? "border-[#D7525A] bg-rose-100/50"
                              : "border-slate-300 hover:border-slate-400 bg-white"
                          }`}
                        >
                          <input {...getScheduleInputProps()} />
                          <Upload className="w-5 h-5 text-slate-500 mx-auto" />
                          <p className="text-xs font-semibold text-slate-800 mt-1">
                            {scheduleFile ? scheduleFile.name : "Select CSV / Excel schedule file"}
                          </p>
                          <p className="text-[10px] text-slate-400 mt-0.5">
                            {scheduleFile ? `${(scheduleFile.size / 1024).toFixed(0)} KB ready` : "Supports .csv, .xlsx"}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Card B: AI Auto-Pilot */}
                  <div
                    onClick={() => setSchedulingMode("AI_AUTO")}
                    className={`cursor-pointer rounded-xl border p-5 transition-all text-left flex flex-col justify-between ${
                      schedulingMode === "AI_AUTO"
                        ? "border-[#D7525A] bg-rose-50/30 ring-1 ring-[#D7525A]"
                        : "border-slate-200 hover:border-slate-300 bg-white"
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <div className="w-10 h-10 rounded-lg bg-rose-100 text-[#D7525A] flex items-center justify-center">
                          <Bot className="w-5 h-5" />
                        </div>
                        <div
                          className={`w-5 h-5 rounded-full border flex items-center justify-center ${
                            schedulingMode === "AI_AUTO"
                              ? "bg-[#D7525A] border-[#D7525A] text-white"
                              : "border-slate-300"
                          }`}
                        >
                          {schedulingMode === "AI_AUTO" && <Check className="w-3.5 h-3.5 stroke-[3]" />}
                        </div>
                      </div>
                      <h3 className="text-sm font-bold text-slate-900 mt-4">Card B: AI Auto-Pilot (Recommended)</h3>
                      <p className="text-xs text-slate-500 mt-1">
                        AI dynamically schedules posts at high-conversion times across Tuesday–Thursday mornings.
                      </p>
                    </div>

                    {schedulingMode === "AI_AUTO" && (
                      <div className="mt-4 pt-4 border-t border-rose-200/60" onClick={(e) => e.stopPropagation()}>
                        <div className="space-y-2">
                          <div className="flex items-center justify-between text-xs font-bold text-slate-800">
                            <span>Posts per week:</span>
                            <span className="text-[#D7525A] text-sm bg-rose-50 px-2.5 py-0.5 rounded-full border border-rose-200">
                              {postsPerWeek} posts / wk
                            </span>
                          </div>
                          <input
                            type="range"
                            min="1"
                            max="5"
                            step="1"
                            value={postsPerWeek}
                            onChange={(e) => setPostsPerWeek(parseInt(e.target.value, 10))}
                            className="w-full accent-[#D7525A] cursor-pointer"
                          />
                          <div className="flex justify-between text-[10px] text-slate-400 font-medium">
                            <span>1 post (Light)</span>
                            <span>3 posts (Standard)</span>
                            <span>5 posts (Aggressive)</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* STEP 4: AI Training & Approval Settings */}
            {currentStep === 4 && (
              <div className="space-y-8">
                <div>
                  <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                    <ShieldCheck className="w-5 h-5 text-[#D7525A]" />
                    Step 4: Train Your AI Assistant
                  </h2>
                  <p className="text-xs text-slate-500 mt-1">
                    Establish guardrails and supervision rules before permitting full autonomous content syndication.
                  </p>
                </div>

                {/* Training Period Selection */}
                <div className="space-y-3">
                  <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                    Initial Training &amp; Calibration Window
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {[
                      { days: 30, label: "30 Days", desc: "Fast-track baseline (for rapid ramp)" },
                      { days: 45, label: "45 Days", desc: "Recommended balance of feedback & calibration", recommended: true },
                      { days: 60, label: "60 Days", desc: "Deep enterprise governance & multi-pillar tuning" },
                    ].map((option) => (
                      <div
                        key={option.days}
                        onClick={() => setTrainingPeriodDays(option.days)}
                        className={`cursor-pointer rounded-xl border p-4 text-left transition-all ${
                          trainingPeriodDays === option.days
                            ? "border-[#D7525A] bg-rose-50/40 ring-1 ring-[#D7525A]"
                            : "border-slate-200 hover:border-slate-300 bg-white"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-bold text-slate-900">{option.label}</span>
                          {option.recommended && (
                            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">
                              Recommended
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-500 mt-2">{option.desc}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Toggles */}
                <div className="space-y-4 pt-2">
                  {/* Toggle 1: Require approval */}
                  <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/60 flex items-start justify-between gap-4">
                    <div className="space-y-1">
                      <p className="text-xs sm:text-sm font-bold text-slate-900">
                        Require my approval before posting during the training period
                      </p>
                      <p className="text-xs text-slate-500 leading-relaxed">
                        Every AI-generated post will stay in the <strong>&ldquo;Awaiting Approval&rdquo;</strong> Kanban column.
                        You can review the platform visual mockup, submit feedback rules, or approve with one click.
                      </p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer shrink-0 mt-0.5">
                      <input
                        type="checkbox"
                        checked={requireApproval}
                        onChange={(e) => setRequireApproval(e.target.checked)}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-slate-300 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#D7525A]"></div>
                    </label>
                  </div>

                  {/* Toggle 2: Auto-publish after training */}
                  <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/60 flex items-start justify-between gap-4">
                    <div className="space-y-1">
                      <p className="text-xs sm:text-sm font-bold text-slate-900">
                        Automatically switch to Auto-Publish after training period ends
                      </p>
                      <p className="text-xs text-slate-500 leading-relaxed">
                        After the {trainingPeriodDays}-day learning period expires, high-confidence posts will schedule and publish automatically without manual sign-off.
                      </p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer shrink-0 mt-0.5">
                      <input
                        type="checkbox"
                        checked={autoPublish}
                        onChange={(e) => setAutoPublish(e.target.checked)}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-slate-300 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#D7525A]"></div>
                    </label>
                  </div>
                </div>

                {/* Final Summary Card */}
                <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 space-y-2 text-xs">
                  <p className="font-bold text-slate-800">Launch Configuration Summary:</p>
                  <ul className="list-disc list-inside space-y-1 text-slate-600">
                    <li>Campaign: <span className="font-medium text-slate-800">{name || "Untitled"}</span></li>
                    <li>Channels: <span className="font-medium text-slate-800">{platforms.join(", ")}</span></li>
                    <li>Uploaded Assets: <span className="font-medium text-slate-800">{knowledgeFiles.length} file(s){websiteUrl ? " + Scraped URL" : ""}</span></li>
                    <li>Mode: <span className="font-medium text-slate-800">{schedulingMode === "AI_AUTO" ? `${postsPerWeek} posts/week (AI Auto-Pilot)` : "Sync with Existing Excel Schedule"}</span></li>
                    <li>Training Window: <span className="font-medium text-slate-800">{trainingPeriodDays} Days (Supervised: {requireApproval ? "Yes" : "No"})</span></li>
                  </ul>
                </div>
              </div>
            )}

            {/* Step Actions Footer */}
            <div className="flex items-center justify-between pt-8 border-t border-slate-100 mt-8">
              {currentStep > 1 ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleBack}
                  disabled={isSubmitting}
                  className="text-xs"
                >
                  <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
                  Previous Step
                </Button>
              ) : (
                <div />
              )}

              {currentStep < 4 ? (
                <Button
                  type="button"
                  variant="primary"
                  onClick={handleNext}
                  className="bg-[#D7525A] hover:bg-[#c2434b] text-white text-xs px-5 shadow-xs"
                >
                  Continue
                  <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                </Button>
              ) : (
                <Button
                  type="button"
                  variant="primary"
                  onClick={handleSubmit}
                  disabled={isSubmitting}
                  className="bg-[#D7525A] hover:bg-[#c2434b] text-white font-semibold text-xs px-6 py-2.5 shadow-sm flex items-center gap-2"
                >
                  {isSubmitting ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      <span>Launching AI Campaign...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      <span>Launch Campaign</span>
                    </>
                  )}
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
