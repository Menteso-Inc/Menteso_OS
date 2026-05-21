import { Worker } from "bullmq";

import { loadWorkerSettings } from "./config";
import { runJobHandler } from "./jobs";
import { WorkerLogger } from "./lib/worker-logger";
import { ALL_QUEUE_NAMES, type QueueName } from "./queue-names";
import { connection } from "./queues";

const settings = loadWorkerSettings();

for (const queueName of ALL_QUEUE_NAMES) {
  const worker = new Worker(
    queueName,
    async (job) => {
      const logger = new WorkerLogger(settings, String(job.id));
      logger.step(`Started ${queueName} job.`);
      try {
        const result = await runJobHandler(queueName as QueueName, settings, logger, job.data, String(job.id));
        logger.step(`Finished ${queueName} job successfully.`);
        return {
          job_id: String(job.id),
          job_type: queueName,
          status: "success",
          started_at: job.timestamp,
          finished_at: Date.now(),
          input_ref: job.data?.inputRef || "manual",
          output_ref: result.outputRef || null,
          warnings: logger.warnings,
          errors: [],
          result,
        };
      } catch (error) {
        logger.error(error instanceof Error ? error.message : String(error));
        throw error;
      }
    },
    {
      connection,
      concurrency: 1,
    },
  );

  worker.on("completed", (job) => {
    console.log(`[worker:${queueName}] completed job ${job.id}`);
  });

  worker.on("failed", (job, error) => {
    console.error(`[worker:${queueName}] failed job ${job?.id}: ${error.message}`);
  });
}

console.log("PatentZoom SEO worker is running.");
