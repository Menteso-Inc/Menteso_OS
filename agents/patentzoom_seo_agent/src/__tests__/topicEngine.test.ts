import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { chooseTopic } from "../topicEngine";

const mockLogger = {
  step: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
} as any;

const oauthState = {
  rows: [] as Array<{ keys?: string[]; clicks?: number; impressions?: number; position?: number }>,
  accessToken: "token",
};

vi.mock("googleapis", () => {
  class OAuth2 {
    setCredentials() {}

    async getAccessToken() {
      return oauthState.accessToken;
    }
  }

  return {
    google: {
      auth: { OAuth2 },
      webmasters: () => ({
        searchanalytics: {
          query: vi.fn(async () => ({
            data: {
              rows: oauthState.rows,
            },
          })),
        },
      }),
    },
  };
});

function createConfig() {
  const stateDir = mkdtempSync(join(tmpdir(), "pz-topic-engine-"));
  return {
    serpApiKey: "demo",
    timeZone: "Asia/Kolkata",
    googleSearchConsoleProperty: "sc-domain:patentzoom.us",
    googleOAuthClientId: "client",
    googleOAuthClientSecret: "secret",
    googleOAuthRefreshToken: "refresh",
    paths: {
      topicDiscoveryFile: join(stateDir, "topic-discovery.json"),
    },
  } as any;
}

function createResponse(payload: Record<string, unknown>) {
  return {
    ok: true,
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  } as Response;
}

describe("topicEngine dynamic discovery", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    oauthState.rows = [
      {
        keys: ["office action response deadline", "https://patentzoom.us/office-action-deadlines"],
        clicks: 12,
        impressions: 210,
        position: 7.2,
      },
      {
        keys: ["software patent filing cost", "https://patentzoom.us/software-patent-cost"],
        clicks: 9,
        impressions: 185,
        position: 8.4,
      },
    ];
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      const engine = url.searchParams.get("engine");
      const query = url.searchParams.get("q") || "";

      if (engine === "google_autocomplete") {
        return createResponse({
          suggestions: [
            { value: `${query} checklist` },
            { value: `${query} for startups` },
          ],
        });
      }

      return createResponse({
        related_questions: [{ question: `How does ${query} work?` }],
        related_searches: [{ query: `${query} cost and timing` }],
        organic_results: [
          {
            title: `${query} guide for founders`,
            link: "https://competitor.example.com/founder-guide",
            snippet: `Fresh competitor article about ${query}`,
            date: "3 days ago",
          },
          {
            title: `${query} on PatentZoom`,
            link: "https://patentzoom.us/should-be-excluded",
            snippet: `PatentZoom result should be excluded for ${query}`,
            date: "1 day ago",
          },
        ],
      });
    }) as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("selects a non-calendar topic from mixed live signals and stores evidence", async () => {
    const config = createConfig();
    const result = await chooseTopic({
      config,
      logger: mockLogger,
      ledger: [],
      recentPosts: [],
    });

    expect(result.primaryKeyword.toLowerCase()).not.toContain("monday");
    expect(result.sourceTypes.length).toBeGreaterThan(0);
    expect(result.sourceTypes).toContain("search_console_query");
    expect(result.demandScore).toBeGreaterThan(0);
    expect(result.sourceEvidence.length).toBeGreaterThan(0);

    const snapshot = JSON.parse(readFileSync(config.paths.topicDiscoveryFile, "utf-8"));
    expect(snapshot.mode).toBe("mixed_signal_dynamic");
    expect(snapshot.selectedTopic.primaryKeyword).toBe(result.primaryKeyword);
    expect(snapshot.liveSignals.length).toBeGreaterThan(0);
  });

  it("continues when SerpAPI is degraded by relying on Search Console signals", async () => {
    const config = {
      ...createConfig(),
      serpApiKey: "",
    };

    const result = await chooseTopic({
      config,
      logger: mockLogger,
      ledger: [],
      recentPosts: [],
    });

    expect(
      ["office action response deadline", "software patent filing cost"].includes(result.primaryKeyword.toLowerCase()),
    ).toBe(true);
    const snapshot = JSON.parse(readFileSync(config.paths.topicDiscoveryFile, "utf-8"));
    expect(snapshot.degradedSources).toContain("serpapi_keywords");
    expect(snapshot.degradedSources).toContain("competitor_search");
    expect(snapshot.selectedTopic.sourceTypes).toContain("search_console_query");
  });

  it("treats manual topic override as a hard override on top of dynamic discovery", async () => {
    const config = createConfig();
    const result = await chooseTopic({
      config,
      logger: mockLogger,
      ledger: [],
      recentPosts: [],
      topicOverride: "USPTO office action appeal options for startups",
    });

    expect(result.primaryKeyword).toBe("USPTO office action appeal options for startups");
    expect(result.sourceTypes).toContain("manual_override");
    const snapshot = JSON.parse(readFileSync(config.paths.topicDiscoveryFile, "utf-8"));
    expect(snapshot.selectedTopic.primaryKeyword).toBe("USPTO office action appeal options for startups");
    expect(snapshot.mode).toBe("mixed_signal_dynamic");
  });

  it("uses adjacent expansion before failing when the first-pass shortlist is exhausted", async () => {
    const config = createConfig();
    oauthState.rows = [
      {
        keys: ["provisional patent filing", "https://patentzoom.us/provisional"],
        clicks: 17,
        impressions: 310,
        position: 5.4,
      },
    ];
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      const engine = url.searchParams.get("engine");
      const query = url.searchParams.get("q") || "";
      if (engine === "google_autocomplete") {
        return createResponse({
          suggestions: [{ value: query }],
        });
      }
      return createResponse({
        related_questions: [{ question: query }],
        related_searches: [{ query }],
        organic_results: [],
      });
    }) as typeof fetch;

    const ledger = [
      {
        date: "2026-05-16",
        topicId: "provisional-patent-filing",
        primaryKeyword: "provisional patent filing",
        secondaryKeywords: [],
        slug: "provisional-patent-filing",
        wpPostId: 12,
        wpUrl: "https://patentzoom.us/provisional-patent-filing",
        status: "publish",
        source: "dashboard",
        fingerprint: "provisional::filing",
        intentCluster: "provisional patents",
      },
    ];

    const result = await chooseTopic({
      config,
      logger: mockLogger,
      ledger: ledger as any,
      recentPosts: [],
    });

    expect(result.primaryKeyword.toLowerCase()).not.toBe("provisional patent filing");
    const snapshot = JSON.parse(readFileSync(config.paths.topicDiscoveryFile, "utf-8"));
    expect(snapshot.rejectedTopics.length).toBeGreaterThan(0);
    expect(snapshot.selectedTopic.primaryKeyword.toLowerCase()).not.toBe("provisional patent filing");
  });
});
