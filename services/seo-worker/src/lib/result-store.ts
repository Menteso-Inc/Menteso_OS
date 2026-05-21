import { writeFileSync } from "node:fs";
import { join } from "node:path";

import type { WorkerSettings } from "../config";

export function saveJobResult(settings: WorkerSettings, jobId: string, result: unknown) {
  const target = join(settings.resultsDir, `${jobId}.json`);
  writeFileSync(target, JSON.stringify(result, null, 2), "utf-8");
  return target;
}
