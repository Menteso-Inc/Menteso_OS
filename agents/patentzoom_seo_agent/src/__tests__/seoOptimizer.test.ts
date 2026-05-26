import { describe, expect, it } from "vitest";
import { validateAndOptimizeArticle } from "../seoOptimizer";

const mockConfig = {
  siteName: "PatentZoom",
  siteDomain: "patentzoom.us",
};

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
    }, mockConfig as never);

    expect(result.article.slug).toBe("bad-slug");
    expect(result.article.articleHtml).toContain("PatentZoom");
    expect(result.article.articleHtml).toContain("This article is for informational purposes only and does not constitute legal advice.");
    expect(result.issues.length).toBeGreaterThan(0);
  });

  it("does not leave provisional patent titles cut off mid-phrase", () => {
    const result = validateAndOptimizeArticle({
      title: "How to Strategically File a Provisional Patent Application with the USPTO",
      slug: "strategic-provisional-patent-filing-uspto",
      metaTitle: "",
      metaDescription: "",
      excerpt: "Guide for inventors.",
      primaryKeyword: "Provisional patent filing USPTO",
      secondaryKeywords: ["provisional patent filing uspto"],
      tags: ["Patents"],
      category: "Article",
      articleHtml: "<p>Body copy.</p>",
      faqSchemaJsonLd: "{\"@context\":\"https://schema.org\"}",
      imagePrompt: "Professional USPTO filing image",
      imageAltText: "USPTO patent filing visual",
    }, mockConfig as never);

    expect(result.article.title).toBe("How to Strategically File a Provisional Patent Application with the USPTO");
  });

  it("repairs broken links and adds an authoritative external reference", () => {
    const result = validateAndOptimizeArticle({
      title: "AI Patent Portfolio Management Software Guide",
      slug: "ai-patent-portfolio-management-software-guide",
      metaTitle: "",
      metaDescription: "",
      excerpt: "Guide for AI founders.",
      primaryKeyword: "ai patent portfolio management software",
      secondaryKeywords: ["software patent strategy", "ai patent workflow"],
      tags: ["Patents"],
      category: "Article",
      articleHtml: `
        <h2>Introduction</h2>
        <p>Teams often struggle with the <a href="#">patent application process</a> when tools and timelines are disconnected.</p>
        <p>Portfolio managers need a repeatable workflow.</p>
      `,
      faqSchemaJsonLd: "{\"@context\":\"https://schema.org\"}",
      imagePrompt: "Professional AI patent workflow image",
      imageAltText: "AI patent workflow visual",
    }, mockConfig as never);

    expect(result.article.articleHtml).not.toContain('href="#"');
    expect(result.article.articleHtml).toContain("https://www.uspto.gov/patents/basics");
    expect(result.issues).toContain("Repaired broken anchor targets");
  });
});
