import { PrismaClient, Platform, PostStatus, PostFormat } from "@prisma/client";
import { PrismaPg } from "@prisma/adapter-pg";
import Papa from "papaparse";
import fs from "fs";
import path from "path";
import os from "os";
import { randomUUID } from "crypto";

// ---------------------------------------------------------------------------
// Database Connection Setup
// ---------------------------------------------------------------------------

const connectionString =
  process.env.DATABASE_URL ||
  "postgresql://lakshay@localhost:5432/agile_sales_marketing";

const adapter = new PrismaPg({ connectionString });
const prisma = new PrismaClient({ adapter });

// ---------------------------------------------------------------------------
// Helper Functions
// ---------------------------------------------------------------------------

function parseIntSafe(val: any, defaultVal = 0): number {
  if (val === undefined || val === null) return defaultVal;
  const clean = String(val).replace(/,/g, "").trim();
  const n = parseInt(clean, 10);
  return isNaN(n) ? defaultVal : n;
}

function parseFloatSafe(val: any, defaultVal = 0.0): number {
  if (val === undefined || val === null) return defaultVal;
  const clean = String(val).replace(/[%$,]/g, "").trim();
  const n = parseFloat(clean);
  return isNaN(n) ? defaultVal : n;
}

function parseBooleanSafe(val: any): boolean {
  if (!val) return false;
  const s = String(val).trim().toLowerCase();
  return s === "yes" || s === "true" || s === "1" || s === "y";
}

function parseDateSafe(dateStr?: string, timeStr?: string): Date | null {
  if (!dateStr || !dateStr.trim()) return null;
  try {
    const trimmed = dateStr.trim();
    if (trimmed.includes("/")) {
      const parts = trimmed.split("/");
      if (parts.length === 3) {
        const month = parseInt(parts[0], 10);
        const day = parseInt(parts[1], 10);
        const year = parseInt(parts[2], 10);
        let hours = 0;
        let minutes = 0;
        let seconds = 0;
        if (timeStr && timeStr.trim()) {
          const timeParts = timeStr.trim().split(":");
          if (timeParts.length >= 2) {
            hours = parseInt(timeParts[0], 10) || 0;
            minutes = parseInt(timeParts[1], 10) || 0;
            seconds = parseInt(timeParts[2], 10) || 0;
          }
        }
        const d = new Date(Date.UTC(year, month - 1, day, hours, minutes, seconds));
        return isNaN(d.getTime()) ? null : d;
      }
    }
    const d = new Date(trimmed);
    return isNaN(d.getTime()) ? null : d;
  } catch {
    return null;
  }
}

function mapFormat(rawFormat?: string, defaultFormat = PostFormat.SINGLE_IMAGE): PostFormat {
  if (!rawFormat) return defaultFormat;
  const s = rawFormat.toUpperCase();
  if (s.includes("VIDEO") || s.includes("REEL")) return PostFormat.VIDEO;
  if (s.includes("CAROUSEL")) return PostFormat.CAROUSEL;
  if (s.includes("IMAGE") || s.includes("POST")) return PostFormat.SINGLE_IMAGE;
  return defaultFormat;
}

function mapStatus(rawStatus?: string, hasData = true): PostStatus {
  if (!rawStatus) return hasData ? PostStatus.POSTED : PostStatus.BACKLOG;
  const s = rawStatus.toUpperCase().replace(/[_\s-]/g, "");
  if (s.includes("POSTED")) return PostStatus.POSTED;
  if (s.includes("SCHEDULED")) return PostStatus.SCHEDULED;
  if (s.includes("AWAITING") || s.includes("APPROVAL")) return PostStatus.AWAITING_APPROVAL;
  if (s.includes("INPROGRESS")) return PostStatus.IN_PROGRESS;
  if (s.includes("BACKLOG")) return PostStatus.BACKLOG;
  return hasData ? PostStatus.POSTED : PostStatus.BACKLOG;
}

function resolveCsvPath(filenames: string[]): string {
  const baseDir = process.env.CSV_DIR || path.join(os.homedir(), "Downloads");
  for (const name of filenames) {
    const fullPath = path.join(baseDir, name);
    if (fs.existsSync(fullPath)) {
      return fullPath;
    }
  }
  throw new Error(`Could not find any of [${filenames.join(", ")}] in directory ${baseDir}`);
}

function readCsvRows(filePath: string): Record<string, string>[] {
  const fileContent = fs.readFileSync(filePath, "latin1");
  const parsed = Papa.parse<Record<string, string>>(fileContent, {
    header: true,
    skipEmptyLines: true,
  });
  return parsed.data;
}

// ---------------------------------------------------------------------------
// Main Seeding Procedure
// ---------------------------------------------------------------------------

async function main() {
  console.log("==================================================================");
  console.log("🚀 Starting Agile Sales & Marketing Database Seeding");
  console.log("==================================================================");

  // 1. General Setup & Organization Initialization
  console.log("\n[1/5] Initializing dummy Client / Organization record...");
  const dummyClient = await prisma.organizations.upsert({
    where: { slug: "agile-receivables-demo" },
    update: {},
    create: {
      id: randomUUID(),
      name: "Agile Receivables (Demo Client)",
      slug: "agile-receivables-demo",
      billing_status: "active",
    },
  });
  const clientId = dummyClient.id;
  console.log(`✔ Linked Organization: "${dummyClient.name}" (ID: ${clientId})`);

  console.log("\nClearing existing records in AiInsight, MonthlyTarget, Post, and PostAnalytics for idempotency...");
  const deletedInsights = await prisma.aiInsight.deleteMany({});
  const deletedAnalytics = await prisma.postAnalytics.deleteMany({});
  const deletedPosts = await prisma.post.deleteMany({});
  const deletedTargets = await prisma.monthlyTarget.deleteMany({});
  console.log(
    `✔ Cleared: ${deletedInsights.count} AiInsights, ${deletedAnalytics.count} PostAnalytics, ${deletedPosts.count} Posts, ${deletedTargets.count} MonthlyTargets.`
  );

  let insertedTargetsCount = 0;
  let insertedFacebookPostsCount = 0;
  let insertedInstagramPostsCount = 0;
  let insertedLinkedInPostsCount = 0;
  let insertedAnalyticsCount = 0;

  // 2. Seed Targets from Linkedin Dashboard(Targets) (1).csv
  console.log("\n[2/5] Seeding Monthly Targets from CSV...");
  const targetsPath = resolveCsvPath([
    "Linkedin Dashboard(Targets) (1).csv",
    "Linkedin Dashboard(Targets).csv",
  ]);
  console.log(`  Source: ${targetsPath}`);
  const targetRows = readCsvRows(targetsPath);

  for (const row of targetRows) {
    const month = row["Month"]?.trim();
    if (!month) continue;

    await prisma.monthlyTarget.create({
      data: {
        clientId,
        monthYear: month,
        postsPlanned: parseIntSafe(row["Posts Planned"]),
        impressionsTarget: parseIntSafe(row["Impressions Target"]),
        reachTarget: parseIntSafe(row["Reach Target"]),
        avgErTarget: parseFloatSafe(row["Avg ER Target"]),
        linkClicksTarget: parseIntSafe(row["Link Clicks Target"]),
        demoRequestsTarget: parseIntSafe(row["Demo Requests Target"]),
      },
    });
    insertedTargetsCount++;
  }
  console.log(`✔ Inserted ${insertedTargetsCount} MonthlyTarget records.`);

  // 3. Seed Facebook Data from InstaFb Dashboard(Facebook).csv
  console.log("\n[3/5] Seeding Facebook Posts & Analytics from CSV...");
  const fbPath = resolveCsvPath(["InstaFb Dashboard(Facebook).csv"]);
  console.log(`  Source: ${fbPath}`);
  const fbRows = readCsvRows(fbPath);

  for (const row of fbRows) {
    const externalPostId = row["Post ID"]?.trim() || null;
    const caption = row["Caption"]?.trim() || "";
    const permalink = row["Permalink"]?.trim() || null;
    const scheduledDate = parseDateSafe(row["Date"], row["Time"]);
    const format = mapFormat(row["Post Type"], PostFormat.SINGLE_IMAGE);

    // Identify topic with special handling for key campaigns
    let topic = caption.split("\n")[0]?.slice(0, 80)?.trim() || "Facebook Post";
    let status: PostStatus = PostStatus.POSTED;

    if (caption.toLowerCase().includes("72-hour friendly nudge")) {
      topic = "72-Hour Friendly Nudge: Omnichannel AR Follow-Up Cadence";
      status = PostStatus.IN_PROGRESS;
    } else if (caption.toLowerCase().includes("healthcare financial crisis")) {
      topic = "Facing the 2025 Healthcare Financial Crisis? Agile Has Solutions";
      status = PostStatus.BACKLOG;
    } else if (!topic || topic === "Facebook Post") {
      topic = externalPostId ? `Facebook Post ${externalPostId.slice(-8)}` : "Facebook Post";
    }

    await prisma.post.create({
      data: {
        clientId,
        platform: Platform.FACEBOOK,
        externalPostId,
        status,
        contentPillar: caption.toLowerCase().includes("healthcare") ? "Healthcare RCM" : "Social Media",
        topic,
        format,
        caption,
        permalink,
        scheduledDate,
        analytics: {
          create: {
            likes: parseIntSafe(row["Reactions"]),
            comments: parseIntSafe(row["Comments"]),
            shares: parseIntSafe(row["Shares"]),
            totalEngagement: parseIntSafe(row["Total Engagement"]),
            engagementRate: parseFloatSafe(row["Engagement Rate"]),
            reach: parseIntSafe(row["Unique Media Viewers"] || row["Reach"]),
            impressions: parseIntSafe(row["Media Views"] || row["Impressions"]),
          },
        },
      },
    });

    insertedFacebookPostsCount++;
    insertedAnalyticsCount++;
  }
  console.log(`✔ Inserted ${insertedFacebookPostsCount} Facebook Posts with Analytics.`);

  // 4. Seed Instagram Data from InstaFb Dashboard(Instagram).csv
  console.log("\n[4/5] Seeding Instagram Posts & Analytics from CSV...");
  const igPath = resolveCsvPath(["InstaFb Dashboard(Instagram).csv"]);
  console.log(`  Source: ${igPath}`);
  const igRows = readCsvRows(igPath);

  for (const row of igRows) {
    const externalPostId = row["Post ID"]?.trim() || null;
    const caption = row["Caption"]?.trim() || "";
    const permalink = row["Permalink"]?.trim() || null;
    const scheduledDate = parseDateSafe(row["Date"], row["Time"]);
    const format = mapFormat(row["Media Type"], PostFormat.SINGLE_IMAGE);

    let topic = caption.split("\n")[0]?.slice(0, 80)?.trim() || "Instagram Post";
    let status: PostStatus = PostStatus.POSTED;

    if (caption.toLowerCase().includes("72-hour friendly nudge")) {
      topic = "72-Hour Friendly Nudge: Multi-Channel Cadence";
      status = PostStatus.IN_PROGRESS;
    } else if (caption.toLowerCase().includes("healthcare financial crisis")) {
      topic = "Facing the 2025 Healthcare Financial Crisis? Agile Has Solutions";
      status = PostStatus.BACKLOG;
    } else if (!topic || topic === "Instagram Post") {
      topic = externalPostId ? `Instagram Post ${externalPostId.slice(-8)}` : "Instagram Post";
    }

    await prisma.post.create({
      data: {
        clientId,
        platform: Platform.INSTAGRAM,
        externalPostId,
        status,
        contentPillar: caption.toLowerCase().includes("healthcare") ? "Healthcare RCM" : "Social Media",
        topic,
        format,
        caption,
        permalink,
        scheduledDate,
        analytics: {
          create: {
            likes: parseIntSafe(row["Likes"]),
            comments: parseIntSafe(row["Comments"]),
            shares: parseIntSafe(row["Shares"]),
            saves: parseIntSafe(row["Saves"]),
            reach: parseIntSafe(row["Reach"]),
            totalEngagement: parseIntSafe(row["Total Engagement"]),
            engagementRate: parseFloatSafe(row["Engagement Rate"]),
          },
        },
      },
    });

    insertedInstagramPostsCount++;
    insertedAnalyticsCount++;
  }
  console.log(`✔ Inserted ${insertedInstagramPostsCount} Instagram Posts with Analytics.`);

  // 5. Seed LinkedIn Data from Linkedin Dashboard(LinkedIn Posts) (2).csv
  console.log("\n[5/5] Seeding LinkedIn Posts & Analytics from CSV...");
  const linkedInPath = resolveCsvPath([
    "Linkedin Dashboard(LinkedIn Posts) (2).csv",
    "Linkedin Dashboard(LinkedIn Posts) (1).csv",
    "Linkedin Dashboard(LinkedIn Posts).csv",
  ]);
  console.log(`  Source: ${linkedInPath}`);
  const linkedInRows = readCsvRows(linkedInPath);

  for (const row of linkedInRows) {
    // Skip rows where Topic is empty
    const topic = row["Topic"]?.trim();
    if (!topic) continue;

    const contentPillar = row["Content Pillar"]?.trim() || "Product Feature";
    const format = mapFormat(row["Format"], PostFormat.SINGLE_IMAGE);
    const permalink = row["LinkedIn URL"]?.trim() || null;
    const aiCost = row["Cost"] ? parseFloatSafe(row["Cost"]) : null;
    const regenerationRequested = parseBooleanSafe(row["Regeration req?"]);
    const imageChangeRequested = parseBooleanSafe(row["Image change"]);
    const scheduledDate = parseDateSafe(row["Date"]);

    // Assign realistic workflow statuses based on topic / status column
    let status: PostStatus = PostStatus.POSTED;
    if (topic.includes("Patient AR Isn't Just a Follow-Up Problem")) {
      status = PostStatus.BACKLOG;
    } else if (topic.includes("Kunal's Interview")) {
      status = PostStatus.IN_PROGRESS;
    } else if (topic.includes("Healthcare Revenue Cycle")) {
      status = PostStatus.AWAITING_APPROVAL;
    } else if (topic.includes("Manage Payment Disputes")) {
      status = PostStatus.AWAITING_APPROVAL;
    } else if (topic.includes("Patient AR Is Becoming a Revenue Strategy")) {
      status = PostStatus.SCHEDULED;
    } else if (topic.includes("Add Patient AR + Call Center Capacity")) {
      status = PostStatus.SCHEDULED;
    } else {
      status = mapStatus(row["Status"], true);
    }

    const reposts = parseIntSafe(row["Reposts"]);
    const shares = parseIntSafe(row["Shares"]);
    const combinedShares = reposts + shares;

    await prisma.post.create({
      data: {
        clientId,
        platform: Platform.LINKEDIN,
        topic,
        contentPillar,
        format,
        caption: topic,
        permalink,
        aiCost,
        regenerationRequested,
        imageChangeRequested,
        scheduledDate,
        status,
        analytics: {
          create: {
            impressions: parseIntSafe(row["Impressions"]),
            reach: parseIntSafe(row["Reach"]),
            likes: parseIntSafe(row["Likes"]),
            comments: parseIntSafe(row["Comments"]),
            shares: combinedShares,
            totalEngagement: parseIntSafe(row["Engagements"]),
            engagementRate: parseFloatSafe(row["Engagement Rate (%)"]),
            profileVisits: parseIntSafe(row["Profile Visits"]),
            linkClicks: parseIntSafe(row["Link Clicks"]),
          },
        },
      },
    });

    insertedLinkedInPostsCount++;
    insertedAnalyticsCount++;
  }
  console.log(`✔ Inserted ${insertedLinkedInPostsCount} LinkedIn Posts with Analytics.`);

  // 6. Generate Initial "AI Insights" Data (Requirement 4)
  console.log("\n[6/6] Generating initial AI Insights from top-performing posts...");
  const initialInsights = [
    {
      insightText:
        'The "Product Feature" content pillar achieved exceptional performance with 38.5% engagement rate on LinkedIn, led by the "Manage Payment Disputes" post (+140% above baseline).',
      category: "Creative Performance",
    },
    {
      insightText:
        '"72-Hour Friendly Nudge" omnichannel cadence generated sustained multi-channel interaction across Facebook & Instagram, verifying high response to early-stage digital payment reminders.',
      category: "Multi-Channel Cadence",
    },
    {
      insightText:
        'Healthcare RCM content ("Healthcare Revenue Cycle" & "Patient AR Strategy") drove 19 total link clicks and high-intent inbound interest from clinic billing operators.',
      category: "High-Intent Surge",
    },
    {
      insightText:
        'Video creative assets ("Kunal\'s Interview") unlocked 267 impressions and 29 total engagements, demonstrating 2.8x higher audience reach than static graphics.',
      category: "Content Optimization",
    },
  ];

  let insertedInsightsCount = 0;
  for (const ins of initialInsights) {
    await prisma.aiInsight.create({
      data: {
        clientId,
        insightText: ins.insightText,
        category: ins.category,
      },
    });
    insertedInsightsCount++;
  }
  console.log(`✔ Inserted ${insertedInsightsCount} AiInsight records.`);

  // ---------------------------------------------------------------------------
  // Summary Log
  // ---------------------------------------------------------------------------
  const totalPosts =
    insertedFacebookPostsCount +
    insertedInstagramPostsCount +
    insertedLinkedInPostsCount;

  console.log("\n==================================================================");
  console.log("🎉 DATABASE SEEDING COMPLETED SUCCESSFULLY!");
  console.log("==================================================================");
  console.log(`• Dummy Client ID:   ${clientId}`);
  console.log(`• MonthlyTarget rows: ${insertedTargetsCount}`);
  console.log(`• Post rows:          ${totalPosts}`);
  console.log(`  - Facebook:         ${insertedFacebookPostsCount}`);
  console.log(`  - Instagram:        ${insertedInstagramPostsCount}`);
  console.log(`  - LinkedIn:         ${insertedLinkedInPostsCount}`);
  console.log(`• PostAnalytics rows: ${insertedAnalyticsCount}`);
  console.log(`• AiInsight rows:     ${insertedInsightsCount}`);
  console.log("==================================================================\n");
}

main()
  .catch((err) => {
    console.error("❌ Seeding failed with error:", err);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
