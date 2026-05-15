import type { WorkerSettings } from "../config";
import { loadSeoAgentRuntime } from "../lib/agent-runtime";
import { saveJobResult } from "../lib/result-store";
import { runSerpApiResearch } from "../lib/serpapi";
import type { WorkerLogger } from "../lib/worker-logger";

type JobInput = {
  inputRef?: string;
  payload?: {
    query?: string;
    topicOverride?: string;
    limit?: number;
  };
};

export async function runKeywordResearchJob(settings: WorkerSettings, logger: WorkerLogger, input: JobInput, jobId: string) {
  const runtime = loadSeoAgentRuntime(settings);
  const config = runtime.config.loadConfig();
  const wpClient = new runtime.wordpressClient.WordPressClient(config, logger);
  const recentPosts = await wpClient.fetchRecentPosts(20).catch(() => []);
  const ledger = runtime.topicEngine.loadGeneratedPosts(config.paths.generatedPostsFile);
  const { slot, weekOfMonth, isoDate } = runtime.topicEngine.resolveEditorialSlot(new Date(), config.timeZone);
  const query = input.payload?.query || input.payload?.topicOverride || slot.seedKeywords[0];
  const research = await runSerpApiResearch(config.serpApiKey, query, logger);
  const candidates = runtime.topicEngine
    .buildTopicCandidates(slot, weekOfMonth, research)
    .filter((candidate: { fingerprint: string; primaryKeyword: string }) => {
      if (runtime.textUtils.isLedgerDuplicate(candidate.fingerprint, candidate.primaryKeyword, ledger.generatedPosts, new Date())) {
        return false;
      }
      return !recentPosts.some((post: { slug: string; title: string }) => {
        const sameSlug = post.slug === runtime.textUtils.slugify(candidate.primaryKeyword);
        const sameTitle = runtime.textUtils.normalizeKeyword(post.title) === runtime.textUtils.normalizeKeyword(candidate.primaryKeyword);
        return sameSlug || sameTitle;
      });
    })
    .slice(0, input.payload?.limit || 8)
    .map((candidate: { primaryKeyword: string; pillar: string; cluster: string; angle: string; secondaryKeywords: string[]; score: number; relatedSearches: string[]; serpQuestions: string[] }) => ({
      keyword: candidate.primaryKeyword,
      pillar: candidate.pillar,
      cluster: candidate.cluster,
      angle: candidate.angle,
      secondaryKeywords: candidate.secondaryKeywords,
      intent: "High intent / informational",
      volume: Math.max(120, candidate.score * 90),
      difficulty: Math.max(8, 42 - candidate.score),
      cpc: Number((1.5 + candidate.score / 10).toFixed(2)),
      trend: candidate.relatedSearches.length > 4 ? "Rising" : "Stable",
      competitionTier: candidate.score >= 14 ? "low" : candidate.score >= 10 ? "medium" : "high",
      relatedQuestions: candidate.serpQuestions,
    }));

  const result = {
    status: "success",
    jobType: "keyword-research",
    runDate: isoDate,
    editorialSlot: {
      pillar: slot.pillar,
      cluster: slot.cluster,
      weekdayName: slot.weekdayName,
      weekOfMonth,
    },
    candidates,
  };
  const resultPath = saveJobResult(settings, jobId, result);
  logger.step(`Keyword research completed with ${candidates.length} candidates.`);
  return { ...result, outputRef: resultPath };
}
