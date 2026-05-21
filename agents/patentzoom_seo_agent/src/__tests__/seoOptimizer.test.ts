import { describe, expect, it } from "vitest";
import { validateAndOptimizeArticle } from "../seoOptimizer";

describe("seoOptimizer", () => {
  it("repairs missing SEO basics", () => {
    const result = validateAndOptimizeArticle({
      title: "A very long title about patent filing strategy for startups that should be shortened carefully for search",
      slug: "Bad Slug!!",
      metaTitle: "An extremely long meta title for patent strategy that should also be trimmed before publishing",
      metaDescription: "Short description",
      excerpt: "This is a useful excerpt for founders.",
      primaryKeyword: "patent filing strategy for startups",
      secondaryKeywords: ["startup patent strategy", "patent filing checklist", "founder patent roadmap"],
      tags: ["Patents", "Startups", "IP"],
      category: "Patent Filing",
      articleHtml: "<p>Short content without the keyword.</p>",
      faqSchemaJsonLd: "{\"@context\":\"https://schema.org\"}",
      imagePrompt: "Professional patent strategy image",
      imageAltText: "Patent strategy visual",
    });

    expect(result.article.slug).toBe("bad-slug");
    expect(result.article.articleHtml).toContain("PatentZoom");
    expect(result.article.articleHtml).toContain("This article is for informational purposes only and does not constitute legal advice.");
    expect(result.issues.length).toBeGreaterThan(0);
  });
});
