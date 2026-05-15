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

export function keywordStem(value: string): string {
  return normalizeKeyword(value)
    .split(" ")
    .map((token) => {
      if (token.endsWith("ies") && token.length > 3) return `${token.slice(0, -3)}y`;
      return token.replace(/(ing|ed|es|s)$/g, "");
    })
    .filter(Boolean)
    .join(" ");
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
  return ledger.some((entry) => {
    if (entry.fingerprint === candidateFingerprint) return true;
    const days = Math.abs(currentTime - new Date(entry.date).getTime()) / (1000 * 60 * 60 * 24);
    return days <= 180 && keywordStem(entry.primaryKeyword) === keyword;
  });
}

export function wordCountFromHtml(html: string): number {
  return html
    .replace(/<[^>]+>/g, " ")
    .split(/\s+/)
    .filter(Boolean).length;
}
