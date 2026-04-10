"""
Menteso Virtual Office — CLI entry point.

Usage:
    python main.py                  # List all agents
    python main.py run <agent>      # Run a specific agent
    python main.py dashboard        # Launch the web dashboard
"""
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

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
    print("\n  Menteso Virtual Office — Dashboard")
    print("  http://127.0.0.1:8000\n")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)


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
