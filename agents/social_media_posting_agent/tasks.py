def create_task(agent):
    from crewai import Task
    return Task(description='Prepare a Lexmom week using approved product facts and brand assets. Return platform-specific private drafts; never publish or upload.',
        expected_output='Validated product/platform content JSON with distinct draft keys and zero public publications.',agent=agent)
