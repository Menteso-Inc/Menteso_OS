import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { AppConfig } from "./config";
import { RunLogger } from "./logger";
import { withRetry } from "./retry";
import {
  EditorialSlot,
  GeneratedPostRecord,
  GeneratedPostsLedger,
  RecentPost,
  TopicCandidate,
  TopicSelection,
} from "./types";
import { isLedgerDuplicate, normalizeKeyword, slugify, topicFingerprint, uniqueStrings } from "./textUtils";

const editorialCalendar: EditorialSlot[] = [
  {
    weekday: 1,
    weekdayName: "Monday",
    pillar: "Patent Filing Strategy",
    cluster: "startup filing playbooks",
    seedKeywords: ["patent filing strategy for startups", "startup patent strategy", "patent filing checklist"],
    weekAngles: {
      1: ["foundational strategy", "first-time inventor playbook"],
      2: ["filing roadmap", "timing strategy"],
      3: ["SaaS startup protection", "venture-backed company planning"],
      4: ["advanced portfolio planning", "international filing readiness"],
    },
  },
  {
    weekday: 2,
    weekdayName: "Tuesday",
    pillar: "Provisional Patents",
    cluster: "filing checklists",
    seedKeywords: ["provisional patent filing checklist", "provisional vs non provisional patent", "when to file provisional patent"],
    weekAngles: {
      1: ["beginner explainer", "step-by-step checklist"],
      2: ["cost and timing", "mistakes to avoid"],
      3: ["software and AI use cases", "startup product launch timing"],
      4: ["conversion strategy", "international bridge planning"],
    },
  },
  {
    weekday: 3,
    weekdayName: "Wednesday",
    pillar: "Patent Cost and USPTO Process",
    cluster: "budget and timeline",
    seedKeywords: ["how much does patent filing cost", "USPTO patent process timeline", "patent attorney fees startup"],
    weekAngles: {
      1: ["cost fundamentals", "timeline overview"],
      2: ["budget planning", "USPTO milestones"],
      3: ["software and AI cost scenarios", "startup budget examples"],
      4: ["advanced prosecution costs", "global filing cost planning"],
    },
  },
  {
    weekday: 4,
    weekdayName: "Thursday",
    pillar: "Startup IP Protection",
    cluster: "search and office actions",
    seedKeywords: ["startup IP protection strategy", "patent search before filing", "office action response strategy"],
    weekAngles: {
      1: ["IP basics for founders", "pre-filing diligence"],
      2: ["office action process", "response checklist"],
      3: ["fundraising readiness", "SaaS moat building"],
      4: ["portfolio strengthening", "cross-border risk management"],
    },
  },
  {
    weekday: 5,
    weekdayName: "Friday",
    pillar: "AI and Software Patents",
    cluster: "technology company filing strategy",
    seedKeywords: ["AI patent filing strategy", "software patent mistakes to avoid", "can you patent software in the US"],
    weekAngles: {
      1: ["eligibility basics", "software claim strategy"],
      2: ["mistakes and risks", "office action readiness"],
      3: ["AI startup positioning", "product-specific examples"],
      4: ["advanced subject-matter eligibility", "global software protection"],
    },
  },
  {
    weekday: 6,
    weekdayName: "Saturday",
    pillar: "Patent Mistakes and Comparisons",
    cluster: "practical checklists",
    seedKeywords: ["design patent vs utility patent", "patent filing mistakes to avoid", "patent search checklist"],
    weekAngles: {
      1: ["fundamental comparisons", "checklist format"],
      2: ["mistake prevention", "cost-saving decisions"],
      3: ["startup-specific pitfalls", "technology product mistakes"],
      4: ["global filing pitfalls", "portfolio maintenance mistakes"],
    },
  },
  {
    weekday: 0,
    weekdayName: "Sunday",
    pillar: "PCT Filing and Patent Trends",
    cluster: "international protection",
    seedKeywords: ["PCT filing strategy", "international patent protection", "patent trends for startups"],
    weekAngles: {
      1: ["evergreen PCT basics", "trend explainer"],
      2: ["international timing", "cost and process"],
      3: ["AI and software global filing", "investor-facing international strategy"],
      4: ["advanced PCT timing", "jurisdiction planning"],
    },
  },
];

function getTimeZoneDate(date: Date, timeZone: string): { day: number; weekday: number; isoDate: string } {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
  });
  const parts = formatter.formatToParts(date);
  const lookup = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const weekdayLookup: Record<string, number> = {
    Sun: 0,
    Mon: 1,
    Tue: 2,
    Wed: 3,
    Thu: 4,
    Fri: 5,
    Sat: 6,
  };
  return {
    day: Number(lookup.day),
    weekday: weekdayLookup[lookup.weekday],
    isoDate: `${lookup.year}-${lookup.month}-${lookup.day}`,
  };
}

function getWeekOfMonth(day: number): number {
  return Math.min(4, Math.max(1, Math.ceil(day / 7)));
}

export function resolveEditorialSlot(date: Date, timeZone: string): { slot: EditorialSlot; weekOfMonth: number; isoDate: string } {
  const tzDate = getTimeZoneDate(date, timeZone);
  const weekOfMonth = getWeekOfMonth(tzDate.day);
  const slot =
    editorialCalendar.find((entry) => entry.weekday === tzDate.weekday) || editorialCalendar[0];
  return { slot, weekOfMonth, isoDate: tzDate.isoDate };
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

function isRecentWordPressDuplicate(candidate: TopicCandidate, posts: RecentPost[]): boolean {
  const candidateSlug = slugify(candidate.primaryKeyword);
  const candidateNorm = normalizeKeyword(candidate.primaryKeyword);
  return posts.some((post) => {
    if (post.slug === candidateSlug) return true;
    return normalizeKeyword(post.title) === candidateNorm;
  });
}

async function fetchSerpApi(endpoint: URL, logger: RunLogger): Promise<Record<string, unknown>> {
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

async function researchKeywordSet(config: AppConfig, logger: RunLogger, query: string) {
  const fallbackResearch = (reason: string) => {
    logger.warn(reason, {
      stage: "keywords",
      status: "warning",
      mode: "fallback",
    });
    const fallbacks = uniqueStrings(
      [
        query,
        `${query} for startups`,
        `${query} checklist`,
        `${query} strategy`,
        `${query} cost`,
        `${query} mistakes to avoid`,
      ],
      8,
    );
    return {
      relatedQuestions: uniqueStrings(
        [
          `What is the best ${query} strategy?`,
          `How much does ${query} cost?`,
          `What mistakes should founders avoid with ${query}?`,
        ],
        5,
      ),
      relatedSearches: fallbacks,
      suggestions: fallbacks,
    };
  };

  if (!config.serpApiKey) {
    return fallbackResearch(
      "SERPAPI_API_KEY is missing. Falling back to the editorial calendar seed keywords for topic research.",
    );
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

  let searchResult: Record<string, unknown>;
  let autocompleteResult: Record<string, unknown>;
  try {
    [searchResult, autocompleteResult] = await Promise.all([
      fetchSerpApi(searchUrl, logger),
      fetchSerpApi(autocompleteUrl, logger),
    ]);
  } catch (error) {
    return fallbackResearch(
      `SerpAPI is unavailable for this run. Falling back to the editorial calendar seed keywords. ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
  }

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

  return {
    relatedQuestions: uniqueStrings(relatedQuestions, 8),
    relatedSearches: uniqueStrings(relatedSearches, 10),
    suggestions: uniqueStrings(suggestions, 10),
  };
}

export function buildTopicCandidates(
  slot: EditorialSlot,
  weekOfMonth: number,
  research: Awaited<ReturnType<typeof researchKeywordSet>>,
): TopicCandidate[] {
  const angles = slot.weekAngles[weekOfMonth] || slot.weekAngles[4];
  const candidates: TopicCandidate[] = [];

  angles.forEach((angle, angleIndex) => {
    const rawKeywords = uniqueStrings(
      [
        ...research.suggestions,
        ...research.relatedSearches,
        ...slot.seedKeywords,
        ...research.relatedQuestions.map((question) => question.replace(/\?+$/, "")),
      ],
      8,
    );

    rawKeywords.forEach((keyword, keywordIndex) => {
      const fingerprint = topicFingerprint(slot.pillar, angle, keyword);
      const score =
        (keyword.toLowerCase().includes(slot.cluster.split(" ")[0]) ? 4 : 0) +
        (keyword.split(" ").length >= 5 ? 3 : 1) +
        (research.relatedQuestions.some((question) => question.toLowerCase().includes(keyword.toLowerCase())) ? 2 : 0) +
        Math.max(0, 6 - angleIndex) +
        Math.max(0, 5 - keywordIndex);

      candidates.push({
        topicId: slugify(`${slot.pillar}-${angle}-${keyword}`),
        pillar: slot.pillar,
        cluster: slot.cluster,
        angle,
        primaryKeyword: keyword,
        secondaryKeywords: uniqueStrings(
          [
            ...research.relatedSearches.filter((entry) => entry !== keyword),
            ...slot.seedKeywords.filter((entry) => entry !== keyword),
          ],
          6,
        ),
        serpQuestions: research.relatedQuestions,
        relatedSearches: research.relatedSearches,
        score,
        fingerprint,
      });
    });
  });

  return candidates.sort((a, b) => b.score - a.score);
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
  const { slot, weekOfMonth, isoDate } = resolveEditorialSlot(now, config.timeZone);

  logger.step(
    `Selecting topic from ${slot.weekdayName}'s ${slot.pillar} calendar slot (week ${weekOfMonth})`,
  );

  const researchQuery = topicOverride || slot.seedKeywords[0];
  const research = await researchKeywordSet(config, logger, researchQuery);

  let candidates = buildTopicCandidates(slot, weekOfMonth, research);
  if (topicOverride) {
    const fingerprint = topicFingerprint(slot.pillar, slot.weekAngles[weekOfMonth][0], topicOverride);
    candidates = [
      {
        topicId: slugify(`${slot.pillar}-${topicOverride}`),
        pillar: slot.pillar,
        cluster: slot.cluster,
        angle: slot.weekAngles[weekOfMonth][0],
        primaryKeyword: topicOverride,
        secondaryKeywords: uniqueStrings([...research.relatedSearches, ...slot.seedKeywords], 6),
        serpQuestions: research.relatedQuestions,
        relatedSearches: research.relatedSearches,
        score: 999,
        fingerprint,
      },
      ...candidates,
    ];
  }

  const filtered = candidates.filter((candidate) => {
    if (isLedgerDuplicate(candidate.fingerprint, candidate.primaryKeyword, ledger, now)) return false;
    if (isRecentWordPressDuplicate(candidate, recentPosts)) return false;
    return true;
  });

  const winner = filtered[0];
  if (!winner) {
    throw new Error("No eligible PatentZoom topic remained after duplicate checks");
  }

  logger.step(`Chosen topic: ${winner.primaryKeyword}`, {
    pillar: winner.pillar,
    angle: winner.angle,
  });

  return {
    ...winner,
    runDate: isoDate,
  };
}
