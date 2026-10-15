"""Loads the agent prompts from this folder.

Each agent's instructions = shop_rules.md (shared by everyone) + its own prompt file.
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT_NAMES = ("boss", "inventory", "accounting", "facilities", "customer_service")

SHOP_RULES = (HERE / "shop_rules.md").read_text()
PROMPTS = {name: (HERE / f"{name}.md").read_text() for name in AGENT_NAMES}


def instructions_for(agent_name: str) -> str:
    """Full instructions for one agent: its own prompt, then the shared shop rules."""
    return f"{PROMPTS[agent_name]}\n\n---\n\n{SHOP_RULES}"
