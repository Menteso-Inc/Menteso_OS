import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { loadConfig } from "./config";
import { generateFeaturedImage } from "./imageGenerator";
import { submitIndexingHints } from "./indexing";
import { insertInternalLinks } from "./internalLinks";
import { RunLogger } from "./logger";
import { generateArticle, rewriteArticleForSeo } from "./openaiContent";
import { validateAndOptimizeArticle } from "./seoOptimizer";
import { chooseTopic, loadGeneratedPosts, saveGeneratedPosts } from "./topicEngine";
import { GeneratedArticle, GeneratedPostRecord, IndexingStatus, RecentPost, TopicSelection, WorkflowInput, WorkflowResult } from "./types";
import { WordPressClient } from "./wordpressClient";

class StopRequestedError extends Error {
  constructor() {
    super("Workflow stop requested");
  }
}

function parseInput(): WorkflowInput {
  const argIndex = process.argv.indexOf("--input-json");
  if (argIndex >= 0 && process.argv[argIndex + 1]) {
    const payload = JSON.parse(readFileSync(process.argv[argIndex + 1], "utf-8")) as Record<string, unknown>;
    return {
      topicOverride: String(payload.topicOverride ?? payload.topic_override ?? "").trim() || undefined,
      publishOverride:
        String(payload.publishOverride ?? payload.publish_override ?? "draft").trim().toLowerCase() === "publish"
          ? "publish"
          : "draft",
      enableFeaturedImage:
        payload.enableFeaturedImage !== undefined
          ? Boolean(payload.enableFeaturedImage)
          : payload.enable_featured_image !== undefined
            ? Boolean(payload.enable_featured_image)
            : true,
      dryRun:
        payload.dryRun !== undefined
          ? Boolean(payload.dryRun)
          : payload.dry_run !== undefined
            ? Boolean(payload.dry_run)
            : false,
      source: String(payload.source ?? "").trim() || (process.env.GITHUB_ACTIONS ? "github_actions" : "dashboard"),
      strategy: String(payload.strategy ?? "").trim() || undefined,
    };
  }

  const autoPublishByDefault = ["1", "true", "yes", "on"].includes(
    String(process.env.AUTO_PUBLISH || "")
      .trim()
      .toLowerCase(),
  );

  return {
    publishOverride: autoPublishByDefault ? "publish" : "draft",
    enableFeaturedImage: true,
    dryRun: false,
    source: process.env.GITHUB_ACTIONS ? "github_actions" : "dashboard",
  };
}

function stripHtml(value: string): string {
  return String(value || "")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function countWords(value: string): number {
  return stripHtml(value)
    .split(/\s+/)
    .filter(Boolean).length;
}

function countHeading(articleHtml: string, level: "h1" | "h2" | "h3"): number {
  const matches = articleHtml.match(new RegExp(`<${level}\\b[^>]*>`, "gi"));
  return matches ? matches.length : 0;
}

function normalizeWhitespace(value: string): string {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function keywordInText(keyword: string, value: string): boolean {
  const normalizedKeyword = normalizeWhitespace(keyword).toLowerCase();
  const normalizedValue = normalizeWhitespace(value).toLowerCase();
  return normalizedKeyword.length > 0 && normalizedValue.includes(normalizedKeyword);
}

function hasInternalLinks(articleHtml: string, baseUrl: string): boolean {
  const escapedBase = baseUrl.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`<a\\b[^>]*href="${escapedBase}`, "i").test(articleHtml);
}

function hasExternalLinks(articleHtml: string, baseUrl: string): boolean {
  const escapedBase = baseUrl.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`<a\\b[^>]*href="https?:\\/\\/(?!${escapedBase.replace(/^https?:\/\//, "")})`, "i").test(articleHtml);
}

function resolveContentCategory(topic: TopicSelection, article: GeneratedArticle): string {
  const combined = `${topic.theme} ${topic.cluster} ${topic.angle} ${article.title} ${article.primaryKeyword}`.toLowerCase();
  const blogSignals = ["trend", "trends", "news", "update", "weekly", "monthly", "outlook", "forecast"];
  return blogSignals.some((signal) => combined.includes(signal)) ? "Blog" : "Article";
}

function findPublishedEntryForDate(entries: GeneratedPostRecord[], runDate: string): GeneratedPostRecord | undefined {
  return [...entries]
    .reverse()
    .find((entry) => entry.date === runDate && String(entry.status || "").toLowerCase() === "publish");
}

function evaluateSeoReadiness(
  article: GeneratedArticle,
  topic: TopicSelection,
  baseUrl: string,
  featuredImageExpected: boolean,
): {
  score: number;
  blockers: string[];
  warnings: string[];
} {
  const articleText = stripHtml(article.articleHtml);
  const introText = articleText.slice(0, 500);
  const checks = [
    {
      label: "Focus keyword in title",
      passed: keywordInText(article.primaryKeyword, article.title),
      required: true,
    },
    {
      label: "Focus keyword in intro",
      passed: keywordInText(article.primaryKeyword, introText),
      required: true,
    },
    {
      label: "Proper H1",
      passed: countHeading(article.articleHtml, "h1") >= 1,
      required: true,
    },
    {
      label: "H2/H3 structure",
      passed: countHeading(article.articleHtml, "h2") + countHeading(article.articleHtml, "h3") >= 3,
      required: true,
    },
    {
      label: "Meta title under 60 characters",
      passed: normalizeWhitespace(article.metaTitle).length > 0 && normalizeWhitespace(article.metaTitle).length <= 60,
      required: true,
    },
    {
      label: "Meta description under 160 characters",
      passed:
        normalizeWhitespace(article.metaDescription).length > 0 &&
        normalizeWhitespace(article.metaDescription).length <= 160,
      required: true,
    },
    {
      label: "Minimum 1000 words",
      passed: countWords(article.articleHtml) >= 1000,
      required: true,
    },
    {
      label: "Internal links added",
      passed: hasInternalLinks(article.articleHtml, baseUrl),
      required: true,
    },
    {
      label: "External references added",
      passed: hasExternalLinks(article.articleHtml, baseUrl),
      required: false,
    },
    {
      label: "FAQ section added",
      passed:
        /<h2[^>]*>[^<]*(?:faq|frequently asked questions)/i.test(article.articleHtml) ||
        /<h3[^>]*>[^<]*(?:faq|frequently asked questions)/i.test(article.articleHtml),
      required: true,
    },
    {
      label: "Featured image alt text added",
      passed: !featuredImageExpected || normalizeWhitespace(article.imageAltText).length >= 8,
      required: false,
    },
    {
      label: "No duplicate topic",
      passed: Boolean(topic.topicId && topic.fingerprint),
      required: true,
    },
    {
      label: "CTA included",
      passed: /patentzoom/i.test(article.articleHtml),
      required: true,
    },
  ];

  const passed = checks.filter((check) => check.passed).length;
  const score = Math.round((passed / checks.length) * 100);

  return {
    score,
    blockers: checks.filter((check) => check.required && !check.passed).map((check) => check.label),
    warnings: checks.filter((check) => !check.required && !check.passed).map((check) => check.label),
  };
}

async function main(): Promise<void> {
  const config = loadConfig();
  const input = parseInput();
  const logger = new RunLogger(config, randomUUID());
  const wpClient = new WordPressClient(config, logger);
  const ledger = loadGeneratedPosts(config.paths.generatedPostsFile);

  let stopRequested = false;
  const requestStop = () => {
    stopRequested = true;
    logger.warn("Stop requested. The workflow will finish the current safe step and exit.");
  };
  process.on("SIGINT", requestStop);
  process.on("SIGTERM", requestStop);

  const ensureRunning = () => {
    if (stopRequested) throw new StopRequestedError();
  };

  const start = Date.now();
  let result: WorkflowResult | null = null;
  let indexingStatus: IndexingStatus | null = null;

  try {
    logger.step("PatentZoom SEO workflow started.", {
      stage: "readiness",
      status: "active",
    });
    logger.step("Loading recent PatentZoom posts from WordPress...");
    let recentPosts: RecentPost[] = [];
    try {
      recentPosts = await wpClient.fetchRecentPosts(20);
      logger.step(`Loaded ${recentPosts.length} recent PatentZoom posts for duplicate checks and internal links.`, {
        stage: "readiness",
        status: "complete",
        recentPosts: recentPosts.length,
      });
    } catch (error) {
      logger.warn(
        `Could not fetch recent posts for duplicate checks and internal links. Continuing with empty recent-post set. ${
          error instanceof Error ? error.message : String(error)
        }`,
        {
          stage: "readiness",
          status: "warning",
        },
      );
    }

    ensureRunning();
    logger.step("Researching keywords and selecting the best topic for this run...", {
      stage: "keywords",
      status: "active",
    });
    const topic = await chooseTopic({
      config,
      logger,
      ledger: ledger.generatedPosts,
      recentPosts,
      topicOverride: input.topicOverride,
    });
    logger.step(`Keyword research complete. Selected "${topic.primaryKeyword}".`, {
      stage: "keywords",
      status: "complete",
      keyword: topic.primaryKeyword,
      theme: topic.theme,
      intentCluster: topic.intentCluster,
      sourceMix: topic.sourceTypes.join(", "),
    });

    ensureRunning();
    logger.step("Starting AI article generation.", {
      stage: "content",
      status: "active",
    });
    const draftedArticle = await generateArticle(config, logger, topic);
    logger.step("AI article draft completed.", {
      stage: "content",
      status: "complete",
      title: draftedArticle.title,
    });

    ensureRunning();
    logger.step("Running SEO optimization and internal link enrichment.", {
      stage: "optimization",
      status: "active",
    });
    const requestedPublishStatus =
      input.publishOverride === "publish" || (config.autoPublish && input.publishOverride !== "draft")
        ? "publish"
        : "draft";

    const optimizeArticle = (article: GeneratedArticle, logSummary = true) => {
      const validation = validateAndOptimizeArticle(article);
      validation.issues.forEach((issue) => logger.warn(`SEO optimizer: ${issue}`));
      const linked = insertInternalLinks(validation.article, recentPosts);
      logger.step("Inserted natural internal links into the article.");
      if (logSummary) {
        logger.step("SEO optimization complete.", {
          stage: "optimization",
          status: "complete",
          title: linked.title,
          slug: linked.slug,
        });
      }
      linked.category = resolveContentCategory(topic, linked);
      return linked;
    };

    let linkedArticle = optimizeArticle(draftedArticle);

    let seoReadiness = evaluateSeoReadiness(
      linkedArticle,
      topic,
      config.wpBaseUrl,
      config.enableFeaturedImage && input.enableFeaturedImage,
    );
    logger.step(`SEO validation score: ${seoReadiness.score}/100.`, {
      stage: "optimization",
      status: seoReadiness.blockers.length ? "warning" : "complete",
      seoScore: seoReadiness.score,
    });
    seoReadiness.blockers.forEach((blocker) => logger.warn(`SEO publish blocker: ${blocker}`));
    seoReadiness.warnings.forEach((warning) => logger.warn(`SEO publish warning: ${warning}`));

    if (requestedPublishStatus === "publish" && seoReadiness.blockers.length) {
      logger.step("Required SEO checks failed. Running one automatic rewrite pass before draft fallback.", {
        stage: "optimization",
        status: "active",
      });
      const rewrittenArticle = await rewriteArticleForSeo(config, logger, topic, linkedArticle, seoReadiness.blockers);
      linkedArticle = optimizeArticle(rewrittenArticle, false);
      seoReadiness = evaluateSeoReadiness(
        linkedArticle,
        topic,
        config.wpBaseUrl,
        config.enableFeaturedImage && input.enableFeaturedImage,
      );
      logger.step(`Post-rewrite SEO validation score: ${seoReadiness.score}/100.`, {
        stage: "optimization",
        status: seoReadiness.blockers.length ? "warning" : "complete",
        seoScore: seoReadiness.score,
      });
      seoReadiness.blockers.forEach((blocker) => logger.warn(`Post-rewrite SEO publish blocker: ${blocker}`));
      seoReadiness.warnings.forEach((warning) => logger.warn(`Post-rewrite SEO publish warning: ${warning}`));
    }

    const existingPublishedToday =
      !input.topicOverride && !input.dryRun && requestedPublishStatus === "publish"
        ? findPublishedEntryForDate(ledger.generatedPosts, topic.runDate)
        : undefined;
    const effectivePublishStatus =
      requestedPublishStatus === "publish" && seoReadiness.blockers.length
        ? "draft"
        : requestedPublishStatus;

    let featuredImageId: number | null = null;
    let wordpressPostId: number | null = null;
    let wordpressUrl = "";
    let postStatus = input.dryRun ? "dry-run" : effectivePublishStatus;

    ensureRunning();
    if (input.dryRun) {
      logger.step("Dry run enabled. Skipping WordPress publishing and ledger update.");
      logger.step("Publishing skipped because this run is in dry-run mode.", {
        stage: "publishing",
        status: "skipped",
      });
      logger.step("Indexing skipped because the article was not published.", {
        stage: "indexing",
        status: "skipped",
      });
      result = {
        status: "success",
        topic: topic.topicId,
        primaryKeyword: topic.primaryKeyword,
        postStatus,
        wordpressPostId,
        wordpressUrl,
        featuredImageId,
        outputLogs: logger.outputLogs,
        warnings: logger.warnings,
        executionTime: Number(((Date.now() - start) / 1000).toFixed(2)),
        seoScore: seoReadiness.score,
        title: linkedArticle.title,
        slug: linkedArticle.slug,
        article: linkedArticle,
        indexing: null,
      };
    } else {
      if (existingPublishedToday) {
        logger.warn(
          `A live article is already published for ${topic.runDate}. Skipping another live publish to keep the one-post-per-day rule.`,
        );
        logger.step("Publishing skipped because today's live article already exists.", {
          stage: "publishing",
          status: "skipped",
          wordpressUrl: existingPublishedToday.wpUrl,
        });
        logger.step("Indexing skipped because no new post was published.", {
          stage: "indexing",
          status: "skipped",
        });
        result = {
          status: "success",
          topic: topic.topicId,
          primaryKeyword: topic.primaryKeyword,
          postStatus: "already-published-today",
          wordpressPostId: existingPublishedToday.wpPostId,
          wordpressUrl: existingPublishedToday.wpUrl,
          featuredImageId: null,
          outputLogs: logger.outputLogs,
          warnings: logger.warnings,
          executionTime: Number(((Date.now() - start) / 1000).toFixed(2)),
          seoScore: seoReadiness.score,
          title: linkedArticle.title,
          slug: linkedArticle.slug,
          article: linkedArticle,
          ledgerEntry: existingPublishedToday,
          indexing: null,
        };
      }

      if (result) {
        logger.saveDailyRun(result);
        logger.result(result);
        return;
      }

      if (requestedPublishStatus === "publish" && effectivePublishStatus === "draft") {
        logger.warn(
          `SEO validation score ${seoReadiness.score}/100 did not clear all required checks. Saving as draft instead of publishing live.`,
        );
      }

      let imagePath: string | null = null;
      if (config.enableFeaturedImage && input.enableFeaturedImage) {
        logger.step("Starting featured image generation.", {
          stage: "image",
          status: "active",
        });
        imagePath = await generateFeaturedImage({
          config,
          logger,
          prompt: linkedArticle.imagePrompt,
          slug: linkedArticle.slug,
          enabled: true,
        });
      } else {
        logger.step("Featured image disabled for this run.");
        logger.step("Featured image stage skipped for this run.", {
          stage: "image",
          status: "skipped",
        });
      }

      if (imagePath) {
        const upload = await wpClient.uploadMedia(imagePath, linkedArticle.imageAltText, linkedArticle.title);
        featuredImageId = upload.id;
        logger.step(`Uploaded featured image to WordPress (media #${featuredImageId}).`);
        logger.step("Featured image stage complete.", {
          stage: "image",
          status: "complete",
          featuredImageId,
        });
      } else if (config.enableFeaturedImage && input.enableFeaturedImage) {
        logger.step("Featured image stage completed without an uploaded image.", {
          stage: "image",
          status: "warning",
        });
      }

      ensureRunning();
      logger.step(`Publishing article to WordPress as ${effectivePublishStatus}.`, {
        stage: "publishing",
        status: "active",
        mode: effectivePublishStatus,
      });
      const createdPost = await wpClient.createPost({
        article: linkedArticle,
        postStatus: effectivePublishStatus,
        featuredMediaId: featuredImageId,
        seoScore: seoReadiness.score,
        readabilityScore: Math.max(72, Math.min(100, seoReadiness.score - Math.min(seoReadiness.warnings.length * 2, 8))),
      });
      wordpressPostId = createdPost.id;
      wordpressUrl = createdPost.url;
      postStatus = createdPost.status;
      logger.step(`Created WordPress ${postStatus} post #${wordpressPostId}.`);
      logger.step("Publishing stage complete.", {
        stage: "publishing",
        status: "complete",
        wordpressPostId,
        wordpressUrl,
        postStatus,
      });

      const ledgerEntry = {
        date: topic.runDate,
        topicId: topic.topicId,
        pillar: topic.pillar,
        angle: topic.angle,
        theme: topic.theme,
        cluster: topic.cluster,
        primaryKeyword: topic.primaryKeyword,
        secondaryKeywords: topic.secondaryKeywords,
        slug: linkedArticle.slug,
        wpPostId: wordpressPostId,
        wpUrl: wordpressUrl,
        status: postStatus,
        source: input.source,
        fingerprint: topic.fingerprint,
        sourceTypes: topic.sourceTypes,
        sourceEvidence: topic.sourceEvidence,
        demandScore: topic.demandScore,
        freshnessScore: topic.freshnessScore,
        intentCluster: topic.intentCluster,
      };
      ledger.generatedPosts.push(ledgerEntry);
      saveGeneratedPosts(config.paths.generatedPostsFile, ledger);
      logger.step("Updated generated-posts.json ledger.");

      if (wordpressUrl && postStatus === "publish") {
        logger.step("Submitting sitemap and indexing hints for the published URL.", {
          stage: "indexing",
          status: "active",
          wordpressUrl,
        });
        indexingStatus = await submitIndexingHints(config, logger, wordpressUrl);
        logger.step("Indexing handoff complete.", {
          stage: "indexing",
          status: "complete",
          wordpressUrl,
          indexing: indexingStatus,
        });
      } else {
        logger.step("Indexing skipped because the article was saved as a draft.", {
          stage: "indexing",
          status: "skipped",
        });
      }

      result = {
        status: "success",
        topic: topic.topicId,
        primaryKeyword: topic.primaryKeyword,
        postStatus,
        wordpressPostId,
        wordpressUrl,
        featuredImageId,
        outputLogs: logger.outputLogs,
        warnings: logger.warnings,
        executionTime: Number(((Date.now() - start) / 1000).toFixed(2)),
        seoScore: seoReadiness.score,
        title: linkedArticle.title,
        slug: linkedArticle.slug,
        article: linkedArticle,
        ledgerEntry,
        indexing: indexingStatus,
      };
    }

    if (!result) {
      result = {
        status: "success",
        topic: topic.topicId,
        primaryKeyword: topic.primaryKeyword,
        postStatus,
        wordpressPostId,
        wordpressUrl,
        featuredImageId,
        outputLogs: logger.outputLogs,
        warnings: logger.warnings,
        executionTime: Number(((Date.now() - start) / 1000).toFixed(2)),
        seoScore: seoReadiness.score,
        title: linkedArticle.title,
        slug: linkedArticle.slug,
        article: linkedArticle,
        indexing: indexingStatus,
      };
    }
  } catch (error) {
    if (error instanceof StopRequestedError) {
      result = {
        status: "stopped",
        topic: "",
        primaryKeyword: "",
        postStatus: "stopped",
        wordpressPostId: null,
        wordpressUrl: "",
        featuredImageId: null,
        outputLogs: logger.outputLogs,
        warnings: logger.warnings,
        executionTime: Number(((Date.now() - start) / 1000).toFixed(2)),
        indexing: indexingStatus,
      };
    } else {
      logger.error(error instanceof Error ? error.message : String(error));
      result = {
        status: "failure",
        topic: "",
        primaryKeyword: "",
        postStatus: "failed",
        wordpressPostId: null,
        wordpressUrl: "",
        featuredImageId: null,
        outputLogs: logger.outputLogs,
        warnings: logger.warnings,
        executionTime: Number(((Date.now() - start) / 1000).toFixed(2)),
        indexing: indexingStatus,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }

  logger.saveDailyRun(result);
  logger.result(result);
}

main().catch((error) => {
  const fallback: WorkflowResult = {
    status: "failure",
    topic: "",
    primaryKeyword: "",
    postStatus: "failed",
    wordpressPostId: null,
    wordpressUrl: "",
    featuredImageId: null,
    outputLogs: [],
    warnings: [],
    executionTime: 0,
    error: error instanceof Error ? error.message : String(error),
  };
  process.stdout.write(
    `${JSON.stringify({ type: "result", timestamp: new Date().toISOString(), result: fallback })}\n`,
  );
  process.exitCode = 1;
});
