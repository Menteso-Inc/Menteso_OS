import type { WorkerSettings } from "../config";
import { loadSeoAgentRuntime } from "../lib/agent-runtime";
import { saveJobResult } from "../lib/result-store";
import type { WorkerLogger } from "../lib/worker-logger";

type JobInput = {
  inputRef?: string;
  payload?: {
    topicOverride?: string;
    keyword?: string;
    dryRun?: boolean;
    publishOverride?: "draft" | "publish";
  };
};

export async function runArticleGenerationJob(settings: WorkerSettings, logger: WorkerLogger, input: JobInput, jobId: string) {
  const runtime = loadSeoAgentRuntime(settings);
  const config = runtime.config.loadConfig();
  const wpClient = new runtime.wordpressClient.WordPressClient(config, logger);
  const ledger = runtime.topicEngine.loadGeneratedPosts(config.paths.generatedPostsFile);
  const recentPosts = await wpClient.fetchRecentPosts(20).catch(() => []);

  const topic = await runtime.topicEngine.chooseTopic({
    config,
    logger,
    ledger: ledger.generatedPosts,
    recentPosts,
    topicOverride: input.payload?.topicOverride || input.payload?.keyword,
  });
  const draftedArticle = await runtime.openaiContent.generateArticle(config, logger, topic);
  const validation = runtime.seoOptimizer.validateAndOptimizeArticle(draftedArticle);
  validation.issues.forEach((issue: string) => logger.warn(`SEO optimizer: ${issue}`));
  const linkedArticle = runtime.internalLinks.insertInternalLinks(validation.article, recentPosts);

  const result = {
    status: "success",
    jobType: "article-generation",
    topic,
    article: linkedArticle,
    warnings: logger.warnings,
    outputLogs: logger.outputLogs,
    dryRun: input.payload?.dryRun ?? true,
    publishOverride: input.payload?.publishOverride || "draft",
  };
  const resultPath = saveJobResult(settings, jobId, result);
  logger.step(`Article draft generated for "${topic.primaryKeyword}".`);
  return { ...result, outputRef: resultPath };
}
