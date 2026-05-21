import { describe, expect, it, vi } from "vitest";

const generateMock = vi.fn().mockRejectedValue(new Error("image failure"));

vi.mock("openai", () => {
  return {
    default: class OpenAI {
      images = {
        generate: generateMock,
      };
    },
  };
});

import { generateFeaturedImage } from "../imageGenerator";

describe("imageGenerator", () => {
  it("continues without image when generation fails", async () => {
    const result = await generateFeaturedImage({
      config: {
        openAiApiKey: "key",
        paths: {
          imagesDir: "runtime/images",
        },
      } as any,
      logger: {
        step: vi.fn(),
        warn: vi.fn(),
      } as any,
      prompt: "Prompt",
      slug: "sample-image",
      enabled: true,
    });

    expect(result).toBeNull();
  });
});

