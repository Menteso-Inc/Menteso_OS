"""
PatentZoom SEO Posting Agent
Runs the TypeScript publishing workflow and normalizes results for the Menteso dashboard.
"""
import json
import os
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from dotenv import dotenv_values

from shared.memory import get_best_strategy, load_memory, save_learning
from .tests import tests

AGENT_NAME = "patentzoom_seo_agent"
AGENT_DIR = Path(__file__).parent
RUNTIME_DIR = AGENT_DIR / "runtime"
REQUESTS_DIR = RUNTIME_DIR / "requests"
DIST_ENTRY = AGENT_DIR / "dist" / "main.js"
STATE_FILE = AGENT_DIR / "state" / "generated-posts.json"
INDEXING_STATE_FILE = AGENT_DIR / "state" / "indexing-status.json"
TOPIC_DISCOVERY_FILE = AGENT_DIR / "state" / "topic-discovery.json"
SCHEDULER_STATE_FILE = AGENT_DIR / "state" / "scheduler-state.json"
LOGS_DIR = RUNTIME_DIR / "logs"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

AGENT_CONFIG = {
    "name": "SEO Posting Agent",
    "description": (
        "PatentZoom daily SEO publishing workflow. Researches patent-law topics, "
        "generates SEO content with the configured AI provider, optionally creates a featured image, "
        "and publishes drafts or live posts to WordPress."
    ),
    "role": "Daily SEO Publisher",
    "goal": "Generate high-quality PatentZoom blog posts without duplicate topics",
    "status": "active",
    "version": "1.0.0",
    "requires_llm": True,
    "accepts_upload": False,
    "group": "PatentZoom Agents",
    "ui_type": "seo_posting",
    "input_fields": [
        {"name": "topic_override", "type": "text", "label": "Topic Override"},
        {
            "name": "publish_override",
            "type": "select",
            "label": "Publish Mode",
            "options": ["draft", "publish"],
        },
        {
            "name": "enable_featured_image",
            "type": "boolean",
            "label": "Generate Featured Image",
        },
        {"name": "dry_run", "type": "boolean", "label": "Dry Run"},
    ],
    "sub_agents": ["Topic Engine", "Content Writer", "SEO Validator", "WordPress Publisher"],
}


def _load_env_values():
    if ENV_FILE.exists():
        return dotenv_values(ENV_FILE)
    return {}


def _is_set(value):
    return bool(value and str(value).strip())


def _is_placeholder_value(value):
    normalized = str(value or "").strip().lower()
    if not normalized:
        return True
    markers = [
        "your_",
        "example",
        "placeholder",
        "changeme",
        "change_me",
        "replace_me",
        "replace-with",
        "replace_",
        "test_key",
    ]
    return any(marker in normalized for marker in markers)


def _is_configured_secret(value):
    return _is_set(value) and not _is_placeholder_value(value)


def _selected_content_provider(env):
    provider = str(env.get("CONTENT_LLM_PROVIDER", "openai") or "openai").strip().lower()
    return "anthropic" if provider == "anthropic" else "openai"


def _load_topic_discovery():
    if not TOPIC_DISCOVERY_FILE.exists():
        return {
            "generatedAt": "",
            "mode": "mixed_signal_dynamic",
            "selectedTopic": None,
            "shortlist": [],
            "rejectedTopics": [],
            "liveSignals": [],
            "sourceHealth": [],
            "degradedSources": [],
        }
    try:
        payload = json.loads(TOPIC_DISCOVERY_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {
            "generatedAt": "",
            "mode": "mixed_signal_dynamic",
            "selectedTopic": None,
            "shortlist": [],
            "rejectedTopics": [],
            "liveSignals": [],
            "sourceHealth": [],
            "degradedSources": [],
        }


def _load_generated_posts():
    if not STATE_FILE.exists():
        return []
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        posts = payload.get("generatedPosts", [])
        return posts if isinstance(posts, list) else []
    except Exception:
        return []


def _load_indexing_statuses():
    if not INDEXING_STATE_FILE.exists():
        return {}
    try:
        payload = json.loads(INDEXING_STATE_FILE.read_text(encoding="utf-8"))
        urls = payload.get("urls", {})
        return urls if isinstance(urls, dict) else {}
    except Exception:
        return {}


def _load_scheduler_state():
    if not SCHEDULER_STATE_FILE.exists():
        return {}
    try:
        payload = json.loads(SCHEDULER_STATE_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _load_recent_runs(limit=6):
    if not LOGS_DIR.exists():
        return []
    runs = []
    for path in sorted(LOGS_DIR.glob("*.json"), reverse=True):
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(entries, list):
            continue
        for entry in reversed(entries):
            result = entry.get("result") or {}
            article = result.get("article") or {}
            runs.append({
                "runId": entry.get("runId", ""),
                "createdAt": entry.get("createdAt", ""),
                "status": result.get("status", ""),
                "primaryKeyword": result.get("primaryKeyword", ""),
                "postStatus": result.get("postStatus", ""),
                "wordpressUrl": result.get("wordpressUrl", ""),
                "executionTime": result.get("executionTime", 0),
                "title": result.get("title") or article.get("title", ""),
                "error": result.get("error", ""),
                "slug": result.get("slug") or article.get("slug", ""),
                "metaDescription": article.get("metaDescription", ""),
                "seoScore": _compute_seo_score(article),
                "article": article,
                "indexing": result.get("indexing") or {},
            })
            if len(runs) >= limit:
                return runs
    return runs


def _strip_html(value):
    return re.sub(r"<[^>]+>", "", str(value or "")).strip()


def _count_matches(text, needle):
    if not text or not needle:
        return 0
    return str(text).lower().count(str(needle).lower())


def _compute_seo_score(article):
    if not isinstance(article, dict) or not article:
        return None

    score = 0
    title = str(article.get("title", "")).strip()
    meta_title = str(article.get("metaTitle", "")).strip()
    meta_description = str(article.get("metaDescription", "")).strip()
    slug = str(article.get("slug", "")).strip()
    article_html = str(article.get("articleHtml", "")).strip()
    primary_keyword = str(article.get("primaryKeyword", "")).strip()
    faq_schema = str(article.get("faqSchemaJsonLd", "")).strip()
    category = str(article.get("category", "")).strip()
    tags = article.get("tags") or []

    if title:
        score += 12 if 45 <= len(title) <= 70 else 7
    if meta_title:
        score += 10 if 45 <= len(meta_title) <= 65 else 5
    if meta_description:
        score += 12 if 120 <= len(meta_description) <= 170 else 6
    if slug:
        score += 8 if len(slug) <= 80 else 4
    if article_html:
        score += 12
        if "<h2" in article_html.lower():
            score += 8
        if "<h3" in article_html.lower():
            score += 5
        if "informational purposes only" in article_html.lower():
            score += 5
        if "href=" in article_html.lower():
            score += 8
        if "<table" in article_html.lower() or "checklist" in article_html.lower():
            score += 5
    if primary_keyword and _count_matches(_strip_html(article_html), primary_keyword) >= 2:
        score += 10
    if faq_schema:
        score += 8
    if category:
        score += 3
    if tags:
        score += min(4, len(tags))

    return max(0, min(100, int(score)))


def _top_keywords(posts, recent_runs, limit=5):
    counts = {}
    for item in posts:
        keyword = str(item.get("primaryKeyword", "")).strip()
        if keyword:
            counts[keyword] = counts.get(keyword, 0) + 1
    for run in recent_runs:
        keyword = str(run.get("primaryKeyword", "")).strip()
        if keyword:
            counts[keyword] = counts.get(keyword, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    return [{"keyword": keyword, "count": count} for keyword, count in ordered[:limit]]


def _fetch_recent_patentzoom_posts(limit=8):
    env = _load_env_values()
    base_url = str(env.get("WP_BASE_URL") or "").rstrip("/")
    if not base_url:
        return []

    url = (
        f"{base_url}/wp-json/wp/v2/posts?"
        + urllib_parse.urlencode(
            {
                "per_page": limit,
                "orderby": "date",
                "order": "desc",
                "_fields": "id,slug,link,title,excerpt",
            }
        )
    )
    try:
        with urllib_request.urlopen(url, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    posts = []
    for item in payload if isinstance(payload, list) else []:
        title = _strip_html((item.get("title") or {}).get("rendered", ""))
        excerpt = _strip_html((item.get("excerpt") or {}).get("rendered", ""))
        posts.append(
            {
                "id": item.get("id"),
                "slug": item.get("slug", ""),
                "url": item.get("link", ""),
                "title": title,
                "excerpt": excerpt,
            }
        )
    return posts


def _build_dynamic_queue(topic_discovery):
    shortlist = list((topic_discovery or {}).get("shortlist", []) or [])
    queue = []
    for index, item in enumerate(shortlist[:6]):
        queue.append(
            {
                "rank": index + 1,
                "theme": item.get("theme") or item.get("pillar") or "Patent Topic",
                "primaryKeyword": item.get("primaryKeyword", ""),
                "intentCluster": item.get("intentCluster", ""),
                "score": item.get("score"),
                "freshnessScore": item.get("freshnessScore"),
                "status": "Selected" if index == 0 else "Queued",
                "sourceMix": ", ".join(item.get("sourceTypes", []) or []),
            }
        )
    return queue


def _normalize_indexing_status(indexing, fallback_status=""):
    if not isinstance(indexing, dict) or not indexing:
        lower = str(fallback_status or "").lower()
        if lower == "publish":
            return "Published - awaiting Google status"
        if lower == "draft":
            return "Draft - not submitted"
        return "Pending"

    inspection = indexing.get("inspection") or {}
    coverage = str(inspection.get("coverageState") or "").strip()
    verdict = str(inspection.get("verdict") or "").strip()
    if coverage:
        return coverage
    if verdict:
        return verdict.title()
    if indexing.get("autoSubmitSucceeded"):
        return "Submitted to Google"
    if indexing.get("error"):
        return f"Error: {indexing.get('error')}"
    return "Pending"


def _is_indexed_status(status_text):
    status = str(status_text or "").strip().lower()
    if not status:
        return False
    negative_markers = [
        "not indexed",
        "awaiting google",
        "unknown to google",
        "pending",
        "error:",
        "submitted to google",
        "discovered - currently not indexed",
        "crawled - currently not indexed",
    ]
    if any(marker in status for marker in negative_markers):
        return False
    positive_markers = [
        "indexed",
        "submitted and indexed",
        "url is on google",
        "passed",
    ]
    return any(marker in status for marker in positive_markers)


def _merge_indexing_status(url, run_indexing, index_cache):
    if isinstance(run_indexing, dict) and run_indexing:
        return run_indexing
    cached = index_cache.get(url or "")
    return cached if isinstance(cached, dict) else {}


def _build_article_manager(recent_runs, index_cache):
    articles = []
    for run in recent_runs:
        article = run.get("article") or {}
        merged_indexing = _merge_indexing_status(run.get("wordpressUrl", ""), run.get("indexing"), index_cache)
        preview_html = str(article.get("articleHtml", "") or "")
        articles.append(
            {
                "id": run.get("runId", ""),
                "title": run.get("title") or article.get("title", "PatentZoom SEO draft"),
                "seoScore": run.get("seoScore"),
                "primaryKeyword": run.get("primaryKeyword") or article.get("primaryKeyword", ""),
                "slug": run.get("slug") or article.get("slug", ""),
                "metaDescription": run.get("metaDescription") or article.get("metaDescription", ""),
                "publishStatus": run.get("postStatus") or run.get("status", ""),
                "url": run.get("wordpressUrl", ""),
                "previewHtml": preview_html[:2400] if preview_html else "",
                "createdAt": run.get("createdAt", ""),
                "indexingStatus": _normalize_indexing_status(merged_indexing, run.get("postStatus") or run.get("status", "")),
                "indexing": merged_indexing,
            }
        )
    return articles


def _build_recent_runs_summary(recent_runs):
    summaries = []
    for run in recent_runs:
        summaries.append(
            {
                "runId": run.get("runId", ""),
                "createdAt": run.get("createdAt", ""),
                "status": run.get("status", ""),
                "primaryKeyword": run.get("primaryKeyword", ""),
                "postStatus": run.get("postStatus", ""),
                "executionTime": run.get("executionTime", 0),
                "title": run.get("title", ""),
                "error": run.get("error", ""),
                "wordpressUrl": run.get("wordpressUrl", ""),
            }
        )
    return summaries


def _build_internal_linking(recent_posts, topic_discovery):
    selected = (topic_discovery or {}).get("selectedTopic") or {}
    candidate_keywords = [
        selected.get("primaryKeyword", ""),
        *((selected.get("secondaryKeywords") or [])[:4]),
    ]
    keyword_roots = [str(item).split(" ")[0].lower() for item in candidate_keywords if str(item).strip()]
    suggestions = []
    for post in recent_posts:
        haystack = f"{post.get('title', '')} {post.get('excerpt', '')}".lower()
        score = sum(1 for root in keyword_roots if root and root in haystack)
        suggestions.append(
            {
                "title": post.get("title", ""),
                "url": post.get("url", ""),
                "slug": post.get("slug", ""),
                "score": score,
            }
        )
    suggestions.sort(key=lambda item: (-item["score"], item["title"].lower()))
    return suggestions[:5]


def _build_automation_settings(env, readiness, scheduler_state=None):
    readiness_map = {item["key"]: item["ready"] for item in readiness}
    default_word_count = str(env.get("SEO_DEFAULT_WORD_COUNT", "1400")).strip() or "1400"
    publish_time = str(env.get("SEO_AUTO_PUBLISH_TIME", "07:00 IST")).strip() or "07:00 IST"
    google_connected = bool(
        str(env.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
        and str(env.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
        and str(env.get("GOOGLE_OAUTH_REFRESH_TOKEN") or "").strip()
    )
    scheduler_state = scheduler_state or {}
    scheduler_label = "Local Daily Scheduler"
    if scheduler_state.get("last_auto_attempt_date"):
        scheduler_label += f": {scheduler_state.get('last_auto_attempt_date')}"
        if scheduler_state.get("last_auto_result_status"):
            scheduler_label += f" ({scheduler_state.get('last_auto_result_status')})"
    return [
        {"key": "content_provider", "label": f"Content Provider: {_selected_content_provider(env).title()}", "enabled": readiness_map.get("content_llm", False), "kind": "service"},
        {"key": "wordpress", "label": "WordPress API", "enabled": readiness_map.get("wordpress", False), "kind": "service"},
        {"key": "google_search_console", "label": "Google Search Console", "enabled": google_connected, "kind": "service"},
        {"key": "local_scheduler", "label": scheduler_label, "enabled": str(env.get("AUTO_PUBLISH", "false")).strip().lower() == "true", "kind": "service"},
        {"key": "auto_publish", "label": "Auto Publish", "enabled": str(env.get("AUTO_PUBLISH", "false")).strip().lower() == "true", "kind": "toggle"},
        {"key": "default_publish_mode", "label": "Default Publish Mode: Publish" if str(env.get("AUTO_PUBLISH", "false")).strip().lower() == "true" else "Default Publish Mode: Draft", "enabled": True, "kind": "setting"},
        {"key": "default_word_count", "label": f"Default Word Count: {default_word_count}", "enabled": True, "kind": "setting"},
        {"key": "default_category", "label": f"Default Category: {str(env.get('DEFAULT_CATEGORY', 'Patent Filing')).strip() or 'Patent Filing'}", "enabled": True, "kind": "setting"},
        {"key": "default_author", "label": f"Default Author: {str(env.get('DEFAULT_AUTHOR', 'Editorial Team')).strip() or 'Editorial Team'}", "enabled": True, "kind": "setting"},
        {"key": "publish_time", "label": f"Auto Publish Time: {publish_time}", "enabled": True, "kind": "setting"},
        {"key": "featured_image", "label": "Featured Image", "enabled": str(env.get("ENABLE_FEATURED_IMAGE", "true")).strip().lower() == "true", "kind": "toggle"},
        {"key": "internal_linking", "label": "Internal Linking", "enabled": True, "kind": "toggle"},
        {"key": "faq_section", "label": "FAQ Section", "enabled": True, "kind": "toggle"},
        {"key": "duplicate_check", "label": "Duplicate Topic Check", "enabled": True, "kind": "toggle"},
        {"key": "seo_validation", "label": "SEO Validation Before Publishing", "enabled": True, "kind": "toggle"},
        {"key": "google_indexing", "label": "Google Indexing", "enabled": str(env.get("ENABLE_GOOGLE_INDEXING", "false")).strip().lower() == "true", "kind": "toggle"},
        {"key": "draft_first", "label": "Draft-First Mode", "enabled": str(env.get("AUTO_PUBLISH", "false")).strip().lower() != "true", "kind": "toggle"},
    ]


def _build_today_run(env, topic_discovery):
    selected = (topic_discovery or {}).get("selectedTopic") or {}
    secondary_keywords = list(selected.get("secondaryKeywords", []) or [])
    source_mix = ", ".join(selected.get("sourceTypes", []) or [])
    confidence = round(float(selected.get("score") or 0), 1) if selected else 0
    return {
        "selectedTopic": selected.get("theme") or selected.get("pillar") or "Dynamic topic discovery will choose the strongest live topic",
        "targetKeyword": selected.get("primaryKeyword", ""),
        "secondaryKeywords": secondary_keywords[:4],
        "contentType": "SEO Blog Article",
        "targetAudience": "Founders, inventors, startup teams, and businesses",
        "publishMode": "publish" if str(env.get("AUTO_PUBLISH", "false")).strip().lower() == "true" else "draft",
        "generateFeaturedImage": str(env.get("ENABLE_FEATURED_IMAGE", "true")).strip().lower() == "true",
        "dryRun": False,
        "sourceMix": source_mix,
        "confidenceScore": confidence,
        "freshnessLevel": "High" if float(selected.get("freshnessScore") or 0) >= 12 else ("Medium" if float(selected.get("freshnessScore") or 0) >= 7 else "Low"),
    }


def _build_wordpress_monitor(env, posts, recent_runs):
    published_posts = [item for item in posts if str(item.get("status", "")).lower() == "publish"]
    draft_posts = [item for item in posts if str(item.get("status", "")).lower() == "draft"]
    failed_runs = [item for item in recent_runs if str(item.get("status", "")).lower() == "failure"]
    last_published = published_posts[-1] if published_posts else None
    return {
        "connectionStatus": "Connected" if _is_set(env.get("WP_BASE_URL")) and _is_set(env.get("WP_USERNAME")) and _is_configured_secret(env.get("WP_APPLICATION_PASSWORD")) else "Not Connected",
        "websiteUrl": str(env.get("WP_BASE_URL") or "https://patentzoom.us"),
        "lastPublishedPost": (last_published or {}).get("primaryKeyword", ""),
        "lastPublishedUrl": (last_published or {}).get("wpUrl", ""),
        "draftsCreated": len(draft_posts),
        "failedPublishes": len(failed_runs),
        "defaultCategory": str(env.get("DEFAULT_CATEGORY") or "Patent Filing"),
        "defaultAuthor": str(env.get("DEFAULT_AUTHOR") or "Editorial Team"),
        "mediaUploadStatus": "Enabled" if str(env.get("ENABLE_FEATURED_IMAGE", "true")).strip().lower() == "true" else "Disabled",
    }


def _build_seo_performance(posts, recent_runs, index_cache):
    runs_by_url = {}
    for run in recent_runs:
        url = str(run.get("wordpressUrl", "")).strip()
        if url:
            runs_by_url[url] = run
    rows = []
    for item in reversed(posts[-8:]):
        url = item.get("wpUrl", "")
        run = runs_by_url.get(url, {})
        indexing = _merge_indexing_status(url, run.get("indexing"), index_cache)
        rows.append(
            {
                "articleTitle": (run.get("title") or item.get("primaryKeyword") or "PatentZoom article"),
                "publishedDate": item.get("date", ""),
                "focusKeyword": item.get("primaryKeyword", ""),
                "impressions": "Pending",
                "clicks": "Pending",
                "ctr": "Pending",
                "averagePosition": "Pending",
                "indexedStatus": _normalize_indexing_status(indexing, item.get("status", "")),
                "leadsGenerated": "Pending",
                "url": url,
                "requestIndexingEligible": str(item.get("status", "")).lower() == "publish" and bool(url),
            }
        )
    return rows


def _build_latest_article_preview(article_manager, wp_monitor):
    latest = article_manager[0] if article_manager else {}
    return {
        "title": latest.get("title", ""),
        "slug": latest.get("slug", ""),
        "focusKeyword": latest.get("primaryKeyword", ""),
        "metaTitle": latest.get("title", ""),
        "metaDescription": latest.get("metaDescription", ""),
        "wordCount": len(_strip_html(latest.get("previewHtml", "")).split()) if latest.get("previewHtml") else 0,
        "category": "Patent Filing",
        "author": wp_monitor.get("defaultAuthor", "Editorial Team"),
        "featuredImagePreview": "",
        "wordpressUrl": latest.get("url", ""),
        "status": latest.get("publishStatus", ""),
        "seoScore": latest.get("seoScore"),
        "previewHtml": latest.get("previewHtml", ""),
    }


def _build_seo_checklist(article_preview, internal_linking, posts):
    html = str(article_preview.get("previewHtml", "") or "")
    title = str(article_preview.get("title", "") or "")
    focus_keyword = str(article_preview.get("focusKeyword", "") or "")
    meta_title = str(article_preview.get("metaTitle", "") or "")
    meta_description = str(article_preview.get("metaDescription", "") or "")
    word_count = int(article_preview.get("wordCount") or 0)
    duplicate_topics = {str(item.get("primaryKeyword", "")).strip().lower() for item in posts}
    focus_in_intro = focus_keyword.lower() in _strip_html(html)[:260].lower() if html and focus_keyword else False
    checklist = [
        {"label": "Focus keyword in title", "passed": bool(focus_keyword and focus_keyword.lower() in title.lower())},
        {"label": "Focus keyword in intro", "passed": focus_in_intro},
        {"label": "Proper H1", "passed": "<h1" in html.lower()},
        {"label": "H2/H3 structure", "passed": "<h2" in html.lower() and "<h3" in html.lower()},
        {"label": "Meta title under 60 characters", "passed": bool(meta_title and len(meta_title) <= 60)},
        {"label": "Meta description under 160 characters", "passed": bool(meta_description and len(meta_description) <= 160)},
        {"label": "Minimum 1000 words", "passed": word_count >= 1000},
        {"label": "Internal links added", "passed": ("href=" in html.lower()) or bool(internal_linking)},
        {"label": "External references added", "passed": "http" in html.lower()},
        {"label": "FAQ section added", "passed": "faq" in html.lower()},
        {"label": "Featured image alt text added", "passed": bool(article_preview.get("featuredImagePreview")) or str(article_preview.get("status", "")).lower() in {"draft", "publish", "published"}},
        {"label": "No duplicate topic", "passed": not focus_keyword or focus_keyword.strip().lower() not in duplicate_topics},
        {"label": "CTA included", "passed": "patentzoom" in html.lower()},
    ]
    return checklist


def _infer_failed_step(error_message, status):
    if str(status or "").lower() != "failure":
        return ""
    lower = str(error_message or "").lower()
    if "serpapi" in lower or "keyword" in lower:
        return "Keyword Research"
    if "anthropic" in lower or "openai" in lower or "quota" in lower or "credit balance" in lower:
        return "Content Writer"
    if "meta" in lower or "seo" in lower:
        return "SEO Validator"
    if "image" in lower:
        return "Featured Image"
    if "wordpress" in lower or "publish" in lower:
        return "WordPress Publisher"
    return "Workflow"


def get_dashboard_data():
    env = _load_env_values()
    content_provider = _selected_content_provider(env)
    posts = _load_generated_posts()
    index_cache = _load_indexing_statuses()
    topic_discovery = _load_topic_discovery()
    scheduler_state = _load_scheduler_state()
    recent_runs = _load_recent_runs()
    recent_site_posts = _fetch_recent_patentzoom_posts()

    publish_statuses = {str(item.get("status", "")).lower() for item in posts}
    published_count = sum(1 for item in posts if str(item.get("status", "")).lower() == "publish")
    draft_count = sum(1 for item in posts if str(item.get("status", "")).lower() == "draft")
    top_keywords = _top_keywords(posts, recent_runs)
    scored_runs = [run.get("seoScore") for run in recent_runs if isinstance(run.get("seoScore"), int)]
    average_seo_score = round(sum(scored_runs) / len(scored_runs), 1) if scored_runs else 0
    article_manager = _build_article_manager(recent_runs[:8], index_cache)
    wp_monitor = _build_wordpress_monitor(env, posts, recent_runs)
    latest_article_preview = _build_latest_article_preview(article_manager, wp_monitor)
    seo_checklist = _build_seo_checklist(latest_article_preview, _build_internal_linking(recent_site_posts, topic_discovery), posts)
    logs_history = [
        {
            "topic": item.get("title") or item.get("primaryKeyword") or "PatentZoom SEO run",
            "status": item.get("postStatus") or item.get("status"),
            "publishDate": item.get("createdAt", ""),
            "url": item.get("wordpressUrl", ""),
            "seoScore": item.get("seoScore"),
            "timeTaken": item.get("executionTime", 0),
            "failedStep": _infer_failed_step(item.get("error", ""), item.get("status", "")),
            "errorMessage": item.get("error", ""),
            "mode": "Dry Run" if str(item.get("postStatus", "")).lower() == "dry-run" else ("Publish" if str(item.get("postStatus", "")).lower() == "publish" else "Draft"),
            "indexingStatus": _normalize_indexing_status(_merge_indexing_status(item.get("wordpressUrl", ""), item.get("indexing"), index_cache), item.get("postStatus") or item.get("status")),
            "requestIndexingEligible": str(item.get("postStatus", "")).lower() == "publish" and bool(item.get("wordpressUrl", "")),
        }
        for item in recent_runs
    ]
    indexed_urls = sum(
        1
        for item in posts
        if _is_indexed_status(
            _normalize_indexing_status(_merge_indexing_status(item.get("wpUrl", ""), None, index_cache), item.get("status", ""))
        )
    )
    organic_traffic = None
    tz = timezone(timedelta(hours=5, minutes=30))
    today_iso = datetime.now(tz).strftime("%Y-%m-%d")
    published_today = any(str(item.get("status", "")).lower() == "publish" and str(item.get("date", "")) == str(today_iso) for item in posts)
    monthly_articles = sum(1 for item in posts if str(item.get("status", "")).lower() == "publish" and str(item.get("date", "")).startswith(str(today_iso)[:7]))
    success_rate_pct = round(
        (sum(1 for item in recent_runs if str(item.get("status", "")).lower() == "success") / len(recent_runs) * 100)
        if recent_runs
        else 0,
        1,
    )

    readiness = [
        {
            "key": "content_llm",
            "label": f"{content_provider.title()} content generation",
            "ready": _is_configured_secret(env.get("ANTHROPIC_API_KEY")) if content_provider == "anthropic" else _is_configured_secret(env.get("OPENAI_API_KEY")),
            "detail": (
                "Anthropic is currently selected for article generation."
                if content_provider == "anthropic"
                else "OpenAI is currently selected for article generation."
            ),
        },
        {
            "key": "serpapi",
            "label": "SERPAPI keyword research",
            "ready": _is_configured_secret(env.get("SERPAPI_API_KEY")),
            "detail": "SERPAPI powers live related searches, autocomplete demand signals, and competitor discovery.",
        },
        {
            "key": "wordpress",
            "label": "WordPress publishing",
            "ready": _is_set(env.get("WP_BASE_URL")) and _is_set(env.get("WP_USERNAME")) and _is_configured_secret(env.get("WP_APPLICATION_PASSWORD")),
            "detail": "Needed to create draft or published posts on patentzoom.us. Use a WordPress Application Password, not a placeholder value.",
        },
        {
            "key": "indexing",
            "label": "Google indexing handoff",
            "ready": str(env.get("ENABLE_GOOGLE_INDEXING", "false")).strip().lower() != "true" or _is_configured_secret(env.get("GOOGLE_SERVICE_ACCOUNT_JSON")),
            "detail": "If Google indexing is enabled, a service account JSON must also be configured.",
        },
        {
            "key": "search_console_oauth",
            "label": "Google Search Console OAuth",
            "ready": bool(
                str(env.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
                and str(env.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
                and str(env.get("GOOGLE_OAUTH_REFRESH_TOKEN") or "").strip()
            ),
            "detail": "Connect once with Google OAuth to let the dashboard pull Search Console data without the service-account setup.",
        },
    ]

    next_actions = []
    if not readiness[0]["ready"]:
        next_actions.append({
            "tone": "error",
            "title": f"Add a valid {content_provider.upper()} API key",
            "detail": f"The current {content_provider.title()} key is missing or still a placeholder, so article generation cannot start.",
        })
    if not readiness[1]["ready"]:
        next_actions.append({
            "tone": "warning",
            "title": "Add SERPAPI_API_KEY for live topic discovery",
            "detail": "Without SerpAPI, the dynamic topic engine loses autocomplete, related-search, and competitor topic signals.",
        })
    if not readiness[2]["ready"]:
        next_actions.append({
            "tone": "error",
            "title": "Add a WordPress Application Password",
            "detail": "Publishing drafts or live posts is blocked until WP_APPLICATION_PASSWORD is configured in .env.",
        })
    if str(env.get("ENABLE_GOOGLE_INDEXING", "false")).strip().lower() == "true" and not readiness[3]["ready"]:
        next_actions.append({
            "tone": "warning",
            "title": "Add GOOGLE_SERVICE_ACCOUNT_JSON or disable indexing",
            "detail": "The agent can publish content, but automatic indexing handoff will remain unavailable.",
        })
    if not readiness[4]["ready"]:
        next_actions.append({
            "tone": "info",
            "title": "Connect Google Search Console",
            "detail": "Save your Google OAuth web-app client ID and secret, then connect once from the SEO dashboard to pull Search Console data.",
        })
    if recent_runs and str(recent_runs[0].get("status", "")).lower() == "failure":
        next_actions.append({
            "tone": "error",
            "title": "Fix the last failed SEO run",
            "detail": recent_runs[0].get("error") or "Open the recent run log below to see the latest failure reason.",
        })
    if not recent_runs:
        next_actions.append({
            "tone": "info",
            "title": "Start with a dry run",
            "detail": "A dry run will validate keyword selection, article structure, and the SEO dashboard without publishing anything.",
        })

    last_run = recent_runs[0] if recent_runs else None
    last_topic = posts[-1] if posts else None

    return {
        "readiness": readiness,
        "topicDiscovery": topic_discovery,
        "overview": {
            "articlesPublished": published_count,
            "draftsPending": draft_count,
            "seoScore": average_seo_score,
            "indexedUrls": indexed_urls,
            "organicTraffic": organic_traffic,
            "topKeywords": top_keywords,
            "publishedToday": published_today,
            "monthlyArticlesPublished": monthly_articles,
            "monthlyTarget": 30,
            "successRate": success_rate_pct,
            "wordpressStatus": wp_monitor.get("connectionStatus", "Not Connected"),
            "lastPublishedDate": (posts[-1] if posts else {}).get("date", ""),
        },
        "todayRun": _build_today_run(env, topic_discovery),
        "topicRadar": {
            "mode": topic_discovery.get("mode", "mixed_signal_dynamic"),
            "generatedAt": topic_discovery.get("generatedAt", ""),
            "queue": _build_dynamic_queue(topic_discovery),
            "sourceHealth": topic_discovery.get("sourceHealth", []),
            "degradedSources": topic_discovery.get("degradedSources", []),
        },
        "liveSignals": topic_discovery.get("liveSignals", []),
        "rejectedTopics": topic_discovery.get("rejectedTopics", []),
        "articleManager": article_manager,
        "articlePreview": latest_article_preview,
        "seoChecklist": seo_checklist,
        "internalLinking": {
            "suggestions": _build_internal_linking(recent_site_posts, topic_discovery),
            "note": "Suggestions are based on recent PatentZoom posts and the selected topic discovery signals.",
        },
        "automationSettings": _build_automation_settings(env, readiness, scheduler_state),
        "googleAuth": {
            "clientConfigured": bool(
                str(env.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
                and str(env.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
            ),
            "connected": bool(
                str(env.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
                and str(env.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
                and str(env.get("GOOGLE_OAUTH_REFRESH_TOKEN") or "").strip()
            ),
            "property": str(env.get("GOOGLE_SEARCH_CONSOLE_PROPERTY") or "sc-domain:patentzoom.us").strip() or "sc-domain:patentzoom.us",
            "redirectUri": "http://127.0.0.1:8000/api/google/search-console/callback",
        },
        "wordpressMonitor": wp_monitor,
        "seoPerformance": _build_seo_performance(posts, recent_runs, index_cache),
        "logsHistory": logs_history,
        "workflowStages": [
            {"key": "readiness", "label": "Topic Engine", "description": "Load history, validate services, and prepare live demand sources for dynamic discovery."},
            {"key": "keywords", "label": "Research", "description": "Score live search, Search Console, and competitor signals to choose the strongest PatentZoom topic."},
            {"key": "content", "label": "Content Writer", "description": "Generate the outline, article, metadata, and FAQ structure."},
            {"key": "optimization", "label": "SEO Validator", "description": "Improve headings, internal links, readability, and SEO structure."},
            {"key": "image", "label": "Featured Image", "description": "Create and upload a featured image when enabled."},
            {"key": "publishing", "label": "WordPress Publisher", "description": "Create the draft or published post and update the topic ledger."},
            {"key": "indexing", "label": "Indexing Handoff", "description": "Ping the sitemap, inspect the URL, and request Google indexing when needed."},
        ],
        "summary": {
            "totalTopics": len(posts),
            "publishedCount": published_count,
            "draftCount": draft_count,
            "recentRunCount": len(recent_runs),
            "lastRunStatus": last_run.get("status", "never") if last_run else "never",
            "lastPrimaryKeyword": last_run.get("primaryKeyword", "") if last_run else "",
            "autoPublish": str(env.get("AUTO_PUBLISH", "false")).strip().lower() == "true",
            "contentProvider": content_provider,
            "publishConfigured": readiness[2]["ready"],
            "keywordResearchConfigured": readiness[1]["ready"],
            "indexingConfigured": readiness[3]["ready"],
            "hasPublishedTopics": "publish" in publish_statuses,
            "lastAutoSchedulerAttempt": scheduler_state.get("last_auto_attempt_date", ""),
        },
        "recentTopics": list(reversed(posts[-8:])),
        "recentRuns": _build_recent_runs_summary(recent_runs[:10]),
        "lastTopic": last_topic or {},
        "nextActions": next_actions,
    }


def _npm_command():
    return "npm.cmd" if os.name == "nt" else "npm"


def _node_command():
    candidates = [
        Path(__file__).resolve().parents[2] / ".venv" / "Lib" / "site-packages" / "playwright" / "driver" / "node.exe",
        Path(__file__).resolve().parents[2] / ".venv" / "lib" / "site-packages" / "playwright" / "driver" / "node",
        shutil.which("node"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate) if not isinstance(candidate, Path) else candidate
        if path.exists() and "WindowsApps" not in str(path):
            return str(path)
    return "node"


def _normalize_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _extract_bypass_daily_limit(topic_override):
    topic_text = str(topic_override or "").strip()
    if not topic_text:
        return "", False
    lowered = topic_text.lower()
    command = "/bypass-daily-limit"
    if not lowered.startswith(command):
        return topic_text, False

    remainder = topic_text[len(command):].lstrip()
    if remainder.startswith(":") or remainder.startswith("-"):
        remainder = remainder[1:].lstrip()
    return remainder.strip(), True


def _build_payload(input_data):
    payload = dict(input_data or {})
    payload.pop("register_stop_handler", None)
    payload.pop("stop_requested", None)
    payload.setdefault(
        "source",
        "github_actions" if os.getenv("GITHUB_ACTIONS", "").lower() == "true" else "dashboard",
    )
    payload["enable_featured_image"] = _normalize_bool(
        payload.get("enable_featured_image"),
        default=True,
    )
    payload["dry_run"] = _normalize_bool(payload.get("dry_run"), default=False)
    payload["bypass_daily_limit"] = _normalize_bool(payload.get("bypass_daily_limit"), default=False)
    publish_override = str(payload.get("publish_override") or "draft").strip().lower()
    payload["publish_override"] = "publish" if publish_override == "publish" else "draft"
    topic_override, command_bypass = _extract_bypass_daily_limit(payload.get("topic_override"))
    if command_bypass:
        payload["bypass_daily_limit"] = True
    if topic_override:
        payload["topic_override"] = topic_override
    else:
        payload.pop("topic_override", None)
    return payload


def _build_command(input_path):
    node_cmd = _node_command()
    if DIST_ENTRY.exists():
        return [node_cmd, str(DIST_ENTRY), "--input-json", str(input_path)]
    return [_npm_command(), "run", "generate", "--", "--input-json", str(input_path)]


def _read_stderr(proc, warnings, output_logs, on_step=None):
    for raw_line in iter(proc.stderr.readline, ""):
        line = raw_line.strip()
        if not line:
            continue
        warnings.append(line)
        output_logs.append(line)
        if on_step:
            on_step(f"[stderr] {line}")


def _default_failure(error_message, output_logs, warnings, execution_time):
    return {
        "status": "failure",
        "error": error_message,
        "topic": "",
        "primaryKeyword": "",
        "postStatus": "failed",
        "wordpressPostId": None,
        "wordpressUrl": "",
        "featuredImageId": None,
        "outputLogs": output_logs,
        "warnings": warnings,
        "executionTime": round(execution_time, 2),
    }


def run_agent(input_data=None, on_step=None):
    """
    Run the PatentZoom SEO agent by delegating execution to the TypeScript workflow.
    """
    start_time = time.time()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    REQUESTS_DIR.mkdir(parents=True, exist_ok=True)

    memory = load_memory(AGENT_NAME)
    strategy = get_best_strategy(AGENT_NAME, "daily_seo_blog", default="mixed_signal_dynamic")
    if str(strategy).strip().lower() == "serpapi_calendar":
        strategy = "mixed_signal_dynamic"
    if on_step:
        on_step("Loading PatentZoom SEO agent memory...")
        on_step(
            f"Memory loaded - {memory.get('stats', {}).get('total_runs', 0)} past runs, "
            f"{round(memory.get('stats', {}).get('success_rate', 0.0) * 100)}% success rate"
        )
        on_step(f"Selected strategy: {strategy}")

    payload = _build_payload(input_data)
    payload["strategy"] = strategy
    if on_step:
        on_step({
            "type": "step",
            "message": "Validating local PatentZoom SEO setup and preparing the workflow.",
            "data": {"stage": "readiness", "status": "active"},
        })

    input_path = REQUESTS_DIR / f"request_{uuid.uuid4().hex}.json"
    input_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    process_ref = {"proc": None}
    stop_requested = {"value": False}
    output_logs = []
    warnings = []

    def interrupt():
        stop_requested["value"] = True
        proc = process_ref.get("proc")
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    register_stop_handler = (input_data or {}).get("register_stop_handler")
    if callable(register_stop_handler):
        register_stop_handler(interrupt)

    result = None
    try:
        command = _build_command(input_path)
        if on_step:
            on_step(f"Starting TypeScript workflow: {' '.join(command[:3])} ...")

        env = os.environ.copy()
        node_dir = str(Path(_node_command()).parent)
        env["PATH"] = f"{node_dir}{os.pathsep}{env.get('PATH', '')}"
        env.setdefault("NODE_OPTIONS", "--max-old-space-size=4096")

        proc = subprocess.Popen(
            command,
            cwd=str(AGENT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=env,
        )
        process_ref["proc"] = proc

        stderr_thread = threading.Thread(
            target=_read_stderr,
            args=(proc, warnings, output_logs, on_step),
            daemon=True,
        )
        stderr_thread.start()

        for raw_line in iter(proc.stdout.readline, ""):
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                output_logs.append(line)
                if on_step:
                    on_step(line)
                continue

            event_type = event.get("type", "step")
            message = event.get("message") or event.get("result", {}).get("status", "")

            if event_type == "result":
                result = event.get("result", {})
                continue

            if message:
                if event_type == "warning":
                    warnings.append(message)
                output_logs.append(message)
                if on_step:
                    payload = {
                        "type": event_type,
                        "message": message,
                    }
                    if event.get("data"):
                        payload["data"] = event.get("data")
                    if event.get("timestamp"):
                        payload["timestamp"] = event.get("timestamp")
                    on_step(payload)

        proc.wait(timeout=60)
        stderr_thread.join(timeout=5)

        execution_time = time.time() - start_time
        if stop_requested["value"] and result is None:
            result = {
                "status": "stopped",
                "topic": "",
                "primaryKeyword": "",
                "postStatus": "stopped",
                "wordpressPostId": None,
                "wordpressUrl": "",
                "featuredImageId": None,
                "outputLogs": output_logs,
                "warnings": warnings,
                "executionTime": round(execution_time, 2),
            }
        elif result is None:
            error_message = (
                f"TypeScript workflow exited with code {proc.returncode}"
                if proc.returncode not in (0, None)
                else "TypeScript workflow did not return a result payload"
            )
            result = _default_failure(error_message, output_logs, warnings, execution_time)
        else:
            result.setdefault("status", "success")
            result.setdefault("topic", "")
            result.setdefault("primaryKeyword", "")
            result.setdefault("postStatus", result["status"])
            result.setdefault("wordpressPostId", None)
            result.setdefault("wordpressUrl", "")
            result.setdefault("featuredImageId", None)
            result.setdefault("outputLogs", output_logs)
            result.setdefault("warnings", warnings)
            result["executionTime"] = round(result.get("executionTime", execution_time), 2)

    except Exception as exc:
        execution_time = time.time() - start_time
        result = _default_failure(str(exc), output_logs, warnings, execution_time)
    finally:
        try:
            input_path.unlink(missing_ok=True)
        except Exception:
            pass

    execution_time = result.get("executionTime", round(time.time() - start_time, 2))
    test_report = tests.run(result)
    result["tests"] = test_report

    insight = (
        f"status={result.get('status')} "
        f"keyword={result.get('primaryKeyword') or '-'} "
        f"post_status={result.get('postStatus') or '-'}"
    )
    save_learning(
        AGENT_NAME,
        "daily_seo_blog",
        result.get("status", "failure"),
        insight,
        strategy,
        execution_time=float(execution_time),
    )

    if result.get("status") == "success" and not test_report["passed"]:
        result["status"] = "failure"
        result["error"] = "SEO agent output failed self-tests"

    return result
