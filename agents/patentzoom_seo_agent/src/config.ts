import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import dotenv from "dotenv";
import { z } from "zod";
import { WorkflowConfigOverrides } from "./types";

const agentRoot = resolve(__dirname, "..");
const projectRoot = resolve(agentRoot, "..", "..");

dotenv.config({ path: resolve(projectRoot, ".env") });

const schema = z.object({
  OPENAI_API_KEY: z.string().optional().default(""),
  OPENAI_MODEL: z.string().min(1).default("gpt-4.1-mini"),
  ANTHROPIC_API_KEY: z.string().optional().default(""),
  ANTHROPIC_MODEL: z.string().min(1).default("claude-sonnet-4-20250514"),
  CONTENT_LLM_PROVIDER: z.enum(["openai", "anthropic"]).optional().default("openai"),
  WP_BASE_URL: z.string().optional().default(""),
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

function resolveUrl(value: string, keyName: string): string {
  const normalized = String(value || "").trim().replace(/\/+$/, "");
  if (!normalized) {
    throw new Error(`${keyName} must be configured before this SEO workspace can run`);
  }

  try {
    return new URL(normalized).toString().replace(/\/+$/, "");
  } catch {
    throw new Error(`${keyName} must be a valid URL`);
  }
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

export function loadConfig(overrides: WorkflowConfigOverrides = {}) {
  const env = schema.parse(process.env);
  if (env.CONTENT_LLM_PROVIDER === "openai" && isPlaceholderSecret(env.OPENAI_API_KEY)) {
    throw new Error("OPENAI_API_KEY is missing or still set to a placeholder value in .env");
  }
  if (env.CONTENT_LLM_PROVIDER === "anthropic" && isPlaceholderSecret(env.ANTHROPIC_API_KEY)) {
    throw new Error("ANTHROPIC_API_KEY is missing or still set to a placeholder value in .env");
  }
  const parsedAuthor =
    overrides.defaultAuthor !== undefined
      ? overrides.defaultAuthor
      : env.DEFAULT_AUTHOR
        ? Number(env.DEFAULT_AUTHOR)
        : null;

  const stateDir = resolve(overrides.paths?.stateDir || resolve(agentRoot, "state"));
  const runtimeDir = resolve(overrides.paths?.runtimeDir || resolve(agentRoot, "runtime"));
  const logsDir = resolve(overrides.paths?.logsDir || resolve(runtimeDir, "logs"));
  const imagesDir = resolve(overrides.paths?.imagesDir || resolve(runtimeDir, "images"));
  mkdirSync(stateDir, { recursive: true });
  mkdirSync(runtimeDir, { recursive: true });
  mkdirSync(logsDir, { recursive: true });
  mkdirSync(imagesDir, { recursive: true });

  const siteName = String(overrides.siteName || env.SITE_NAME || "PatentZoom").trim() || "PatentZoom";
  const wpBaseUrl = resolveUrl(overrides.wpBaseUrl ?? env.WP_BASE_URL, "WP_BASE_URL");

  return {
    projectRoot,
    agentRoot,
    workspaceId: String(overrides.workspaceId || "patentzoom").trim() || "patentzoom",
    workspaceName: String(overrides.workspaceName || siteName).trim() || siteName,
    timeZone: "Asia/Kolkata",
    contentLlmProvider: env.CONTENT_LLM_PROVIDER,
    openAiApiKey: env.OPENAI_API_KEY,
    openAiModel: env.OPENAI_MODEL,
    anthropicApiKey: env.ANTHROPIC_API_KEY,
    anthropicModel: env.ANTHROPIC_MODEL,
    serpApiKey: env.SERPAPI_API_KEY,
    wpBaseUrl,
    siteDomain: new URL(wpBaseUrl).hostname.replace(/^www\./i, "").toLowerCase(),
    wpUsername: String(overrides.wpUsername ?? env.WP_USERNAME),
    wpApplicationPassword: String(overrides.wpApplicationPassword ?? env.WP_APPLICATION_PASSWORD),
    autoPublish: overrides.autoPublish !== undefined ? Boolean(overrides.autoPublish) : toBool(env.AUTO_PUBLISH),
    siteName,
    brandTone: String(overrides.brandTone || env.BRAND_TONE),
    defaultCategory: String(overrides.defaultCategory || env.DEFAULT_CATEGORY),
    defaultAuthor: parsedAuthor !== null && Number.isFinite(parsedAuthor) ? parsedAuthor : null,
    enableFeaturedImage:
      overrides.enableFeaturedImage !== undefined ? Boolean(overrides.enableFeaturedImage) : toBool(env.ENABLE_FEATURED_IMAGE),
    enableGoogleIndexing:
      overrides.enableGoogleIndexing !== undefined ? Boolean(overrides.enableGoogleIndexing) : toBool(env.ENABLE_GOOGLE_INDEXING),
    googleServiceAccountJson: String(overrides.googleServiceAccountJson ?? env.GOOGLE_SERVICE_ACCOUNT_JSON),
    googleOAuthClientId: env.GOOGLE_OAUTH_CLIENT_ID,
    googleOAuthClientSecret: env.GOOGLE_OAUTH_CLIENT_SECRET,
    googleOAuthRefreshToken: env.GOOGLE_OAUTH_REFRESH_TOKEN,
    googleSearchConsoleProperty: String(overrides.googleSearchConsoleProperty ?? env.GOOGLE_SEARCH_CONSOLE_PROPERTY),
    paths: {
      stateDir,
      runtimeDir,
      generatedPostsFile: resolve(overrides.paths?.generatedPostsFile || resolve(stateDir, "generated-posts.json")),
      indexingStatusFile: resolve(overrides.paths?.indexingStatusFile || resolve(stateDir, "indexing-status.json")),
      topicDiscoveryFile: resolve(overrides.paths?.topicDiscoveryFile || resolve(stateDir, "topic-discovery.json")),
      logsDir,
      imagesDir,
    },
  };
}

export type AppConfig = ReturnType<typeof loadConfig>;
