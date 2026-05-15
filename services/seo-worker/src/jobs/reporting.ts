import type { WorkerSettings } from "../config";
import { saveJobResult } from "../lib/result-store";
import type { WorkerLogger } from "../lib/worker-logger";

export async function runReportingJob(settings: WorkerSettings, logger: WorkerLogger, _input: unknown, jobId: string) {
  logger.step("Prepared weekly reporting placeholder.");
  const result = {
    status: "success",
    jobType: "reporting",
    summary: "Reporting pipeline placeholder ready. Connect dashboard analytics rollups and email/report delivery in the next phase.",
  };
  const resultPath = saveJobResult(settings, jobId, result);
  return { ...result, outputRef: resultPath };
}
