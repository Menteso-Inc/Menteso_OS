def run_agent(*args, **kwargs):
    from .agent import run_agent as execute
    return execute(*args, **kwargs)

__all__ = ['run_agent']
