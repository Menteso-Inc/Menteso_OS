import { GeneratedArticle, SeoValidationResult } from "./types";
import { slugify, wordCountFromHtml } from "./textUtils";

function trimAtWordBoundary(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  const sliced = value.slice(0, maxLength + 1);
  return sliced.slice(0, sliced.lastIndexOf(" ")).trim();
}

function stripHtml(value: string): string {
  return String(value || "")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function toTitleCase(value: string): string {
  return value.replace(/\w\S*/g, (word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase());
}

function words(value: string): string[] {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
}

const STOPWORDS = new Set([
  "a",
  "an",
  "and",
  "as",
  "at",
  "by",
  "for",
  "from",
  "in",
  "into",
  "of",
  "on",
  "or",
  "the",
  "to",
  "with",
]);

const TRANSITION_PREFIXES = [
  "First",
  "Next",
  "For example",
  "Also",
  "Meanwhile",
  "In addition",
  "However",
  "As a result",
  "At the same time",
  "Finally",
];

function cleanFocusKeyword(phrase: string): string {
  const tokens = words(phrase);
  while (tokens.length && STOPWORDS.has(tokens[0]!)) tokens.shift();
  while (tokens.length && STOPWORDS.has(tokens[tokens.length - 1]!)) tokens.pop();
  if (tokens.length > 4) {
    const last = tokens[tokens.length - 1] || "";
    if (["india", "us", "usa", "startup", "startups", "software", "ai"].includes(last)) {
      return tokens.slice(-4).join(" ");
    }
    return tokens.slice(0, 4).join(" ");
  }
  return tokens.join(" ");
}

function countPhrase(value: string, phrase: string): number {
  const normalizedValue = stripHtml(value).toLowerCase();
  const normalizedPhrase = String(phrase || "").trim().toLowerCase();
  if (!normalizedPhrase) return 0;
  return normalizedValue.split(normalizedPhrase).length - 1;
}

function chooseFocusKeyword(article: GeneratedArticle): string {
  const current = String(article.primaryKeyword || "").trim();
  const currentWords = words(cleanFocusKeyword(current));
  if (currentWords.length > 0 && currentWords.length <= 4) return currentWords.join(" ");

  const candidates = new Map<string, number>();
  const seedSources = [
    current,
    article.title,
    ...(article.secondaryKeywords || []),
  ];

  for (const source of seedSources) {
    const tokens = words(source);
    for (let size = 2; size <= 4; size += 1) {
      for (let index = 0; index <= tokens.length - size; index += 1) {
        const phrase = tokens.slice(index, index + size).join(" ");
        if (!phrase.includes("patent")) continue;
        if (STOPWORDS.has(tokens[index + size - 1] || "")) continue;
        if (STOPWORDS.has(tokens[index] || "")) continue;
        let score = 0;
        if (current.toLowerCase().includes(phrase)) score += 4;
        if (article.title.toLowerCase().includes(phrase)) score += 4;
        if (/provisional|software|startup|timeline|cost|filing|checklist|application/.test(phrase)) score += 3;
        if (size === 3 || size === 4) score += 2;
        const cleaned = cleanFocusKeyword(phrase);
        if (!cleaned || words(cleaned).length < 2) continue;
        candidates.set(cleaned, Math.max(candidates.get(cleaned) || 0, score));
      }
    }
  }

  const best = [...candidates.entries()].sort((a, b) => b[1] - a[1] || b[0].length - a[0].length)[0]?.[0];
  if (best) return cleanFocusKeyword(best);

  return cleanFocusKeyword(currentWords.slice(0, 4).join(" ")) || "patent filing strategy";
}

function ensureTitleHasKeyword(title: string, focusKeyword: string): string {
  const keywordTitle = toTitleCase(focusKeyword);
  if (title.toLowerCase().includes(focusKeyword.toLowerCase())) return title;
  return `${keywordTitle}: ${title}`.trim();
}

function ensureMetaTitle(focusKeyword: string, title: string): string {
  const keywordTitle = toTitleCase(focusKeyword);
  const preferred = `${keywordTitle} | PatentZoom`;
  if (preferred.length <= 60) return preferred;
  return trimAtWordBoundary(ensureTitleHasKeyword(title, focusKeyword), 60);
}

function repairIncompleteTitle(title: string, focusKeyword: string): string {
  const cleaned = String(title || "").trim().replace(/[,:;\-–—]+$/, "").trim();
  if (!cleaned) return `${toTitleCase(focusKeyword)} Guide for Startups and Inventors`;
  if (!/\b(for|in|to|and|or|with|of|on|at|from)$/i.test(cleaned)) return cleaned;
  if (/india/i.test(focusKeyword)) return `${toTitleCase(focusKeyword)} Guide for Startups and Inventors`;
  return `${cleaned} Startups and Inventors`;
}

function ensureMetaDescription(focusKeyword: string, metaDescription: string): string {
  let result = String(metaDescription || "").trim();
  if (!result.toLowerCase().includes(focusKeyword.toLowerCase())) {
    result = `${toTitleCase(focusKeyword)} explained for startups and inventors, including timing, cost, filing steps, and next actions with PatentZoom guidance.`;
  }
  if (result.length > 155) result = trimAtWordBoundary(result, 150);
  if (result.length < 120) {
    result = trimAtWordBoundary(
      `${result} Learn practical filing steps, cost considerations, and strategic next moves for inventors and startups.`,
      155,
    );
  }
  return result;
}

function ensureKeywordInIntro(articleHtml: string, focusKeyword: string): string {
  if (countPhrase(articleHtml.slice(0, 500), focusKeyword) > 0) return articleHtml;
  return articleHtml.replace(
    /(<h2[^>]*>.*?<\/h2>)/i,
    `$1\n<p>${toTitleCase(focusKeyword)} is one of the most important planning issues for founders who need to protect innovation without slowing product development.</p>`,
  );
}

function ensureKeywordInSubheading(articleHtml: string, focusKeyword: string): string {
  const escapedKeyword = focusKeyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const matches = articleHtml.match(new RegExp(`<h[23][^>]*>[^<]*${escapedKeyword}`, "gi")) || [];
  if (matches.length >= 2) {
    return articleHtml;
  }
  const headings = [...articleHtml.matchAll(/<h([23])([^>]*)>([^<]*)<\/h\1>/gi)];
  if (!headings.length) return articleHtml;

  let updatedHtml = articleHtml;
  let insertsNeeded = Math.max(0, 2 - matches.length);
  for (const heading of headings) {
    if (!insertsNeeded) break;
    const original = heading[0];
    const tag = heading[1];
    const attrs = heading[2];
    const text = heading[3];
    if (new RegExp(escapedKeyword, "i").test(text)) continue;
    updatedHtml = updatedHtml.replace(
      original,
      `<h${tag}${attrs}>${toTitleCase(focusKeyword)}: ${text}</h${tag}>`,
    );
    insertsNeeded -= 1;
  }

  return updatedHtml;
}

function ensureOutboundLink(articleHtml: string): string {
  if (/href="https?:\/\/(?!patentzoom\.us)/i.test(articleHtml)) return articleHtml;
  return articleHtml.replace(
    /(<\/p>)/i,
    ` <a href="https://www.uspto.gov/patents" target="_blank" rel="noopener noreferrer">USPTO patent guidance</a>$1`,
  );
}

function normalizeArticleHtml(articleHtml: string): string {
  return String(articleHtml || "")
    .replace(/<p>\s*<p>/gi, "<p>")
    .replace(/<\/p>\s*<\/p>/gi, "</p>")
    .replace(/<p>\s*(Related reading:\s*<a\b[^>]*>.*?<\/a>)\s*<\/p>/gi, "<p>$1</p>")
    .replace(/<\/a>\s*<\//gi, "</a></")
    .replace(/\n{3,}/g, "\n\n");
}

function startsWithTransition(text: string): boolean {
  const normalized = stripHtml(text).trim().toLowerCase();
  return TRANSITION_PREFIXES.some((prefix) => normalized.startsWith(`${prefix.toLowerCase()},`));
}

function ensureTransitionWords(articleHtml: string): string {
  let paragraphIndex = 0;
  let injected = 0;

  return articleHtml.replace(/<p>([\s\S]*?)<\/p>/gi, (match, inner) => {
    paragraphIndex += 1;
    const plain = stripHtml(inner);
    if (
      paragraphIndex <= 2 ||
      plain.length < 90 ||
      startsWithTransition(plain) ||
      /itemprop="text"/i.test(match) ||
      /informational purposes only|PatentZoom can help/i.test(plain)
    ) {
      return match;
    }

    const prefix = TRANSITION_PREFIXES[injected % TRANSITION_PREFIXES.length];
    injected += 1;
    return `<p>${prefix}, ${inner.trim()}</p>`;
  });
}

export function validateAndOptimizeArticle(article: GeneratedArticle): SeoValidationResult {
  const issues: string[] = [];
  const optimized: GeneratedArticle = { ...article, articleHtml: normalizeArticleHtml(article.articleHtml) };
  const focusKeyword = chooseFocusKeyword(optimized);
  optimized.primaryKeyword = focusKeyword;

  optimized.title = ensureTitleHasKeyword(optimized.title, focusKeyword);
  optimized.title = repairIncompleteTitle(optimized.title, focusKeyword);
  optimized.metaTitle = ensureMetaTitle(focusKeyword, optimized.title);
  optimized.metaDescription = ensureMetaDescription(focusKeyword, optimized.metaDescription);

  if (optimized.title.length > 70) {
    optimized.title = trimAtWordBoundary(optimized.title, 68);
    issues.push("Trimmed long title");
  }
  if (optimized.metaTitle.length > 60) {
    optimized.metaTitle = trimAtWordBoundary(optimized.metaTitle, 60);
    issues.push("Trimmed meta title");
  }
  if (optimized.metaDescription.length > 155) {
    optimized.metaDescription = trimAtWordBoundary(optimized.metaDescription, 150);
    issues.push("Trimmed meta description");
  }
  if (optimized.metaDescription.length < 120) issues.push("Expanded short meta description");

  optimized.slug = slugify(optimized.slug || optimized.title);
  if (!/^[a-z0-9-]+$/.test(optimized.slug)) {
    optimized.slug = slugify(optimized.title);
    issues.push("Rebuilt invalid slug");
  }

  if (!optimized.articleHtml.includes("<h1")) {
    optimized.articleHtml = `<h1>${optimized.title}</h1>\n${optimized.articleHtml}`;
    issues.push("Added missing H1");
  }
  if (!optimized.articleHtml.includes("<h2")) {
    optimized.articleHtml += "\n<h2>Key Filing Considerations</h2><p>Inventors should align timing, disclosure planning, and budget with their filing strategy.</p>";
    issues.push("Added missing H2 section");
  }

  const beforeKeywordCount = countPhrase(optimized.articleHtml, focusKeyword);
  optimized.articleHtml = ensureKeywordInIntro(optimized.articleHtml, focusKeyword);
  optimized.articleHtml = ensureKeywordInSubheading(optimized.articleHtml, focusKeyword);
  if (beforeKeywordCount === 0) issues.push("Inserted primary keyword into article");

  if (!optimized.articleHtml.includes("PatentZoom")) {
    optimized.articleHtml += "\n<p>If you want help mapping the right next filing step, PatentZoom can help you evaluate timing, scope, and filing options.</p>";
    issues.push("Added PatentZoom CTA");
  }

  if (!optimized.articleHtml.includes("This article is for informational purposes only and does not constitute legal advice.")) {
    optimized.articleHtml += "\n<p><em>This article is for informational purposes only and does not constitute legal advice.</em></p>";
    issues.push("Appended legal disclaimer");
  }

  if (!/frequently asked questions|faq/i.test(optimized.articleHtml)) {
    optimized.articleHtml +=
      "\n<h2>Frequently Asked Questions</h2><p>Review the filing strategy questions above and use them as a preparation checklist before speaking with counsel.</p><h3>What should founders prepare before filing?</h3><p>Prepare an invention summary, the product roadmap, public disclosure dates, and a budget estimate so the filing strategy matches business timing.</p><h3>When should inventors talk to a patent professional?</h3><p>Inventors should get guidance before public launch, fundraising diligence, or international expansion decisions so filing scope and timing are planned together.</p>";
    issues.push("Added FAQ section fallback");
  }

  optimized.articleHtml = ensureOutboundLink(optimized.articleHtml);

  const placeholders = optimized.articleHtml.match(/<!--\s*INTERNAL_LINK:[^>]+-->/g) || [];
  if (placeholders.length < 3) {
    optimized.articleHtml += [
      "\n<!-- INTERNAL_LINK:provisional patent filing -->",
      "\n<!-- INTERNAL_LINK:patent filing costs -->",
      "\n<!-- INTERNAL_LINK:startup IP protection -->",
    ].slice(0, 3 - placeholders.length).join("");
    issues.push("Added missing internal link placeholders");
  }

  let words = wordCountFromHtml(optimized.articleHtml);
  if (words < 1200) {
    optimized.articleHtml +=
      "\n<h2>Practical Next Steps</h2><p>Before you file, document the invention clearly, capture alternatives, evaluate your public disclosure timeline, compare budget choices, and map the next six to twelve months of product development against the filing schedule.</p><p>Teams should also identify which claims matter most commercially, what disclosures have already occurred, and whether a provisional, utility, or international strategy fits the near-term business plan.</p>";
    issues.push("Expanded short article");
    words = wordCountFromHtml(optimized.articleHtml);
  }

  const readabilityParagraphs = [
    "First, founders should compare patent costs with the next product milestone so legal spend supports the moments that matter most for launch timing and investor diligence.",
    "Next, teams should document prior disclosures, prototype iterations, and inventor contributions so the filing record stays organized before formal drafting begins.",
    "For example, a startup that expects investor diligence within a quarter may benefit from filing earlier so the patent timeline matches fundraising discussions and roadmap decisions.",
    "Meanwhile, businesses should decide whether they need only India coverage or whether future PCT or foreign filings should influence the first-year patent budget.",
    "In addition, inventors should note which claims matter most commercially because stronger claim planning can reduce avoidable redrafts and prosecution expenses later.",
    "However, cutting professional drafting support too aggressively can increase risk if the invention is technically complex or likely to face examination objections.",
    "As a result, many teams treat filing cost as one part of a broader protection strategy that also includes disclosure control, roadmap timing, and market priorities.",
    "Finally, India patent filing cost should be reviewed alongside budget, launch timing, disclosure plans, and the strength of the underlying invention record.",
  ];

  let readabilityIndex = 0;
  while (words < 1050) {
    optimized.articleHtml += `\n<p>${readabilityParagraphs[readabilityIndex % readabilityParagraphs.length]}</p>`;
    readabilityIndex += 1;
    words = wordCountFromHtml(optimized.articleHtml);
  }

  while (countPhrase(optimized.articleHtml, focusKeyword) < 3) {
    optimized.articleHtml += `\n<p>${toTitleCase(focusKeyword)} should be reviewed alongside budget, launch timing, disclosure plans, and the strength of the underlying invention record.</p>`;
  }

  optimized.articleHtml = ensureTransitionWords(optimized.articleHtml);

  return { article: optimized, issues };
}
