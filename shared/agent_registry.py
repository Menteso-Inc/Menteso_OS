import importlib
from pathlib import Path

AGENTS_DIR = Path(__file__).parent.parent / "agents"


def discover_agents():
    """Scan agents/ directory and return list of agent configs."""
    agents = []

    if not AGENTS_DIR.exists():
        return agents

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
    module = importlib.import_module(f"agents.{module_name}")
    return module.run_agent
