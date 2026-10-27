"""Reusable prospect research specialist; external services load only at execution."""

from .agent import AGENT_CONFIG, get_dashboard_data, run_agent

__all__ = ["AGENT_CONFIG", "get_dashboard_data", "run_agent"]
