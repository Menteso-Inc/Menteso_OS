import { writeFileSync } from "node:fs";
import { join } from "node:path";
import OpenAI from "openai";
import { AppConfig } from "./config";
import { RunLogger } from "./logger";

export async function generateFeaturedImage(args: {
  config: AppConfig;
  logger: RunLogger;
  prompt: string;
  slug: string;
  enabled: boolean;
}): Promise<string | null> {
  const { config, logger, prompt, slug, enabled } = args;
  if (!enabled) {
    logger.step("Featured image generation disabled for this run.");
    return null;
  }

  try {
    const client = new OpenAI({ apiKey: config.openAiApiKey });
    logger.step("Generating featured image with OpenAI...");
    const response = await client.images.generate({
      model: "gpt-image-1",
      prompt,
      size: "1536x1024",
    });

    const imageBase64 = response.data?.[0]?.b64_json;
    if (!imageBase64) {
      throw new Error("Image API returned no image data");
    }

    const filePath = join(config.paths.imagesDir, `${slug}.png`);
    writeFileSync(filePath, Buffer.from(imageBase64, "base64"));
    logger.step(`Featured image saved locally: ${filePath}`);
    return filePath;
  } catch (error) {
    logger.warn(
      `Featured image generation failed. Continuing without image. ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
    return null;
  }
}
