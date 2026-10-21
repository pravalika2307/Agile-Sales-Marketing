"use client";

import * as React from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  ArrowLeft,
  CheckCircle2,
  Share2,
  Key,
} from "lucide-react";
import { LinkedInIcon, InstagramIcon, FacebookIcon, XIcon } from "@/components/social/social-icons";

export default function MarketingSettingsPage() {
  const [savedToast, setSavedToast] = React.useState(false);
  const [webhookUrl, setWebhookUrl] = React.useState(
    "https://n8n.agilereceivables.com/webhook/client-marketing-approval"
  );

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSavedToast(true);
    setTimeout(() => setSavedToast(false), 4000);
  };

  return (
    <AppShell>
      <div className="space-y-6 max-w-4xl">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-slate-200/80">
          <div>
            <div className="flex items-center gap-2">
              <Link
                href="/marketing"
                className="text-xs font-semibold text-slate-500 hover:text-slate-800 flex items-center gap-1 transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Marketing</span>
              </Link>
              <span className="text-slate-300">/</span>
              <span className="text-xs font-semibold text-indigo-600">Settings</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 mt-1">
              Marketing &amp; Platform Settings
            </h1>
            <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
              Manage connected social accounts, n8n webhook parameters, and workspace configurations.
            </p>
          </div>
        </div>

        {savedToast && (
          <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2 animate-in fade-in">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span className="font-semibold">Settings updated successfully.</span>
          </div>
        )}

        {/* Connected Social Accounts */}
        <Card className="rounded-xl border border-slate-200/80 bg-white shadow-xs">
          <CardHeader className="p-4 sm:p-5 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Share2 className="w-4 h-4 text-indigo-600" />
              <CardTitle className="text-sm sm:text-base font-bold text-slate-900">
                Connected Social Platforms
              </CardTitle>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Channels active for automated Content Calendar scheduling and analytics synchronization.
            </p>
          </CardHeader>
          <CardContent className="p-4 sm:p-5 space-y-3">
            {[
              {
                name: "LinkedIn Company Page",
                account: "Agile Receivables (Corporate)",
                icon: <LinkedInIcon className="w-4 h-4 text-[#0A66C2]" />,
                status: "Connected",
              },
              {
                name: "X (Twitter) Commercial",
                account: "@AgileAR_Ops",
                icon: <XIcon className="w-4 h-4 text-slate-900" />,
                status: "Connected",
              },
              {
                name: "Meta / Facebook Business",
                account: "Agile Receivables Cloud",
                icon: <FacebookIcon className="w-4 h-4 text-[#1877F2]" />,
                status: "Connected",
              },
              {
                name: "Instagram Professional",
                account: "@agile_receivables",
                icon: <InstagramIcon className="w-4 h-4 text-[#E4405F]" />,
                status: "Connected",
              },
            ].map((chan) => (
              <div
                key={chan.name}
                className="flex items-center justify-between p-3 rounded-lg border border-slate-100 bg-slate-50/50"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-white border border-slate-200 flex items-center justify-center shadow-2xs">
                    {chan.icon}
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-slate-800">{chan.name}</h4>
                    <p className="text-[11px] text-slate-400">{chan.account}</p>
                  </div>
                </div>
                <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                  {chan.status}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* n8n Webhook Configuration */}
        <Card className="rounded-xl border border-slate-200/80 bg-white shadow-xs">
          <CardHeader className="p-4 sm:p-5 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Key className="w-4 h-4 text-indigo-600" />
              <CardTitle className="text-sm sm:text-base font-bold text-slate-900">
                n8n Webhook Pipeline Configuration
              </CardTitle>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Specify the webhook endpoint invoked when clicking &quot;Review&quot; in the Client Approval Queue.
            </p>
          </CardHeader>
          <CardContent className="p-4 sm:p-5">
            <form onSubmit={handleSave} className="space-y-4">
              <div>
                <label className="text-xs font-bold text-slate-700 block mb-1">
                  Client Approval Webhook URL
                </label>
                <input
                  type="url"
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-hidden focus:ring-1 focus:ring-indigo-500"
                />
                <p className="text-[11px] text-slate-400 mt-1">
                  Sends payload containing post title, campaign ID, client identity, and HMAC security tokens.
                </p>
              </div>

              <div className="flex justify-end pt-2">
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold"
                >
                  Save Settings
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
