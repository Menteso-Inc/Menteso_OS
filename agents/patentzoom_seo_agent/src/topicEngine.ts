import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { google } from "googleapis";
import { AppConfig } from "./config";
import { RunLogger } from "./logger";
import { withRetry } from "./retry";
import {
  GeneratedPostRecord,
  GeneratedPostsLedger,
  HotTopicCandidate,
  RecentPost,
  TopicDiscoverySnapshot,
  TopicRejectedCandidate,
  TopicSelection,
  TopicSignal,
  TopicSignalSource,
  TopicSourceHealth,
} from "./types";
import {
  findModerateDuplicateReason,
  inferIntentCluster,
  intentClusterLabel,
  jaccardSimilarity,
  normalizeKeyword,
  slugify,
  titleCaseWords,
  topicFingerprint,
  uniqueStrings,
} from "./textUtils";

const DISCOVERY_MODE = "mixed_signal_dynamic";
const DISCOVERY_SEED_QUERIES = [
  "patent filing strategy startups",
  "provisional patent filing",
  "software patent",
  "AI patent",
  "office action response",
  "patent filing cost",
  "PCT filing strategy",
  "startup IP protection",
  "design patent vs utility patent",
];

const ADJACENT_EXPANSION_MODIFIERS = [
  "checklist",
  "mistakes to avoid",
  "cost and timing",
  "strategy guide",
  "examples",
  "response process",
];

const EVERGREEN_FALLBACK_TOPICS = [
  {
    primaryKeyword: "provisional patent filing checklist for startups",
    theme: "Provisional Patent Strategy",
    intentCluster: "provisional patents",
    angle: "evergreen checklist",
    secondaryKeywords: ["provisional patent checklist", "when to file provisional patent", "startup patent filing steps"],
  },
  {
    primaryKeyword: "software patent strategy for SaaS startups",
    theme: "Software and AI Patent Protection",
    intentCluster: "software and ai patents",
    angle: "evergreen strategy guide",
    secondaryKeywords: ["software patent filing", "SaaS patent protection", "software patent claims"],
  },
  {
    primaryKeyword: "office action response strategy for founders",
    theme: "Office Action and Response Strategy",
    intentCluster: "office actions",
    angle: "evergreen response strategy",
    secondaryKeywords: ["office action response", "patent rejection response", "USPTO office action"],
  },
  {
    primaryKeyword: "patent filing cost guide for startups",
    theme: "Patent Cost and Filing Budget",
    intentCluster: "patent costs",
    angle: "evergreen cost guide",
    secondaryKeywords: ["patent filing cost", "patent attorney fees", "startup patent budget"],
  },
  {
    primaryKeyword: "PCT filing strategy for global patent protection",
    theme: "PCT and International Filing",
    intentCluster: "pct filing",
    angle: "evergreen international strategy",
    secondaryKeywords: ["PCT filing guide", "international patent filing", "global patent timeline"],
  },
  {
    primaryKeyword: "startup IP protection strategy before fundraising",
    theme: "Startup IP Protection",
    intentCluster: "startup ip protection",
    angle: "evergreen fundraising strategy",
    secondaryKeywords: ["startup IP strategy", "protecting IP before fundraising", "investor ready patent strategy"],
  },
  {
    primaryKeyword: "design patent vs utility patent for product founders",
    theme: "Patent Comparisons and Filing Choices",
    intentCluster: "patent comparisons",
    angle: "evergreen comparison",
    secondaryKeywords: ["design patent vs utility patent", "product patent strategy", "founder patent decisions"],
  },
  {
    primaryKeyword: "USPTO patent process timeline for first-time inventors",
    theme: "USPTO Filing Process",
    intentCluster: "uspto process",
    angle: "evergreen timeline guide",
    secondaryKeywords: ["USPTO timeline", "patent process steps", "first time inventor patent guide"],
  },
];

const DRAWING_DISCOVERY_SEED_QUERIES = [
  "utility patent drawings",
  "design patent drawings",
  "USPTO drawing requirements",
  "patent illustration services",
  "patent drawing rules",
  "reference numerals patent drawings",
  "patent drawing corrections",
  "patent drawing cost",
];

const DRAWING_EVERGREEN_FALLBACK_TOPICS = [
  {
    primaryKeyword: "utility patent drawings requirements guide",
    theme: "Utility Patent Drawings",
    intentCluster: "utility patent drawings",
    angle: "evergreen requirements guide",
    secondaryKeywords: ["utility patent drawing requirements", "patent figure requirements", "utility patent drawing checklist"],
  },
  {
    primaryKeyword: "design patent drawings rules for USPTO filings",
    theme: "Design Patent Drawings",
    intentCluster: "design patent drawings",
    angle: "evergreen USPTO rules guide",
    secondaryKeywords: ["design patent drawing rules", "ornamental drawing requirements", "design patent figure examples"],
  },
  {
    primaryKeyword: "USPTO patent drawing requirements checklist",
    theme: "Patent Drawing Rules",
    intentCluster: "patent drawing rules",
    angle: "evergreen compliance checklist",
    secondaryKeywords: ["USPTO drawing requirements", "patent drawing margins", "reference numerals patent drawings"],
  },
  {
    primaryKeyword: "patent drawing corrections after USPTO objections",
    theme: "Patent Drawing Corrections",
    intentCluster: "patent drawing rules",
    angle: "evergreen objection response guide",
    secondaryKeywords: ["patent drawing objections", "correcting patent drawings", "USPTO drawing objection response"],
  },
  {
    primaryKeyword: "patent drawing cost guide for inventors",
    theme: "Patent Drawings Cost",
    intentCluster: "patent drawing costs",
    angle: "evergreen pricing guide",
    secondaryKeywords: ["patent drawing fees", "utility patent drawing cost", "design patent drawing pricing"],
  },
  {
    primaryKeyword: "how patent illustrators prepare filing-ready figures",
    theme: "Patent Illustrations",
    intentCluster: "patent illustrations",
    angle: "evergreen process guide",
    secondaryKeywords: ["patent illustrator workflow", "patent illustration process", "filing ready patent figures"],
  },
];

const IP_DOCKETERS_DISCOVERY_SEED_QUERIES = [
  "ip docketing services",
  "ip docketing systems",
  "patent prosecution workflow",
  "ip prosecution paralegal services",
  "missed deadlines ip docketing",
  "ip docketing software integrations",
  "anaqua docketing support",
  "patricia docketing workflow",
];

const IP_DOCKETERS_EVERGREEN_FALLBACK_TOPICS = [
  {
    primaryKeyword: "what is ip docketing for law firms",
    theme: "IP Docketing Services",
    intentCluster: "ip docketing",
    angle: "evergreen fundamentals guide",
    secondaryKeywords: ["ip docketing services", "law firm docketing workflow", "deadline management for patents"],
  },
  {
    primaryKeyword: "how ip docketing prevents missed patent deadlines",
    theme: "Missed Deadline Prevention",
    intentCluster: "ip docketing",
    angle: "evergreen risk-reduction guide",
    secondaryKeywords: ["missed patent deadlines", "patent deadline tracking", "ip docketing risk management"],
  },
  {
    primaryKeyword: "patent prosecution workflow support for growing law firms",
    theme: "IP Prosecution Support",
    intentCluster: "ip prosecution support",
    angle: "evergreen workflow guide",
    secondaryKeywords: ["patent prosecution workflow", "prosecution support services", "law firm patent workflow"],
  },
  {
    primaryKeyword: "ip paralegal services for docketing and prosecution teams",
    theme: "IP Paralegal Services",
    intentCluster: "ip paralegal services",
    angle: "evergreen support-services guide",
    secondaryKeywords: ["ip paralegal services", "docketing paralegal support", "patent prosecution paralegal"],
  },
  {
    primaryKeyword: "best ip docketing integrations for law firm operations",
    theme: "Docketing System Integrations",
    intentCluster: "docketing integrations",
    angle: "evergreen integrations guide",
    secondaryKeywords: ["anaqua support", "patricia integration", "ip docketing systems"],
  },
  {
    primaryKeyword: "how outsourced ip docketing supports global patent portfolios",
    theme: "Global Portfolio Docketing",
    intentCluster: "ip docketing",
    angle: "evergreen portfolio management guide",
    secondaryKeywords: ["global ip portfolio management", "outsourced ip docketing", "international patent deadlines"],
  },
];

const OUT_OF_SCOPE_PATTERNS = [
  /\b(salary|salaries|pay scale|hourly pay|compensation)\b/,
  /\b(job|jobs|career|careers|resume|cv|cover letter|internship|internships)\b/,
  /\b(hiring|vacancy|vacancies|recruitment|recruiter|interview questions)\b/,
];

function isOutOfScopeTopic(value: string): boolean {
  const raw = String(value || "").toLowerCase();
  const normalized = normalizeKeyword(value);
  if (OUT_OF_SCOPE_PATTERNS.some((pattern) => pattern.test(raw) || pattern.test(normalized))) return true;

  const attorneyStyleTopic = /\b(attorney|attorneys|lawyer|lawyers|law firm|legal counsel|patent law)\b/.test(raw);
  const allowedAttorneyAngles = /\b(cost|costs|fee|fees|pricing|hire|hiring|choose|choosing|strategy|filing|provisional|office action|pct|uspto)\b/.test(raw);
  if (attorneyStyleTopic && !allowedAttorneyAngles) return true;

  return false;
}

function nowIso(): string {
  return new Date().toISOString();
}

function getTimeZoneIsoDate(date: Date, timeZone: string): string {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const parts = formatter.formatToParts(date);
  const lookup = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${lookup.year}-${lookup.month}-${lookup.day}`;
}

export function loadGeneratedPosts(filePath: string): GeneratedPostsLedger {
  if (!existsSync(filePath)) {
    const initial: GeneratedPostsLedger = { generatedPosts: [] };
    writeFileSync(filePath, JSON.stringify(initial, null, 2), "utf-8");
    return initial;
  }
  return JSON.parse(readFileSync(filePath, "utf-8")) as GeneratedPostsLedger;
}

export function saveGeneratedPosts(filePath: string, ledger: GeneratedPostsLedger): void {
  writeFileSync(filePath, JSON.stringify(ledger, null, 2), "utf-8");
}

export function loadTopicDiscoverySnapshot(filePath: string): TopicDiscoverySnapshot | null {
  if (!existsSync(filePath)) return null;
  return JSON.parse(readFileSync(filePath, "utf-8")) as TopicDiscoverySnapshot;
}

function saveTopicDiscoverySnapshot(filePath: string, snapshot: TopicDiscoverySnapshot): void {
  writeFileSync(filePath, JSON.stringify(snapshot, null, 2), "utf-8");
}

function patentAdjacentScore(value: string): number {
  const normalized = normalizeKeyword(value);
  const checks: Array<[RegExp, number]> = [
    [/\bpatent\b/, 5],
    [/\bdocketing\b|\bdocket\b/, 5],
    [/\bdeadline\b|\bdeadlines\b|\bdeadline tracking\b/, 4],
    [/\bparalegal\b|\blaw firm support\b|\badmin support\b/, 4],
    [/\bprosecution\b|\bprosecution workflow\b/, 4],
    [/\bportfolio management\b|\bip portfolio\b/, 4],
    [/\banaqua\b|\bpattsy\b|\bpatricia\b|\bwebtms\b|\bcpi\b|\bdockettrak\b|\bflextrac\b|\bappcoll\b/, 5],
    [/\bprovisional\b/, 4],
    [/\buspto\b/, 4],
    [/\boffice action\b/, 4],
    [/\bpct\b/, 4],
    [/\bsoftware\b/, 3],
    [/\bai\b|\bartificial intelligence\b/, 3],
    [/\bdrawing\b|\bdrawings\b|\bfigure\b|\bfigures\b/, 4],
    [/\billustration\b|\billustrator\b/, 4],
    [/\breference numerals?\b|\bshading\b|\bline styles?\b|\bmargins?\b/, 4],
    [/\bdesign patent\b|\butility patent\b/, 4],
    [/\bstartup\b|\bfounder\b/, 3],
    [/\bcost\b|\bfees\b|\bbudget\b/, 3],
    [/\bfiling\b|\bapplication\b|\bclaim\b/, 3],
    [/\bip protection\b|\bintellectual property\b/, 3],
  ];

  return checks.reduce((sum, [pattern, weight]) => (pattern.test(normalized) ? sum + weight : sum), 0);
}

function isPatentAdjacent(value: string): boolean {
  if (isOutOfScopeTopic(value)) return false;
  return patentAdjacentScore(value) >= 5;
}

function workspaceId(config: AppConfig): string {
  return String(config.workspaceId || "").trim().toLowerCase();
}

function isDrawingWorkspace(config: AppConfig): boolean {
  return workspaceId(config) === "patent-drawing-experts";
}

function isIpDocketersWorkspace(config: AppConfig): boolean {
  return workspaceId(config) === "ip-docketers";
}

function isWorkspaceRelevantTopic(config: AppConfig, value: string): boolean {
  if (!isPatentAdjacent(value)) return false;

  const normalized = normalizeKeyword(value);

  if (isDrawingWorkspace(config)) {
    return /\bdrawing|drawings|figure|figures|illustration|illustrator|reference numerals|uspto drawing|design patent drawing|utility patent drawing|shading|line rules|margins?\b/.test(normalized);
  }

  if (isIpDocketersWorkspace(config)) {
    if (/\b(certificate|certificates|certification|certifications|course|courses|training|exam|salary|salaries|job|jobs|career|careers|resume|interview)\b/.test(normalized)) {
      return false;
    }

    return /\b(ip docketing|trademark docketing|patent docketing|docketing|deadline|deadlines|deadline tracking|missed deadlines|prosecution|prosecution workflow|paralegal|anaqua|pattsy|patricia|webtms|cpi|dockettrak|flextrac|appcoll|law firm|law firms|legal ops|legal operations|outsourced ip|integration|integrations|docketing systems?)\b/.test(normalized);
  }

  return true;
}

function discoverySeedQueriesForConfig(config: AppConfig): string[] {
  if (isDrawingWorkspace(config)) return DRAWING_DISCOVERY_SEED_QUERIES;
  if (isIpDocketersWorkspace(config)) return IP_DOCKETERS_DISCOVERY_SEED_QUERIES;
  return DISCOVERY_SEED_QUERIES;
}

function evergreenFallbackTopicsForConfig(config: AppConfig) {
  if (isDrawingWorkspace(config)) return DRAWING_EVERGREEN_FALLBACK_TOPICS;
  if (isIpDocketersWorkspace(config)) return IP_DOCKETERS_EVERGREEN_FALLBACK_TOPICS;
  return EVERGREEN_FALLBACK_TOPICS;
}

function inferTheme(cluster: string): string {
  const themeMap: Record<string, string> = {
    "ip docketing": "IP Docketing Services",
    "ip prosecution support": "IP Prosecution Support",
    "ip paralegal services": "IP Paralegal Services",
    "docketing integrations": "Docketing System Integrations",
    "utility patent drawings": "Utility Patent Drawings",
    "design patent drawings": "Design Patent Drawings",
    "patent drawing rules": "Patent Drawing Rules",
    "patent illustrations": "Patent Illustrations",
    "patent drawing costs": "Patent Drawings Cost",
    "provisional patents": "Provisional Patent Strategy",
    "software and ai patents": "Software and AI Patent Protection",
    "patent costs": "Patent Cost and Filing Budget",
    "office actions": "Office Action and Response Strategy",
    "pct filing": "PCT and International Filing",
    "startup ip protection": "Startup IP Protection",
    "patent search": "Patent Search and Prior Art",
    "patent comparisons": "Patent Comparisons and Filing Choices",
    "patent filing strategy": "Patent Filing Strategy",
    "uspto process": "USPTO Filing Process",
    "patent strategy": "Patent Strategy",
  };
  return themeMap[cluster] || titleCaseWords(cluster);
}

function normalizeSignalQuery(value: string): string {
  return String(value || "")
    .replace(/\s+/g, " ")
    .replace(/\?+$/, "")
    .trim();
}

function computeCommercialRelevance(text: string): number {
  const normalized = normalizeKeyword(text);
  let score = 0;
  if (/\b(cost|fees|budget|pricing)\b/.test(normalized)) score += 8;
  if (/\b(strategy|guide|checklist|steps|process|timeline)\b/.test(normalized)) score += 8;
  if (/\bstartup|founder|saas|company\b/.test(normalized)) score += 7;
  if (/\bpatent filing|provisional|office action|pct\b/.test(normalized)) score += 7;
  if (/\bdocketing|deadline|prosecution|paralegal|integration|law firm\b/.test(normalized)) score += 8;
  return Math.min(25, score);
}

function computeBrandFit(text: string): number {
  return Math.min(25, patentAdjacentScore(text));
}

function scoreCompetitorGap(title: string, snippet: string): number {
  const normalized = normalizeKeyword(`${title} ${snippet}`);
  let score = 0;
  if (/\bguide|checklist|mistakes|timeline|cost|strategy|example\b/.test(normalized)) score += 8;
  if (/\bstartup|founder|software|ai|office action|provisional\b/.test(normalized)) score += 6;
  if (/\bdocketing|deadline|prosecution|paralegal|integration|law firm\b/.test(normalized)) score += 7;
  return Math.min(20, score);
}

function freshnessScoreFromDays(days?: number | null): number {
  if (days === null || days === undefined || Number.isNaN(days)) return 4;
  if (days <= 3) return 20;
  if (days <= 7) return 16;
  if (days <= 14) return 12;
  if (days <= 30) return 8;
  if (days <= 90) return 5;
  return 2;
}

function parseFreshnessDays(value?: string | null): number | null {
  const text = String(value || "").trim().toLowerCase();
  if (!text) return null;

  const dayMatch = text.match(/(\d+)\s+day/);
  if (dayMatch) return Number(dayMatch[1]);
  const weekMatch = text.match(/(\d+)\s+week/);
  if (weekMatch) return Number(weekMatch[1]) * 7;
  const monthMatch = text.match(/(\d+)\s+month/);
  if (monthMatch) return Number(monthMatch[1]) * 30;
  const yearMatch = text.match(/(\d+)\s+year/);
  if (yearMatch) return Number(yearMatch[1]) * 365;

  return null;
}

function extractOrganicText(result: Record<string, unknown>): { title: string; url: string; snippet: string; freshnessDays: number | null } {
  const title = String(result.title || "").trim();
  const url = String(result.link || "").trim();
  const snippet = String(result.snippet || result.snippet_highlighted_words || "").trim();
  const freshnessDays = parseFreshnessDays(String(result.date || result.snippet || ""));
  return { title, url, snippet, freshnessDays };
}

function uniqueSignalId(sourceType: TopicSignalSource, query: string, url = ""): string {
  return slugify(`${sourceType}-${query}-${url}`);
}

async function fetchJsonWithRetry(endpoint: URL, logger: RunLogger): Promise<Record<string, unknown>> {
  return withRetry(
    async () => {
      const response = await fetch(endpoint);
      if (!response.ok) {
        const body = await response.text();
        throw new Error(`SerpAPI request failed (${response.status}): ${body}`);
      }
      return (await response.json()) as Record<string, unknown>;
    },
    {
      retries: 3,
      delayMs: 1200,
      onRetry: (attempt, error) =>
        logger.warn(`SerpAPI request retry ${attempt + 1}: ${error instanceof Error ? error.message : String(error)}`),
    },
  );
}

async function createSearchConsoleAuth(config: AppConfig): Promise<InstanceType<typeof google.auth.OAuth2> | null> {
  const property = String(config.googleSearchConsoleProperty || "").trim();
  const clientId = String(config.googleOAuthClientId || "").trim();
  const clientSecret = String(config.googleOAuthClientSecret || "").trim();
  const refreshToken = String(config.googleOAuthRefreshToken || "").trim();

  if (!property || !clientId || !clientSecret || !refreshToken) return null;

  const auth = new google.auth.OAuth2(clientId, clientSecret);
  auth.setCredentials({ refresh_token: refreshToken });
  await auth.getAccessToken();
  return auth;
}

async function fetchSearchConsoleSignals(
  config: AppConfig,
  logger: RunLogger,
): Promise<{ signals: TopicSignal[]; health: TopicSourceHealth }> {
  const auth = await createSearchConsoleAuth(config).catch(() => null);
  const property = String(config.googleSearchConsoleProperty || "").trim();
  if (!auth || !property) {
    return {
      signals: [],
      health: {
        source: "search_console",
        ok: false,
        detail: "Search Console OAuth is not fully configured.",
      },
    };
  }

  try {
    const searchConsole = google.webmasters({ version: "v3", auth });
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 28);
    const startDate = start.toISOString().slice(0, 10);
    const endDate = end.toISOString().slice(0, 10);
    const response = await searchConsole.searchanalytics.query({
      siteUrl: property,
      requestBody: {
        startDate,
        endDate,
        rowLimit: 30,
        dimensions: ["query", "page"],
        searchType: "web",
      },
    });

    const rows = response.data.rows || [];
    const signals: TopicSignal[] = [];
    for (const row of rows) {
      const query = normalizeSignalQuery(String(row.keys?.[0] || ""));
      const page = String(row.keys?.[1] || "");
      if (!query || !isWorkspaceRelevantTopic(config, query)) continue;

      const impressions = Number(row.impressions || 0);
      const clicks = Number(row.clicks || 0);
      const ctr = Number(row.ctr || 0);
      const position = Number(row.position || 0);
      const demandScore = Math.min(35, Math.round(impressions / 6) + Math.round(clicks * 1.5) + Math.max(0, 10 - position));
      const signal: TopicSignal = {
        id: uniqueSignalId("search_console_query", query, page),
        sourceType: "search_console_query",
        label: query,
        query,
        url: page,
        title: query,
        impressions,
        clicks,
        ctr,
        position,
        freshnessDays: null,
        demandScore,
        freshnessScore: 6,
        commercialRelevanceScore: computeCommercialRelevance(query),
        brandFitScore: computeBrandFit(query),
        competitorGapScore: 4,
        intentCluster: inferIntentCluster(query),
        evidence: [
          `Search Console query with ${Math.round(impressions)} impressions`,
          page ? `Current traction on ${page}` : "Current site traction",
        ],
      };
      signals.push(signal);
    }

    return {
      signals,
      health: {
        source: "search_console",
        ok: true,
        detail: signals.length
          ? `Loaded ${signals.length} Search Console query signals.`
          : "Search Console responded but returned no relevant patent-adjacent query signals.",
      },
    };
  } catch (error) {
    return {
      signals: [],
      health: {
        source: "search_console",
        ok: false,
        detail: `Search Console query fetch failed: ${error instanceof Error ? error.message : String(error)}`,
      },
    };
  }
}

async function fetchSerpResearchBundle(
  config: AppConfig,
  logger: RunLogger,
  query: string,
): Promise<{
  relatedQuestions: string[];
  relatedSearches: string[];
  suggestions: string[];
  competitors: Array<{ title: string; url: string; snippet: string; freshnessDays: number | null }>;
}> {
  if (!config.serpApiKey) {
    throw new Error("SERPAPI_API_KEY is missing.");
  }

  const searchUrl = new URL("https://serpapi.com/search.json");
  searchUrl.searchParams.set("engine", "google");
  searchUrl.searchParams.set("num", "10");
  searchUrl.searchParams.set("q", query);
  searchUrl.searchParams.set("api_key", config.serpApiKey);

  const autocompleteUrl = new URL("https://serpapi.com/search.json");
  autocompleteUrl.searchParams.set("engine", "google_autocomplete");
  autocompleteUrl.searchParams.set("q", query);
  autocompleteUrl.searchParams.set("api_key", config.serpApiKey);

  const [searchResult, autocompleteResult] = await Promise.all([
    fetchJsonWithRetry(searchUrl, logger),
    fetchJsonWithRetry(autocompleteUrl, logger),
  ]);

  const relatedQuestions = Array.isArray(searchResult.related_questions)
    ? searchResult.related_questions
        .map((item) => String((item as Record<string, unknown>).question || "").trim())
        .filter(Boolean)
    : [];
  const relatedSearches = Array.isArray(searchResult.related_searches)
    ? searchResult.related_searches
        .map((item) => String((item as Record<string, unknown>).query || "").trim())
        .filter(Boolean)
    : [];
  const suggestions = Array.isArray(autocompleteResult.suggestions)
    ? autocompleteResult.suggestions
        .map((item) => String((item as Record<string, unknown>).value || "").trim())
        .filter(Boolean)
    : [];
  const competitors = Array.isArray(searchResult.organic_results)
    ? searchResult.organic_results
        .map((item) => extractOrganicText(item as Record<string, unknown>))
        .filter((item) => item.url && !item.url.toLowerCase().includes(config.siteDomain))
        .slice(0, 5)
    : [];

  return {
    relatedQuestions: uniqueStrings(relatedQuestions, 8),
    relatedSearches: uniqueStrings(relatedSearches, 10),
    suggestions: uniqueStrings(suggestions, 10),
    competitors,
  };
}

async function fetchSerpSignals(
  config: AppConfig,
  logger: RunLogger,
  seedQueries: string[],
): Promise<{ signals: TopicSignal[]; health: TopicSourceHealth; competitorSignals: TopicSignal[]; competitorHealth: TopicSourceHealth }> {
  if (!config.serpApiKey) {
    return {
      signals: [],
      health: {
        source: "serpapi_keywords",
        ok: false,
        detail: "SERPAPI_API_KEY is missing.",
      },
      competitorSignals: [],
      competitorHealth: {
        source: "competitor_search",
        ok: false,
        detail: "Competitor search skipped because SerpAPI is unavailable.",
      },
    };
  }

  const pickedQueries = uniqueStrings(seedQueries.filter((query) => isWorkspaceRelevantTopic(config, query)), 4);
  const signals: TopicSignal[] = [];
  const competitorSignals: TopicSignal[] = [];
  const errors: string[] = [];

  for (const query of pickedQueries) {
    try {
      const bundle = await fetchSerpResearchBundle(config, logger, query);

      for (const suggestion of bundle.suggestions) {
        if (!isWorkspaceRelevantTopic(config, suggestion)) continue;
        signals.push({
          id: uniqueSignalId("serp_autocomplete", suggestion),
          sourceType: "serp_autocomplete",
          label: suggestion,
          query: suggestion,
          title: suggestion,
          demandScore: 16,
          freshnessScore: 6,
          commercialRelevanceScore: computeCommercialRelevance(suggestion),
          brandFitScore: computeBrandFit(suggestion),
          competitorGapScore: 4,
          freshnessDays: null,
          intentCluster: inferIntentCluster(suggestion),
          evidence: [`Autocomplete suggestion for "${query}"`],
        });
      }

      for (const search of bundle.relatedSearches) {
        if (!isWorkspaceRelevantTopic(config, search)) continue;
        signals.push({
          id: uniqueSignalId("serp_related_search", search),
          sourceType: "serp_related_search",
          label: search,
          query: search,
          title: search,
          demandScore: 18,
          freshnessScore: 7,
          commercialRelevanceScore: computeCommercialRelevance(search),
          brandFitScore: computeBrandFit(search),
          competitorGapScore: 6,
          freshnessDays: null,
          intentCluster: inferIntentCluster(search),
          evidence: [`Related Google search for "${query}"`],
        });
      }

      for (const question of bundle.relatedQuestions) {
        if (!isWorkspaceRelevantTopic(config, question)) continue;
        signals.push({
          id: uniqueSignalId("serp_related_question", question),
          sourceType: "serp_related_question",
          label: question,
          query: question,
          title: question,
          demandScore: 14,
          freshnessScore: 7,
          commercialRelevanceScore: computeCommercialRelevance(question),
          brandFitScore: computeBrandFit(question),
          competitorGapScore: 8,
          freshnessDays: null,
          intentCluster: inferIntentCluster(question),
          evidence: [`People also ask signal for "${query}"`],
        });
      }

      for (const competitor of bundle.competitors) {
        const candidateText = competitor.title || competitor.snippet || query;
        if (!isWorkspaceRelevantTopic(config, candidateText)) continue;
        competitorSignals.push({
          id: uniqueSignalId("competitor_article", candidateText, competitor.url),
          sourceType: "competitor_article",
          label: competitor.title || candidateText,
          query: candidateText,
          title: competitor.title,
          url: competitor.url,
          snippet: competitor.snippet,
          demandScore: 15,
          freshnessScore: freshnessScoreFromDays(competitor.freshnessDays),
          commercialRelevanceScore: computeCommercialRelevance(candidateText),
          brandFitScore: computeBrandFit(candidateText),
          competitorGapScore: scoreCompetitorGap(competitor.title, competitor.snippet),
          freshnessDays: competitor.freshnessDays,
          intentCluster: inferIntentCluster(candidateText),
          evidence: [
            `Competitor article surfaced for "${query}"`,
            competitor.url,
          ],
        });
      }
    } catch (error) {
      errors.push(`${query}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return {
    signals,
    health: {
      source: "serpapi_keywords",
      ok: signals.length > 0,
      detail: signals.length
        ? `Loaded ${signals.length} keyword-demand signals from SerpAPI.`
        : `No dynamic keyword signals were loaded from SerpAPI${errors.length ? ` (${errors.join(" | ")})` : ""}.`,
    },
    competitorSignals,
    competitorHealth: {
      source: "competitor_search",
      ok: competitorSignals.length > 0,
      detail: competitorSignals.length
        ? `Loaded ${competitorSignals.length} live competitor article signals.`
        : `No competitor article signals were loaded${errors.length ? ` (${errors.join(" | ")})` : ""}.`,
    },
  };
}

function aggregateSignalsIntoCandidates(config: AppConfig, signals: TopicSignal[]): HotTopicCandidate[] {
  const grouped = new Map<string, HotTopicCandidate>();

  for (const signal of signals) {
    const primaryKeyword = normalizeSignalQuery(signal.query || signal.label || signal.title || "");
    if (!primaryKeyword || !isWorkspaceRelevantTopic(config, primaryKeyword) || isOutOfScopeTopic(primaryKeyword)) continue;

    const intentCluster = signal.intentCluster || inferIntentCluster(primaryKeyword);
    const theme = inferTheme(intentCluster);
    const aggregateKey = `${intentCluster}::${normalizeKeyword(primaryKeyword)}`;
    const angle =
      signal.sourceType === "competitor_article"
        ? "competitor gap"
        : signal.freshnessScore >= 12
          ? "fresh demand"
          : "search demand";

    const existing = grouped.get(aggregateKey);
    if (existing) {
      existing.score += signal.demandScore + signal.freshnessScore + signal.commercialRelevanceScore + signal.brandFitScore + signal.competitorGapScore;
      existing.sourceTypes = uniqueStrings([...existing.sourceTypes, signal.sourceType], 8) as TopicSignalSource[];
      existing.sourceEvidence = uniqueStrings([...existing.sourceEvidence, ...signal.evidence], 12);
      existing.secondaryKeywords = uniqueStrings([...existing.secondaryKeywords, signal.label, signal.query], 8);
      existing.serpQuestions = signal.sourceType === "serp_related_question"
        ? uniqueStrings([...existing.serpQuestions, signal.label], 6)
        : existing.serpQuestions;
      existing.relatedSearches = ["serp_related_search", "serp_autocomplete"].includes(signal.sourceType)
        ? uniqueStrings([...existing.relatedSearches, signal.label], 8)
        : existing.relatedSearches;
      existing.demandScore = Math.max(existing.demandScore, signal.demandScore);
      existing.freshnessScore = Math.max(existing.freshnessScore, signal.freshnessScore);
      existing.commercialRelevanceScore = Math.max(existing.commercialRelevanceScore, signal.commercialRelevanceScore);
      existing.brandFitScore = Math.max(existing.brandFitScore, signal.brandFitScore);
      existing.competitorGapScore = Math.max(existing.competitorGapScore, signal.competitorGapScore);
      continue;
    }

    grouped.set(aggregateKey, {
      topicId: slugify(`${intentCluster}-${primaryKeyword}`),
      pillar: theme,
      cluster: intentCluster,
      angle,
      theme,
      primaryKeyword,
      secondaryKeywords: uniqueStrings([signal.label, signal.query], 8).filter((entry) => normalizeKeyword(entry) !== normalizeKeyword(primaryKeyword)),
      serpQuestions: signal.sourceType === "serp_related_question" ? [signal.label] : [],
      relatedSearches: ["serp_related_search", "serp_autocomplete"].includes(signal.sourceType) ? [signal.label] : [],
      score: signal.demandScore + signal.freshnessScore + signal.commercialRelevanceScore + signal.brandFitScore + signal.competitorGapScore,
      fingerprint: topicFingerprint(theme, angle, primaryKeyword),
      intentCluster,
      sourceTypes: [signal.sourceType],
      sourceEvidence: [...signal.evidence],
      demandScore: signal.demandScore,
      freshnessScore: signal.freshnessScore,
      commercialRelevanceScore: signal.commercialRelevanceScore,
      brandFitScore: signal.brandFitScore,
      competitorGapScore: signal.competitorGapScore,
    });
  }

  return [...grouped.values()]
    .map((candidate) => ({
      ...candidate,
      score:
        candidate.demandScore * 0.35 +
        candidate.freshnessScore * 0.15 +
        candidate.commercialRelevanceScore * 0.2 +
        candidate.brandFitScore * 0.15 +
        candidate.competitorGapScore * 0.15 +
        candidate.sourceTypes.length * 2,
    }))
    .sort((a, b) => b.score - a.score);
}

function buildAdjacentExpansionCandidates(
  config: AppConfig,
  candidates: HotTopicCandidate[],
  liveSignals: TopicSignal[],
): HotTopicCandidate[] {
  const expansions: HotTopicCandidate[] = [];
  const basis = candidates.length ? candidates.slice(0, 4) : aggregateSignalsIntoCandidates(config, liveSignals).slice(0, 4);

  for (const candidate of basis) {
    if (isOutOfScopeTopic(candidate.primaryKeyword)) continue;
    for (const modifier of ADJACENT_EXPANSION_MODIFIERS) {
      const keyword = `${candidate.primaryKeyword} ${modifier}`.trim();
      if (isOutOfScopeTopic(keyword) || !isWorkspaceRelevantTopic(config, keyword)) continue;
      expansions.push({
        ...candidate,
        topicId: slugify(`${candidate.intentCluster}-${keyword}`),
        primaryKeyword: keyword,
        secondaryKeywords: uniqueStrings([candidate.primaryKeyword, ...candidate.secondaryKeywords], 8),
        angle: `adjacent ${modifier}`,
        fingerprint: topicFingerprint(candidate.theme, `adjacent ${modifier}`, keyword),
        sourceTypes: uniqueStrings([...candidate.sourceTypes, "adjacent_expansion"], 8) as TopicSignalSource[],
        sourceEvidence: uniqueStrings(
          [...candidate.sourceEvidence, `Expanded from live signal shortlist using modifier "${modifier}"`],
          12,
        ),
        score: candidate.score - 2,
      });
    }
  }

  return expansions;
}

function buildManualOverrideCandidate(topicOverride: string): TopicSelection {
  const intentCluster = inferIntentCluster(topicOverride);
  const theme = inferTheme(intentCluster);
  return {
    topicId: slugify(`manual-${topicOverride}`),
    pillar: theme,
    cluster: intentCluster,
    angle: "manual override",
    theme,
    primaryKeyword: topicOverride,
    secondaryKeywords: [],
    serpQuestions: [],
    relatedSearches: [],
    score: 100,
    fingerprint: topicFingerprint(theme, "manual override", topicOverride),
    intentCluster,
    sourceTypes: ["manual_override"],
    sourceEvidence: ["Operator supplied a manual topic override."],
    demandScore: 20,
    freshnessScore: 10,
    commercialRelevanceScore: computeCommercialRelevance(topicOverride),
    brandFitScore: computeBrandFit(topicOverride),
    competitorGapScore: 8,
    runDate: "",
  };
}

function buildEvergreenFallbackCandidates(config: AppConfig): HotTopicCandidate[] {
  return evergreenFallbackTopicsForConfig(config)
    .filter((item) => !isOutOfScopeTopic(item.primaryKeyword) && isWorkspaceRelevantTopic(config, item.primaryKeyword))
    .map((item, index) => {
      const sourceEvidence = [
        "Fallback evergreen topic selected because live discovery did not produce a safe publishable topic.",
        `Evergreen angle: ${item.angle}`,
      ];
      const demandScore = 13;
      const freshnessScore = 5;
      const commercialRelevanceScore = Math.max(14, computeCommercialRelevance(item.primaryKeyword));
      const brandFitScore = Math.max(16, computeBrandFit(item.primaryKeyword));
      const competitorGapScore = 7;
      return {
        topicId: slugify(`evergreen-${item.intentCluster}-${item.primaryKeyword}`),
        pillar: item.theme,
        cluster: item.intentCluster,
        angle: item.angle,
        theme: item.theme,
        primaryKeyword: item.primaryKeyword,
        secondaryKeywords: uniqueStrings(item.secondaryKeywords, 6),
        serpQuestions: [],
        relatedSearches: uniqueStrings(item.secondaryKeywords, 6),
        score:
          demandScore * 0.35 +
          freshnessScore * 0.15 +
          commercialRelevanceScore * 0.2 +
          brandFitScore * 0.15 +
          competitorGapScore * 0.15 +
          1.5 -
          index * 0.05,
        fingerprint: topicFingerprint(item.theme, item.angle, item.primaryKeyword),
        intentCluster: item.intentCluster,
        sourceTypes: ["evergreen_fallback"] as TopicSignalSource[],
        sourceEvidence,
        demandScore,
        freshnessScore,
        commercialRelevanceScore,
        brandFitScore,
        competitorGapScore,
      };
    })
    .sort((a, b) => b.score - a.score);
}

export async function chooseTopic(args: {
  config: AppConfig;
  logger: RunLogger;
  ledger: GeneratedPostRecord[];
  recentPosts: RecentPost[];
  topicOverride?: string;
}): Promise<TopicSelection> {
  const { config, logger, ledger, recentPosts, topicOverride } = args;
  const now = new Date();
  const runDate = getTimeZoneIsoDate(now, config.timeZone);

  logger.step(`Discovering a dynamic ${config.siteName} topic from live search-demand and competitor signals.`, {
    stage: "keywords",
    mode: DISCOVERY_MODE,
  });

  if (topicOverride) {
    const override = buildManualOverrideCandidate(topicOverride);
    override.runDate = runDate;
    const snapshot: TopicDiscoverySnapshot = {
      generatedAt: nowIso(),
      mode: DISCOVERY_MODE,
      selectedTopic: override,
      shortlist: [override],
      rejectedTopics: [],
      liveSignals: [],
      sourceHealth: [],
      degradedSources: [],
    };
    saveTopicDiscoverySnapshot(config.paths.topicDiscoveryFile, snapshot);
    logger.step(`Chosen topic: ${override.primaryKeyword}`, {
      theme: override.theme,
      sourceMix: override.sourceTypes.join(", "),
    });
    return override;
  }

  const searchConsoleResult = await fetchSearchConsoleSignals(config, logger);
  if (!searchConsoleResult.health.ok) {
    logger.warn(searchConsoleResult.health.detail, { stage: "keywords", status: "warning", source: "search_console" });
  }

  const seedQueries = uniqueStrings(
    [
      ...searchConsoleResult.signals.map((signal) => signal.query),
      ...discoverySeedQueriesForConfig(config),
    ],
    6,
  );

  const serpResult = await fetchSerpSignals(config, logger, seedQueries);
  if (!serpResult.health.ok) {
    logger.warn(serpResult.health.detail, { stage: "keywords", status: "warning", source: "serpapi_keywords" });
  }
  if (!serpResult.competitorHealth.ok) {
    logger.warn(serpResult.competitorHealth.detail, { stage: "keywords", status: "warning", source: "competitor_search" });
  }

  const sourceHealth = [searchConsoleResult.health, serpResult.health, serpResult.competitorHealth];
  const degradedSources = sourceHealth.filter((item) => !item.ok).map((item) => item.source);
  const liveSignals = [...searchConsoleResult.signals, ...serpResult.signals, ...serpResult.competitorSignals]
    .filter((signal) => isWorkspaceRelevantTopic(config, signal.query || signal.label || signal.title || ""))
    .sort(
      (a, b) =>
        b.demandScore + b.freshnessScore + b.commercialRelevanceScore + b.brandFitScore + b.competitorGapScore -
        (a.demandScore + a.freshnessScore + a.commercialRelevanceScore + a.brandFitScore + a.competitorGapScore),
    );

  logger.step(`Collected ${liveSignals.length} live topic signals.`, {
    stage: "keywords",
    sourceMix: uniqueStrings(liveSignals.map((signal) => signal.sourceType), 8).join(", "),
  });

  let candidates = aggregateSignalsIntoCandidates(config, liveSignals);
  let rejectedTopics: TopicRejectedCandidate[] = [];

  const filterCandidates = (items: HotTopicCandidate[]) =>
    items.filter((candidate) => {
      const reason = findModerateDuplicateReason(
        {
          primaryKeyword: candidate.primaryKeyword,
          fingerprint: candidate.fingerprint,
          slug: candidate.topicId,
          intentCluster: candidate.intentCluster,
        },
        ledger,
        recentPosts,
        now,
      );

      if (reason) {
        rejectedTopics.push({
          topicId: candidate.topicId,
          primaryKeyword: candidate.primaryKeyword,
          intentCluster: candidate.intentCluster,
          score: Math.round(candidate.score),
          reason,
          sourceTypes: candidate.sourceTypes,
        });
        return false;
      }
      return true;
    });

  let filtered = filterCandidates(candidates);
  if (!filtered.length) {
    logger.warn("Primary dynamic shortlist was exhausted by duplicate checks. Trying adjacent-angle expansion.", {
      stage: "keywords",
      status: "warning",
      mode: "adjacent_expansion",
    });
    const expanded = buildAdjacentExpansionCandidates(config, candidates, liveSignals);
    filtered = filterCandidates(expanded);
    candidates = expanded;
  }

  if (!filtered.length) {
    logger.warn("Live discovery and adjacent expansion were exhausted. Falling back to the evergreen topic pool.", {
      stage: "keywords",
      status: "warning",
      mode: "evergreen_fallback",
    });
    const evergreen = buildEvergreenFallbackCandidates(config);
    filtered = filterCandidates(evergreen);
    candidates = evergreen;
  }

  const winner = filtered[0];
  const snapshot: TopicDiscoverySnapshot = {
    generatedAt: nowIso(),
    mode: DISCOVERY_MODE,
    selectedTopic: winner ? { ...winner, runDate } : null,
    shortlist: filtered.slice(0, 8),
    rejectedTopics: rejectedTopics.slice(0, 12),
    liveSignals: liveSignals.slice(0, 16),
    sourceHealth,
    degradedSources,
  };
  saveTopicDiscoverySnapshot(config.paths.topicDiscoveryFile, snapshot);

  if (!winner) {
    throw new Error(`No eligible ${config.siteName} topic remained after duplicate checks`);
  }

  logger.step(`Chosen topic: ${winner.primaryKeyword}`, {
    theme: winner.theme,
    intentCluster: winner.intentCluster,
    sourceMix: winner.sourceTypes.join(", "),
    demandScore: winner.demandScore,
    freshnessScore: winner.freshnessScore,
  });

  return {
    ...winner,
    runDate,
  };
}
