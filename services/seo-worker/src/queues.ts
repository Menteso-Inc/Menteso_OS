import { Queue } from "bullmq";
import IORedis from "ioredis";

import { loadWorkerSettings } from "./config";
import { ALL_QUEUE_NAMES, type QueueName } from "./queue-names";

const settings = loadWorkerSettings();

export const connection = new IORedis(settings.redisUrl, {
  maxRetriesPerRequest: null,
  enableReadyCheck: false,
});

export function createQueue(name: QueueName) {
  return new Queue(name, { connection });
}

export const queues = Object.fromEntries(
  ALL_QUEUE_NAMES.map((name) => [name, createQueue(name)]),
) as Record<QueueName, Queue>;
