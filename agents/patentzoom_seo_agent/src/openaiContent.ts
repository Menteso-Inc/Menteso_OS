import OpenAI from "openai";
import { z } from "zod";
import { AppConfig } from "./config";
import { RunLogger } from "./logger";
import { withRetry } from "./retry";
import { ArticleOutline, GeneratedArticle, TopicSelection } from "./types";
import { slugify, uniqueStrings } from "./textUtils";

function workspaceAudienceGuidance(config: AppConfig): string {
  const workspaceId = String(config.workspaceId || "").trim().toLowerCase();
  if (workspaceId === "patent-drawing-experts") {
    return "Write for inventors, patent attorneys, law firms, prosecution teams, and businesses that need USPTO-compliant patent drawings and illustrations.";
  }
  if (workspaceId === "ip-docketers") {
    return "Write for law firms, in-house IP teams, docketing managers, prosecution teams, and legal operations professionals responsible for IP deadlines and workflow accuracy.";
  }
  return "Write for founders, inventors, product teams, and businesses considering patent protection in the United States or internationally.";
}

function workspaceTopicGuidance(config: AppConfig): string {
  const workspaceId = String(config.workspaceId || "").trim().toLowerCase();
  if (workspaceId === "patent-drawing-experts") {
    return "Stay tightly focused on patent drawings, design patent drawings, utility patent drawings, USPTO drawing rules, patent illustrations, figure preparation, objections, corrections, and inventor drawing readiness.";
  }
  if (workspaceId === "ip-docketers") {
    return "Stay tightly focused on IP docketing, patent prosecution workflow, missed-deadline prevention, docketing-system integrations, outsourced docketing support, and IP paralegal operations for law firms and in-house IP teams.";
  }
  return "Stay tightly focused on practical patent, filing, prosecution, and IP-protection topics relevant to the active site.";
}

function workspaceDefaultCta(config: AppConfig): string {
  const workspaceId = String(config.workspaceId || "").trim().toLowerCase();
  if (workspaceId === "patent-drawing-experts") {
    return "Patent Drawing Experts can help you prepare USPTO-compliant utility and design patent drawings before filing.";
  }
  if (workspaceId === "ip-docketers") {
    return "IP Docketers can help law firms and IP teams improve deadline control, prosecution workflow, and docketing support across systems.";
  }
  return `${config.siteName} can help you evaluate timing, scope, and next filing steps.`;
}

function workspaceDefaultTags(config: AppConfig, topic: TopicSelection): string[] {
  const workspaceId = String(config.workspaceId || "").trim().toLowerCase();
  if (workspaceId === "patent-drawing-experts") {
    return [
      topic.theme,
      "Patent Drawings",
      "USPTO Drawing Requirements",
      "Patent Illustrations",
    ];
  }
  if (workspaceId === "ip-docketers") {
    return [
      topic.theme,
      "IP Docketing",
      "Patent Prosecution",
      "Law Firm Operations",
    ];
  }
  return [
    topic.theme,
    "Patent Strategy",
    "Startup IP",
    "Patent Filing",
  ];
}

function workspaceDefaultInternalTargets(config: AppConfig): string[] {
  const workspaceId = String(config.workspaceId || "").trim().toLowerCase();
  if (workspaceId === "patent-drawing-experts") {
    return [
      "utility patent drawings",
      "design patent drawings",
      "patent drawing FAQs",
      "patent drawing samples",
    ];
  }
  if (workspaceId === "ip-docketers") {
    return [
      "ip docketing services",
      "ip prosecution paralegal services",
      "support for all ip docketing systems",
      "virtual ip litigation paralegal",
    ];
  }
  return [
    "provisional patent filing",
    "patent filing costs",
    "startup IP protection",
  ];
}

function workspaceFallbackTitle(topic: TopicSelection, config: AppConfig): string {
  const workspaceId = String(config.workspaceId || "").trim().toLowerCase();
  if (workspaceId === "ip-docketers") {
    return `${topic.primaryKeyword}: A Practical Guide for Law Firms and IP Teams`;
  }
  if (workspaceId === "patent-drawing-experts") {
    return `${topic.primaryKeyword}: A Practical Guide for Inventors and Patent Teams`;
  }
  return `${topic.primaryKeyword}: A Practical Guide for Startups and Inventors`;
}

function workspaceFallbackHeadings(config: AppConfig): string[] {
  const workspaceId = String(config.workspaceId || "").trim().toLowerCase();
  if (workspaceId === "ip-docketers") {
    return [
      "Why this workflow matters for law firms and IP teams",
      "Where deadline risk appears in daily docketing operations",
      "Common docketing mistakes to avoid",
      "Operational and system considerations",
      "Integration and reporting best practices",
      "Frequently Asked Questions",
    ];
  }
  return [
    "What this strategy means for startups",
    "When to file and why timing matters",
    "Common filing mistakes to avoid",
    "Cost and process considerations",
    "International planning and future options",
    "Frequently Asked Questions",
  ];
}

function workspaceFallbackFaqs(topic: TopicSelection, config: AppConfig): string[] {
  const workspaceId = String(config.workspaceId || "").trim().toLowerCase();
  if (workspaceId === "ip-docketers") {
    return [
      `What is the best ${topic.primaryKeyword} approach for law firms?`,
      `How much does ${topic.primaryKeyword} usually cost?`,
      `What operational mistakes should teams avoid with ${topic.primaryKeyword}?`,
    ];
  }
  return [
    `What is the best ${topic.primaryKeyword} approach for startups?`,
    `How much does ${topic.primaryKeyword} usually cost?`,
    `What mistakes should founders avoid with ${topic.primaryKeyword}?`,
  ];
}

function workspaceFallbackMetaDescription(primaryKeyword: string, config: AppConfig): string {
  const workspaceId = String(config.workspaceId || "").trim().toLowerCase();
  if (workspaceId === "ip-docketers") {
    return `${primaryKeyword} explained for law firms and IP teams, including workflow design, deadline control, system integration, and next operational steps.`;
  }
  return `${primaryKeyword} explained for startups and inventors, including timing, filing strategy, cost considerations, and next steps.`;
}

function workspaceFallbackExcerpt(primaryKeyword: string, config: AppConfig): string {
  const workspaceId = String(config.workspaceId || "").trim().toLowerCase();
  if (workspaceId === "ip-docketers") {
    return `${primaryKeyword} can improve deadline control, workflow accuracy, and team coordination for law firms and in-house IP operations.`;
  }
  return `${primaryKeyword} can shape how startups protect innovation, manage cost, and prepare for future filings.`;
}

function workspaceFallbackImagePrompt(config: AppConfig): string {
  const workspaceId = String(config.workspaceId || "").trim().toLowerCase();
  if (workspaceId === "ip-docketers") {
    return "Professional editorial illustration of an IP operations team managing docketing software dashboards, deadline workflows, and patent prosecution calendars in a clean legal-tech office setting.";
  }
  return "Professional editorial illustration about patent filing strategy, innovation, startup IP protection, clean blue legal-tech visual.";
}

function workspaceArticleExampleInstruction(config: AppConfig): string {
  const workspaceId = String(config.workspaceId || "").trim().toLowerCase();
  if (workspaceId === "ip-docketers") {
    return "- include practical examples for law firms, docketing managers, and in-house IP teams";
  }
  return "- include practical examples for founders and inventors";
}

const outlineSchema = z.object({
  title: z.string().min(10),
  slug: z.string().min(5),
  metaTitle: z.string().min(20),
  metaDescription: z.string().min(80),
  excerpt: z.string().min(40),
  primaryKeyword: z.string().min(4),
  secondaryKeywords: z.array(z.string()).min(3).max(8),
  tags: z.array(z.string()).min(3).max(8),
  category: z.string().min(3),
  headingPlan: z.array(z.string()).min(6).max(12),
  faqQuestions: z.array(z.string()).min(3).max(6),
  cta: z.string().min(20),
  internalLinkTargets: z.array(z.string()).min(3).max(5),
  imagePrompt: z.string().min(20),
  imageAltText: z.string().min(12),
});

const articleSchema = z.object({
  title: z.string().min(10),
  slug: z.string().min(5),
  metaTitle: z.string().min(20),
  metaDescription: z.string().min(80),
  excerpt: z.string().min(40),
  primaryKeyword: z.string().min(4),
  secondaryKeywords: z.array(z.string()).min(3).max(8),
  tags: z.array(z.string()).min(3).max(8),
  category: z.string().min(3),
  articleHtml: z.string().min(800),
  faqSchemaJsonLd: z.string().min(20),
  imagePrompt: z.string().min(20),
  imageAltText: z.string().min(12),
});

function extractJson(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed.startsWith("```")) {
    return trimmed.replace(/^```(?:json)?/i, "").replace(/```$/i, "").trim();
  }
  const firstBrace = trimmed.indexOf("{");
  const lastBrace = trimmed.lastIndexOf("}");
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    return trimmed.slice(firstBrace, lastBrace + 1).trim();
  }
  return trimmed;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function unwrapModelPayload(value: unknown): Record<string, unknown> {
  let current = asRecord(value);
  const wrapperKeys = ["outline", "article", "data", "result", "payload", "contentBrief", "content_brief"];
  for (let depth = 0; depth < 3; depth += 1) {
    const nextKey = wrapperKeys.find((key) => current[key] && typeof current[key] === "object");
    if (!nextKey) break;
    current = asRecord(current[nextKey]);
  }
  return current;
}

function pickString(source: Record<string, unknown>, keys: string[], fallback = ""): string {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return fallback;
}

function pickStringArray(source: Record<string, unknown>, keys: string[], fallback: string[] = []): string[] {
  for (const key of keys) {
    const value = source[key];
    if (Array.isArray(value)) {
      return uniqueStrings(
        value
          .map((item) => String(item || "").trim())
          .filter(Boolean),
        8,
      );
    }
    if (typeof value === "string" && value.trim()) {
      return uniqueStrings(
        value
          .split(/\||,|;|\n/)
          .map((item) => item.trim())
          .filter(Boolean),
        8,
      );
    }
  }
  return fallback;
}

function normalizeOutlinePayload(raw: unknown, topic: TopicSelection, config: AppConfig): ArticleOutline {
  const source = unwrapModelPayload(raw);
  const primaryKeyword = pickString(source, ["primaryKeyword", "primary_keyword", "keyword", "focusKeyword"], topic.primaryKeyword);
  const title = pickString(
    source,
    ["title", "headline", "articleTitle", "article_title", "seoTitle"],
    workspaceFallbackTitle(topic, config),
  );
  const headingPlan = pickStringArray(source, ["headingPlan", "heading_plan", "headings"], workspaceFallbackHeadings(config));
  const faqQuestions = pickStringArray(source, ["faqQuestions", "faq_questions", "faqs"], workspaceFallbackFaqs(topic, config));
  const secondaryKeywords = pickStringArray(source, ["secondaryKeywords", "secondary_keywords", "supportingKeywords"], [
    ...topic.secondaryKeywords,
    ...topic.relatedSearches,
  ]).filter((item) => item.toLowerCase() !== primaryKeyword.toLowerCase());
  const tags = pickStringArray(source, ["tags", "tagList", "tag_list"], [
    ...workspaceDefaultTags(config, topic),
  ]);
  const internalLinkTargets = pickStringArray(source, ["internalLinkTargets", "internal_link_targets", "internalLinks"], [
    ...workspaceDefaultInternalTargets(config),
  ]);

  return {
    title,
    slug: slugify(pickString(source, ["slug", "urlSlug", "url_slug"], title)),
    metaTitle: pickString(source, ["metaTitle", "meta_title", "seoTitle"], title).slice(0, 65),
    metaDescription: pickString(
      source,
      ["metaDescription", "meta_description", "seoDescription"],
      workspaceFallbackMetaDescription(primaryKeyword, config),
    ),
    excerpt: pickString(
      source,
      ["excerpt", "summary", "introSummary"],
      workspaceFallbackExcerpt(primaryKeyword, config),
    ),
    primaryKeyword,
    secondaryKeywords: uniqueStrings(secondaryKeywords, 6).slice(0, 6),
    tags: uniqueStrings(tags, 6).slice(0, 6),
    category: pickString(source, ["category", "contentCategory"], config.defaultCategory),
    headingPlan: uniqueStrings(headingPlan, 8).slice(0, 8),
    faqQuestions: uniqueStrings(faqQuestions, 5).slice(0, 5),
    cta: pickString(
      source,
      ["cta", "callToAction", "call_to_action"],
      workspaceDefaultCta(config),
    ),
    internalLinkTargets: uniqueStrings(internalLinkTargets, 5).slice(0, 5),
    imagePrompt: pickString(
      source,
      ["imagePrompt", "image_prompt"],
      workspaceFallbackImagePrompt(config),
    ),
    imageAltText: pickString(
      source,
      ["imageAltText", "image_alt_text", "altText"],
      `${title} featured image for ${config.siteName}`,
    ),
  };
}

function normalizeArticlePayload(
  raw: unknown,
  topic: TopicSelection,
  outline: ArticleOutline,
  config: AppConfig,
): GeneratedArticle {
  const source = unwrapModelPayload(raw);
  const title = pickString(source, ["title", "headline", "articleTitle", "article_title"], outline.title);
  const primaryKeyword = pickString(
    source,
    ["primaryKeyword", "primary_keyword", "keyword", "focusKeyword"],
    outline.primaryKeyword || topic.primaryKeyword,
  );
  const articleHtml = pickString(source, ["articleHtml", "article_html", "html", "content"], "");
  const tags = pickStringArray(source, ["tags", "tagList", "tag_list"], outline.tags);
  const secondaryKeywords = pickStringArray(
    source,
    ["secondaryKeywords", "secondary_keywords", "supportingKeywords"],
    outline.secondaryKeywords,
  );

  return {
    title,
    slug: slugify(pickString(source, ["slug", "urlSlug", "url_slug"], outline.slug || title)),
    metaTitle: pickString(source, ["metaTitle", "meta_title", "seoTitle"], outline.metaTitle || title),
    metaDescription: pickString(
      source,
      ["metaDescription", "meta_description", "seoDescription"],
      outline.metaDescription,
    ),
    excerpt: pickString(source, ["excerpt", "summary", "introSummary"], outline.excerpt),
    primaryKeyword,
    secondaryKeywords: uniqueStrings(secondaryKeywords, 8).slice(0, 8),
    tags: uniqueStrings(tags, 8).slice(0, 8),
    category: pickString(source, ["category", "contentCategory"], outline.category || config.defaultCategory),
    articleHtml,
    faqSchemaJsonLd: pickString(
      source,
      ["faqSchemaJsonLd", "faq_schema_json_ld", "faqSchema", "faq_schema"],
      JSON.stringify({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        mainEntity: outline.faqQuestions.map((question) => ({
          "@type": "Question",
          name: question,
          acceptedAnswer: {
            "@type": "Answer",
            text: "Review the article guidance above and adapt the filing strategy to your timeline, invention scope, and budget.",
          },
        })),
      }),
    ),
    imagePrompt: pickString(source, ["imagePrompt", "image_prompt"], outline.imagePrompt),
    imageAltText: pickString(source, ["imageAltText", "image_alt_text", "altText"], outline.imageAltText),
  };
}

async function generateStructuredJson<T>(
  config: AppConfig,
  schema: z.ZodType<T>,
  logger: RunLogger,
  systemPrompt: string,
  userPrompt: string,
  normalizer?: (raw: unknown) => T,
): Promise<T> {
  const providerLabel = config.contentLlmProvider === "anthropic" ? "Anthropic" : "OpenAI";
  return withRetry(
    async () => {
      let content = "";
      if (config.contentLlmProvider === "anthropic") {
        const response = await fetch("https://api.anthropic.com/v1/messages", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-api-key": config.anthropicApiKey,
            "anthropic-version": "2023-06-01",
          },
          body: JSON.stringify({
            model: config.anthropicModel,
            max_tokens: 4200,
            temperature: 0.7,
            system: `${systemPrompt} Respond with JSON only. No markdown fences. No commentary outside the JSON object.`,
            messages: [
              {
                role: "user",
                content: `${userPrompt}\n\nReturn strict JSON only. Do not wrap it in markdown fences.`,
              },
            ],
          }),
        });

        if (!response.ok) {
          const body = await response.text();
          throw new Error(`Anthropic request failed (${response.status}): ${body}`);
        }

        const payload = (await response.json()) as {
          content?: Array<{ type?: string; text?: string }>;
        };
        content = (payload.content || [])
          .filter((item) => item.type === "text")
          .map((item) => item.text || "")
          .join("\n")
          .trim();
      } else {
        const client = new OpenAI({ apiKey: config.openAiApiKey });
        const response = await client.chat.completions.create({
          model: config.openAiModel,
          temperature: 0.7,
          response_format: { type: "json_object" },
          messages: [
            { role: "system", content: systemPrompt },
            { role: "user", content: userPrompt },
          ],
        });

        content = response.choices[0]?.message?.content || "";
      }

      if (!content) throw new Error(`${providerLabel} returned empty content`);
      const rawPayload = JSON.parse(extractJson(content));
      if (normalizer) {
        return schema.parse(normalizer(rawPayload));
      }
      return schema.parse(rawPayload);
    },
    {
      retries: 3,
      delayMs: 1800,
      onRetry: (attempt, error) =>
        logger.warn(`${providerLabel} retry ${attempt + 1}: ${error instanceof Error ? error.message : String(error)}`),
    },
  );
}

export async function generateArticle(
  config: AppConfig,
  logger: RunLogger,
  topic: TopicSelection,
): Promise<GeneratedArticle> {
  const systemPrompt = [
    `You are the editorial strategist and writer for ${config.siteName}.`,
    `Brand tone: ${config.brandTone}.`,
    workspaceAudienceGuidance(config),
    workspaceTopicGuidance(config),
    "Never say 'as an AI'.",
    "Do not invent legal citations, court decisions, or statistics.",
    "This article must be practical, authoritative, SEO-optimized, and readable.",
  ].join(" ");

  logger.step(`Generating SEO article outline with ${config.contentLlmProvider === "anthropic" ? "Anthropic" : "OpenAI"}...`);
  const outline = await generateStructuredJson<ArticleOutline>(
    config,
    outlineSchema,
    logger,
    `${systemPrompt} Return one flat JSON object with exactly these keys: title, slug, metaTitle, metaDescription, excerpt, primaryKeyword, secondaryKeywords, tags, category, headingPlan, faqQuestions, cta, internalLinkTargets, imagePrompt, imageAltText.`,
    [
      `Create a JSON-only content brief for a ${config.siteName} blog article.`,
      `Primary topic: ${topic.primaryKeyword}`,
      `Theme: ${topic.theme}`,
      `Intent cluster: ${topic.intentCluster}`,
      `Opportunity angle: ${topic.angle}`,
      `Source mix: ${topic.sourceTypes.join(", ")}`,
      `Evidence: ${topic.sourceEvidence.join(" | ")}`,
      `Related search ideas: ${topic.relatedSearches.join("; ")}`,
      `People also ask questions: ${topic.serpQuestions.join("; ")}`,
      "Return JSON only with this exact object shape:",
      `{"title":"","slug":"","metaTitle":"","metaDescription":"","excerpt":"","primaryKeyword":"","secondaryKeywords":[""],"tags":[""],"category":"","headingPlan":[""],"faqQuestions":[""],"cta":"","internalLinkTargets":[""],"imagePrompt":"","imageAltText":""}`,
      "Requirements:",
      "- 1200-1800 words final article target",
      "- choose a strong long-tail SEO title",
      "- meta title and description must be search-friendly",
      "- include 3-5 internal link targets as plain phrases",
      "- include an FAQ section plan",
      `- include one CTA aimed at ${config.siteName} consultations`,
      "- category should be specific but usable in WordPress",
    ].join("\n"),
    (raw) => normalizeOutlinePayload(raw, topic, config),
  );

  const normalizedOutline: ArticleOutline = {
    ...outline,
    slug: slugify(outline.slug || outline.title),
    category: outline.category || config.defaultCategory,
    secondaryKeywords: uniqueStrings(outline.secondaryKeywords, 6),
    tags: uniqueStrings(outline.tags, 6),
    internalLinkTargets: uniqueStrings(outline.internalLinkTargets, 5),
  };

  logger.step(`Generating final SEO article draft with ${config.contentLlmProvider === "anthropic" ? "Anthropic" : "OpenAI"}...`);
  const article = await generateStructuredJson<GeneratedArticle>(
    config,
    articleSchema,
    logger,
    `${systemPrompt} Return one flat JSON object with exactly these keys: title, slug, metaTitle, metaDescription, excerpt, primaryKeyword, secondaryKeywords, tags, category, articleHtml, faqSchemaJsonLd, imagePrompt, imageAltText.`,
    [
      "Write the final article as strict JSON only.",
      `Topic: ${topic.primaryKeyword}`,
      `Theme: ${topic.theme}`,
      `Intent cluster: ${topic.intentCluster}`,
      `Target title: ${normalizedOutline.title}`,
      `Meta title: ${normalizedOutline.metaTitle}`,
      `Meta description: ${normalizedOutline.metaDescription}`,
      `Heading plan: ${normalizedOutline.headingPlan.join(" | ")}`,
      `FAQ questions: ${normalizedOutline.faqQuestions.join(" | ")}`,
      `Secondary keywords: ${normalizedOutline.secondaryKeywords.join(" | ")}`,
      `CTA: ${normalizedOutline.cta}`,
      `Internal link placeholders needed for: ${normalizedOutline.internalLinkTargets.join(" | ")}`,
      "Return JSON only with this exact object shape:",
      `{"title":"","slug":"","metaTitle":"","metaDescription":"","excerpt":"","primaryKeyword":"","secondaryKeywords":[""],"tags":[""],"category":"","articleHtml":"","faqSchemaJsonLd":"","imagePrompt":"","imageAltText":""}`,
      "Article rules:",
      "- articleHtml must be valid HTML with one <h1> and multiple <h2>/<h3> headings",
      workspaceArticleExampleInstruction(config),
      "- include a checklist or a simple HTML table where useful",
      "- include an FAQ section near the end",
      "- add 3-5 placeholders in this exact format: <!-- INTERNAL_LINK:target phrase -->",
      "- include this disclaimer verbatim near the end: This article is for informational purposes only and does not constitute legal advice.",
      `- include a clear CTA for ${config.siteName} in the conclusion`,
      "- keep tone human, confident, and practical",
      "- return faqSchemaJsonLd as a JSON-LD string with FAQPage markup",
    ].join("\n"),
    (raw) => normalizeArticlePayload(raw, topic, normalizedOutline, config),
  );

  return {
    ...article,
    slug: slugify(article.slug || normalizedOutline.slug || article.title),
    category: article.category || normalizedOutline.category || config.defaultCategory,
    tags: uniqueStrings(article.tags, 8),
    secondaryKeywords: uniqueStrings(article.secondaryKeywords, 8),
  };
}

export async function rewriteArticleForSeo(
  config: AppConfig,
  logger: RunLogger,
  topic: TopicSelection,
  article: GeneratedArticle,
  blockers: string[],
): Promise<GeneratedArticle> {
  const systemPrompt = [
    `You are the senior SEO editor for ${config.siteName}.`,
    `Brand tone: ${config.brandTone}.`,
    workspaceAudienceGuidance(config),
    workspaceTopicGuidance(config),
    "You repair near-complete blog drafts so they can pass publish-quality SEO checks.",
    "Never say 'as an AI'.",
    "Do not invent legal citations, court decisions, or statistics.",
    "Preserve the core topic, improve quality, and return JSON only.",
  ].join(" ");

  logger.step(
    `Running one automatic SEO rewrite pass with ${config.contentLlmProvider === "anthropic" ? "Anthropic" : "OpenAI"}...`,
  );

  const rewritten = await generateStructuredJson<GeneratedArticle>(
    config,
    articleSchema,
    logger,
    `${systemPrompt} Return one flat JSON object with exactly these keys: title, slug, metaTitle, metaDescription, excerpt, primaryKeyword, secondaryKeywords, tags, category, articleHtml, faqSchemaJsonLd, imagePrompt, imageAltText.`,
    [
      `Rewrite the following ${config.siteName} article draft so it clears all publish checks.`,
      `Primary keyword: ${article.primaryKeyword || topic.primaryKeyword}`,
      `Required blockers to fix: ${blockers.join(" | ")}`,
      `Current title: ${article.title}`,
      `Current meta title: ${article.metaTitle}`,
      `Current meta description: ${article.metaDescription}`,
      `Current slug: ${article.slug}`,
      `Current category: ${article.category || config.defaultCategory}`,
      `Secondary keywords: ${(article.secondaryKeywords || []).join(" | ")}`,
      `Current tags: ${(article.tags || []).join(" | ")}`,
      "Current article HTML:",
      article.articleHtml,
      "Return JSON only with this exact object shape:",
      `{"title":"","slug":"","metaTitle":"","metaDescription":"","excerpt":"","primaryKeyword":"","secondaryKeywords":[""],"tags":[""],"category":"","articleHtml":"","faqSchemaJsonLd":"","imagePrompt":"","imageAltText":""}`,
      "Rewrite rules:",
      "- Keep the same core topic and audience",
      "- Use the exact primary keyword naturally in the title and intro",
      "- Meta title must be 60 characters or fewer",
      "- Meta description must be 120-160 characters",
      "- articleHtml must be valid HTML with exactly one <h1>, several <h2>/<h3>, and at least 1200 words",
      "- Include a clear FAQ section with an <h2> heading containing 'Frequently Asked Questions'",
      "- Include 3-5 placeholders in this exact format: <!-- INTERNAL_LINK:target phrase -->",
      "- Include a practical checklist or simple HTML table",
      "- Include at least one external reference link to an authoritative source such as USPTO or WIPO when useful",
      "- Include this disclaimer verbatim near the end: This article is for informational purposes only and does not constitute legal advice.",
      `- Include a clear ${config.siteName} CTA in the conclusion`,
      "- Return faqSchemaJsonLd as a valid FAQPage JSON-LD string",
    ].join("\n"),
    (raw) =>
      normalizeArticlePayload(
        raw,
        topic,
        {
          title: article.title,
          slug: article.slug,
          metaTitle: article.metaTitle,
          metaDescription: article.metaDescription,
          excerpt: article.excerpt,
          primaryKeyword: article.primaryKeyword,
          secondaryKeywords: article.secondaryKeywords,
          tags: article.tags,
          category: article.category || config.defaultCategory,
          headingPlan: [],
          faqQuestions: [],
          cta: workspaceDefaultCta(config),
          internalLinkTargets: workspaceDefaultInternalTargets(config),
          imagePrompt: article.imagePrompt,
          imageAltText: article.imageAltText,
        },
        config,
      ),
  );

  return {
    ...rewritten,
    slug: slugify(rewritten.slug || article.slug || rewritten.title),
    category: rewritten.category || article.category || config.defaultCategory,
    tags: uniqueStrings(rewritten.tags, 8),
    secondaryKeywords: uniqueStrings(rewritten.secondaryKeywords, 8),
  };
}
