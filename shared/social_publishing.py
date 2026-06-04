import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


WORKSPACE_SOCIAL = {
    "patentzoom": {
        "env_prefix": "PATENTZOOM",
        "name": "PatentZoom",
        "default_platforms": ["facebook", "instagram", "linkedin"],
        "base_hashtags": ["#PatentStrategy", "#Innovation", "#PatentLaw"],
    },
    "patent-drawing-experts": {
        "env_prefix": "PATENT_DRAWING_EXPERTS",
        "name": "Patent Drawing Experts",
        "default_platforms": ["facebook", "linkedin"],
        "base_hashtags": ["#PatentDrawings", "#USPTO", "#PatentIllustration"],
    },
    "ip-docketers": {
        "env_prefix": "IP_DOCKETERS",
        "name": "IP Docketers",
        "default_platforms": ["facebook", "linkedin"],
        "base_hashtags": ["#IPDocketing", "#LawFirmOps", "#IPManagement"],
    },
    "menteso": {
        "env_prefix": "MENTESO",
        "name": "Menteso",
        "default_platforms": ["facebook", "linkedin"],
        "base_hashtags": ["#AIAutomation", "#Operations", "#Menteso"],
    },
}

_META_TOKEN_HEALTH_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_META_TOKEN_HEALTH_TTL_SECONDS = 300


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_workspace_id(workspace_id: str | None) -> str:
    key = str(workspace_id or "patentzoom").strip().lower() or "patentzoom"
    return key if key in WORKSPACE_SOCIAL else "patentzoom"


def _workspace_meta(workspace_id: str | None) -> dict[str, Any]:
    return WORKSPACE_SOCIAL[_normalize_workspace_id(workspace_id)]


def _prefixed_env_key(workspace_id: str | None, suffix: str) -> str:
    prefix = _workspace_meta(workspace_id)["env_prefix"]
    return f"{prefix}_{suffix}"


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _strip_html(value: Any) -> str:
    return _clean_text(re.sub(r"<[^>]+>", " ", str(value or "")))


def _slug_to_hashtag(value: str) -> str:
    words = [part for part in re.split(r"[^a-zA-Z0-9]+", value or "") if part]
    if not words:
        return ""
    return "#" + "".join(word[:1].upper() + word[1:] for word in words[:4])


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for item in items:
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(item.strip())
    return ordered


def _build_hashtags(workspace_id: str | None, primary_keyword: str, title: str) -> list[str]:
    meta = _workspace_meta(workspace_id)
    dynamic = []
    keyword_tag = _slug_to_hashtag(primary_keyword)
    title_tag = _slug_to_hashtag(title)
    if keyword_tag:
        dynamic.append(keyword_tag)
    if title_tag and title_tag.lower() != keyword_tag.lower():
        dynamic.append(title_tag)
    return _dedupe_preserve_order(list(meta.get("base_hashtags") or []) + dynamic)[:5]


def _excerpt_from_payload(payload: dict[str, Any]) -> str:
    excerpt = _clean_text(payload.get("excerpt") or "")
    if excerpt:
        return excerpt
    article = payload.get("article") or {}
    article_excerpt = _clean_text(article.get("excerpt") or "")
    if article_excerpt:
        return article_excerpt
    article_html = article.get("articleHtml") or payload.get("articleHtml") or ""
    text = _strip_html(article_html)
    if not text:
        return ""
    return text[:220].rsplit(" ", 1)[0].strip()


def build_social_caption(
    workspace_id: str | None,
    payload: dict[str, Any],
    platform: str,
    use_hashtags: bool = True,
) -> str:
    workspace = _workspace_meta(workspace_id)
    title = _clean_text(payload.get("title") or "")
    primary_keyword = _clean_text(payload.get("primaryKeyword") or "")
    url = _clean_text(payload.get("wordpressUrl") or payload.get("url") or "")
    excerpt = _excerpt_from_payload(payload)
    intro = excerpt or f"New from {workspace['name']}: {title}"
    intro = intro[:240].rsplit(" ", 1)[0].strip(" -,:;")
    cta = "Read the full article"
    if platform == "instagram":
        cta = "Read more via the link in bio"

    lines = [title] if title else []
    if intro and intro.lower() != title.lower():
        lines.append(intro)
    if primary_keyword:
        lines.append(f"Focus topic: {primary_keyword}")
    if url:
        lines.append(f"{cta}: {url}")
    if use_hashtags:
        tags = _build_hashtags(workspace_id, primary_keyword, title)
        if tags:
            lines.append(" ".join(tags))
    return "\n\n".join(line for line in lines if line)


def _extract_og_image(url: str, timeout: int = 25) -> str:
    if not url:
        return ""
    try:
        response = requests.get(url, timeout=timeout, headers={"User-Agent": "MentesoSocialBot/1.0"})
        response.raise_for_status()
        html = response.text
        match = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            html,
            flags=re.IGNORECASE,
        )
        if match:
            return _clean_text(match.group(1))
    except Exception:
        return ""
    return ""


def get_social_config(workspace_id: str | None, env: dict[str, Any]) -> dict[str, Any]:
    workspace_key = _normalize_workspace_id(workspace_id)
    meta = _workspace_meta(workspace_key)
    default_platforms = list(meta.get("default_platforms") or [])
    requested_platforms = _clean_text(env.get(_prefixed_env_key(workspace_key, "SOCIAL_PLATFORMS"))).lower()
    platforms = default_platforms
    if requested_platforms:
        parsed = [item.strip().lower() for item in requested_platforms.split(",") if item.strip()]
        if parsed:
            platforms = parsed

    facebook_page_id = _clean_text(env.get(_prefixed_env_key(workspace_key, "SOCIAL_FACEBOOK_PAGE_ID")))
    meta_access_token = _clean_text(env.get(_prefixed_env_key(workspace_key, "SOCIAL_META_ACCESS_TOKEN")))
    instagram_account_id = _clean_text(env.get(_prefixed_env_key(workspace_key, "SOCIAL_INSTAGRAM_BUSINESS_ACCOUNT_ID")))
    linkedin_organization = _clean_text(env.get(_prefixed_env_key(workspace_key, "SOCIAL_LINKEDIN_ORGANIZATION_URN")))
    linkedin_access_token = _clean_text(env.get(_prefixed_env_key(workspace_key, "SOCIAL_LINKEDIN_ACCESS_TOKEN")))

    configured = {
        "facebook": bool(facebook_page_id and meta_access_token),
        "instagram": bool(instagram_account_id and meta_access_token),
        "linkedin": bool(linkedin_organization and linkedin_access_token),
    }

    return {
        "workspaceId": workspace_key,
        "workspaceName": meta["name"],
        "autoPostEnabled": _is_truthy(env.get(_prefixed_env_key(workspace_key, "SOCIAL_AUTO_POST"))),
        "useFeaturedImage": not str(env.get("SOCIAL_USE_FEATURED_IMAGE", "true")).strip().lower() == "false",
        "useHashtags": not str(env.get("SOCIAL_USE_HASHTAGS", "true")).strip().lower() == "false",
        "platforms": platforms,
        "facebookPageId": facebook_page_id,
        "instagramBusinessAccountId": instagram_account_id,
        "linkedinOrganizationUrn": linkedin_organization,
        "metaAccessToken": meta_access_token,
        "linkedinAccessToken": linkedin_access_token,
        "configured": configured,
        "configuredPlatformCount": sum(1 for value in configured.values() if value),
        "metaGraphVersion": _clean_text(env.get("META_GRAPH_API_VERSION")) or "v23.0",
        "linkedinVersion": _clean_text(env.get("LINKEDIN_API_VERSION")) or "202605",
    }


def _meta_token_health(config: dict[str, Any]) -> dict[str, Any]:
    token = _clean_text(config.get("metaAccessToken"))
    if not token:
        return {"checked": False, "valid": False, "status": "missing", "detail": "Meta token is not configured."}

    page_id = _clean_text(config.get("facebookPageId"))
    if not page_id:
        return {"checked": False, "valid": False, "status": "missing", "detail": "Facebook Page ID is not configured."}

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    cache_key = f"{config.get('workspaceId')}:{page_id}:{token_hash}"
    cached = _META_TOKEN_HEALTH_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < _META_TOKEN_HEALTH_TTL_SECONDS:
        return dict(cached[1])

    try:
        response = requests.get(
            f"https://graph.facebook.com/{config['metaGraphVersion']}/{page_id}",
            params={"fields": "id,name", "access_token": token},
            timeout=5,
        )
        data = response.json()
        if response.ok:
            result = {
                "checked": True,
                "valid": True,
                "status": "valid",
                "detail": f"Meta token is valid for {data.get('name') or 'this page'}.",
            }
            _META_TOKEN_HEALTH_CACHE[cache_key] = (now, result)
            return dict(result)

        error = data.get("error") if isinstance(data, dict) else {}
        message = _clean_text((error or {}).get("message") or response.text[:300])
        code = str((error or {}).get("code") or "")
        subcode = str((error or {}).get("error_subcode") or (error or {}).get("subcode") or "")
        status = "expired" if code == "190" or "expired" in message.lower() else "invalid"
        result = {
            "checked": True,
            "valid": False,
            "status": status,
            "detail": message or "Meta token validation failed.",
            "code": code,
            "subcode": subcode,
        }
        _META_TOKEN_HEALTH_CACHE[cache_key] = (now, result)
        return dict(result)
    except Exception as exc:
        result = {
            "checked": True,
            "valid": False,
            "status": "check_failed",
            "detail": f"Could not check Meta token: {exc}",
        }
        if cached:
            stale = dict(cached[1])
            stale["checked"] = True
            stale["stale"] = True
            stale["detail"] = f"{stale.get('detail', 'Using last token health result.')} Latest check failed: {exc}"
            return stale
        return result


def read_social_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"history": [], "updatedAt": "", "workspaceId": ""}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"history": [], "updatedAt": "", "workspaceId": ""}


def write_social_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_social_history(path: Path, workspace_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    state = read_social_state(path)
    history = state.get("history") if isinstance(state.get("history"), list) else []
    history.insert(0, entry)
    state["history"] = history[:50]
    state["workspaceId"] = workspace_id
    state["updatedAt"] = _now_iso()
    write_social_state(path, state)
    return state


def social_status_snapshot(workspace_id: str | None, env: dict[str, Any], state_path: Path | None = None) -> dict[str, Any]:
    config = get_social_config(workspace_id, env)
    meta_health = _meta_token_health(config)
    history = []
    updated_at = ""
    if state_path:
        state = read_social_state(state_path)
        history = state.get("history") if isinstance(state.get("history"), list) else []
        updated_at = _clean_text(state.get("updatedAt"))
    return {
        "workspaceId": config["workspaceId"],
        "workspaceName": config["workspaceName"],
        "autoPostEnabled": config["autoPostEnabled"],
        "useFeaturedImage": config["useFeaturedImage"],
        "useHashtags": config["useHashtags"],
        "platforms": config["platforms"],
        "configured": config["configured"],
        "configuredPlatformCount": config["configuredPlatformCount"],
        "tokenHealth": {
            "meta": meta_health,
            "linkedin": {
                "checked": False,
                "valid": bool(config.get("linkedinAccessToken")),
                "status": "configured" if config.get("linkedinAccessToken") else "missing",
                "detail": "LinkedIn token health check is pending setup.",
            },
        },
        "updatedAt": updated_at,
        "recentHistory": history[:10],
    }


def _post_facebook(config: dict[str, Any], message: str, article_url: str) -> dict[str, Any]:
    endpoint = f"https://graph.facebook.com/{config['metaGraphVersion']}/{config['facebookPageId']}/feed"
    response = requests.post(
        endpoint,
        data={
            "message": message,
            "link": article_url,
            "access_token": config["metaAccessToken"],
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return {"ok": True, "platform": "facebook", "postId": data.get("id", ""), "response": data}


def _post_instagram(config: dict[str, Any], caption: str, image_url: str) -> dict[str, Any]:
    create_endpoint = (
        f"https://graph.facebook.com/{config['metaGraphVersion']}/"
        f"{config['instagramBusinessAccountId']}/media"
    )
    create_response = requests.post(
        create_endpoint,
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": config["metaAccessToken"],
        },
        timeout=30,
    )
    create_response.raise_for_status()
    creation_data = create_response.json()
    creation_id = _clean_text(creation_data.get("id"))
    if not creation_id:
        raise RuntimeError("Instagram media container creation did not return an id.")

    publish_endpoint = (
        f"https://graph.facebook.com/{config['metaGraphVersion']}/"
        f"{config['instagramBusinessAccountId']}/media_publish"
    )
    publish_response = requests.post(
        publish_endpoint,
        data={
            "creation_id": creation_id,
            "access_token": config["metaAccessToken"],
        },
        timeout=30,
    )
    publish_response.raise_for_status()
    publish_data = publish_response.json()
    return {
        "ok": True,
        "platform": "instagram",
        "creationId": creation_id,
        "postId": publish_data.get("id", ""),
        "response": publish_data,
    }


def _post_linkedin(config: dict[str, Any], commentary: str) -> dict[str, Any]:
    endpoint = "https://api.linkedin.com/rest/posts"
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {config['linkedinAccessToken']}",
            "Linkedin-Version": config["linkedinVersion"],
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        },
        json={
            "author": config["linkedinOrganizationUrn"],
            "commentary": commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        },
        timeout=30,
    )
    response.raise_for_status()
    post_id = _clean_text(response.headers.get("x-restli-id"))
    body = {}
    if response.text.strip():
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text[:500]}
    return {"ok": True, "platform": "linkedin", "postId": post_id, "response": body}


def publish_article_to_social(
    workspace_id: str | None,
    payload: dict[str, Any],
    env: dict[str, Any],
    state_path: Path | None = None,
) -> dict[str, Any]:
    config = get_social_config(workspace_id, env)
    workspace_key = config["workspaceId"]
    article_url = _clean_text(payload.get("wordpressUrl") or payload.get("url"))
    title = _clean_text(payload.get("title") or "")
    primary_keyword = _clean_text(payload.get("primaryKeyword") or "")
    excerpt = _excerpt_from_payload(payload)
    image_url = ""

    if not article_url:
        raise ValueError("A published article URL is required before posting to social media.")

    results: dict[str, Any] = {}
    errors: list[str] = []

    if config["useFeaturedImage"]:
        image_url = _extract_og_image(article_url)

    for platform in config["platforms"]:
        platform_key = str(platform).strip().lower()
        if platform_key not in {"facebook", "instagram", "linkedin"}:
            continue

        if not config["configured"].get(platform_key):
            results[platform_key] = {
                "ok": False,
                "status": "not_configured",
                "message": f"{platform_key.title()} posting is not configured for this workspace.",
            }
            continue

        try:
            caption = build_social_caption(
                workspace_key,
                {
                    "title": title,
                    "wordpressUrl": article_url,
                    "excerpt": excerpt,
                    "primaryKeyword": primary_keyword,
                    "article": payload.get("article") or {},
                },
                platform_key,
                use_hashtags=config["useHashtags"],
            )
            if platform_key == "facebook":
                results[platform_key] = _post_facebook(config, caption, article_url)
            elif platform_key == "instagram":
                if not image_url:
                    raise RuntimeError("Instagram posting requires a featured image URL from the published article.")
                results[platform_key] = _post_instagram(config, caption, image_url)
            elif platform_key == "linkedin":
                results[platform_key] = _post_linkedin(config, caption)
        except Exception as exc:
            message = str(exc)
            results[platform_key] = {"ok": False, "status": "failed", "message": message}
            errors.append(f"{platform_key}: {message}")

    summary = {
        "workspaceId": workspace_key,
        "workspaceName": config["workspaceName"],
        "autoPostEnabled": config["autoPostEnabled"],
        "articleUrl": article_url,
        "title": title,
        "primaryKeyword": primary_keyword,
        "imageUrl": image_url,
        "postedAt": _now_iso(),
        "results": results,
        "ok": any(bool(item.get("ok")) for item in results.values()),
        "errors": errors,
    }

    if state_path:
        append_social_history(state_path, workspace_key, summary)
    return summary
