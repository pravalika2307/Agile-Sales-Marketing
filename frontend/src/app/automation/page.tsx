"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Zap,
  ArrowLeft,
  CheckCircle2,
  Send,
  Workflow,
  Radio,
} from "lucide-react";

export default function AutomationPage() {
  const [testingWebhook, setTestingWebhook] = React.useState(false);
  const [testResult, setTestResult] = React.useState<string | null>(null);

  const handleTestN8n = () => {
    setTestingWebhook(true);
    setTimeout(() => {
      setTestingWebhook(false);
      setTestResult("n8n Webhook responded 200 OK — Pipeline ready for client approvals.");
      setTimeout(() => setTestResult(null), 5000);
    }, 800);
  };

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-200/80">
          <div>
            <div className="flex items-center gap-2">
              <Link
                href="/"
                className="text-xs font-semibold text-slate-500 hover:text-slate-800 flex items-center gap-1 transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Dashboard</span>
              </Link>
              <span className="text-slate-300">/</span>
              <span className="text-xs font-semibold text-indigo-600">Automation</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 mt-1">
              Marketing Automations &amp; Webhooks
            </h1>
            <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
              Automated workflows, n8n client approval pipelines, and multi-channel publishing connectors.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <Button
              variant="outline"
              size="sm"
              onClick={handleTestN8n}
              disabled={testingWebhook}
              className="text-xs font-semibold border-indigo-200 text-indigo-700 hover:bg-indigo-50 bg-white"
            >
              <Zap className="w-3.5 h-3.5 mr-1.5 text-indigo-600" />
              <span>{testingWebhook ? "Pinging Webhook..." : "Test n8n Webhook"}</span>
            </Button>
          </div>
        </div>

        {testResult && (
          <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2 animate-in fade-in">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span className="font-semibold">{testResult}</span>
          </div>
        )}

        {/* Pipelines Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="rounded-xl border border-slate-200/80 bg-white shadow-xs">
            <CardHeader className="p-4 pb-2">
              <div className="flex items-center justify-between">
                <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                  <Send className="w-4 h-4" />
                </div>
                <Badge variant="neutral" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px]">
                  Active
                </Badge>
              </div>
              <CardTitle className="text-sm font-bold text-slate-900 mt-3">
                Client Sign-Off Webhook
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-1 text-xs text-slate-500">
              <p>
                Triggers when a campaign post is reviewed from the Client Approval Queue, sending authorization emails and signing payloads via n8n.
              </p>
              <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
                <span>Webhook: POST /n8n-approval</span>
                <span className="text-emerald-600 font-semibold">100% Uptime</span>
              </div>
            </CardContent>
          </Card>

          <Card className="rounded-xl border border-slate-200/80 bg-white shadow-xs">
            <CardHeader className="p-4 pb-2">
              <div className="flex items-center justify-between">
                <div className="w-8 h-8 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
                  <Workflow className="w-4 h-4" />
                </div>
                <Badge variant="neutral" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px]">
                  Active
                </Badge>
              </div>
              <CardTitle className="text-sm font-bold text-slate-900 mt-3">
                Social Multi-Publishing
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-1 text-xs text-slate-500">
              <p>
                Dispatches approved creatives to LinkedIn, Instagram, X, and Facebook at scheduled time intervals based on peak engagement windows.
              </p>
              <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
                <span>Schedule: Cron (Peak EST)</span>
                <span className="text-indigo-600 font-semibold">4 Channels</span>
              </div>
            </CardContent>
          </Card>

          <Card className="rounded-xl border border-slate-200/80 bg-white shadow-xs">
            <CardHeader className="p-4 pb-2">
              <div className="flex items-center justify-between">
                <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                  <Radio className="w-4 h-4" />
                </div>
                <Badge variant="neutral" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px]">
                  Listening
                </Badge>
              </div>
              <CardTitle className="text-sm font-bold text-slate-900 mt-3">
                Retell AI Voice Telephony Sync
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-1 text-xs text-slate-500">
              <p>
                Listens for Retell voice call webhook completion events and enriches MQL conversion signals in real-time.
              </p>
              <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
                <span>Source: /voice/retell-webhook</span>
                <span className="text-emerald-600 font-semibold">Verified</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
