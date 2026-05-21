import type { WorkerSettings } from "../config";
import { loadSeoAgentRuntime } from "../lib/agent-runtime";
import { saveJobResult } from "../lib/result-store";
import type { WorkerLogger } from "../lib/worker-logger";

type JobInput = {
  payload?: {
    url?: string;
  };
};

export async function runIndexingJob(settings: WorkerSettings, logger: WorkerLogger, input: JobInput, jobId: string) {
  const runtime = loadSeoAgentRuntime(settings);
  const config = runtime.config.loadConfig();
  const url = input.payload?.url;
  if (!url) {
    throw new Error("Indexing job requires payload.url");
  }
  await runtime.indexing.submitIndexingHints(config, logger, url);
  const result = {
    status: "success",
    jobType: "indexing",
    url,
    warnings: logger.warnings,
    outputLogs: logger.outputLogs,
  };
  const resultPath = saveJobResult(settings, jobId, result);
  return { ...result, outputRef: resultPath };
}
