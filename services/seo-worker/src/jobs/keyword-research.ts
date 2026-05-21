import type { WorkerSettings } from "../config";
import { loadSeoAgentRuntime } from "../lib/agent-runtime";
import { saveJobResult } from "../lib/result-store";
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
  const topicOverride = input.payload?.topicOverride || input.payload?.query;
  const chosenTopic = await runtime.topicEngine.chooseTopic({
    config,
    logger,
    ledger: ledger.generatedPosts,
    recentPosts,
    topicOverride,
  });
  const discoverySnapshot = runtime.topicEngine.loadTopicDiscoverySnapshot
    ? runtime.topicEngine.loadTopicDiscoverySnapshot(config.paths.topicDiscoveryFile)
    : null;
  const shortlist = Array.isArray(discoverySnapshot?.shortlist) && discoverySnapshot.shortlist.length
    ? discoverySnapshot.shortlist
    : [chosenTopic];
  const candidates = shortlist
    .slice(0, input.payload?.limit || 8)
    .map((candidate: {
      primaryKeyword: string;
      theme: string;
      intentCluster: string;
      angle: string;
      secondaryKeywords: string[];
      score: number;
      demandScore: number;
      freshnessScore: number;
      sourceTypes: string[];
      sourceEvidence: string[];
    }) => ({
      keyword: candidate.primaryKeyword,
      theme: candidate.theme,
      cluster: candidate.intentCluster,
      angle: candidate.angle,
      secondaryKeywords: candidate.secondaryKeywords,
      intent: candidate.intentCluster,
      volume: Math.max(120, Math.round(candidate.demandScore * 90)),
      difficulty: Math.max(8, 48 - Math.round(candidate.score)),
      cpc: Number((1.5 + candidate.score / 12).toFixed(2)),
      trend: candidate.freshnessScore >= 14 ? "Rising" : "Stable",
      competitionTier: candidate.score >= 70 ? "low" : candidate.score >= 55 ? "medium" : "high",
      sourceMix: candidate.sourceTypes,
      evidence: candidate.sourceEvidence,
    }));

  const result = {
    status: "success",
    jobType: "keyword-research",
    runDate: chosenTopic.runDate,
    mode: "mixed_signal_dynamic",
    selectedTopic: {
      keyword: chosenTopic.primaryKeyword,
      theme: chosenTopic.theme,
      cluster: chosenTopic.intentCluster,
      sourceMix: chosenTopic.sourceTypes,
      demandScore: chosenTopic.demandScore,
      freshnessScore: chosenTopic.freshnessScore,
    },
    sourceHealth: discoverySnapshot?.sourceHealth || [],
    degradedSources: discoverySnapshot?.degradedSources || [],
    candidates,
  };
  const resultPath = saveJobResult(settings, jobId, result);
  logger.step(`Keyword research completed with ${candidates.length} candidates.`);
  return { ...result, outputRef: resultPath };
}
