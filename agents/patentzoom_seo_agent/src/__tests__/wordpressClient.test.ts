import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WordPressClient, buildPostPayload, stripLeadingH1 } from "../wordpressClient";

describe("wordpressClient", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/categories?")) {
        return { ok: true, json: async () => [{ id: 3, name: "Patent Filing" }] } as Response;
      }
      if (url.includes("/tags?")) {
        return { ok: true, json: async () => [{ id: 9, name: "Startups" }] } as Response;
      }
      if (url.endsWith("/posts") && init?.method === "POST") {
        return { ok: true, json: async () => ({ id: 41, link: "https://example.com/post", status: "draft" }) } as Response;
      }
      if (url.includes("/posts/41")) {
        return { ok: true, json: async () => ({ id: 41 }) } as Response;
      }
      throw new Error(`Unhandled URL in test: ${url}`);
    }) as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("builds a correct WordPress post payload", () => {
    const payload = buildPostPayload({
      article: {
        title: "Patent filing strategy for startups",
        slug: "patent-filing-strategy-for-startups",
        metaTitle: "Patent filing strategy for startups",
        metaDescription: "Learn how startup founders can build a practical filing plan.",
        excerpt: "A practical article for founders.",
        primaryKeyword: "patent filing strategy for startups",
        secondaryKeywords: ["startup patent strategy", "patent filing checklist", "provisional patent"],
        tags: ["Startups", "Patents", "IP"],
        category: "Patent Filing",
        articleHtml: "<h1>Patent filing strategy for startups</h1>",
        faqSchemaJsonLd: "{\"@context\":\"https://schema.org\"}",
        imagePrompt: "Prompt",
        imageAltText: "Alt text",
      },
      status: "draft",
      categoryId: 3,
      tagIds: [9],
      featuredMediaId: 12,
    });

    expect(payload.title).toBe("Patent filing strategy for startups");
    expect(payload.categories).toEqual([3]);
    expect(payload.tags).toEqual([9]);
    expect(payload.featured_media).toBe(12);
    expect(payload.content).not.toContain("<h1>Patent filing strategy for startups</h1>");
  });

  it("strips the leading H1 before publishing to WordPress", () => {
    expect(stripLeadingH1("<h1>Main title</h1><h2>Overview</h2><p>Body</p>")).toBe(
      "<h2>Overview</h2><p>Body</p>",
    );
  });

  it("creates a post through the WordPress API", async () => {
    const client = new WordPressClient(
      {
        wpBaseUrl: "https://example.com",
        wpUsername: "user",
        wpApplicationPassword: "app-pass",
        defaultCategory: "Patent Filing",
        defaultAuthor: null,
      } as any,
      {
        step: vi.fn(),
        warn: vi.fn(),
      } as any,
    );

    const created = await client.createPost({
      article: {
        title: "Patent filing strategy for startups",
        slug: "patent-filing-strategy-for-startups",
        metaTitle: "Patent filing strategy for startups",
        metaDescription: "Learn how startup founders can build a practical filing plan.",
        excerpt: "A practical article for founders.",
        primaryKeyword: "patent filing strategy for startups",
        secondaryKeywords: ["startup patent strategy", "patent filing checklist", "provisional patent"],
        tags: ["Startups"],
        category: "Patent Filing",
        articleHtml: "<h1>Patent filing strategy for startups</h1>",
        faqSchemaJsonLd: "{\"@context\":\"https://schema.org\"}",
        imagePrompt: "Prompt",
        imageAltText: "Alt text",
      },
      postStatus: "draft",
      featuredMediaId: null,
    });

    expect(created.id).toBe(41);
    expect(created.url).toBe("https://example.com/post");
  });
});
