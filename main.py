"""
Menteso Virtual Office — CLI entry point.

Usage:
    python main.py                  # List all agents
    python main.py run <agent>      # Run a specific agent
    python main.py dashboard        # Launch the web dashboard
"""
import sys
import os
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def configure_runtime_temp():
    """Use project-local runtime dirs so Playwright avoids Windows profile ACL/path issues."""
    runtime_tmp = PROJECT_ROOT / ".runtime-tmp"
    browsers_dir = PROJECT_ROOT / ".playwright-browsers"
    runtime_tmp.mkdir(exist_ok=True)
    browsers_dir.mkdir(exist_ok=True)

    for key in ("TEMP", "TMP", "TMPDIR"):
        os.environ[key] = str(runtime_tmp)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers_dir))


configure_runtime_temp()

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", override=True)
except Exception:
    pass

from shared.agent_registry import discover_agents, get_agent_runner


def list_agents():
    agents = discover_agents()
    if not agents:
        print("No agents found in agents/ directory.")
        return

    print(f"\n{'='*50}")
    print("  Menteso Virtual Office — Registered Agents")
    print(f"{'='*50}\n")

    for a in agents:
        status = a.get("status", "unknown")
        icon = "[OK]" if status == "active" else "[!!]"
        print(f"  {icon} {a.get('name', a['module_name'])}")
        print(f"      Role: {a.get('role', 'N/A')}")
        print(f"      {a.get('description', '')}")
        print()


def run_agent_cli(agent_name):
    print(f"\nRunning agent: {agent_name}\n")

    def on_step(msg):
        print(f"  > {msg}")

    try:
        runner = get_agent_runner(agent_name)
        result = runner(input_data=None, on_step=on_step)

        print(f"\n{'='*40}")
        print(f"  Status: {result.get('status', 'unknown')}")

        if result.get("status") == "success":
            import json
            print(f"  Execution time: {result.get('execution_time', 'N/A')}s")
            print(f"  Tests: {result.get('tests', {}).get('passed_count', '?')}/{result.get('tests', {}).get('total', '?')} passed")
            print(f"\n  Output:")
            print(json.dumps(result.get("data", {}), indent=4))
        else:
            print(f"  Errors: {result.get('errors', [])}")
        print(f"{'='*40}\n")

    except Exception as e:
        print(f"  ERROR: {e}")


def launch_dashboard():
    import uvicorn
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("DASHBOARD_PORT", "8000"))
    reload = os.getenv("DASHBOARD_RELOAD", "false").strip().lower() in ("1", "true", "yes")
    print("\n  Menteso Virtual Office — Dashboard")
    print(f"  Local:   http://127.0.0.1:{port}")
    print(f"  Network: http://<server-ip>:{port}\n")
    uvicorn.run("server:app", host=host, port=port, reload=reload)


def main():
    args = sys.argv[1:]

    if not args:
        list_agents()
        print("  Usage:")
        print("    python main.py                  List agents")
        print("    python main.py run <agent>      Run an agent")
        print("    python main.py dashboard        Launch web dashboard")
        print()
        return

    cmd = args[0]

    if cmd == "dashboard":
        launch_dashboard()
    elif cmd == "run" and len(args) > 1:
        run_agent_cli(args[1])
    elif cmd == "list":
        list_agents()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python main.py [list | run <agent> | dashboard]")


if __name__ == "__main__":
    main()
