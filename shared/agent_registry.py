import importlib
import os
from pathlib import Path

AGENTS_DIR = Path(__file__).parent.parent / "agents"


def _disabled_agents():
    return {
        name.strip()
        for name in os.getenv("MENTESO_DISABLED_AGENTS", "").split(",")
        if name.strip()
    }


def discover_agents():
    """Scan agents/ directory and return list of agent configs."""
    agents = []

    if not AGENTS_DIR.exists():
        return agents

    disabled = _disabled_agents()
    for item in sorted(AGENTS_DIR.iterdir()):
        if not item.is_dir() or item.name.startswith("_"):
            continue
        init_file = item / "__init__.py"
        if not init_file.exists():
            continue

        try:
            module = importlib.import_module(f"agents.{item.name}")
            if hasattr(module, "AGENT_CONFIG"):
                config = dict(module.AGENT_CONFIG)
                config["module_name"] = item.name
                if item.name in disabled:
                    # Keep hybrid/local agents visible in the shared dashboard,
                    # while get_agent_runner() continues to block execution on
                    # this AWS target.
                    config["execution_disabled"] = True
                    config["execution_target"] = "local_server"
                    config["runtime_status"] = "remote"
                agents.append(config)
        except Exception as e:
            agents.append({
                "name": item.name,
                "description": f"Error loading agent: {e}",
                "status": "error",
                "module_name": item.name,
            })

    return agents


def get_agent_runner(module_name):
    """Import and return the run_agent function for an agent."""
    if module_name in _disabled_agents():
        raise PermissionError(f"Agent {module_name!r} is disabled on this execution target")
    module = importlib.import_module(f"agents.{module_name}")
    return module.run_agent
