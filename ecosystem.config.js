module.exports = {
  apps: [
    {
      name: "menteso-os",
      script: "C:\\sites\\Menteso_OS\\.venv\\Scripts\\python.exe",
      args: "main.py dashboard",
      cwd: "C:\\sites\\Menteso_OS",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 5000,
      env: {
        DASHBOARD_HOST: "0.0.0.0",
        DASHBOARD_PORT: "8010",
        DASHBOARD_RELOAD: "false",
        TEMP: "C:\\sites\\Menteso_OS\\.runtime-tmp",
        TMP: "C:\\sites\\Menteso_OS\\.runtime-tmp",
        TMPDIR: "C:\\sites\\Menteso_OS\\.runtime-tmp",
        PLAYWRIGHT_BROWSERS_PATH: "C:\\sites\\Menteso_OS\\.playwright-browsers"
      }
    },
    {
      // Free multi-IP rotation for the PCT agent: one Tor process exposing
      // 12 SOCKS ports (9050-9061), each an independent circuit / exit IP.
      // Enable in the PCT run by setting TOR_ENABLED=true in .env.
      name: "pct-tor",
      script: "C:\\ProgramData\\chocolatey\\lib\\tor\\tools\\tor\\tor.exe",
      args: "-f C:\\sites\\Menteso_OS\\.tor\\torrc",
      interpreter: "none",
      cwd: "C:\\sites\\Menteso_OS",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 5000
    }
  ]
};
