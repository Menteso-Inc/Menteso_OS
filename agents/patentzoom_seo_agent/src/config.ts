import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import dotenv from "dotenv";
import { z } from "zod";

const agentRoot = resolve(__dirname, "..");
const projectRoot = resolve(agentRoot, "..", "..");

dotenv.config({ path: resolve(projectRoot, ".env") });

const schema = z.object({
  OPENAI_API_KEY: z.string().optional().default(""),
  OPENAI_MODEL: z.string().min(1).default("gpt-4.1-mini"),
  ANTHROPIC_API_KEY: z.string().optional().default(""),
  ANTHROPIC_MODEL: z.string().min(1).default("claude-sonnet-4-20250514"),
  CONTENT_LLM_PROVIDER: z.enum(["openai", "anthropic"]).optional().default("openai"),
  WP_BASE_URL: z.string().url("WP_BASE_URL must be a valid URL"),
  WP_USERNAME: z.string().optional().default(""),
  WP_APPLICATION_PASSWORD: z.string().optional().default(""),
  AUTO_PUBLISH: z.string().optional().default("false"),
  SITE_NAME: z.string().optional().default("PatentZoom"),
  BRAND_TONE: z.string().optional().default("Professional, authoritative, practical, helpful"),
  DEFAULT_CATEGORY: z.string().optional().default("Patent Filing"),
  DEFAULT_AUTHOR: z.string().optional().default(""),
  ENABLE_FEATURED_IMAGE: z.string().optional().default("true"),
  ENABLE_GOOGLE_INDEXING: z.string().optional().default("false"),
  GOOGLE_SERVICE_ACCOUNT_JSON: z.string().optional().default(""),
  GOOGLE_OAUTH_CLIENT_ID: z.string().optional().default(""),
  GOOGLE_OAUTH_CLIENT_SECRET: z.string().optional().default(""),
  GOOGLE_OAUTH_REFRESH_TOKEN: z.string().optional().default(""),
  GOOGLE_SEARCH_CONSOLE_PROPERTY: z.string().optional().default("sc-domain:patentzoom.us"),
  SERPAPI_API_KEY: z.string().optional().default(""),
});

function toBool(value: string): boolean {
  return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
}

function normalizeSecret(value: string | undefined | null): string {
  return String(value ?? "").trim();
}

function isPlaceholderSecret(value: string | undefined | null): boolean {
  const normalized = normalizeSecret(value).toLowerCase();
  if (!normalized) return true;

  return [
    "your_",
    "example",
    "placeholder",
    "changeme",
    "change_me",
    "replace_me",
    "replace-with",
    "replace_",
    "test_key",
  ].some((token) => normalized.includes(token));
}

export function loadConfig() {
  const env = schema.parse(process.env);
  if (env.CONTENT_LLM_PROVIDER === "openai" && isPlaceholderSecret(env.OPENAI_API_KEY)) {
    throw new Error("OPENAI_API_KEY is missing or still set to a placeholder value in .env");
  }
  if (env.CONTENT_LLM_PROVIDER === "anthropic" && isPlaceholderSecret(env.ANTHROPIC_API_KEY)) {
    throw new Error("ANTHROPIC_API_KEY is missing or still set to a placeholder value in .env");
  }
  const parsedAuthor = env.DEFAULT_AUTHOR ? Number(env.DEFAULT_AUTHOR) : null;

  const stateDir = resolve(agentRoot, "state");
  const runtimeDir = resolve(agentRoot, "runtime");
  const logsDir = resolve(runtimeDir, "logs");
  const imagesDir = resolve(runtimeDir, "images");
  mkdirSync(stateDir, { recursive: true });
  mkdirSync(runtimeDir, { recursive: true });
  mkdirSync(logsDir, { recursive: true });
  mkdirSync(imagesDir, { recursive: true });

  return {
    projectRoot,
    agentRoot,
    timeZone: "Asia/Kolkata",
    contentLlmProvider: env.CONTENT_LLM_PROVIDER,
    openAiApiKey: env.OPENAI_API_KEY,
    openAiModel: env.OPENAI_MODEL,
    anthropicApiKey: env.ANTHROPIC_API_KEY,
    anthropicModel: env.ANTHROPIC_MODEL,
    serpApiKey: env.SERPAPI_API_KEY,
    wpBaseUrl: env.WP_BASE_URL.replace(/\/+$/, ""),
    wpUsername: env.WP_USERNAME,
    wpApplicationPassword: env.WP_APPLICATION_PASSWORD,
    autoPublish: toBool(env.AUTO_PUBLISH),
    siteName: env.SITE_NAME,
    brandTone: env.BRAND_TONE,
    defaultCategory: env.DEFAULT_CATEGORY,
    defaultAuthor: parsedAuthor !== null && Number.isFinite(parsedAuthor) ? parsedAuthor : null,
    enableFeaturedImage: toBool(env.ENABLE_FEATURED_IMAGE),
    enableGoogleIndexing: toBool(env.ENABLE_GOOGLE_INDEXING),
    googleServiceAccountJson: env.GOOGLE_SERVICE_ACCOUNT_JSON,
    googleOAuthClientId: env.GOOGLE_OAUTH_CLIENT_ID,
    googleOAuthClientSecret: env.GOOGLE_OAUTH_CLIENT_SECRET,
    googleOAuthRefreshToken: env.GOOGLE_OAUTH_REFRESH_TOKEN,
    googleSearchConsoleProperty: env.GOOGLE_SEARCH_CONSOLE_PROPERTY,
    paths: {
      stateDir,
      generatedPostsFile: resolve(stateDir, "generated-posts.json"),
      indexingStatusFile: resolve(stateDir, "indexing-status.json"),
      topicDiscoveryFile: resolve(stateDir, "topic-discovery.json"),
      logsDir,
      imagesDir,
    },
  };
}

export type AppConfig = ReturnType<typeof loadConfig>;
