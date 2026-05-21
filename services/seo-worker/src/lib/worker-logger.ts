import { appendFileSync } from "node:fs";
import { join } from "node:path";

import type { WorkerSettings } from "../config";

type LogLevel = "step" | "warning" | "error";

export class WorkerLogger {
  readonly outputLogs: string[] = [];
  readonly warnings: string[] = [];

  constructor(
    private readonly settings: WorkerSettings,
    private readonly jobId: string,
  ) {}

  private write(level: LogLevel, message: string, data?: unknown) {
    const line = JSON.stringify({
      timestamp: new Date().toISOString(),
      jobId: this.jobId,
      level,
      message,
      data,
    });
    appendFileSync(join(this.settings.logsDir, `${new Date().toISOString().slice(0, 10)}.jsonl`), `${line}\n`, "utf-8");
    this.outputLogs.push(message);
    if (level === "warning") this.warnings.push(message);
    const printer = level === "error" ? console.error : level === "warning" ? console.warn : console.log;
    printer(`[${this.jobId}] ${message}`);
  }

  step(message: string, data?: unknown) {
    this.write("step", message, data);
  }

  warn(message: string, data?: unknown) {
    this.write("warning", message, data);
  }

  error(message: string, data?: unknown) {
    this.write("error", message, data);
  }
}
