import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def get_env(key, required=False, default=None):
    """Get an environment variable. Raises ValueError if required and missing."""
    value = os.getenv(key, default)
    if required and not value:
        raise ValueError(f"{key} is not set in .env")
    return value


# Global defaults
DEFAULT_LLM_MODEL = get_env("DEFAULT_LLM_MODEL", default="gpt-4o")
