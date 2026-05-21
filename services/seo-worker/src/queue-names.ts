export const QUEUE_NAMES = {
  keywordResearch: "keyword-research",
  articleGeneration: "article-generation",
  publishing: "publishing",
  indexing: "indexing",
  contentRefresh: "content-refresh",
  reporting: "reporting",
} as const;

export type QueueName = (typeof QUEUE_NAMES)[keyof typeof QUEUE_NAMES];

export const ALL_QUEUE_NAMES: QueueName[] = Object.values(QUEUE_NAMES);
