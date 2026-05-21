import { z } from "zod";

export const ArticleStatusSchema = z.enum([
  "Draft",
  "Reviewing",
  "Approved",
  "Scheduled",
  "Published",
  "Indexed",
]);

export const KeywordStatusSchema = z.enum([
  "discovered",
  "clustered",
  "selected",
  "writing",
  "published",
  "archived",
]);

export const AutomationStateSchema = z.enum([
  "active",
  "paused",
  "error",
]);

export const PublishingStateSchema = z.enum([
  "queued",
  "processing",
  "published",
  "failed",
]);

export const IndexingStateSchema = z.enum([
  "pending",
  "requested",
  "indexed",
  "error",
]);

export const KpiCardSchema = z.object({
  label: z.string(),
  value: z.union([z.number(), z.string()]),
  delta: z.string().optional(),
  tone: z.enum(["default", "success", "warning", "danger"]).default("default"),
  helpText: z.string().optional(),
});

export const ActivityItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  message: z.string(),
  actor: z.string(),
  status: z.string(),
  createdAt: z.string(),
});

export const KeywordRecordSchema = z.object({
  id: z.string(),
  keyword: z.string(),
  cluster: z.string(),
  intent: z.string(),
  volume: z.number(),
  difficulty: z.number(),
  cpc: z.number(),
  trend: z.string(),
  competitionTier: z.enum(["low", "medium", "high"]),
  status: KeywordStatusSchema,
});

export const ArticleRecordSchema = z.object({
  id: z.string(),
  title: z.string(),
  primaryKeyword: z.string(),
  status: ArticleStatusSchema,
  seoScore: z.number(),
  readabilityScore: z.number(),
  updatedAt: z.string(),
  authoringMode: z.string(),
});

export const PublishingLogSchema = z.object({
  id: z.string(),
  articleTitle: z.string(),
  destination: z.string(),
  status: PublishingStateSchema,
  createdAt: z.string(),
  detail: z.string(),
});

export const AutomationRuleSchema = z.object({
  id: z.string(),
  name: z.string(),
  schedule: z.string(),
  state: AutomationStateSchema,
  lastRunAt: z.string().nullable(),
  nextRunAt: z.string().nullable(),
  description: z.string(),
});

export const DashboardSummarySchema = z.object({
  kpis: z.array(KpiCardSchema),
  activityFeed: z.array(ActivityItemSchema),
  publishingLogs: z.array(PublishingLogSchema),
  automationRules: z.array(AutomationRuleSchema),
  seoScore: z.number(),
  indexedPages: z.number(),
  organicTraffic: z.number(),
});

export const JobRequestSchema = z.object({
  jobType: z.enum([
    "keyword-research",
    "article-generation",
    "publishing",
    "indexing",
    "content-refresh",
    "reporting",
  ]),
  inputRef: z.string(),
  payload: z.record(z.any()),
});

export type ArticleStatus = z.infer<typeof ArticleStatusSchema>;
export type KeywordStatus = z.infer<typeof KeywordStatusSchema>;
export type AutomationState = z.infer<typeof AutomationStateSchema>;
export type PublishingState = z.infer<typeof PublishingStateSchema>;
export type IndexingState = z.infer<typeof IndexingStateSchema>;
export type KpiCard = z.infer<typeof KpiCardSchema>;
export type ActivityItem = z.infer<typeof ActivityItemSchema>;
export type KeywordRecord = z.infer<typeof KeywordRecordSchema>;
export type ArticleRecord = z.infer<typeof ArticleRecordSchema>;
export type PublishingLog = z.infer<typeof PublishingLogSchema>;
export type AutomationRule = z.infer<typeof AutomationRuleSchema>;
export type DashboardSummary = z.infer<typeof DashboardSummarySchema>;
export type JobRequest = z.infer<typeof JobRequestSchema>;
