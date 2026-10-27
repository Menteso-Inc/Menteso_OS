# Responsive dashboard layout — 20 October 2026

The responsive research workspace and shared mobile agent menu are deployed at
`https://os.menteso.com/`. Final UI source commit:
`bc104a777008fe6670fbecb7e8b243b20ee49abc`.

## Behavior

- Saved leads use the full workspace width, below the source preview. The source
  card stays on the left when the content area is wide enough; narrower spaces
  stack the source form and results. Container queries use actual content width.
- Statistics have readable labels and consistent spacing. Filter labels sit above
  full-width controls, with 44-pixel minimum targets and stable accessible names.
  Filters wrap to two columns or one column as space decreases.
- Desktop tables retain aligned columns, contained scrolling and sticky headers.
  Narrow lead/source tables show labeled rows without horizontal page overflow.
  Long email addresses wrap within their field; qualification and Details remain
  visible. Explicit table semantics remain available to assistive technology.
- Below 768 pixels, the shared dashboard sidebar opens from a header menu button.
  The drawer includes an overlay, keyboard activation, focus containment, Escape
  dismissal, focus restoration and an inert closed state. Selecting an agent
  closes it. Desktop navigation stays visible. Header and workspace tabs adapt
  without consuming a second navigation strip on phones.
- The main area owns vertical scrolling; focusing a control or closing a drawer
  no longer scrolls the whole page/header out of view. Reduced-motion settings
  disable the sidebar transition. Dark/light colors use existing theme tokens.

No lead qualification, source permissions, provider quotas, data contracts,
campaign controls or publishing capabilities changed.

## Deployment and verification

Only actual live `static/app.js`, `static/style.css` and `static/index.html` were
patched. The first research layout patch used commit `94c3284`; the final shared
navigation patch used `bc104a7`. Both preserve unrelated live customizations.
Static cache versions are `20261020-responsive-navigation`. Neither deployment
required a service/container restart, environment update or business-data write.

- Eighteen manager checks passed, plus the existing manager UI harness against
  the patched actual live JavaScript. JavaScript syntax and PCT reconnect checks
  passed. A publication audit found no known credentials/private runtime data.
- Live public JavaScript/CSS matched the installed release hashes. Environment,
  dashboard process ID and shared-container start time remained unchanged.
  Campaign sending, publishing and paid-generation flags stayed off.
- The authenticated live workspace was checked at exact CSS widths **320, 375,
  768, 1024, 1366 and 1920**, at 900-pixel height. Document/main horizontal sizes
  matched their viewports; document height stayed at viewport height. All four
  lead filter/refresh controls retained 44-pixel minimum height.
- The phone menu opened, focused the active agent, blocked background interaction
  and closed with Escape. Product filtering returned the existing three Launch
  contacts, and a lead drawer opened at the full 375-pixel phone width. Filters,
  theme and browser viewport were restored afterward. Light theme was checked.
- A separate local preview used synthetic records, including a long email address,
  to check wrapping, product/activity variants and drawer focus restoration.
  No prospect extraction, provider-credit operation, campaign or social write
  was performed for this UI repair.

Private browser measurements, served-asset checks and the final live screenshot
remain in `runtime-data/responsive-repair-20261020/`, outside Git.

## Cleanup receipt

Stopped only the verified task-owned synthetic preview listener on
`127.0.0.1:8064`; its browser tab was closed. Reset temporary viewport overrides.
Inspected exact file paths for project containment, reparse points, byte counts
and active use before deleting with native PowerShell `LiteralPath` operations.

Local parent:
`C:\Users\hp\Desktop\Menteso\Menteso_OS\runtime-data\responsive-repair-20261020`.

| Removed child path | File bytes |
| --- | ---: |
| `live-app.js` | 273,351 |
| `live-style.css` | 93,114 |
| `patched-app.js` | 276,755 |
| `patched-style.css` | 95,015 |
| `deploy.sh` | 12,773 |

Removed file bytes: **751,008**. Measured available local space:
**18,309,296,128 → 18,310,057,984 bytes**.

No disposable remote staging/archive was created by these static-only patches.
Required rollback files and compact receipts remain under both AWS releases:

- `/home/menteso_os/agents/lexmom_sub_manager/releases/20261020-responsive-research`
- `/home/menteso_os/agents/lexmom_sub_manager/releases/20261020-responsive-navigation`

Preserved live source/static assets, data, environment, dependencies, both rollback
sets, private task helpers, detailed receipts and the review screenshot. No shared
dependency/cache directory or unrelated process was cleaned.
