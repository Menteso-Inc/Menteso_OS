import { GeneratedArticle, RecentPost } from "./types";
import { normalizeKeyword, uniqueStrings } from "./textUtils";

function keywordScore(target: string, post: RecentPost): number {
  const targetTokens = new Set(normalizeKeyword(target).split(" ").filter(Boolean));
  const postTokens = new Set(normalizeKeyword(`${post.title} ${post.excerpt || ""}`).split(" ").filter(Boolean));
  let score = 0;
  targetTokens.forEach((token) => {
    if (postTokens.has(token)) score += 1;
  });
  return score;
}

function buildAnchorText(target: string, post: RecentPost): string {
  const normalizedTitle = normalizeKeyword(post.title);
  const normalizedTarget = normalizeKeyword(target);
  return normalizedTitle.includes(normalizedTarget) ? post.title : target;
}

export function insertInternalLinks(
  article: GeneratedArticle,
  recentPosts: RecentPost[],
): GeneratedArticle {
  const placeholders = article.articleHtml.match(/<!--\s*INTERNAL_LINK:([^>]+)-->/g) || [];
  if (!placeholders.length || !recentPosts.length) {
    return article;
  }

  let updatedHtml = article.articleHtml;
  const usedPostIds = new Set<number>();
  const targets = uniqueStrings(
    placeholders.map((placeholder) => placeholder.replace(/<!--\s*INTERNAL_LINK:|-->/g, "").trim()),
    5,
  );

  targets.forEach((target) => {
    const ranked = recentPosts
      .filter((post) => !usedPostIds.has(post.id))
      .map((post) => ({ post, score: keywordScore(target, post) }))
      .sort((a, b) => b.score - a.score);

    const best = ranked.find((entry) => entry.score > 0);
    const placeholder = `<!-- INTERNAL_LINK:${target} -->`;
    if (!best) {
      updatedHtml = updatedHtml.replace(placeholder, "");
      return;
    }

    usedPostIds.add(best.post.id);
    const anchorText = buildAnchorText(target, best.post);
    updatedHtml = updatedHtml.replace(
      placeholder,
      `Related reading: <a href="${best.post.url}">${anchorText}</a>`,
    );
  });

  return {
    ...article,
    articleHtml: updatedHtml.replace(/<!--\s*INTERNAL_LINK:[^>]+-->/g, ""),
  };
}
