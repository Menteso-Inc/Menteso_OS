"""CrewAI tasks are opt-in; the default runtime uses validated zero-inference drafts."""

def create_draft_task(agent):
    from crewai import Task
    return Task(description='Review the two approved JSON campaign definitions against sourced Lexmom product facts. Return structured issues only. Do not call an email sender, create recipients or activate schedules.',
                expected_output='Structured product-specific content review with unsupported claims explicitly identified.',agent=agent)
