export type PublishOverride = "draft" | "publish";

export interface WorkflowInput {
  topicOverride?: string;
  publishOverride: PublishOverride;
  enableFeaturedImage: boolean;
  dryRun: boolean;
  source: string;
  strategy?: string;
}

export interface EditorialSlot {
  weekday: number;
  weekdayName: string;
  pillar: string;
  cluster: string;
  seedKeywords: string[];
  weekAngles: Record<number, string[]>;
}

export interface TopicCandidate {
  topicId: string;
  pillar: string;
  cluster: string;
  angle: string;
  primaryKeyword: string;
  secondaryKeywords: string[];
  serpQuestions: string[];
  relatedSearches: string[];
  score: number;
  fingerprint: string;
}

export interface TopicSelection extends TopicCandidate {
  runDate: string;
}

export interface GeneratedPostRecord {
  date: string;
  topicId: string;
  pillar: string;
  angle: string;
  primaryKeyword: string;
  secondaryKeywords: string[];
  slug: string;
  wpPostId: number | null;
  wpUrl: string;
  status: string;
  source: string;
  fingerprint: string;
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
