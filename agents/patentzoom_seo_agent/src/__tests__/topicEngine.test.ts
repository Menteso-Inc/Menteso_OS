import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildTopicCandidates, chooseTopic, resolveEditorialSlot } from "../topicEngine";

const mockLogger = {
  step: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
} as any;

describe("topicEngine", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("google_autocomplete")) {
        return {
          ok: true,
          json: async () => ({
            suggestions: [{ value: "ai patent filing strategy for startups" }],
          }),
        } as Response;
      }

      return {
        ok: true,
        json: async () => ({
          related_questions: [{ question: "How do startups protect AI inventions?" }],
          related_searches: [{ query: "software patent mistakes to avoid" }],
        }),
      } as Response;
    }) as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("resolves the weekly editorial calendar slot and week of month", () => {
    const resolved = resolveEditorialSlot(new Date("2026-05-04T02:00:00Z"), "Asia/Kolkata");
    expect(resolved.slot.pillar).toBe("Patent Filing Strategy");
    expect(resolved.weekOfMonth).toBe(1);
  });

  it("builds ranked candidates from research signals", () => {
    const slot = resolveEditorialSlot(new Date("2026-05-08T02:00:00Z"), "Asia/Kolkata").slot;
    const candidates = buildTopicCandidates(slot, 2, {
      relatedQuestions: ["How do startups protect AI inventions?"],
      relatedSearches: ["software patent mistakes to avoid"],
      suggestions: ["ai patent filing strategy for startups"],
    });
    expect(candidates[0].primaryKeyword.length).toBeGreaterThan(5);
    expect(candidates[0].fingerprint).toContain("::");
  });

  it("chooses a non-duplicate topic with SerpAPI research", async () => {
    const result = await chooseTopic({
      config: {
        serpApiKey: "demo",
        timeZone: "Asia/Kolkata",
      } as any,
      logger: mockLogger,
      ledger: [],
      recentPosts: [],
      topicOverride: "AI patent filing strategy",
    });

    expect(result.primaryKeyword.toLowerCase()).toContain("ai patent");
    expect(result.topicId.length).toBeGreaterThan(5);
  });
});

