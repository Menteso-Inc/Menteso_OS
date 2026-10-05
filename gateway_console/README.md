# OpenAI usage dashboard for server.menteso.com

This directory contains the OpenAI organization usage dashboard deployed to the
authenticated Menteso Server Console at `https://server.menteso.com/openai-dashboard`.

The console process imports `openai_usage.py` and serves `openai-dashboard.html`.
Its systemd environment file is `/etc/menteso-console/console.env`. Organization
cost and per-key usage require `OPENAI_ADMIN_KEY`; workload and project service
keys must not be substituted because OpenAI denies them access to organization
usage endpoints.

The key stays in the server environment and is never sent to the browser or
written to logs. Restart `menteso-console-next.service` after changing it.

The dashboard loads all projects (including archived ones), lists enabled project
keys with `owner_project_access=any`, and retains historical IDs from usage/costs.
Admin reporting keys are not workload keys and are not used for model requests.
Keys with zero activity remain visible. Deleted keys may only have a historical
ID because OpenAI no longer returns their names or owners.

Spend is taken directly from OpenAI's Costs API, grouped by key, project and
invoice line item. No token-price estimates are substituted. Usage and billing
can update at different times; the dashboard does not report prepaid balance.
Project/owner/model/API-family attribution does not reveal each application or
website sharing a key. That requires application telemetry or separate keys.

Search and CSV export use masked identifiers only. The Admin credential stays in
the root-readable systemd environment file, never in HTML, exports or API output.
