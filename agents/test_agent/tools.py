import platform
import os
import shutil
import sys


def get_system_info():
    """Collect OS and hardware information."""
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "architecture": platform.architecture()[0],
        "machine": platform.machine(),
        "processor": platform.processor() or "N/A",
        "hostname": platform.node(),
    }


def get_python_info():
    """Collect Python runtime information."""
    return {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
        "packages_path": os.path.dirname(os.__file__),
    }


def get_disk_info():
    """Collect disk usage for the current drive."""
    total, used, free = shutil.disk_usage(".")
    return {
        "total_gb": round(total / (2**30), 2),
        "used_gb": round(used / (2**30), 2),
        "free_gb": round(free / (2**30), 2),
        "usage_percent": round((used / total) * 100, 1),
    }


def get_env_status():
    """Check which expected env vars are set (without revealing values)."""
    keys_to_check = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
    return {
        key: "set" if os.getenv(key) else "not set"
        for key in keys_to_check
    }
