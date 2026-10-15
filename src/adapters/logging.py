"""
Logging adapter for Agent Ecosystem MCP Server.

Provides structured logging with agent operation tracking and security events.
"""

import json
import logging
import sys
import os
from typing import Any, Dict, Optional
from datetime import datetime

# Add parent directory to path to access core modules
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from core.ports import LoggingPort


class LoggingAdapter(LoggingPort):
    """Adapter for structured logging with agent ecosystem operation support."""

    def __init__(self):
        # Configure main logger
        self.logger = logging.getLogger("agent_ecosystem")
        self.logger.setLevel(logging.INFO)

        # Configure security logger
        self.security_logger = logging.getLogger("agent_ecosystem.security")
        self.security_logger.setLevel(logging.INFO)

        # Configure operations logger
        self.operations_logger = logging.getLogger("agent_ecosystem.operations")
        self.operations_logger.setLevel(logging.INFO)

        # Set up console handler if not already configured
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(logging.INFO)

            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)

            self.logger.addHandler(handler)
            self.security_logger.addHandler(handler)
            self.operations_logger.addHandler(handler)

    def log_info(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Log an informational message."""
        if context:
            enhanced_message = (
                f"{message} | Context: {json.dumps(context, default=str)}"
            )
        else:
            enhanced_message = message

        self.logger.info(enhanced_message)

    def log_warning(
        self, message: str, context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log a warning message."""
        if context:
            enhanced_message = (
                f"{message} | Context: {json.dumps(context, default=str)}"
            )
        else:
            enhanced_message = message

        self.logger.warning(enhanced_message)

    def log_error(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Log an error message."""
        if context:
            enhanced_message = (
                f"{message} | Context: {json.dumps(context, default=str)}"
            )
        else:
            enhanced_message = message

        self.logger.error(enhanced_message)

    def log_agent_operation(
        self, operation: str, context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log an agent ecosystem operation."""
        operation_context = {
            "operation": operation,
            "timestamp": datetime.now().isoformat(),
            **(context or {}),
        }

        enhanced_message = f"OPERATION: {operation} | Context: {json.dumps(operation_context, default=str)}"
        self.operations_logger.info(enhanced_message)

    def log_security_event(
        self, event: str, context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log a security-related event."""
        security_context = {
            "event": event,
            "timestamp": datetime.now().isoformat(),
            **(context or {}),
        }

        enhanced_event = (
            f"SECURITY: {event} | Context: {json.dumps(security_context, default=str)}"
        )
        self.security_logger.warning(enhanced_event)

    def log_agent_discovery(
        self, scope: str, agent_count: int, context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log agent discovery operations."""
        discovery_context = {
            "scope": scope,
            "agent_count": agent_count,
            "timestamp": datetime.now().isoformat(),
            **(context or {}),
        }

        enhanced_message = f"DISCOVERY: Found {agent_count} agents in {scope} scope | Context: {json.dumps(discovery_context, default=str)}"
        self.operations_logger.info(enhanced_message)

    def log_agent_validation(
        self,
        agent_path: str,
        passed: bool,
        score: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log agent validation results."""
        validation_context = {
            "agent_path": agent_path,
            "passed": passed,
            "score": score,
            "timestamp": datetime.now().isoformat(),
            **(context or {}),
        }

        status = "PASSED" if passed else "FAILED"
        enhanced_message = f"VALIDATION: {agent_path} {status} (score: {score}) | Context: {json.dumps(validation_context, default=str)}"

        if passed:
            self.operations_logger.info(enhanced_message)
        else:
            self.operations_logger.warning(enhanced_message)

    def log_agent_lifecycle(
        self,
        action: str,
        agent_id: str,
        success: bool,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log agent lifecycle operations (create, update, delete, deprecate)."""
        lifecycle_context = {
            "action": action,
            "agent_id": agent_id,
            "success": success,
            "timestamp": datetime.now().isoformat(),
            **(context or {}),
        }

        status = "SUCCESS" if success else "FAILED"
        enhanced_message = f"LIFECYCLE: {action.upper()} {agent_id} {status} | Context: {json.dumps(lifecycle_context, default=str)}"

        if success:
            self.operations_logger.info(enhanced_message)
        else:
            self.operations_logger.error(enhanced_message)

    def log_access_control(
        self,
        operation: str,
        agent_path: str,
        allowed: bool,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log access control decisions."""
        access_context = {
            "operation": operation,
            "agent_path": agent_path,
            "allowed": allowed,
            "timestamp": datetime.now().isoformat(),
            **(context or {}),
        }

        decision = "ALLOWED" if allowed else "DENIED"
        enhanced_message = f"ACCESS_CONTROL: {operation} on {agent_path} {decision} | Context: {json.dumps(access_context, default=str)}"

        if allowed:
            self.security_logger.info(enhanced_message)
        else:
            self.security_logger.warning(enhanced_message)

    def log_cache_operation(
        self,
        operation: str,
        key: str,
        hit: Optional[bool] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log cache operations for performance monitoring."""
        cache_context = {
            "operation": operation,
            "key": key,
            "timestamp": datetime.now().isoformat(),
            **(context or {}),
        }

        if hit is not None:
            cache_context["hit"] = hit
            status = "HIT" if hit else "MISS"
            enhanced_message = f"CACHE: {operation} {key} {status} | Context: {json.dumps(cache_context, default=str)}"
        else:
            enhanced_message = f"CACHE: {operation} {key} | Context: {json.dumps(cache_context, default=str)}"

        # Use debug level for cache operations to reduce noise
        self.logger.debug(enhanced_message)

    def log_operation(
        self, operation: str, details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log a general operation (alias for log_agent_operation for compatibility)."""
        self.log_agent_operation(operation, details)

    def log_operation_result(
        self,
        operation: str,
        success: bool,
        execution_time_ms: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log operation result with performance metrics."""
        result_context = {
            "operation": operation,
            "success": success,
            "execution_time_ms": execution_time_ms,
            "timestamp": datetime.now().isoformat(),
            **(context or {}),
        }

        status = "SUCCESS" if success else "FAILED"
        enhanced_message = f"OPERATION: {operation} {status} ({execution_time_ms:.1f}ms) | Context: {json.dumps(result_context, default=str)}"

        if success:
            self.operations_logger.info(enhanced_message)
        else:
            self.operations_logger.error(enhanced_message)
