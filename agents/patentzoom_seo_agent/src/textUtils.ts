import { GeneratedPostRecord } from "./types";

export function slugify(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");
}

export function normalizeKeyword(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\b(the|a|an|for|to|of|and|in|on|with|how|what)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function tokenizeTopic(value: string): string[] {
  return normalizeKeyword(value)
    .split(" ")
    .filter((token) => token.length > 1);
}

function stemToken(token: string): string {
  if (token.endsWith("ies") && token.length > 3) return `${token.slice(0, -3)}y`;
  return token.replace(/(ing|ed|es|s)$/g, "");
}

export function keywordStem(value: string): string {
  return normalizeKeyword(value)
    .split(" ")
    .map((token) => stemToken(token))
    .filter(Boolean)
    .join(" ");
}

export function stemmedTokens(value: string): string[] {
  return tokenizeTopic(value).map((token) => stemToken(token)).filter(Boolean);
}

export function stemmedOverlap(left: string, right: string): number {
  const leftSet = new Set(stemmedTokens(left));
  const rightSet = new Set(stemmedTokens(right));
  if (!leftSet.size || !rightSet.size) return 0;
  let intersection = 0;
  for (const token of leftSet) {
    if (rightSet.has(token)) intersection += 1;
  }
  return intersection;
}

export function inferIntentCluster(value: string): string {
  const normalized = normalizeKeyword(value);
  const checks: Array<[string, RegExp]> = [
    ["provisional patents", /\bprovisional\b/],
    ["software and ai patents", /\b(ai|software|saas|machine learning|artificial intelligence)\b/],
    ["patent costs", /\b(cost|fees|budget|price)\b/],
    ["office actions", /\boffice action|rejection|response\b/],
    ["pct filing", /\bpct|international patent|global filing|jurisdiction\b/],
    ["startup ip protection", /\bstartup ip|ip protection|fundraising|moat\b/],
    ["patent search", /\bpatent search|prior art\b/],
    ["patent comparisons", /\bdesign patent|utility patent|vs\b/],
    ["patent filing strategy", /\bpatent filing|patent strategy|file a patent|filing strategy\b/],
    ["uspto process", /\buspto|patent process|timeline|application\b/],
  ];

  for (const [cluster, pattern] of checks) {
    if (pattern.test(normalized)) return cluster;
  }
  return "patent strategy";
}

export function titleCaseWords(value: string): string {
  return String(value || "")
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

export function intentClusterLabel(cluster: string): string {
  return titleCaseWords(cluster);
}

export function jaccardSimilarity(left: string, right: string): number {
  const leftSet = new Set(tokenizeTopic(left));
  const rightSet = new Set(tokenizeTopic(right));
  if (!leftSet.size || !rightSet.size) return 0;

  let intersection = 0;
  for (const token of leftSet) {
    if (rightSet.has(token)) intersection += 1;
  }
  const union = new Set([...leftSet, ...rightSet]).size;
  return union ? intersection / union : 0;
}

export function topicFingerprint(pillar: string, angle: string, keyword: string): string {
  return `${slugify(pillar)}::${slugify(angle)}::${keywordStem(keyword)}`;
}

export function uniqueStrings(values: string[], limit = values.length): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values.map((item) => item.trim()).filter(Boolean)) {
    const key = value.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      result.push(value);
    }
    if (result.length >= limit) break;
  }
  return result;
}

export function isLedgerDuplicate(
  candidateFingerprint: string,
  primaryKeyword: string,
  ledger: GeneratedPostRecord[],
  currentDate = new Date(),
): boolean {
  const currentTime = currentDate.getTime();
  const keyword = keywordStem(primaryKeyword);
  const candidateCluster = inferIntentCluster(primaryKeyword);
  return ledger.some((entry) => {
    if (entry.fingerprint === candidateFingerprint) return true;
    const days = Math.abs(currentTime - new Date(entry.date).getTime()) / (1000 * 60 * 60 * 24);
    if (days > 120) return false;
    const entryKeyword = String(entry.primaryKeyword || "");
    if (keywordStem(entryKeyword) === keyword) return true;

    const sameCluster = inferIntentCluster(entryKeyword) === candidateCluster;
    if (!sameCluster) return false;

    const overlap = jaccardSimilarity(entryKeyword, primaryKeyword);
    return overlap >= 0.8;
  });
}

export function findModerateDuplicateReason(
  candidate: Pick<GeneratedPostRecord, "primaryKeyword" | "fingerprint" | "slug" | "intentCluster">,
  ledger: GeneratedPostRecord[],
  recentPosts: Array<{ title: string; slug: string }>,
  currentDate = new Date(),
): string | null {
  const currentTime = currentDate.getTime();
  const candidateKeyword = String(candidate.primaryKeyword || "");
  const candidateSlug = slugify(candidate.slug || candidateKeyword);
  const candidateCluster = String(candidate.intentCluster || inferIntentCluster(candidateKeyword));

  for (const entry of ledger) {
    const days = Math.abs(currentTime - new Date(entry.date).getTime()) / (1000 * 60 * 60 * 24);
    const entryKeyword = String(entry.primaryKeyword || "");
    const entryCluster = String(entry.intentCluster || inferIntentCluster(entryKeyword));

    if (entry.fingerprint === candidate.fingerprint) return "Exact topic fingerprint already used";
    if (slugify(entry.slug || entryKeyword) === candidateSlug) return "Slug already used recently";
    if (keywordStem(entryKeyword) === keywordStem(candidateKeyword) && days <= 180) {
      return "Primary keyword already used in the recent ledger";
    }

    if (days <= 90 && entryCluster === candidateCluster) {
      const overlap = jaccardSimilarity(entryKeyword, candidateKeyword);
      if (overlap >= 0.8) return "Recent topic with the same search intent already exists";
      if (stemmedOverlap(entryKeyword, candidateKeyword) >= 3 && overlap >= 0.6) {
        return "Recent topic uses the same core patent-intent terms";
      }
    }
  }

  for (const post of recentPosts) {
    const postTitle = String(post.title || "");
    const postSlug = String(post.slug || "");
    if (slugify(postSlug || postTitle) === candidateSlug) return "Recent WordPress post already uses this slug";
    if (keywordStem(postTitle) === keywordStem(candidateKeyword)) return "Recent WordPress post already targets this keyword";
    if (
      inferIntentCluster(postTitle) === candidateCluster &&
      jaccardSimilarity(postTitle, candidateKeyword) >= 0.8
    ) {
      return "Recent WordPress post covers a near-identical intent";
    }
    if (
      inferIntentCluster(postTitle) === candidateCluster &&
      stemmedOverlap(postTitle, candidateKeyword) >= 3 &&
      jaccardSimilarity(postTitle, candidateKeyword) >= 0.6
    ) {
      return "Recent WordPress post already covers the same core patent-intent terms";
    }
  }

  return null;
}

export function wordCountFromHtml(html: string): number {
  return html
    .replace(/<[^>]+>/g, " ")
    .split(/\s+/)
    .filter(Boolean).length;
}
