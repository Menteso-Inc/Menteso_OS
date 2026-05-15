import type { WorkerSettings } from "../config";
import { saveJobResult } from "../lib/result-store";
import type { WorkerLogger } from "../lib/worker-logger";

type JobInput = {
  payload?: {
    articleId?: string;
    reason?: string;
  };
};

export async function runContentRefreshJob(settings: WorkerSettings, logger: WorkerLogger, input: JobInput, jobId: string) {
  logger.step("Queued content refresh analysis for an existing article.");
  const result = {
    status: "success",
    jobType: "content-refresh",
    articleId: input.payload?.articleId || null,
    recommendation: input.payload?.reason || "Refresh queue placeholder created. Connect article storage and Search Console deltas in the next phase.",
  };
  const resultPath = saveJobResult(settings, jobId, result);
  return { ...result, outputRef: resultPath };
}
