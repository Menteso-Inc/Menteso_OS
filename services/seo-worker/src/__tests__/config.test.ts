import { describe, expect, it } from "vitest";

import { loadWorkerSettings } from "../config";

describe("worker config", () => {
  it("resolves stable runtime directories", () => {
    const settings = loadWorkerSettings();
    expect(settings.redisUrl).toContain("redis://");
    expect(settings.resultsDir).toContain("runtime");
    expect(settings.seoAgentRoot).toContain("patentzoom_seo_agent");
  });
});
