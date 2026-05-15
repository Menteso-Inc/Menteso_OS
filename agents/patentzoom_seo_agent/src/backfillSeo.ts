import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { loadConfig } from "./config";
import { insertInternalLinks } from "./internalLinks";
import { RunLogger } from "./logger";
import { validateAndOptimizeArticle } from "./seoOptimizer";
import { GeneratedArticle, GeneratedPostsLedger, RecentPost } from "./types";

type EditablePost = {
  id: number;
  status: string;
  slug: string;
  link: string;
  title: { raw?: string; rendered?: string };
  excerpt: { raw?: string; rendered?: string };
  content: { raw?: string; rendered?: string };
  categories?: number[];
  tags?: number[];
  featured_media?: number;
  author?: number;
};

function decodeHtml(value: string): string {
  return String(value || "")
    .replace(/&#8217;/g, "'")
    .replace(/&#8211;/g, "-")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#8220;/g, '"')
    .replace(/&#8221;/g, '"')
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function extractFaqSchema(articleHtml: string): { articleHtml: string; faqSchemaJsonLd: string } {
  const match = articleHtml.match(/<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/i);
  return {
    articleHtml: articleHtml.replace(/<script[^>]*type="application\/ld\+json"[^>]*>[\s\S]*?<\/script>/gi, "").trim(),
    faqSchemaJsonLd:
      match?.[1]?.trim() ||
      JSON.stringify({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        mainEntity: [],
      }),
  };
}

async function wpRequest<T>(config: ReturnType<typeof loadConfig>, path: string, init?: RequestInit): Promise<T> {
  const authHeader = `Basic ${Buffer.from(`${config.wpUsername}:${config.wpApplicationPassword}`, "utf-8").toString("base64")}`;
  const response = await fetch(`${config.wpBaseUrl}/wp-json/wp/v2${path}`, {
    ...init,
    headers: {
      Authorization: authHeader,
      ...(init?.headers || {}),
    },
  });

  if (!response.ok) {
    throw new Error(`WordPress request failed (${response.status}) ${path}: ${await response.text()}`);
  }

  return (await response.json()) as T;
}

function buildArticle(entry: GeneratedPostsLedger["generatedPosts"][number], post: EditablePost): GeneratedArticle {
  const rawContent = post.content?.raw || post.content?.rendered || "";
  const { articleHtml, faqSchemaJsonLd } = extractFaqSchema(rawContent);
  return {
    title: post.title?.raw || decodeHtml(post.title?.rendered || ""),
    slug: post.slug,
    metaTitle: post.title?.raw || decodeHtml(post.title?.rendered || ""),
    metaDescription: decodeHtml(post.excerpt?.raw || post.excerpt?.rendered || ""),
    excerpt: decodeHtml(post.excerpt?.raw || post.excerpt?.rendered || ""),
    primaryKeyword: entry.primaryKeyword,
    secondaryKeywords: entry.secondaryKeywords || [],
    tags: [],
    category: "Article",
    articleHtml,
    faqSchemaJsonLd,
    imagePrompt: "",
    imageAltText: "",
  };
}

async function main(): Promise<void> {
  const config = loadConfig();
  const logger = new RunLogger(config, randomUUID());
  const recentPosts = await wpRequest<RecentPost[]>(
    config,
    "/posts?per_page=20&orderby=date&order=desc&_fields=id,slug,link,title,excerpt",
  ).then((posts) =>
    posts.map((post) => ({
      ...post,
      title: decodeHtml(String((post as unknown as { title?: { rendered?: string } }).title?.rendered || (post as unknown as { title?: string }).title || "")),
      excerpt: decodeHtml(String((post as unknown as { excerpt?: { rendered?: string } }).excerpt?.rendered || (post as unknown as { excerpt?: string }).excerpt || "")),
    })),
  );

  const ledger = JSON.parse(readFileSync(config.paths.generatedPostsFile, "utf-8")) as GeneratedPostsLedger;
  const results: Array<Record<string, unknown>> = [];

  for (const entry of ledger.generatedPosts) {
    if (!entry.wpPostId) continue;
    const post = await wpRequest<EditablePost>(config, `/posts/${entry.wpPostId}?context=edit`);
    if (post.status === "trash") {
      results.push({ id: entry.wpPostId, status: "skipped-trash", link: post.link });
      continue;
    }

    const baseArticle = buildArticle(entry, post);
    const optimized = validateAndOptimizeArticle(baseArticle).article;
    const linked = insertInternalLinks(optimized, recentPosts);
    linked.slug = post.slug;

    const updatePayload = {
      title: linked.title,
      content: `${linked.articleHtml}\n<script type="application/ld+json">${linked.faqSchemaJsonLd}</script>`,
      excerpt: linked.excerpt || baseArticle.excerpt,
      slug: post.slug,
      status: post.status,
      categories: post.categories || [],
      tags: post.tags || [],
      ...(post.featured_media ? { featured_media: post.featured_media } : {}),
      ...(post.author ? { author: post.author } : {}),
    };

    await wpRequest(config, `/posts/${entry.wpPostId}?context=edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updatePayload),
    });

    await wpRequest(config, `/posts/${entry.wpPostId}?context=edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        meta: {
          rank_math_title: linked.metaTitle,
          rank_math_description: linked.metaDescription,
          _yoast_wpseo_title: linked.metaTitle,
          _yoast_wpseo_metadesc: linked.metaDescription,
          _yoast_wpseo_focuskw: linked.primaryKeyword,
        },
      }),
    });

    results.push({
      id: entry.wpPostId,
      status: post.status,
      link: post.link,
      focusKeyword: linked.primaryKeyword,
      yoastTitle: linked.metaTitle,
      yoastDescription: linked.metaDescription,
    });
  }

  process.stdout.write(`${JSON.stringify(results, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack || error.message : String(error)}\n`);
  process.exit(1);
});
