import type { WorkerSettings } from "../config";
import type { WorkerLogger } from "../lib/worker-logger";
import type { QueueName } from "../queue-names";
import { runArticleGenerationJob } from "./article-generation";
import { runContentRefreshJob } from "./content-refresh";
import { runIndexingJob } from "./indexing";
import { runKeywordResearchJob } from "./keyword-research";
import { runPublishingJob } from "./publishing";
import { runReportingJob } from "./reporting";

export async function runJobHandler(
  queueName: QueueName,
  settings: WorkerSettings,
  logger: WorkerLogger,
  data: unknown,
  jobId: string,
) {
  switch (queueName) {
    case "keyword-research":
      return runKeywordResearchJob(settings, logger, data as never, jobId);
    case "article-generation":
      return runArticleGenerationJob(settings, logger, data as never, jobId);
    case "publishing":
      return runPublishingJob(settings, logger, data as never, jobId);
    case "indexing":
      return runIndexingJob(settings, logger, data as never, jobId);
    case "content-refresh":
      return runContentRefreshJob(settings, logger, data as never, jobId);
    case "reporting":
      return runReportingJob(settings, logger, data, jobId);
    default:
      throw new Error(`Unsupported queue: ${queueName}`);
  }
}
