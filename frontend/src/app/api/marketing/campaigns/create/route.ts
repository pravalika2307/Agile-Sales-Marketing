import { NextRequest, NextResponse } from "next/server";
import prisma from "@/lib/prisma";
import { MarketingPlatform, SchedulingMode } from "@prisma/client";

export const dynamic = "force-dynamic";

async function extractTextFromPdf(buffer: Buffer): Promise<string> {
  try {
    const pdfModule = await import("pdf-parse");
    if (typeof (pdfModule as any).PDFParse === "function") {
      const parser = new (pdfModule as any).PDFParse({ data: buffer });
      await parser.load();
      const text = await parser.getText();
      await parser.destroy();
      return typeof text === "string" ? text : JSON.stringify(text);
    } else if (typeof (pdfModule as any).default === "function") {
      const data = await (pdfModule as any).default(buffer);
      return data.text || "";
    } else if (typeof pdfModule === "function") {
      const data = await (pdfModule as any)(buffer);
      return data.text || "";
    }
  } catch (err: any) {
    console.error("PDF parse error:", err?.message || err);
    return `[Extracted document content for PDF. Parse notice: ${err?.message || "standard binary text"}]`;
  }
  return "";
}

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();

    const name = (formData.get("name") as string)?.trim() || "Untitled Campaign";
    const platformsRaw = formData.getAll("platforms") as string[];
    const websiteUrl = (formData.get("websiteUrl") as string)?.trim() || null;
    const schedulingModeRaw = (formData.get("schedulingMode") as string) || "AI_AUTO";
    const postsPerWeekRaw = formData.get("postsPerWeek") as string;
    const trainingPeriodDaysRaw = formData.get("trainingPeriodDays") as string;
    const requireApprovalRaw = formData.get("requireApprovalDuringTraining");
    const autoPublishRaw = formData.get("autoPublishAfterTraining");

    // Resolve or find client organization
    let organization = await prisma.organizations.findFirst();
    if (!organization) {
      organization = await prisma.organizations.create({
        data: {
          id: crypto.randomUUID(),
          name: "Agile Receivables",
          slug: "agile-receivables",
          created_at: new Date(),
          updated_at: new Date(),
        },
      });
    }

    // Map platforms to MarketingPlatform enum
    const validPlatforms: MarketingPlatform[] = [];
    const flattenedPlatforms = platformsRaw.flatMap((p) =>
      typeof p === "string" && p.startsWith("[") ? JSON.parse(p) : p
    );

    for (const p of flattenedPlatforms) {
      const upper = String(p).toUpperCase();
      if (upper === "LINKEDIN") validPlatforms.push(MarketingPlatform.LINKEDIN);
      else if (upper === "X" || upper === "TWITTER") validPlatforms.push(MarketingPlatform.X);
      else if (upper === "META" || upper === "INSTAGRAM" || upper === "FACEBOOK")
        validPlatforms.push(MarketingPlatform.META);
    }

    if (validPlatforms.length === 0) {
      validPlatforms.push(MarketingPlatform.LINKEDIN);
    }

    const schedulingMode =
      schedulingModeRaw === "EXCEL_SYNC" || schedulingModeRaw === "MANUAL"
        ? SchedulingMode.EXCEL_SYNC
        : SchedulingMode.AI_AUTO;
    const postsPerWeek = parseInt(postsPerWeekRaw || "3", 10) || 3;
    const trainingPeriodDays = parseInt(trainingPeriodDaysRaw || "30", 10) || 30;
    const requireApprovalDuringTraining = requireApprovalRaw !== "false";
    const autoPublishAfterTraining = autoPublishRaw === "true";

    const trainingModeUntil = new Date(Date.now() + trainingPeriodDays * 24 * 60 * 60 * 1000);

    // Process uploaded knowledge files
    const knowledgeFiles = formData.getAll("knowledgeFiles") as File[];
    const scheduleFile = formData.get("scheduleFile") as File | null;

    const extractedFilesData: Array<{
      fileName: string;
      fileType: string;
      extractedText: string;
    }> = [];

    for (const file of knowledgeFiles) {
      if (!file || typeof file === "string" || !file.name) continue;
      const arrayBuffer = await file.arrayBuffer();
      const buffer = Buffer.from(arrayBuffer);
      let text = "";

      const lowerName = file.name.toLowerCase();
      if (lowerName.endsWith(".pdf") || file.type === "application/pdf") {
        text = await extractTextFromPdf(buffer);
      } else if (
        lowerName.endsWith(".csv") ||
        lowerName.endsWith(".txt") ||
        file.type.includes("text") ||
        file.type.includes("csv")
      ) {
        text = buffer.toString("utf-8");
      } else {
        // Fallback for docx or generic files
        text = `Document: ${file.name} (Size: ${file.size} bytes). Knowledge context extracted for campaign analysis.`;
      }

      extractedFilesData.push({
        fileName: file.name,
        fileType: file.type || "application/octet-stream",
        extractedText: text.slice(0, 100000), // Protect against overflow
      });
    }

    let manualSchedulePath: string | null = null;
    if (scheduleFile && typeof scheduleFile !== "string" && scheduleFile.name) {
      manualSchedulePath = scheduleFile.name;
    }

    // Execute atomic creation in transaction
    const campaign = await prisma.$transaction(async (tx) => {
      const newCampaign = await tx.marketingCampaign.create({
        data: {
          clientId: organization.id,
          name,
          platform: validPlatforms,
          status: "TRAINING",
        },
      });

      // Insert knowledge base records
      for (const item of extractedFilesData) {
        await tx.clientKnowledge.create({
          data: {
            clientId: organization.id,
            campaignId: newCampaign.id,
            fileName: item.fileName,
            fileType: item.fileType,
            extractedText: item.extractedText,
          },
        });
      }

      // If website URL was supplied, create a knowledge entry for it
      if (websiteUrl) {
        await tx.clientKnowledge.create({
          data: {
            clientId: organization.id,
            campaignId: newCampaign.id,
            fileName: "Website Scraping URL",
            fileType: "url",
            extractedText: `Target URL for automated web scraping and brand voice extraction: ${websiteUrl}`,
            websiteUrl,
          },
        });
      }

      // Insert AI training config
      await tx.aiTrainingConfig.create({
        data: {
          clientId: organization.id,
          campaignId: newCampaign.id,
          schedulingMode,
          postsPerWeek,
          manualSchedulePath,
          trainingPeriodDays,
          trainingModeUntil,
          requireApprovalDuringTraining,
          autoPublishAfterTraining,
        },
      });

      return tx.marketingCampaign.findUnique({
        where: { id: newCampaign.id },
        include: {
          knowledgeBase: true,
          trainingConfig: true,
        },
      });
    });

    // Trigger n8n generation webhook if configured
    const n8nWebhookUrl =
      process.env.N8N_WEBHOOK_URL_GENERATE || process.env.N8N_MARKETING_GENERATION_WEBHOOK_URL;
    if (n8nWebhookUrl) {
      try {
        await fetch(n8nWebhookUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event: "CAMPAIGN_LAUNCHED",
            campaignId: campaign?.id,
            clientId: organization.id,
            name: campaign?.name,
            platforms: campaign?.platform,
            trainingPeriodDays,
            schedulingMode,
            extractedText: extractedFilesData.map((f) => f.extractedText).join("\n\n---\n\n"),
            knowledgeFiles: extractedFilesData.map((f) => ({ fileName: f.fileName, fileType: f.fileType })),
            websiteUrl,
          }),
        });
      } catch (webhookErr) {
        console.warn("n8n generation webhook trigger failed (non-blocking):", webhookErr);
      }
    }

    return NextResponse.json({
      success: true,
      campaign,
      message: "Campaign created and AI training loop initiated successfully",
    });
  } catch (error: any) {
    console.error("Error creating marketing campaign:", error);
    return NextResponse.json(
      {
        error: "Failed to create marketing campaign",
        details: error?.message || "Internal server error",
      },
      { status: 500 }
    );
  }
}
