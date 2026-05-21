import { z } from "zod";

import { createQueue } from "./queues";
import { ALL_QUEUE_NAMES, type QueueName } from "./queue-names";

const schema = z.object({
  jobType: z.enum(ALL_QUEUE_NAMES as [string, ...string[]]),
  inputRef: z.string().default("manual"),
  payload: z.string().default("{}"),
  jobId: z.string().optional(),
});

function parseArg(flag: string) {
  const index = process.argv.indexOf(flag);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

async function main() {
  const parsed = schema.parse({
    jobType: parseArg("--job-type"),
    inputRef: parseArg("--input-ref"),
    payload: parseArg("--payload"),
    jobId: parseArg("--job-id"),
  });
  const queue = createQueue(parsed.jobType as QueueName);
  const payload = JSON.parse(parsed.payload || "{}");
  const job = await queue.add(
    parsed.jobType,
    {
      inputRef: parsed.inputRef,
      payload,
    },
    {
      jobId: parsed.jobId,
      removeOnComplete: 50,
      removeOnFail: 100,
      attempts: 3,
      backoff: { type: "exponential", delay: 2000 },
    },
  );
  process.stdout.write(
    JSON.stringify({
      status: "queued",
      queue: parsed.jobType,
      jobId: job.id,
    }),
  );
}

void main().catch((error) => {
  console.error(error);
  process.exit(1);
});
