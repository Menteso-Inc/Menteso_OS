import { readFileSync } from "node:fs";
import { extname } from "node:path";
import { AppConfig } from "./config";
import { RunLogger } from "./logger";
import { GeneratedArticle, MediaUploadResult, RecentPost } from "./types";

function decodeHtml(value: string): string {
  return value
    .replace(/&#8217;/g, "'")
    .replace(/&#8211;/g, "-")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#8220;/g, '"')
    .replace(/&#8221;/g, '"')
    .replace(/<[^>]+>/g, "")
    .trim();
}

function normalizeMetaText(value: string): string {
  return decodeHtml(String(value || ""))
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function mimeTypeFor(filePath: string): string {
  switch (extname(filePath).toLowerCase()) {
    case ".jpg":
    case ".jpeg":
      return "image/jpeg";
    case ".webp":
      return "image/webp";
    default:
      return "image/png";
  }
}

export function buildPostPayload(args: {
  article: GeneratedArticle;
  status: string;
  categoryId: number;
  tagIds: number[];
  featuredMediaId?: number | null;
  authorId?: number | null;
}) {
  const { article, status, categoryId, tagIds, featuredMediaId, authorId } = args;
  const contentHtml = stripLeadingH1(article.articleHtml);
  const content = `${contentHtml}\n<script type="application/ld+json">${article.faqSchemaJsonLd}</script>`;
  return {
    title: article.title,
    content,
    status,
    slug: article.slug,
    excerpt: article.excerpt,
    categories: [categoryId],
    tags: tagIds,
    ...(featuredMediaId ? { featured_media: featuredMediaId } : {}),
    ...(authorId ? { author: authorId } : {}),
  };
}

export function stripLeadingH1(articleHtml: string): string {
  const html = String(articleHtml || "").trim();
  return html.replace(/^\s*<h1\b[^>]*>[\s\S]*?<\/h1>\s*/i, "").trim();
}

export class WordPressClient {
  private readonly config: AppConfig;
  private readonly logger: RunLogger;
  private readonly authHeader: string;

  constructor(config: AppConfig, logger: RunLogger) {
    this.config = config;
    this.logger = logger;
    this.authHeader = `Basic ${Buffer.from(
      `${config.wpUsername}:${config.wpApplicationPassword}`,
      "utf-8",
    ).toString("base64")}`;
  }

  isConfigured(): boolean {
    return Boolean(this.config.wpUsername && this.config.wpApplicationPassword);
  }

  private assertConfigured(): void {
    if (!this.isConfigured()) {
      throw new Error(
        "WordPress publishing is not configured. Add WP_USERNAME and WP_APPLICATION_PASSWORD in .env to create draft or live posts.",
      );
    }
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.config.wpBaseUrl}/wp-json/wp/v2${path}`, {
      ...init,
      headers: {
        ...(this.isConfigured() ? { Authorization: this.authHeader } : {}),
        ...(init?.headers || {}),
      },
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`WordPress request failed (${response.status}) ${path}: ${body}`);
    }

    return (await response.json()) as T;
  }

  private async publicRequest<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.config.wpBaseUrl}/wp-json/wp/v2${path}`, init);
    if (!response.ok) {
      const body = await response.text();
      throw new Error(`WordPress public request failed (${response.status}) ${path}: ${body}`);
    }
    return (await response.json()) as T;
  }

  private toRecentPost(post: Record<string, unknown>): RecentPost {
    return {
      id: Number(post.id),
      slug: String(post.slug || ""),
      url: String(post.link || ""),
      title: decodeHtml(String((post.title as Record<string, unknown>)?.rendered || "")),
      excerpt: decodeHtml(String((post.excerpt as Record<string, unknown>)?.rendered || "")),
    };
  }

  private async fetchDrawingWorkspaceTargets(): Promise<RecentPost[]> {
    const requestFn = this.isConfigured() ? this.request.bind(this) : this.publicRequest.bind(this);
    const [products, pages] = await Promise.all([
      requestFn<Array<Record<string, unknown>>>("/product?per_page=20&_fields=id,slug,link,title,excerpt"),
      requestFn<Array<Record<string, unknown>>>("/pages?per_page=50&_fields=id,slug,link,title,excerpt"),
    ]);

    const usefulPageSlugs = new Set([
      "contact-us",
      "patent-drawing-faqs",
      "samples",
      "utility-patent-drawings-samples",
      "design-patent-drawings-samples",
      "how-it-works",
      "resources",
    ]);

    return [
      ...products.map((item) => this.toRecentPost(item)),
      ...pages.filter((item) => usefulPageSlugs.has(String(item.slug || ""))).map((item) => this.toRecentPost(item)),
    ];
  }

  private async fetchIpDocketersWorkspaceTargets(): Promise<RecentPost[]> {
    const requestFn = this.isConfigured() ? this.request.bind(this) : this.publicRequest.bind(this);
    const pages = await requestFn<Array<Record<string, unknown>>>("/pages?per_page=100&_fields=id,slug,link,title,excerpt");

    const usefulPageSlugs = new Set([
      "ip-docketing-services",
      "ip-prosecution-paralegal-services",
      "virtual-ip-litigation-paralegal",
      "admin-team-law-firm-support",
      "support-for-all-ip-docketing-systems",
      "anaqua",
      "cpi",
      "flextrac",
      "pattsy",
      "dockettrak",
      "patricia",
      "webtms",
      "appcoll",
      "blog",
      "case-study",
    ]);

    return pages.filter((item) => usefulPageSlugs.has(String(item.slug || ""))).map((item) => this.toRecentPost(item));
  }

  async fetchRecentPosts(limit = 50): Promise<RecentPost[]> {
    const path = `/posts?per_page=${limit}&orderby=date&order=desc&_fields=id,slug,link,title,excerpt`;
    let posts: Array<Record<string, unknown>>;
    if (this.isConfigured()) {
      try {
        posts = await this.request<Array<Record<string, unknown>>>(path);
      } catch (error) {
        this.logger.warn(
          `WordPress authenticated recent-post fetch failed. Retrying public fetch for duplicate checks. ${
            error instanceof Error ? error.message : String(error)
          }`,
        );
        posts = await this.publicRequest<Array<Record<string, unknown>>>(path);
      }
    } else {
      posts = await this.publicRequest<Array<Record<string, unknown>>>(path);
    }
    const recentPosts = posts.map((post) => this.toRecentPost(post));
    try {
      if (this.config.workspaceId === "patent-drawing-experts") {
        const workspaceTargets = await this.fetchDrawingWorkspaceTargets();
        const merged = [...workspaceTargets, ...recentPosts];
        const seen = new Set<string>();
        return merged.filter((item) => {
          const key = `${item.url}|${item.slug}`.toLowerCase();
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
      }

      if (this.config.workspaceId === "ip-docketers") {
        const workspaceTargets = await this.fetchIpDocketersWorkspaceTargets();
        const merged = [...workspaceTargets, ...recentPosts];
        const seen = new Set<string>();
        return merged.filter((item) => {
          const key = `${item.url}|${item.slug}`.toLowerCase();
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
      }

      return recentPosts;
    } catch (error) {
      const workspaceLabel = this.config.workspaceId === "ip-docketers" ? "IP Docketers" : "Patent Drawing Experts";
      this.logger.warn(
        `${workspaceLabel} service-page fetch failed. Falling back to recent posts only. ${
          error instanceof Error ? error.message : String(error)
        }`,
      );
      return recentPosts;
    }
  }

  private async ensureTerm(type: "categories" | "tags", name: string): Promise<number> {
    this.assertConfigured();
    const existing = await this.request<Array<Record<string, unknown>>>(
      `/${type}?search=${encodeURIComponent(name)}&per_page=100`,
    );
    const exact = existing.find(
      (item) => String(item.name || "").trim().toLowerCase() === name.trim().toLowerCase(),
    );
    if (exact) return Number(exact.id);

    const created = await this.request<Record<string, unknown>>(`/${type}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    this.logger.step(`Created WordPress ${type.slice(0, -1)}: ${name}`);
    return Number(created.id);
  }

  async ensureCategory(name: string): Promise<number> {
    return this.ensureTerm("categories", name);
  }

  async ensureTags(names: string[]): Promise<number[]> {
    const ids: number[] = [];
    for (const name of names) {
      ids.push(await this.ensureTerm("tags", name));
    }
    return ids;
  }

  async uploadMedia(filePath: string, altText: string, title: string): Promise<MediaUploadResult> {
    this.assertConfigured();
    const fileName = filePath.split(/[\\/]/).pop() || "featured-image.png";
    const media = await this.request<Record<string, unknown>>("/media", {
      method: "POST",
      headers: {
        "Content-Type": mimeTypeFor(filePath),
        "Content-Disposition": `attachment; filename="${fileName}"`,
      },
      body: readFileSync(filePath),
    });

    const mediaId = Number(media.id);
    await this.request(`/media/${mediaId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        alt_text: altText,
        title,
      }),
    });

    return {
      id: mediaId,
      sourceUrl: String(media.source_url || ""),
    };
  }

  async createPost(args: {
    article: GeneratedArticle;
    postStatus: string;
    featuredMediaId?: number | null;
    seoScore?: number;
    readabilityScore?: number;
  }): Promise<{ id: number; url: string; status: string }> {
    this.assertConfigured();
    const categoryId = await this.ensureCategory(args.article.category || this.config.defaultCategory);
    const tagIds = await this.ensureTags(args.article.tags);
    const payload = buildPostPayload({
      article: args.article,
      status: args.postStatus,
      categoryId,
      tagIds,
      featuredMediaId: args.featuredMediaId,
      authorId: this.config.defaultAuthor,
    });

    const created = await this.request<Record<string, unknown>>("/posts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const postId = Number(created.id);
    await this.applySeoMeta(postId, args.article, args.seoScore, args.readabilityScore);
    return {
      id: postId,
      url: String(created.link || ""),
      status: String(created.status || args.postStatus),
    };
  }

  async applySeoMeta(
    postId: number,
    article: GeneratedArticle,
    seoScore?: number,
    readabilityScore?: number,
  ): Promise<void> {
    this.assertConfigured();
    const normalizedSeoScore = Number.isFinite(seoScore) ? Math.max(0, Math.min(100, Math.round(seoScore || 0))) : undefined;
    const normalizedReadabilityScore = Number.isFinite(readabilityScore)
      ? Math.max(0, Math.min(100, Math.round(readabilityScore || 0)))
      : undefined;
    const metaPayload = {
      meta: {
        rank_math_title: article.metaTitle,
        rank_math_description: article.metaDescription,
        _yoast_wpseo_title: article.metaTitle,
        _yoast_wpseo_metadesc: article.metaDescription,
        _yoast_wpseo_focuskw: article.primaryKeyword,
        ...(normalizedSeoScore !== undefined ? { _yoast_wpseo_linkdex: normalizedSeoScore } : {}),
        ...(normalizedReadabilityScore !== undefined
          ? { _yoast_wpseo_content_score: normalizedReadabilityScore }
          : {}),
      },
    };

    try {
      const updated = await this.request<Record<string, unknown>>(`/posts/${postId}?context=edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(metaPayload),
      });

      const updatedMeta = (updated.meta as Record<string, unknown> | undefined) || {};
      const yoast = (updated.yoast_head_json as Record<string, unknown> | undefined) || {};
      const savedTitle = normalizeMetaText(String(updatedMeta._yoast_wpseo_title || ""));
      const savedDescription = normalizeMetaText(String(updatedMeta._yoast_wpseo_metadesc || ""));
      const savedFocus = normalizeMetaText(String(updatedMeta._yoast_wpseo_focuskw || ""));
      const savedSeoScore = Number(updatedMeta._yoast_wpseo_linkdex || 0);
      const savedReadabilityScore = Number(updatedMeta._yoast_wpseo_content_score || 0);
      const appliedTitle = normalizeMetaText(String(yoast.title || ""));
      const appliedDescription = normalizeMetaText(String(yoast.description || yoast.og_description || ""));
      const expectedTitle = normalizeMetaText(article.metaTitle);
      const expectedDescription = normalizeMetaText(article.metaDescription);
      const expectedFocus = normalizeMetaText(article.primaryKeyword);

      if (
        (expectedTitle && savedTitle && !savedTitle.includes(expectedTitle)) ||
        (expectedDescription && savedDescription && !savedDescription.includes(expectedDescription)) ||
        (expectedFocus && savedFocus && !savedFocus.includes(expectedFocus)) ||
        (normalizedSeoScore !== undefined && savedSeoScore !== normalizedSeoScore) ||
        (normalizedReadabilityScore !== undefined && savedReadabilityScore !== normalizedReadabilityScore)
      ) {
        this.logger.warn(
          "Yoast SEO meta save appears incomplete in the REST response. A follow-up WordPress-side check is recommended before relying on the saved fields.",
        );
      } else if (
        (expectedTitle && appliedTitle && !appliedTitle.includes(expectedTitle)) ||
        (expectedDescription && appliedDescription && !appliedDescription.includes(expectedDescription))
      ) {
        this.logger.warn(
          "Yoast meta fields saved, but Yoast front-end indexable output has not caught up yet. Resaving or reindexing Yoast SEO data may be needed.",
        );
      }
    } catch (error) {
      this.logger.warn(
        `WordPress SEO meta update skipped: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }
}
