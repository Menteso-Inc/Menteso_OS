import { existsSync } from "node:fs";
import { join } from "node:path";

import type { WorkerSettings } from "../config";

export type SeoAgentRuntime = ReturnType<typeof loadSeoAgentRuntime>;

export function loadSeoAgentRuntime(settings: WorkerSettings) {
  if (!existsSync(settings.seoAgentDist)) {
    throw new Error(
      `PatentZoom SEO agent dist folder not found at ${settings.seoAgentDist}. Run the SEO agent build first.`,
    );
  }

  const requireFromDist = (file: string) => require(join(settings.seoAgentDist, file));

  return {
    config: requireFromDist("config.js"),
    topicEngine: requireFromDist("topicEngine.js"),
    openaiContent: requireFromDist("openaiContent.js"),
    seoOptimizer: requireFromDist("seoOptimizer.js"),
    internalLinks: requireFromDist("internalLinks.js"),
    wordpressClient: requireFromDist("wordpressClient.js"),
    imageGenerator: requireFromDist("imageGenerator.js"),
    indexing: requireFromDist("indexing.js"),
    textUtils: requireFromDist("textUtils.js"),
  };
}
