import { describe, expect, it, vi } from "vitest";

const createMock = vi
  .fn()
  .mockResolvedValueOnce({
    choices: [
      {
        message: {
          content: JSON.stringify({
            title: "AI patent filing strategy for startups",
            slug: "ai-patent-filing-strategy-for-startups",
            metaTitle: "AI patent filing strategy for startups",
            metaDescription: "Learn how startup founders can build an AI patent filing strategy without wasting budget or disclosures.",
            excerpt: "A practical overview for startup teams planning AI patent protection.",
            primaryKeyword: "AI patent filing strategy for startups",
            secondaryKeywords: ["software patent strategy", "AI patent protection", "startup patent filing"],
            tags: ["AI Patents", "Startups", "Patent Filing"],
            category: "Patent Filing",
            headingPlan: ["Introduction", "Why It Matters", "Patentability Basics", "Checklist", "Examples", "FAQ"],
            faqQuestions: ["Can startups patent AI?", "Should founders file provisional patents first?", "What mistakes delay filing?"],
            cta: "Talk to PatentZoom about your filing strategy.",
            internalLinkTargets: ["provisional patent filing", "patent filing costs", "startup IP protection"],
            imagePrompt: "Professional AI patent illustration",
            imageAltText: "AI patent filing concept",
          }),
        },
      },
    ],
  })
  .mockResolvedValueOnce({
    choices: [
      {
        message: {
          content: JSON.stringify({
            title: "AI patent filing strategy for startups",
            slug: "ai-patent-filing-strategy-for-startups",
            metaTitle: "AI patent filing strategy for startups",
            metaDescription: "Learn how startup founders can build an AI patent filing strategy without wasting budget or disclosures.",
            excerpt: "A practical overview for startup teams planning AI patent protection.",
            primaryKeyword: "AI patent filing strategy for startups",
            secondaryKeywords: ["software patent strategy", "AI patent protection", "startup patent filing"],
            tags: ["AI Patents", "Startups", "Patent Filing"],
            category: "Patent Filing",
            articleHtml: "<h1>AI patent filing strategy for startups</h1><h2>Overview</h2><p>Founders need a practical approach to documenting training data, model outputs, product workflows, and alternative embodiments before they disclose the invention publicly.</p><h2>Why It Matters</h2><p>Software and AI filings often rise or fall on how clearly the patent application explains technical improvements, deployment architecture, and measurable benefits.</p><h2>Checklist</h2><ul><li>Capture the technical problem</li><li>Explain the solution architecture</li><li>Document product variations</li><li>Align public launch timing with filing strategy</li></ul><!-- INTERNAL_LINK:startup IP protection --><h2>Examples</h2><p>A startup building an AI-driven workflow engine may need claims around system architecture, data processing pipelines, and application-specific outputs rather than broad claims to automation alone.</p><h2>FAQ</h2><p>Founders should review timing, ownership, disclosure, and budget questions early in the filing process.</p><p>This article is for informational purposes only and does not constitute legal advice.</p>",
            faqSchemaJsonLd: "{\"@context\":\"https://schema.org\",\"@type\":\"FAQPage\"}",
            imagePrompt: "Professional AI patent illustration",
            imageAltText: "AI patent filing concept",
          }),
        },
      },
    ],
  });

vi.mock("openai", () => {
  return {
    default: class OpenAI {
      chat = {
        completions: {
          create: createMock,
        },
      };
    },
  };
});

import { generateArticle } from "../openaiContent";

describe("openaiContent", () => {
  it("parses structured outline and article responses", async () => {
    const article = await generateArticle(
      {
        openAiApiKey: "key",
        openAiModel: "gpt-4.1-mini",
        siteName: "PatentZoom",
        brandTone: "Professional",
        defaultCategory: "Patent Filing",
      } as any,
      {
        step: vi.fn(),
        warn: vi.fn(),
      } as any,
      {
        topicId: "ai-patent-filing-strategy",
        pillar: "AI and Software Patents",
        cluster: "technology company filing strategy",
        angle: "AI startup positioning",
        theme: "Software and AI Patent Protection",
        primaryKeyword: "AI patent filing strategy for startups",
        secondaryKeywords: ["software patent strategy"],
        serpQuestions: ["Can startups patent AI?"],
        relatedSearches: ["startup patent filing"],
        score: 10,
        fingerprint: "ai::startup::ai patent",
        intentCluster: "software and ai patents",
        sourceTypes: ["serp_related_search", "competitor_article"],
        sourceEvidence: ["Related Google search", "Competitor article surfaced"],
        demandScore: 18,
        freshnessScore: 10,
        commercialRelevanceScore: 16,
        brandFitScore: 18,
        competitorGapScore: 11,
        runDate: "2026-05-08",
      },
    );

    expect(article.title).toContain("AI patent");
    expect(article.slug).toBe("ai-patent-filing-strategy-for-startups");
  });
});
