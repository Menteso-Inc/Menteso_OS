export type PublishOverride = "draft" | "publish";

export interface WorkflowConfigOverrides {
  workspaceId?: string;
  workspaceName?: string;
  siteName?: string;
  brandTone?: string;
  wpBaseUrl?: string;
  wpUsername?: string;
  wpApplicationPassword?: string;
  autoPublish?: boolean;
  defaultCategory?: string;
  defaultAuthor?: number | null;
  enableFeaturedImage?: boolean;
  enableGoogleIndexing?: boolean;
  googleServiceAccountJson?: string;
  googleSearchConsoleProperty?: string;
  paths?: {
    stateDir?: string;
    runtimeDir?: string;
    generatedPostsFile?: string;
    indexingStatusFile?: string;
    topicDiscoveryFile?: string;
    logsDir?: string;
    imagesDir?: string;
  };
}

export interface WorkflowInput {
  topicOverride?: string;
  publishOverride: PublishOverride;
  enableFeaturedImage: boolean;
  dryRun: boolean;
  bypassDailyLimit?: boolean;
  workspaceId?: string;
  configOverrides?: WorkflowConfigOverrides;
  source: string;
  strategy?: string;
}

export type TopicSignalSource =
  | "search_console_query"
  | "search_console_page"
  | "serp_related_search"
  | "serp_autocomplete"
  | "serp_related_question"
  | "competitor_article"
  | "adjacent_expansion"
  | "evergreen_fallback"
  | "manual_override";

export interface TopicSignal {
  id: string;
  sourceType: TopicSignalSource;
  label: string;
  query: string;
  title?: string;
  url?: string;
  snippet?: string;
  impressions?: number;
  clicks?: number;
  ctr?: number;
  position?: number;
  freshnessDays?: number | null;
  demandScore: number;
  freshnessScore: number;
  commercialRelevanceScore: number;
  brandFitScore: number;
  competitorGapScore: number;
  intentCluster: string;
  evidence: string[];
}

export interface HotTopicCandidate {
  topicId: string;
  pillar: string;
  cluster: string;
  angle: string;
  theme: string;
  primaryKeyword: string;
  secondaryKeywords: string[];
  serpQuestions: string[];
  relatedSearches: string[];
  score: number;
  fingerprint: string;
  intentCluster: string;
  sourceTypes: TopicSignalSource[];
  sourceEvidence: string[];
  demandScore: number;
  freshnessScore: number;
  commercialRelevanceScore: number;
  brandFitScore: number;
  competitorGapScore: number;
}

export interface TopicSelection extends HotTopicCandidate {
  runDate: string;
}

export interface TopicRejectedCandidate {
  topicId: string;
  primaryKeyword: string;
  intentCluster: string;
  score: number;
  reason: string;
  sourceTypes: TopicSignalSource[];
}

export interface TopicSourceHealth {
  source: "search_console" | "serpapi_keywords" | "competitor_search";
  ok: boolean;
  detail: string;
}

export interface TopicDiscoverySnapshot {
  generatedAt: string;
  mode: string;
  selectedTopic: TopicSelection | null;
  shortlist: HotTopicCandidate[];
  rejectedTopics: TopicRejectedCandidate[];
  liveSignals: TopicSignal[];
  sourceHealth: TopicSourceHealth[];
  degradedSources: string[];
}

export interface GeneratedPostRecord {
  date: string;
  topicId: string;
  pillar: string;
  angle: string;
  theme?: string;
  cluster?: string;
  primaryKeyword: string;
  secondaryKeywords: string[];
  slug: string;
  wpPostId: number | null;
  wpUrl: string;
  status: string;
  source: string;
  fingerprint: string;
  sourceTypes?: TopicSignalSource[];
  sourceEvidence?: string[];
  demandScore?: number;
  freshnessScore?: number;
  intentCluster?: string;
}

export interface GeneratedPostsLedger {
  generatedPosts: GeneratedPostRecord[];
}

export interface ArticleOutline {
  title: string;
  slug: string;
  metaTitle: string;
  metaDescription: string;
  excerpt: string;
  primaryKeyword: string;
  secondaryKeywords: string[];
  tags: string[];
  category: string;
  headingPlan: string[];
  faqQuestions: string[];
  cta: string;
  internalLinkTargets: string[];
  imagePrompt: string;
  imageAltText: string;
}

export interface GeneratedArticle {
  title: string;
  slug: string;
  metaTitle: string;
  metaDescription: string;
  excerpt: string;
  primaryKeyword: string;
  secondaryKeywords: string[];
  tags: string[];
  category: string;
  articleHtml: string;
  faqSchemaJsonLd: string;
  imagePrompt: string;
  imageAltText: string;
}

export interface SeoValidationResult {
  article: GeneratedArticle;
  issues: string[];
}

export interface MediaUploadResult {
  id: number;
  sourceUrl: string;
}

export interface IndexingInspectionResult {
  verdict: string;
  coverageState: string;
  indexingState: string;
  lastCrawlTime: string;
  referringUrls: string[];
  sitemaps: string[];
}

export interface IndexingStatus {
  postUrl: string;
  source: "auto" | "manual";
  indexable: boolean;
  indexabilityIssues: string[];
  sitemapCandidates: string[];
  sitemapPinged: string[];
  searchConsoleSitemapsSubmitted: string[];
  indexingApiAttempted: boolean;
  indexingApiSubmitted: boolean;
  autoSubmitSucceeded: boolean;
  inspected: boolean;
  inspection: IndexingInspectionResult | null;
  requestCompletedAt: string;
  error?: string;
}

export interface RecentPost {
  id: number;
  title: string;
  slug: string;
  url: string;
  excerpt?: string;
}

export interface WorkflowResult {
  status: "success" | "failure" | "stopped";
  topic: string;
  primaryKeyword: string;
  postStatus: string;
  wordpressPostId: number | null;
  wordpressUrl: string;
  featuredImageId: number | null;
  outputLogs: string[];
  warnings: string[];
  executionTime: number;
  seoScore?: number;
  title?: string;
  slug?: string;
  article?: GeneratedArticle;
  ledgerEntry?: GeneratedPostRecord;
  indexing?: IndexingStatus | null;
  error?: string;
}

export interface LogEvent {
  type: "step" | "warning" | "error" | "result";
  message?: string;
  result?: WorkflowResult;
  timestamp: string;
  data?: Record<string, unknown>;
}
