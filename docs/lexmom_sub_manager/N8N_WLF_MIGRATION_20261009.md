# n8n / WLF SDR paused migration — 2026-10-09

User authorized moving n8n and WLF SDR from the Mumbai gateway to Menteso OS,
preserving credentials for future Lexmom use, stopping their API spending, and
showing both workloads in the os.menteso.com dashboard.

## Result

- Source: `menteso-server-gateway`, Mumbai (`ap-south-1`).
- Destination: `Menteso OS`, Ohio (`us-east-2`).
- Destination root: `/home/menteso_os/agents/n8n_wlf` (private).
- 38 workflow records restored, including saved variants; all 38 match WLF/SDR.
- 11 credentials restored and successfully decrypted offline; seven are
  referenced by WLF workflows. Provider validity was not tested.
- The database contained zero active workflows and zero execution-history
  records at verification. Existing database tables, workflow data, native
  encrypted credentials, n8n files, sandbox TLS/data and inner Docker storage
  were copied. These counts are not counts of distinct operational agents.
- All six n8n containers are stopped on both servers. The Ohio containers are
  created, with the runtime images available, but the application was not started.
- All six destination containers match the original source image IDs exactly;
  the runtime Compose file pins repository digests rather than mutable tags.
- Both Compose configurations use `profiles: [paused]` and `restart: no`.
  The destination network is internal-only; the source backup timer is disabled.
- n8n Automation and WLF SDR are separate authenticated dashboard entries,
  displaying saved counts and a dated pause receipt. No run action is enabled.
- `n8n.menteso.com` returns an explicit paused-service response (HTTP 503),
  directing users to os.menteso.com instead of exposing an execution editor.

## Credentials and reuse

- Runtime environment: `runtime/.env` below the destination root.
- Reusable credential vault: `credential-vault/.env`, root-owned, mode 0600,
  inside a private directory. It holds all exported credential records as
  namespaced environment variables; every record was verified to round-trip
  through the dotenv parser. The temporary decrypted JSON export was deleted.
- The private `credential-inventory.json` maps credential names/types to env
  variable names. Secret values were never printed or copied into this repo.
- The WLF OpenAI key is available as `WLF_SDR_OPENAI_API_KEY` in that vault.
  Other credential records retain their original identities and metadata.
- Lexmom's existing environment was not overwritten. Gmail/Meta/Zoho credentials
  remain associated with their WLF accounts. Future integration must select the
  intended provider and identity explicitly; the full vault should not be loaded
  into every agent process.
- This pauses the local workloads, **not the OpenAI account or key itself**.
  Other applications using the same credentials can still incur charges.

## Preservation and rollback

`migration-backup-20261009.tar.gz` is a retained private rollback backup,
705,233,143 bytes, SHA-256
`7ae8204fb637d529f496eb2ccaecac11f7491bc88e330589e83ff72b5d030f08`.
It contains the original project/configuration, a PostgreSQL logical dump,
cold PostgreSQL data and the mounted files. `restored/` contains the restored
data used by destination bind mounts; it is live runtime data, not cleanup
material. Original stopped source data is retained for rollback.

Source rollback configuration is under `/root/n8n-migration-20261009`.
Dashboard rollback source and test evidence are under
`/home/menteso_os/agents/lexmom_sub_manager/releases/n8n-wlf-dashboard-20261009`.
Do not start the source and destination concurrently. Reactivation requires
explicit authorization, account/budget checks, webhook routing decisions and
review of the original execution configuration. Never simply remove the pause
profile or network isolation to make a workflow test pass.

## Validation and limits

- 12 dashboard tests passed locally and on AWS: authentication, viewer/origin
  restrictions, existing Lexmom behavior, secret exclusion, hidden unverified
  migrations, and refusal to execute paused workloads.
- JavaScript syntax check passed. Public dashboard JavaScript matched the
  deployed SHA-256 `706954b6d0a083dfc172d46a562fb99090fa719416793d6f85f2cfaa093e6a41`.
- Public imported-workload APIs returned 401 without authentication.
- Destination credential permissions and absence of the transient decrypted
  export were verified. Database counts and decryptability were checked offline.
- The shared `menteso-os` container kept its original 2026-10-05 start time.
  LinkedIn PostgreSQL on the gateway stayed running. PCT was not restarted.
- Only the isolated Lexmom dashboard service was restarted; Caddy was reloaded
  with validated scoped routes. No marketing messages, paid research runs or
  provider billing probes were performed.
- Authenticated browser visual verification awaits the user's sign-in. The
  dashboard pause status is a dated verification snapshot, not a live Docker
  monitor. No automatic resume is scheduled.

Cleanup details are recorded in `N8N_WLF_CLEANUP_20261009.json`. Required backups,
secrets, restored data, images needed by the paused stack and release evidence
are intentionally retained.
