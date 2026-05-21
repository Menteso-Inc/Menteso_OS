import type { WorkerSettings } from "../config";
import { loadSeoAgentRuntime } from "../lib/agent-runtime";
import { saveJobResult } from "../lib/result-store";
import type { WorkerLogger } from "../lib/worker-logger";

type JobInput = {
  inputRef?: string;
  payload?: {
    article?: {
      title: string;
      slug: string;
      metaTitle: string;
      metaDescription: string;
      excerpt: string;
      primaryKeyword: string;
      secondaryKeywords: string[];
      tags: string[];
      category: string;
      articleHtml: string;
      faqSchemaJsonLd: string;
      imagePrompt: string;
      imageAltText: string;
    };
    topicOverride?: string;
    keyword?: string;
    publishOverride?: "draft" | "publish";
    enableFeaturedImage?: boolean;
  };
};

export async function runPublishingJob(settings: WorkerSettings, logger: WorkerLogger, input: JobInput, jobId: string) {
  const runtime = loadSeoAgentRuntime(settings);
  const config = runtime.config.loadConfig();
  const wpClient = new runtime.wordpressClient.WordPressClient(config, logger);
  const ledger = runtime.topicEngine.loadGeneratedPosts(config.paths.generatedPostsFile);
  const recentPosts = await wpClient.fetchRecentPosts(20).catch(() => []);

  let topic = null;
  let article = input.payload?.article || null;
  if (!article) {
    topic = await runtime.topicEngine.chooseTopic({
      config,
      logger,
      ledger: ledger.generatedPosts,
      recentPosts,
      topicOverride: input.payload?.topicOverride || input.payload?.keyword,
    });
    const draftedArticle = await runtime.openaiContent.generateArticle(config, logger, topic);
    const validation = runtime.seoOptimizer.validateAndOptimizeArticle(draftedArticle);
    validation.issues.forEach((issue: string) => logger.warn(`SEO optimizer: ${issue}`));
    article = runtime.internalLinks.insertInternalLinks(validation.article, recentPosts);
  }

  if (!article) {
    throw new Error("Publishing job could not resolve an article payload");
  }

  const postStatus =
    input.payload?.publishOverride === "publish" || (config.autoPublish && input.payload?.publishOverride !== "draft")
      ? "publish"
      : "draft";

  let featuredImageId: number | null = null;
  if (config.enableFeaturedImage && input.payload?.enableFeaturedImage !== false && article.imagePrompt) {
    const imagePath = await runtime.imageGenerator.generateFeaturedImage({
      config,
      logger,
      prompt: article.imagePrompt,
      slug: article.slug,
      enabled: true,
    });
    if (imagePath) {
      const upload = await wpClient.uploadMedia(imagePath, article.imageAltText, article.title);
      featuredImageId = upload.id;
      logger.step(`Featured image uploaded (media #${featuredImageId}).`);
    }
  } else {
    logger.step("Publishing without a featured image.");
  }

  const createdPost = await wpClient.createPost({
    article,
    postStatus,
    featuredMediaId: featuredImageId,
  });

  if (topic) {
    ledger.generatedPosts.push({
      date: topic.runDate,
      topicId: topic.topicId,
      pillar: topic.pillar,
      angle: topic.angle,
      primaryKeyword: topic.primaryKeyword,
      secondaryKeywords: topic.secondaryKeywords,
      slug: article.slug,
      wpPostId: createdPost.id,
      wpUrl: createdPost.url,
      status: createdPost.status,
      source: "seo_worker",
      fingerprint: topic.fingerprint,
    });
    runtime.topicEngine.saveGeneratedPosts(config.paths.generatedPostsFile, ledger);
    logger.step("Updated PatentZoom generated-posts ledger.");
  }

  if (createdPost.url && createdPost.status === "publish") {
    await runtime.indexing.submitIndexingHints(config, logger, createdPost.url);
  }

  const result = {
    status: "success",
    jobType: "publishing",
    postStatus: createdPost.status,
    wordpressPostId: createdPost.id,
    wordpressUrl: createdPost.url,
    featuredImageId,
    articleTitle: article.title,
    slug: article.slug,
    warnings: logger.warnings,
    outputLogs: logger.outputLogs,
  };
  const resultPath = saveJobResult(settings, jobId, result);
  logger.step(`Publishing job finished for post #${createdPost.id}.`);
  return { ...result, outputRef: resultPath };
}
