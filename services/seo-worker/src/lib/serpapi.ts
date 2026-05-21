import type { WorkerLogger } from "./worker-logger";

export type KeywordResearchResult = {
  relatedQuestions: string[];
  relatedSearches: string[];
  suggestions: string[];
};

function uniqueStrings(values: string[], limit = values.length) {
  const seen = new Set<string>();
  const output: string[] = [];
  for (const value of values.map((entry) => entry.trim()).filter(Boolean)) {
    const key = value.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      output.push(value);
    }
    if (output.length >= limit) break;
  }
  return output;
}

async function requestJson(url: URL, logger: WorkerLogger) {
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.text();
    logger.warn(`SerpAPI request failed with ${response.status}: ${body}`);
    throw new Error(`SerpAPI request failed (${response.status})`);
  }
  return response.json();
}

export async function runSerpApiResearch(apiKey: string, query: string, logger: WorkerLogger): Promise<KeywordResearchResult> {
  const searchUrl = new URL("https://serpapi.com/search.json");
  searchUrl.searchParams.set("engine", "google");
  searchUrl.searchParams.set("num", "10");
  searchUrl.searchParams.set("q", query);
  searchUrl.searchParams.set("api_key", apiKey);

  const autocompleteUrl = new URL("https://serpapi.com/search.json");
  autocompleteUrl.searchParams.set("engine", "google_autocomplete");
  autocompleteUrl.searchParams.set("q", query);
  autocompleteUrl.searchParams.set("api_key", apiKey);

  const [searchResult, autocompleteResult] = await Promise.all([
    requestJson(searchUrl, logger),
    requestJson(autocompleteUrl, logger),
  ]);

  const relatedQuestions = Array.isArray(searchResult.related_questions)
    ? searchResult.related_questions
        .map((item: { question?: string }) => String(item.question || "").trim())
        .filter(Boolean)
    : [];
  const relatedSearches = Array.isArray(searchResult.related_searches)
    ? searchResult.related_searches
        .map((item: { query?: string }) => String(item.query || "").trim())
        .filter(Boolean)
    : [];
  const suggestions = Array.isArray(autocompleteResult.suggestions)
    ? autocompleteResult.suggestions
        .map((item: { value?: string }) => String(item.value || "").trim())
        .filter(Boolean)
    : [];

  return {
    relatedQuestions: uniqueStrings(relatedQuestions, 8),
    relatedSearches: uniqueStrings(relatedSearches, 10),
    suggestions: uniqueStrings(suggestions, 10),
  };
}
