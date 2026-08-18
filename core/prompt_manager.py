"""Prompt manager for MogBot agents."""

from __future__ import annotations

import string
from typing import Dict, Set

from prompts.agent_prompt_templates import PROMPT_TEMPLATES


class PromptManager:
    """Loads and formats prompt templates for each agent."""

    def get_template(self, agent_name: str, prompt_type: str) -> str:
        """Return a raw prompt template."""
        agent_templates: Dict[str, str] = PROMPT_TEMPLATES.get(agent_name, {})
        return agent_templates.get(prompt_type, "")

    def required_fields(self, agent_name: str, prompt_type: str) -> Set[str]:
        """Return placeholder names required by a template."""
        template = self.get_template(agent_name, prompt_type)
        required: Set[str] = set()
        for _, field_name, _, _ in string.Formatter().parse(template):
            if field_name:
                required.add(field_name)
        return required

    def render(self, agent_name: str, prompt_type: str, values: Dict[str, str]) -> str:
        """Render a prompt template with string values."""
        template = self.get_template(agent_name, prompt_type)
        if not template:
            raise ValueError(f"Missing template for agent={agent_name!r} prompt_type={prompt_type!r}")
        required = self.required_fields(agent_name, prompt_type)
        missing = sorted(field for field in required if field not in values)
        if missing:
            missing_fields = ", ".join(missing)
            raise ValueError(f"Missing required prompt fields: {missing_fields}")
        return template.format(**values)
