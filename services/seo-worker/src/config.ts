import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import dotenv from "dotenv";
import { z } from "zod";

const workerRoot = resolve(__dirname, "..");
const projectRoot = resolve(workerRoot, "..", "..");
dotenv.config({ path: resolve(projectRoot, ".env") });

const schema = z.object({
  SEO_REDIS_URL: z.string().default("redis://127.0.0.1:6379/0"),
  SEO_RUNTIME_DIR: z.string().optional(),
  SEO_CONTROL_API_BASE_URL: z.string().default("http://127.0.0.1:8100"),
});

export type WorkerSettings = {
  projectRoot: string;
  workerRoot: string;
  redisUrl: string;
  controlApiBaseUrl: string;
  runtimeDir: string;
  logsDir: string;
  resultsDir: string;
  seoAgentRoot: string;
  seoAgentDist: string;
};

export function loadWorkerSettings(): WorkerSettings {
  const env = schema.parse(process.env);
  const runtimeDir = env.SEO_RUNTIME_DIR
    ? resolve(env.SEO_RUNTIME_DIR)
    : resolve(workerRoot, "runtime");
  const logsDir = resolve(runtimeDir, "logs");
  const resultsDir = resolve(runtimeDir, "results");
  const seoAgentRoot = resolve(projectRoot, "agents", "patentzoom_seo_agent");
  const seoAgentDist = resolve(seoAgentRoot, "dist");

  [runtimeDir, logsDir, resultsDir].forEach((path) => mkdirSync(path, { recursive: true }));

  return {
    projectRoot,
    workerRoot,
    redisUrl: env.SEO_REDIS_URL,
    controlApiBaseUrl: env.SEO_CONTROL_API_BASE_URL,
    runtimeDir,
    logsDir,
    resultsDir,
    seoAgentRoot,
    seoAgentDist,
  };
}
