"""Approved first-stage manager scope; later channels remain disabled."""

RESEARCH_TASK = "prospect_research"
TASKS = (RESEARCH_TASK,)
DISABLED_CAPABILITIES = ("outreach", "ads", "sales_conversation", "customer_success")
RESEARCH_MESSAGE = (
    "Research solo, small, and mid-size firms for Lexmom Manage and Launch. "
    "Country and attorney-count rules are configurable; unresolved facts stay visible."
)
