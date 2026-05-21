import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { google } from "googleapis";
import { AppConfig } from "./config";
import { RunLogger } from "./logger";
import { IndexingInspectionResult, IndexingStatus } from "./types";

type SearchConsoleSitemapSubmitResult = {
  sitemapUrl: string;
  submitted: boolean;
};

type IndexingStatusFile = {
  urls: Record<string, IndexingStatus>;
};

function nowIso(): string {
  return new Date().toISOString();
}

function loadIndexingStatusFile(config: AppConfig): IndexingStatusFile {
  const filePath = config.paths.indexingStatusFile;
  if (!existsSync(filePath)) {
    return { urls: {} };
  }
  try {
    const parsed = JSON.parse(readFileSync(filePath, "utf-8"));
    return parsed && typeof parsed === "object" && parsed.urls ? parsed : { urls: {} };
  } catch {
    return { urls: {} };
  }
}

function saveIndexingStatus(config: AppConfig, status: IndexingStatus): void {
  const payload = loadIndexingStatusFile(config);
  payload.urls = payload.urls || {};
  payload.urls[status.postUrl] = status;
  writeFileSync(config.paths.indexingStatusFile, JSON.stringify(payload, null, 2), "utf-8");
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function rankSitemap(url: string): number {
  const normalized = url.toLowerCase();
  if (normalized.endsWith("/sitemap_index.xml")) return 0;
  if (normalized.endsWith("/post-sitemap.xml")) return 1;
  if (normalized.endsWith("/news-sitemap.xml")) return 2;
  if (normalized.endsWith("/sitemap.xml")) return 3;
  return 10;
}

async function discoverSitemaps(config: AppConfig, logger: RunLogger): Promise<string[]> {
  const base = config.wpBaseUrl.replace(/\/+$/, "");
  const fallbackCandidates = [
    `${base}/sitemap_index.xml`,
    `${base}/post-sitemap.xml`,
    `${base}/sitemap.xml`,
  ];

  try {
    const robotsResponse = await fetch(`${base}/robots.txt`);
    if (!robotsResponse.ok) {
      logger.warn(`robots.txt lookup returned ${robotsResponse.status}. Falling back to default sitemap guesses.`);
      return fallbackCandidates;
    }

    const robotsText = await robotsResponse.text();
    const robotSitemaps = robotsText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => /^sitemap:/i.test(line))
      .map((line) => line.split(/:/, 2)[1]?.trim() || "")
      .filter(Boolean);

    const candidates = unique([...robotSitemaps, ...fallbackCandidates]).sort((a, b) => rankSitemap(a) - rankSitemap(b));
    logger.step(`Discovered sitemap candidates: ${candidates.join(", ")}`, { stage: "indexing" });
    return candidates;
  } catch (error) {
    logger.warn(`Failed to inspect robots.txt for sitemap discovery: ${error instanceof Error ? error.message : String(error)}`);
    return fallbackCandidates;
  }
}

async function pingSitemaps(logger: RunLogger, sitemapUrls: string[]): Promise<void> {
  for (const sitemapUrl of sitemapUrls) {
    try {
      await fetch(`https://www.google.com/ping?sitemap=${encodeURIComponent(sitemapUrl)}`);
      logger.step(`Sitemap ping sent: ${sitemapUrl}`, { stage: "indexing" });
    } catch (error) {
      logger.warn(`Sitemap ping failed for ${sitemapUrl}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
}

async function createSearchConsoleAuth(config: AppConfig): Promise<InstanceType<typeof google.auth.OAuth2> | null> {
  const property = String(config.googleSearchConsoleProperty || "").trim();
  const clientId = String(config.googleOAuthClientId || "").trim();
  const clientSecret = String(config.googleOAuthClientSecret || "").trim();
  const refreshToken = String(config.googleOAuthRefreshToken || "").trim();

  if (!property || !clientId || !clientSecret || !refreshToken) {
    return null;
  }

  const auth = new google.auth.OAuth2(clientId, clientSecret);
  auth.setCredentials({ refresh_token: refreshToken });
  await auth.getAccessToken();
  return auth;
}

async function submitSitemapsViaSearchConsole(
  config: AppConfig,
  logger: RunLogger,
  sitemapUrls: string[],
): Promise<SearchConsoleSitemapSubmitResult[]> {
  const property = String(config.googleSearchConsoleProperty || "").trim();
  const auth = await createSearchConsoleAuth(config).catch(() => null);
  if (!property || !auth) {
    logger.warn("Search Console OAuth is not fully configured. Skipping Search Console sitemap submission.");
    return sitemapUrls.map((sitemapUrl) => ({ sitemapUrl, submitted: false }));
  }

  try {
    const searchConsole = google.webmasters({ version: "v3", auth });

    const results: SearchConsoleSitemapSubmitResult[] = [];
    for (const sitemapUrl of sitemapUrls) {
      await searchConsole.sitemaps.submit({
        siteUrl: property,
        feedpath: sitemapUrl,
      });
      logger.step(`Submitted sitemap to Search Console: ${sitemapUrl}`, { stage: "indexing" });
      results.push({ sitemapUrl, submitted: true });
    }
    return results;
  } catch (error) {
    logger.warn(`Search Console sitemap submission failed: ${error instanceof Error ? error.message : String(error)}`);
    return sitemapUrls.map((sitemapUrl) => ({ sitemapUrl, submitted: false }));
  }
}

async function inspectUrlViaSearchConsole(
  config: AppConfig,
  logger: RunLogger,
  postUrl: string,
): Promise<IndexingInspectionResult | null> {
  const property = String(config.googleSearchConsoleProperty || "").trim();
  const auth = await createSearchConsoleAuth(config).catch(() => null);
  if (!property || !auth) {
    logger.warn("Search Console OAuth is not fully configured. Skipping URL inspection.");
    return null;
  }

  try {
    const accessToken = await auth.getAccessToken();
    const response = await fetch("https://searchconsole.googleapis.com/v1/urlInspection/index:inspect", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken.token || accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        inspectionUrl: postUrl,
        siteUrl: property,
      }),
    });

    if (!response.ok) {
      logger.warn(`Search Console inspection failed with ${response.status} for ${postUrl}.`);
      return null;
    }

    const payload = await response.json();
    const result = payload?.inspectionResult?.indexStatusResult || {};
    return {
      verdict: String(result.verdict || ""),
      coverageState: String(result.coverageState || ""),
      indexingState: String(result.indexingState || ""),
      lastCrawlTime: String(result.lastCrawlTime || ""),
      referringUrls: Array.isArray(result.referringUrls) ? result.referringUrls.slice(0, 10) : [],
      sitemaps: Array.isArray(result.sitemaps) ? result.sitemaps.slice(0, 10) : [],
    };
  } catch (error) {
    logger.warn(`Search Console inspection failed: ${error instanceof Error ? error.message : String(error)}`);
    return null;
  }
}

async function verifyUrlIndexable(
  logger: RunLogger,
  postUrl: string,
): Promise<{ indexable: boolean; issues: string[] }> {
  const issues: string[] = [];

  try {
    const response = await fetch(postUrl, { redirect: "follow" });
    if (!response.ok) {
      issues.push(`Page returned HTTP ${response.status}`);
      return { indexable: false, issues };
    }

    const xRobots = String(response.headers.get("x-robots-tag") || "");
    if (/noindex/i.test(xRobots)) {
      issues.push("X-Robots-Tag contains noindex");
    }

    const html = await response.text();
    if (/<meta[^>]+name=["']robots["'][^>]+content=["'][^"']*noindex/i.test(html)) {
      issues.push("Meta robots contains noindex");
    }
    if (/<meta[^>]+name=["']googlebot["'][^>]+content=["'][^"']*noindex/i.test(html)) {
      issues.push("Meta googlebot contains noindex");
    }
  } catch (error) {
    issues.push(`Could not fetch published URL: ${error instanceof Error ? error.message : String(error)}`);
  }

  if (!issues.length) {
    logger.step(`Indexability check passed for ${postUrl}`, { stage: "indexing" });
  } else {
    logger.warn(`Indexability issues found for ${postUrl}: ${issues.join("; ")}`);
  }

  return { indexable: issues.length === 0, issues };
}

export async function submitIndexingHints(
  config: AppConfig,
  logger: RunLogger,
  postUrl: string,
): Promise<IndexingStatus> {
  const sitemapCandidates = await discoverSitemaps(config, logger);
  const primarySitemaps = sitemapCandidates.slice(0, 2);
  const indexability = await verifyUrlIndexable(logger, postUrl);

  await pingSitemaps(logger, primarySitemaps);
  const submittedSitemaps = await submitSitemapsViaSearchConsole(config, logger, primarySitemaps);
  const submittedSitemapUrls = submittedSitemaps.filter((item) => item.submitted).map((item) => item.sitemapUrl);

  let indexingApiAttempted = false;
  let indexingApiSubmitted = false;

  if (config.enableGoogleIndexing) {
    logger.warn(
      "Google Indexing API is officially intended mainly for JobPosting and livestream VideoObject pages. Proceeding only because ENABLE_GOOGLE_INDEXING=true.",
    );

    if (!config.googleServiceAccountJson) {
      logger.warn("ENABLE_GOOGLE_INDEXING is true but GOOGLE_SERVICE_ACCOUNT_JSON is empty. Skipping Indexing API call.");
    } else {
      indexingApiAttempted = true;
      try {
        const credentials = JSON.parse(config.googleServiceAccountJson);
        const auth = new google.auth.GoogleAuth({
          credentials,
          scopes: ["https://www.googleapis.com/auth/indexing"],
        });
        const client = await auth.getClient();
        await client.request({
          url: "https://indexing.googleapis.com/v3/urlNotifications:publish",
          method: "POST",
          data: {
            url: postUrl,
            type: "URL_UPDATED",
          },
        });
        indexingApiSubmitted = true;
        logger.step(`Submitted Indexing API request for ${postUrl}`, { stage: "indexing" });
      } catch (error) {
        logger.warn(`Google Indexing API request failed: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
  }

  const inspection = await inspectUrlViaSearchConsole(config, logger, postUrl);
  if (inspection) {
    logger.step(
      `Search Console inspection: ${inspection.coverageState || inspection.verdict || "No status returned"}`,
      { stage: "indexing", inspection },
    );
  }

  const status: IndexingStatus = {
    postUrl,
    source: "auto",
    indexable: indexability.indexable,
    indexabilityIssues: indexability.issues,
    sitemapCandidates,
    sitemapPinged: primarySitemaps,
    searchConsoleSitemapsSubmitted: submittedSitemapUrls,
    indexingApiAttempted,
    indexingApiSubmitted,
    autoSubmitSucceeded: submittedSitemapUrls.length > 0 || indexingApiSubmitted,
    inspected: Boolean(inspection),
    inspection,
    requestCompletedAt: nowIso(),
  };
  saveIndexingStatus(config, status);
  return status;
}
