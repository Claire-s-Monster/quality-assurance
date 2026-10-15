"""
Template stub adapter - minimal implementation for agent ecosystem server.
"""

from typing import List, Dict, Any
from core.models import AgentTemplate


class TemplateStubAdapter:
    """Stub implementation for template management."""

    def list_templates(self) -> List[AgentTemplate]:
        """Return empty list of templates."""
        return []

    def get_template(self, template_id: str) -> AgentTemplate:
        """Return a basic template."""
        return AgentTemplate(
            id="basic",
            name="Basic Agent",
            description="Basic agent template",
            version="1.0.0",
            content="",
            variables={},
            categories=["general"],
        )

    def create_template(self, template: AgentTemplate) -> bool:
        """Stub - always returns True."""
        return True

    def update_template(self, template_id: str, updates: Dict[str, Any]) -> bool:
        """Stub - always returns True."""
        return True

    def delete_template(self, template_id: str) -> bool:
        """Stub - always returns True."""
        return True
