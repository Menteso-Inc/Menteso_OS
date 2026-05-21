import {
  type ArticleRecord,
  type AutomationRule,
  type DashboardSummary,
  type KeywordRecord,
  DashboardSummarySchema,
  KeywordRecordSchema,
  ArticleRecordSchema,
  AutomationRuleSchema,
  PublishingLogSchema,
} from "@patentzoom/seo-types";
import { articleRows, automationRules, dashboardSummary, keywordRows, publishingLogs } from "./mock-data";

const API_BASE = process.env.NEXT_PUBLIC_SEO_API_BASE_URL || "http://127.0.0.1:8100";

async function fetchJson<T>(path: string, fallback: T, validator?: (value: unknown) => T): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Failed: ${response.status}`);
    const json = await response.json();
    return validator ? validator(json) : (json as T);
  } catch {
    return fallback;
  }
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  return fetchJson("/api/dashboard/summary", dashboardSummary, (value) => DashboardSummarySchema.parse(value));
}

export async function getKeywords(): Promise<KeywordRecord[]> {
  return fetchJson("/api/keywords", keywordRows, (value) => KeywordRecordSchema.array().parse(value));
}

export async function getArticles(): Promise<ArticleRecord[]> {
  return fetchJson("/api/articles", articleRows, (value) => ArticleRecordSchema.array().parse(value));
}

export async function getPublishingLogs() {
  return fetchJson("/api/publishing/logs", publishingLogs, (value) => PublishingLogSchema.array().parse(value));
}

export async function getAutomationRules(): Promise<AutomationRule[]> {
  return fetchJson("/api/automations", automationRules, (value) => AutomationRuleSchema.array().parse(value));
}
