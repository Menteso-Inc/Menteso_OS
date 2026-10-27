"""Public application/privacy disclosures only. No runtime data or credentials are exposed."""
from fastapi.responses import HTMLResponse

BASE='/api/agents/lexmom_marketing_agent/social'
HOME=BASE+'/about'
PRIVACY=BASE+'/privacy'

CONTENT={
    'about':'''<p class="eyebrow">LEXMOM · SOCIAL WORKSPACE</p><h1>LexMom Social Media Agent</h1>
<p class="intro">A workspace for LexMom's authorized team to prepare, review and manage content for its own social channels.</p>
<h2>YouTube connection</h2><p>The channel owner chooses their existing channel through Google's consent screen. The app checks the channel identity, displays channel analytics and can upload an approved video after publishing is activated by the operator.</p>
<p>The Google permissions cover YouTube channel read access, video upload and read-only YouTube Analytics. Google passwords are never collected by this app. Offline access lets the AWS worker renew the connection after the owner closes their browser.</p>
<h2>Review before upload</h2><p>Operators can preview a video and choose Private, Unlisted or Public visibility. Content, media, channel, visibility and publishing time must match the approved draft. Preparation alone never uploads a video. Publishing and uploads are currently disabled.</p>
<h2>Account control</h2><p>The signed-in operator can disconnect YouTube and remove its stored API data. This does not delete videos from YouTube or locally authored drafts.</p>
<p><a href="/#lexmom/social_media_posting_agent">Open the authenticated workspace</a> · <a href="https://lexmom.com/">Visit LexMom</a></p>''',
    'privacy':'''<p class="eyebrow">LEXMOM · PRIVACY</p><h1>Social Media Agent privacy notice</h1><p>Effective 15 October 2026. This notice describes the LexMom Social Media Agent operated by Menteso, Inc. at os.menteso.com.</p>
<h2>Information accessed and its purpose</h2><p>With the channel owner's consent, the app uses YouTube API Services to verify the selected channel, read aggregate channel reports and upload operator-approved video content. Requested permissions are YouTube channel read, video upload and read-only YouTube Analytics. Draft text, images and videos are supplied or prepared for LexMom by its authorized operators.</p>
<h2>Storage and sharing</h2><p>OAuth credentials are stored in protected server environment files. Temporary access tokens are held in worker memory. Current channel connection checks, aggregate analytics and upload receipt references are stored in the private AWS runtime. Only authenticated authorized operators can view this data. Approved uploads and the credentials required to authorize them are sent to Google through its official APIs. The server hosting provider is AWS. YouTube channel data and analytics are not supplied to AI text, image or model-training tools, sold, or used to target advertising.</p>
<h2>Retention and removal</h2><p>The monitor normally refreshes channel checks and analytics every fifteen minutes. The dashboard marks older checks as stale. Confirmed authorization revocation removes the live saved grant and cached YouTube API data. The Disconnect YouTube control revokes the grant and removes live stored YouTube API data and managed upload receipt values. Authored draft/media files and internal duplicate-upload protection remain; disconnect does not delete videos hosted by YouTube.</p>
<p>To request removal of retained operational copies or other data, contact <a href="mailto:mail@lexmom.com">mail@lexmom.com</a>. Authorized deletion requests are handled as soon as possible and within seven calendar days. You can also revoke the app's access at <a href="https://security.google.com/settings/security/permissions">Google account permissions</a>.</p>
<h2>Your controls and security</h2><p>The channel owner chooses the channel and permissions during OAuth consent. The application verifies the configured LexMom channel before accepting a grant. Dashboard operations require an authorized account; write actions require a request from the same website. Publishing is disabled until explicitly activated, and uploads require approval of the exact content, media, destination, visibility and schedule.</p>
<p>Use of Google API information follows the <a href="https://developers.google.com/terms/api-services-user-data-policy">Google API Services User Data Policy</a>, including its Limited Use requirements. See also the <a href="https://policies.google.com/privacy">Google Privacy Policy</a> and <a href="https://www.youtube.com/t/terms">YouTube Terms of Service</a>.</p>
<h2>Contact</h2><p>For privacy questions, access requests or complaints, email <a href="mailto:mail@lexmom.com">mail@lexmom.com</a>.</p>'''
}


def public_page(kind):
    content=CONTENT[kind]
    document='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>LexMom Social Media Agent</title><style>
*{box-sizing:border-box}body{margin:0;background:#f6f4ff;color:#19162d;font:1rem/1.65 system-ui,sans-serif}main{max-width:54rem;margin:clamp(1rem,5vw,4rem) auto;padding:clamp(1.25rem,5vw,3.5rem);background:white;border:1px solid #ded7f6;border-radius:1.25rem}h1{font-size:clamp(1.8rem,5vw,2.75rem);line-height:1.15}h2{font-size:1.2rem;margin-top:2rem}.eyebrow{font-size:.8rem;font-weight:700;letter-spacing:.1em;color:#5130a4}.intro{font-size:1.15rem}a{color:#4b26bc;text-underline-offset:.2em;overflow-wrap:anywhere}nav{display:flex;flex-wrap:wrap;gap:1rem;border-top:1px solid #ded7f6;margin-top:2rem;padding-top:1rem}nav a{display:inline-flex;align-items:center;min-height:44px}</style></head><body><main>'''+content+f'<nav aria-label="Application links"><a href="{HOME}">About the app</a><a href="{PRIVACY}">Privacy notice</a><a href="https://lexmom.com/manage/terms-and-conditions">Terms</a></nav></main></body></html>'
    return HTMLResponse(document,headers={'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'})
