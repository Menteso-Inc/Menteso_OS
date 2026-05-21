# PatentZoom SEO Posting Agent

This agent generates one SEO-focused PatentZoom blog article per run, optionally creates a featured image, and publishes the result to WordPress as a draft by default.

## What It Does

- Chooses fresh patent-adjacent topics from live Search Console, SerpAPI, and competitor signals
- Uses moderate duplicate protection so exact repeats are blocked without locking the agent into weekday buckets
- Generates a long-form article with OpenAI in two passes
- Validates SEO basics before publishing
- Adds natural internal links from recent WordPress posts
- Uploads a featured image through the WordPress media API
- Publishes as `draft` by default unless `AUTO_PUBLISH=true` or a publish override is used
- Stores topic history in [generated-posts.json](/C:/Users/New/Desktop/Menteso_OS/agents/patentzoom_seo_agent/state/generated-posts.json)

## Local Setup

1. Install Python dependencies for the main Menteso dashboard:
```bash
pip install -r requirements.txt
```

2. Install the SEO agent dependencies:
```bash
cd agents/patentzoom_seo_agent
npm install
```

3. Add these variables to the repo-root `.env`:
```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
WP_BASE_URL=https://www.patentzoom.us
WP_USERNAME=
WP_APPLICATION_PASSWORD=
AUTO_PUBLISH=false
SITE_NAME=PatentZoom
BRAND_TONE=Professional, authoritative, practical, helpful
DEFAULT_CATEGORY=Patent Filing
DEFAULT_AUTHOR=
ENABLE_FEATURED_IMAGE=true
ENABLE_GOOGLE_INDEXING=false
GOOGLE_SERVICE_ACCOUNT_JSON=
SERPAPI_API_KEY=
```

## WordPress Application Password

1. Sign in to WordPress as the account that will own the posts.
2. Open `Users -> Profile`.
3. Find `Application Passwords`.
4. Create a new password for `PatentZoom SEO Agent`.
5. Use the WordPress username plus that application password in `.env` or GitHub Secrets.

## Local Commands

Build:
```bash
npm run build
```

Run the workflow locally:
```bash
npm run generate
```

Run from the Menteso dashboard:
```bash
python main.py dashboard
```

Run tests:
```bash
npm run test
```

## Draft vs Publish

- Default behavior is safe draft creation.
- Keep `AUTO_PUBLISH=false` while reviewing output quality.
- Set `AUTO_PUBLISH=true` only after you trust the workflow.
- From the dashboard, you can also force a single run to `publish` or `draft`.

## GitHub Actions Setup

Create these GitHub repository secrets:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `WP_BASE_URL`
- `WP_USERNAME`
- `WP_APPLICATION_PASSWORD`
- `AUTO_PUBLISH`
- `SITE_NAME`
- `BRAND_TONE`
- `DEFAULT_CATEGORY`
- `DEFAULT_AUTHOR`
- `ENABLE_FEATURED_IMAGE`
- `ENABLE_GOOGLE_INDEXING`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `SERPAPI_API_KEY`

The workflow file is [daily-patentzoom-blog.yml](/C:/Users/New/Desktop/Menteso_OS/.github/workflows/daily-patentzoom-blog.yml).

## Logs and State

- Run logs are written under `agents/patentzoom_seo_agent/runtime/logs/`
- Generated images are written under `agents/patentzoom_seo_agent/runtime/images/`
- Published-topic history is stored in `agents/patentzoom_seo_agent/state/generated-posts.json`

## Troubleshooting

- If the dashboard says the workflow could not start, run `npm install` inside `agents/patentzoom_seo_agent`.
- If WordPress publishing fails, confirm the application password and REST API access.
- If topics repeat, inspect `generated-posts.json` and confirm the workflow can commit it back on GitHub Actions.
- If image generation fails, the workflow will continue without a featured image and log a warning.
- If Google indexing is enabled, remember that Google officially limits the Indexing API mainly to `JobPosting` and livestream `VideoObject` pages.
