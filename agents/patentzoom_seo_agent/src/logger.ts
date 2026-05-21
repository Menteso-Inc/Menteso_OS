import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { AppConfig } from "./config";
import { LogEvent, WorkflowResult } from "./types";

function nowIso(): string {
  return new Date().toISOString();
}

export class RunLogger {
  private readonly config: AppConfig;
  readonly runId: string;
  readonly outputLogs: string[] = [];
  readonly warnings: string[] = [];
  readonly events: LogEvent[] = [];

  constructor(config: AppConfig, runId: string) {
    this.config = config;
    this.runId = runId;
  }

  private emit(event: LogEvent): void {
    this.events.push(event);
    if (event.type === "step" && event.message) this.outputLogs.push(event.message);
    if (event.type === "warning" && event.message) {
      this.outputLogs.push(event.message);
      this.warnings.push(event.message);
    }
    if (event.type === "error" && event.message) this.outputLogs.push(event.message);
    process.stdout.write(`${JSON.stringify(event)}\n`);
  }

  step(message: string, data?: Record<string, unknown>): void {
    this.emit({ type: "step", message, timestamp: nowIso(), data });
  }

  warn(message: string, data?: Record<string, unknown>): void {
    this.emit({ type: "warning", message, timestamp: nowIso(), data });
  }

  error(message: string, data?: Record<string, unknown>): void {
    this.emit({ type: "error", message, timestamp: nowIso(), data });
  }

  result(result: WorkflowResult): void {
    this.emit({ type: "result", result, timestamp: nowIso() });
  }

  saveDailyRun(result: WorkflowResult): void {
    const day = new Date().toISOString().slice(0, 10);
    const filePath = join(this.config.paths.logsDir, `${day}.json`);
    const prior = existsSync(filePath)
      ? JSON.parse(readFileSync(filePath, "utf-8"))
      : [];
    prior.push({
      runId: this.runId,
      createdAt: nowIso(),
      result,
      events: this.events,
    });
    writeFileSync(filePath, JSON.stringify(prior, null, 2), "utf-8");
  }
}
