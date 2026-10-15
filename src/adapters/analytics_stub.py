"""
Analytics stub adapter - minimal implementation for agent ecosystem server.
"""

from typing import Dict, Any, List
from datetime import datetime
from core.models import AnalyticsData


class AnalyticsStubAdapter:
    """Stub implementation for analytics collection."""

    def collect_usage_metrics(self, scope: str = "both") -> AnalyticsData:
        """Return basic analytics data."""
        return AnalyticsData(
            total_agents=0,
            active_agents=0,
            categories={},
            usage_stats={},
            performance_metrics={},
            collection_time=datetime.now().isoformat(),
        )

    def track_agent_operation(
        self, operation_type: str, agent_path: str, success: bool
    ) -> None:
        """Stub - no-op tracking."""
        pass

    def generate_report(self, report_type: str = "summary") -> Dict[str, Any]:
        """Return empty report."""
        return {
            "report_type": report_type,
            "generated_at": datetime.now().isoformat(),
            "data": {},
        }

    def get_performance_trends(self, days: int = 7) -> Dict[str, Any]:
        """Return empty trends data."""
        return {
            "period_days": days,
            "trends": {},
            "generated_at": datetime.now().isoformat(),
        }
