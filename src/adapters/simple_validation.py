"""
Simple validation adapter for Quality Assurance MCP Server.

This adapter provides basic validation for pixi task names and arguments
without the complex agent validation functionality from other projects.
"""

import re
from typing import List

from core.ports import ValidationPort


class SimpleValidationAdapter(ValidationPort):
    """
    Simple validation adapter for basic pixi operations.

    Provides essential validation without complex agent-specific functionality.
    """

    def __init__(self):
        """Initialize simple validation adapter."""
        # Common pixi task patterns
        self.valid_task_pattern = re.compile(r"^[a-zA-Z][a-zA-Z0-9\-_]*$")

        # Blocked dangerous commands/arguments
        self.blocked_patterns = [
            r"rm\s+-rf",
            r"sudo",
            r"chmod\s+777",
            r"\.\./",  # Directory traversal
            r"`",  # Command substitution
            r"\$\(",  # Command substitution
        ]

    def validate_task_name(self, task_name: str) -> bool:
        """
        Validate pixi task name.

        Args:
            task_name: Task name to validate

        Returns:
            True if task name is valid, False otherwise
        """
        if not task_name:
            return False

        if len(task_name) > 100:  # Reasonable length limit
            return False

        # Check against valid pattern
        if not self.valid_task_pattern.match(task_name):
            return False

        # Check for blocked patterns
        for pattern in self.blocked_patterns:
            if re.search(pattern, task_name, re.IGNORECASE):
                return False

        return True

    def validate_arguments(self, args: List[str]) -> List[str]:
        """
        Validate and sanitize arguments.

        Args:
            args: List of arguments to validate

        Returns:
            List of sanitized arguments (may be empty if all are invalid)
        """
        if not args:
            return []

        validated_args = []

        for arg in args:
            if self._is_safe_argument(arg):
                validated_args.append(arg)

        return validated_args

    def _is_safe_argument(self, arg: str) -> bool:
        """
        Check if an argument is safe to use.

        Args:
            arg: Argument to check

        Returns:
            True if argument is safe, False otherwise
        """
        if not arg:
            return False

        if len(arg) > 500:  # Reasonable length limit
            return False

        # Check for blocked patterns
        for pattern in self.blocked_patterns:
            if re.search(pattern, arg, re.IGNORECASE):
                return False

        # Block arguments that try to escape or execute commands
        dangerous_chars = ["|", "&", ";", "`", "$"]
        for char in dangerous_chars:
            if char in arg:
                return False

        return True
