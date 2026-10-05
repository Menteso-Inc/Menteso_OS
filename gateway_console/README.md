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
