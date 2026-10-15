"""
Dependency injection container for Quality Assurance MCP Server.

This module provides centralized dependency management using the same patterns
as the agent-cache server, ensuring consistent architecture for quality tools.
"""

import os
from pathlib import Path
from typing import Dict, Any

from adapters.environment import EnvironmentAdapter
from adapters.execution import PixiExecutionAdapter
from adapters.logging import LoggingAdapter
from adapters.project import PixiProjectAdapter
from adapters.simple_validation import SimpleValidationAdapter
from adapters.quality_tool_execution import QualityToolExecutionAdapter
from adapters.quality_analysis import QualityAnalysisAdapter
from adapters.quality_trend_analysis import QualityTrendAnalysisAdapter
from adapters.quality_data_storage import QualityDataStorageAdapter
from adapters.git_integration import GitIntegrationAdapter
from adapters.automated_fix import AutomatedFixAdapter
from adapters.direct_pixi_execution import DirectPixiExecutionAdapter
from core.quality_service import QualityAssuranceService
from core.quality_orchestration_service import QualityOrchestrationService


class Container:
    """
    Dependency injection container for the Quality Assurance server.

    Manages all dependencies and provides a clean interface for
    service instantiation with proper configuration.
    """

    def __init__(self, working_dir: str | None = None):
        """Initialize container with optional working directory override."""
        self._working_dir = working_dir or os.getcwd()
        self._services = {}
        self._adapters = {}
        self._initialize_adapters()
        self._initialize_services()

    def _initialize_adapters(self) -> None:
        """Initialize all adapter instances."""
        # Environment adapter
        self._adapters["environment"] = EnvironmentAdapter(
            working_dir=self._working_dir
        )

        # Logging adapter
        self._adapters["logging"] = LoggingAdapter()

        # Simple validation adapter
        self._adapters["validation"] = SimpleValidationAdapter()

        # Pixi project adapter
        self._adapters["project"] = PixiProjectAdapter(
            environment=self._adapters["environment"], logging=self._adapters["logging"]
        )

        # Pixi execution adapter
        self._adapters["execution"] = PixiExecutionAdapter(
            environment=self._adapters["environment"],
            logging=self._adapters["logging"],
            validation=self._adapters["validation"],
        )

        # Direct pixi execution adapter
        self._adapters["direct_pixi"] = DirectPixiExecutionAdapter(
            logging=self._adapters["logging"], working_dir=self._working_dir
        )

        # Quality tool execution adapter
        self._adapters["quality_executor"] = QualityToolExecutionAdapter(
            direct_pixi_executor=self._adapters["direct_pixi"]
        )

        # Quality analysis adapter
        self._adapters["quality_analyzer"] = QualityAnalysisAdapter()

        # Quality data storage adapter. The trend analyzer shares this root so
        # baselines written through either adapter are visible to both
        # (<root>/baselines/<id>.json).
        quality_data_root = str(Path(self._working_dir) / ".claude" / "quality-data")
        self._adapters["data_storage"] = QualityDataStorageAdapter(
            storage_root=quality_data_root
        )

        # Git integration adapter
        self._adapters["git_integration"] = GitIntegrationAdapter(
            working_dir=self._working_dir, logging=self._adapters["logging"]
        )

        # Quality trend analysis adapter (shares the data storage root)
        self._adapters["trend_analyzer"] = QualityTrendAnalysisAdapter(
            storage_path=quality_data_root
        )

        # Automated fix adapter
        self._adapters["automated_fix"] = AutomatedFixAdapter(
            direct_pixi_executor=self._adapters["direct_pixi"],
            working_dir=self._working_dir,
        )

    def _initialize_services(self) -> None:
        """Initialize all service instances."""
        # Core quality assurance service
        self._services["quality"] = QualityAssuranceService(
            quality_executor=self._adapters["quality_executor"],
            logging=self._adapters["logging"],
        )

        # Quality orchestration service (main business logic service)
        self._services["orchestration"] = QualityOrchestrationService(
            quality_executor=self._adapters["quality_executor"],
            quality_analyzer=self._adapters["quality_analyzer"],
            trend_analyzer=self._adapters["trend_analyzer"],
            data_storage=self._adapters["data_storage"],
            git_integration=self._adapters["git_integration"],
            automated_fix=self._adapters["automated_fix"],
            logging=self._adapters["logging"],
        )

    @property
    def quality_service(self) -> QualityAssuranceService:
        """Get the main quality assurance service."""
        return self._services["quality"]

    @property
    def orchestration_service(self) -> QualityOrchestrationService:
        """Get the quality orchestration service."""
        return self._services["orchestration"]

    @property
    def environment(self) -> EnvironmentAdapter:
        """Get the environment adapter."""
        return self._adapters["environment"]

    @property
    def logging(self) -> LoggingAdapter:
        """Get the logging adapter."""
        return self._adapters["logging"]

    @property
    def quality_executor(self) -> QualityToolExecutionAdapter:
        """Get the quality tool execution adapter."""
        return self._adapters["quality_executor"]

    @property
    def pixi_executor(self) -> DirectPixiExecutionAdapter:
        """Get the direct pixi execution adapter.

        Returns the DirectPixiExecutionAdapter for raw pixi command
        execution, NOT the QualityToolExecutionAdapter returned by
        ``quality_executor``.
        """
        return self._adapters["direct_pixi"]

    @property
    def quality_analyzer(self) -> QualityAnalysisAdapter:
        """Get the quality analysis adapter."""
        return self._adapters["quality_analyzer"]

    @property
    def trend_analyzer(self) -> QualityTrendAnalysisAdapter:
        """Get the quality trend analysis adapter."""
        return self._adapters["trend_analyzer"]

    @property
    def data_storage(self) -> QualityDataStorageAdapter:
        """Get the quality data storage adapter."""
        return self._adapters["data_storage"]

    @property
    def git_integration(self) -> GitIntegrationAdapter:
        """Get the git integration adapter."""
        return self._adapters["git_integration"]

    @property
    def automated_fix(self) -> AutomatedFixAdapter:
        """Get the automated fix adapter."""
        return self._adapters["automated_fix"]

    def get_working_directory(self) -> str:
        """Get the configured working directory."""
        return self._working_dir

    def cleanup(self) -> None:
        """Clean up resources when shutting down."""
        try:
            # Clean up any resources that need explicit cleanup
            for adapter in self._adapters.values():
                if hasattr(adapter, "cleanup"):
                    adapter.cleanup()

            self._adapters["logging"].log_info("Container cleanup completed")
        except Exception as e:
            print(f"Error during container cleanup: {e}")  # Fallback logging
