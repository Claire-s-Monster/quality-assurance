"""
Quality Pipeline Orchestration Service for Quality Assurance MCP Server.

Orchestrates quality assessment pipelines using pixi task intelligence with:
- Environment validation and optimization
- Quality tool availability assessment
- Parallel/sequential task execution coordination
- Result aggregation and scoring
- Recommendation generation with pixi-aware insights
"""

import asyncio
import concurrent.futures
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass

from core.ports import LoggingPort
from adapters.direct_pixi_execution import (
    DirectPixiExecutionAdapter,
    QualityEnvironmentInfo,
)


@dataclass
class PipelineStage:
    """Individual pipeline stage configuration."""

    stage_name: str
    quality_tool: str
    task_name: str
    target_paths: List[str]
    quality_config: Dict[str, Any]
    dependencies: List[str]  # Other stages this depends on
    parallel_safe: bool
    timeout: int


@dataclass
class PipelineConfiguration:
    """Quality pipeline configuration."""

    pipeline_id: str
    stages: List[PipelineStage]
    execution_mode: str  # parallel, sequential, hybrid
    fail_fast: bool
    environment_optimization: bool
    aggregate_results: bool
    quality_threshold: float
    working_dir: str


@dataclass
class StageResult:
    """Result from executing a pipeline stage."""

    stage_name: str
    quality_tool: str
    success: bool
    execution_time: float
    result_data: Dict[str, Any]
    quality_intelligence: Dict[str, Any]
    error_message: Optional[str] = None


@dataclass
class PipelineResult:
    """Complete pipeline execution result."""

    pipeline_id: str
    configuration: PipelineConfiguration
    start_time: str
    end_time: str
    total_execution_time: float
    execution_mode_used: str
    stage_results: List[StageResult]
    aggregated_metrics: Dict[str, Any]
    environment_info: QualityEnvironmentInfo
    optimization_applied: Dict[str, Any]
    overall_success: bool
    quality_score: float
    meets_threshold: bool
    recommendations: List[str]
    failed_stages: List[str]


class QualityPipelineService:
    """
    Orchestrates quality assessment pipelines using pixi task intelligence.

    Provides comprehensive pipeline orchestration with:
    - Environment validation and optimization
    - Parallel and sequential execution coordination
    - Quality-aware task orchestration
    - Result aggregation and intelligent scoring
    - Pixi-specific performance optimizations
    """

    def __init__(
        self,
        pixi_adapter: DirectPixiExecutionAdapter,
        logging: LoggingPort,
        max_parallel_workers: int = 4,
    ):
        """
        Initialize the Quality Pipeline Service.

        Args:
            pixi_adapter: Enhanced DirectPixiExecutionAdapter with quality intelligence
            logging: Logging port for operation tracking
            max_parallel_workers: Maximum parallel worker threads
        """
        self.pixi_adapter = pixi_adapter
        self.logging = logging
        self.max_parallel_workers = max_parallel_workers
        self._active_pipelines: Dict[str, PipelineResult] = {}

    def execute_quality_pipeline(
        self, pipeline_config: PipelineConfiguration
    ) -> PipelineResult:
        """
        Execute comprehensive quality pipeline with pixi task orchestration.

        Pipeline stages:
        1. Environment validation and optimization
        2. Quality tool availability assessment
        3. Parallel/sequential task execution
        4. Result aggregation and scoring
        5. Recommendation generation

        Args:
            pipeline_config: Pipeline configuration with stages and execution mode

        Returns:
            PipelineResult with execution details, metrics, and recommendations
        """
        start_time = time.time()
        pipeline_start_time = datetime.now().isoformat()

        try:
            self.logging.log_info(
                f"Starting quality pipeline: {pipeline_config.pipeline_id}",
                {
                    "pipeline_id": pipeline_config.pipeline_id,
                    "stages": len(pipeline_config.stages),
                    "execution_mode": pipeline_config.execution_mode,
                    "fail_fast": pipeline_config.fail_fast,
                },
            )

            # Stage 1: Environment validation and optimization
            env_info, optimization_result = self._validate_and_optimize_environment(
                pipeline_config
            )

            # Stage 2: Quality tool availability assessment
            available_stages, unavailable_stages = self._assess_stage_availability(
                pipeline_config.stages, env_info
            )

            if not available_stages:
                return self._create_failed_result(
                    pipeline_config,
                    pipeline_start_time,
                    start_time,
                    "No quality tools available for pipeline execution",
                    env_info,
                    optimization_result,
                )

            # Stage 3: Execute pipeline stages
            stage_results = self._execute_pipeline_stages(
                available_stages, pipeline_config, env_info
            )

            # Stage 4: Result aggregation and scoring
            aggregated_metrics, quality_score = self._aggregate_stage_results(
                stage_results, pipeline_config
            )

            # Stage 5: Recommendation generation
            recommendations = self._generate_pipeline_recommendations(
                stage_results, env_info, aggregated_metrics, pipeline_config
            )

            # Build final result
            end_time = time.time()
            pipeline_end_time = datetime.now().isoformat()
            total_execution_time = end_time - start_time

            failed_stages = [r.stage_name for r in stage_results if not r.success]
            overall_success = len(failed_stages) == 0 or not pipeline_config.fail_fast
            meets_threshold = quality_score >= pipeline_config.quality_threshold

            result = PipelineResult(
                pipeline_id=pipeline_config.pipeline_id,
                configuration=pipeline_config,
                start_time=pipeline_start_time,
                end_time=pipeline_end_time,
                total_execution_time=total_execution_time,
                execution_mode_used=pipeline_config.execution_mode,
                stage_results=stage_results,
                aggregated_metrics=aggregated_metrics,
                environment_info=env_info,
                optimization_applied=optimization_result,
                overall_success=overall_success,
                quality_score=quality_score,
                meets_threshold=meets_threshold,
                recommendations=recommendations,
                failed_stages=failed_stages,
            )

            # Cache result for monitoring
            self._active_pipelines[pipeline_config.pipeline_id] = result

            self.logging.log_info(
                f"Quality pipeline completed: {pipeline_config.pipeline_id}",
                {
                    "execution_time": total_execution_time,
                    "overall_success": overall_success,
                    "quality_score": quality_score,
                    "stages_executed": len(stage_results),
                    "failed_stages": len(failed_stages),
                },
            )

            return result

        except Exception as e:
            end_time = time.time()
            error_msg = f"Pipeline execution failed: {str(e)}"

            self.logging.log_error(
                error_msg,
                {
                    "pipeline_id": pipeline_config.pipeline_id,
                    "execution_time": end_time - start_time,
                    "error": str(e),
                },
            )

            return self._create_failed_result(
                pipeline_config, pipeline_start_time, start_time, error_msg, None, {}
            )

    def optimize_quality_environment(
        self, required_tools: List[str], working_dir: str = None
    ) -> Dict[str, Any]:
        """
        Optimize pixi environment for quality tool execution.

        Optimizations:
        - Tool availability validation
        - Environment variable optimization
        - Cache management for quality tools
        - Performance tuning suggestions

        Args:
            required_tools: List of quality tools that need optimization
            working_dir: Working directory for optimization

        Returns:
            Optimization results with applied changes and recommendations
        """
        try:
            self.logging.log_info(f"Optimizing environment for tools: {required_tools}")

            # Use the enhanced pixi adapter's optimization capabilities
            optimization_result = self.pixi_adapter.optimize_quality_environment(
                required_tools=required_tools, working_dir=working_dir
            )

            # Add pipeline-specific optimizations
            pipeline_optimizations = self._apply_pipeline_optimizations(
                required_tools, optimization_result
            )

            optimization_result.update(pipeline_optimizations)

            self.logging.log_info(
                "Environment optimization completed",
                {
                    "optimized_tools": len(required_tools),
                    "optimizations_applied": len(
                        optimization_result.get("optimizations_applied", [])
                    ),
                },
            )

            return optimization_result

        except Exception as e:
            self.logging.log_error(f"Environment optimization failed: {str(e)}")
            return {
                "optimizations_applied": [],
                "error": str(e),
                "recommendations": ["Check pixi environment configuration"],
            }

    def get_pipeline_status(self, pipeline_id: str) -> Dict[str, Any] | None:
        """Get status of a specific pipeline execution."""
        result = self._active_pipelines.get(pipeline_id)
        if not result:
            return None

        return {
            "pipeline_id": result.pipeline_id,
            "overall_success": result.overall_success,
            "quality_score": result.quality_score,
            "meets_threshold": result.meets_threshold,
            "execution_time": result.total_execution_time,
            "stages_executed": len(result.stage_results),
            "failed_stages": len(result.failed_stages),
            "environment_health": result.environment_info.environment_health,
            "recommendations_count": len(result.recommendations),
        }

    # =========================================================================
    # PRIVATE PIPELINE ORCHESTRATION METHODS
    # =========================================================================

    def _validate_and_optimize_environment(
        self, pipeline_config: PipelineConfiguration
    ) -> Tuple[QualityEnvironmentInfo, Dict[str, Any]]:
        """Validate and optimize environment for pipeline execution."""
        # Detect quality environment
        env_info = self.pixi_adapter.detect_quality_environment(
            working_dir=pipeline_config.working_dir
        )

        # Extract required tools from pipeline stages
        required_tools = list(
            set(stage.quality_tool for stage in pipeline_config.stages)
        )

        # Apply optimization if requested
        optimization_result = {}
        if pipeline_config.environment_optimization:
            optimization_result = self.pixi_adapter.optimize_quality_environment(
                required_tools=required_tools, working_dir=pipeline_config.working_dir
            )

        return env_info, optimization_result

    def _assess_stage_availability(
        self, stages: List[PipelineStage], env_info: QualityEnvironmentInfo
    ) -> Tuple[List[PipelineStage], List[PipelineStage]]:
        """Assess which stages can be executed based on tool availability."""
        available_stages = []
        unavailable_stages = []

        for stage in stages:
            if stage.quality_tool in env_info.available_tools:
                available_stages.append(stage)
            else:
                unavailable_stages.append(stage)
                self.logging.log_warning(
                    f"Stage '{stage.stage_name}' skipped - tool '{stage.quality_tool}' not available"
                )

        return available_stages, unavailable_stages

    def _execute_pipeline_stages(
        self,
        stages: List[PipelineStage],
        pipeline_config: PipelineConfiguration,
        env_info: QualityEnvironmentInfo,
    ) -> List[StageResult]:
        """Execute pipeline stages according to configuration."""
        if pipeline_config.execution_mode == "parallel":
            return self._execute_stages_parallel(stages, pipeline_config, env_info)
        elif pipeline_config.execution_mode == "sequential":
            return self._execute_stages_sequential(stages, pipeline_config, env_info)
        elif pipeline_config.execution_mode == "hybrid":
            return self._execute_stages_hybrid(stages, pipeline_config, env_info)
        else:
            # Default to sequential
            return self._execute_stages_sequential(stages, pipeline_config, env_info)

    def _execute_stages_parallel(
        self,
        stages: List[PipelineStage],
        pipeline_config: PipelineConfiguration,
        env_info: QualityEnvironmentInfo,
    ) -> List[StageResult]:
        """Execute all compatible stages in parallel."""
        stage_results = []

        # Filter parallel-safe stages
        parallel_stages = [stage for stage in stages if stage.parallel_safe]
        sequential_stages = [stage for stage in stages if not stage.parallel_safe]

        # Execute parallel stages
        if parallel_stages:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_parallel_workers
            ) as executor:
                # Submit all parallel stages
                future_to_stage = {
                    executor.submit(
                        self._execute_single_stage, stage, pipeline_config, env_info
                    ): stage
                    for stage in parallel_stages
                }

                # Collect results as they complete
                for future in concurrent.futures.as_completed(future_to_stage):
                    stage = future_to_stage[future]
                    try:
                        result = future.result()
                        stage_results.append(result)

                        # Check fail-fast condition
                        if pipeline_config.fail_fast and not result.success:
                            self.logging.log_warning(
                                f"Pipeline fail-fast triggered by stage: {stage.stage_name}"
                            )
                            # Cancel remaining futures
                            for remaining_future in future_to_stage:
                                remaining_future.cancel()
                            break

                    except Exception as e:
                        error_result = self._create_error_stage_result(stage, str(e))
                        stage_results.append(error_result)

        # Execute sequential stages after parallel ones complete
        if sequential_stages and not (
            pipeline_config.fail_fast and any(not r.success for r in stage_results)
        ):
            sequential_results = self._execute_stages_sequential(
                sequential_stages, pipeline_config, env_info
            )
            stage_results.extend(sequential_results)

        return stage_results

    def _execute_stages_sequential(
        self,
        stages: List[PipelineStage],
        pipeline_config: PipelineConfiguration,
        env_info: QualityEnvironmentInfo,
    ) -> List[StageResult]:
        """Execute stages one by one in sequence."""
        stage_results = []

        for stage in stages:
            try:
                result = self._execute_single_stage(stage, pipeline_config, env_info)
                stage_results.append(result)

                # Check fail-fast condition
                if pipeline_config.fail_fast and not result.success:
                    self.logging.log_warning(
                        f"Pipeline fail-fast triggered by stage: {stage.stage_name}"
                    )
                    break

            except Exception as e:
                error_result = self._create_error_stage_result(stage, str(e))
                stage_results.append(error_result)

                if pipeline_config.fail_fast:
                    break

        return stage_results

    def _execute_stages_hybrid(
        self,
        stages: List[PipelineStage],
        pipeline_config: PipelineConfiguration,
        env_info: QualityEnvironmentInfo,
    ) -> List[StageResult]:
        """Execute stages using hybrid approach - respecting dependencies."""
        stage_results = []
        completed_stages = set()
        remaining_stages = stages.copy()

        while remaining_stages:
            # Find stages that can be executed (dependencies satisfied)
            ready_stages = []
            for stage in remaining_stages:
                if all(dep in completed_stages for dep in stage.dependencies):
                    ready_stages.append(stage)

            if not ready_stages:
                # No stages ready - might be circular dependency or missing stage
                self.logging.log_error(
                    "No stages ready for execution - possible dependency issue"
                )
                break

            # Separate parallel-safe from sequential stages
            parallel_ready = [s for s in ready_stages if s.parallel_safe]
            sequential_ready = [s for s in ready_stages if not s.parallel_safe]

            # Execute parallel stages first
            if parallel_ready:
                parallel_results = self._execute_stages_parallel(
                    parallel_ready, pipeline_config, env_info
                )
                stage_results.extend(parallel_results)

                # Update completed stages
                for result in parallel_results:
                    completed_stages.add(result.stage_name)
                    remaining_stages = [
                        s for s in remaining_stages if s.stage_name != result.stage_name
                    ]

                # Check fail-fast
                if pipeline_config.fail_fast and any(
                    not r.success for r in parallel_results
                ):
                    break

            # Execute sequential stages
            for stage in sequential_ready:
                try:
                    result = self._execute_single_stage(
                        stage, pipeline_config, env_info
                    )
                    stage_results.append(result)
                    completed_stages.add(result.stage_name)
                    remaining_stages = [
                        s for s in remaining_stages if s.stage_name != result.stage_name
                    ]

                    # Check fail-fast
                    if pipeline_config.fail_fast and not result.success:
                        remaining_stages = []  # Stop all execution
                        break

                except Exception as e:
                    error_result = self._create_error_stage_result(stage, str(e))
                    stage_results.append(error_result)
                    completed_stages.add(stage.stage_name)
                    remaining_stages = [
                        s for s in remaining_stages if s.stage_name != result.stage_name
                    ]

                    if pipeline_config.fail_fast:
                        remaining_stages = []
                        break

        return stage_results

    def _execute_single_stage(
        self,
        stage: PipelineStage,
        pipeline_config: PipelineConfiguration,
        env_info: QualityEnvironmentInfo,
    ) -> StageResult:
        """Execute a single pipeline stage."""
        start_time = time.time()

        try:
            self.logging.log_info(
                f"Executing stage: {stage.stage_name} with {stage.quality_tool}"
            )

            # Use enhanced pixi adapter for quality-aware execution
            result = self.pixi_adapter.run_quality_task(
                task_name=stage.task_name,
                quality_tool=stage.quality_tool,
                target_paths=stage.target_paths,
                quality_config=stage.quality_config,
                environment_optimization=pipeline_config.environment_optimization,
                timeout=stage.timeout,
                working_dir=pipeline_config.working_dir,
            )

            execution_time = time.time() - start_time

            return StageResult(
                stage_name=stage.stage_name,
                quality_tool=stage.quality_tool,
                success=result["success"],
                execution_time=execution_time,
                result_data=result,
                quality_intelligence=result.get("quality_intelligence", {}),
                error_message=result.get("stderr") if not result["success"] else None,
            )

        except Exception as e:
            execution_time = time.time() - start_time
            return StageResult(
                stage_name=stage.stage_name,
                quality_tool=stage.quality_tool,
                success=False,
                execution_time=execution_time,
                result_data={},
                quality_intelligence={},
                error_message=str(e),
            )

    def _aggregate_stage_results(
        self, stage_results: List[StageResult], pipeline_config: PipelineConfiguration
    ) -> Tuple[Dict[str, Any], float]:
        """Aggregate results from all stages and calculate quality score."""
        if not stage_results:
            return {}, 0.0

        # Basic aggregation metrics
        total_stages = len(stage_results)
        successful_stages = len([r for r in stage_results if r.success])
        failed_stages = total_stages - successful_stages
        total_execution_time = sum(r.execution_time for r in stage_results)
        average_execution_time = total_execution_time / total_stages

        # Tool-specific aggregations
        tools_used = list(set(r.quality_tool for r in stage_results))
        tool_success_rates = {}

        for tool in tools_used:
            tool_results = [r for r in stage_results if r.quality_tool == tool]
            tool_success_rates[tool] = len(
                [r for r in tool_results if r.success]
            ) / len(tool_results)

        # Quality intelligence aggregation
        environment_scores = []
        for result in stage_results:
            qi = result.quality_intelligence
            if qi and "performance_indicators" in qi:
                env_score = qi["performance_indicators"].get("environment_score", 5.0)
                environment_scores.append(env_score)

        avg_environment_score = (
            sum(environment_scores) / len(environment_scores)
            if environment_scores
            else 5.0
        )

        # Calculate overall quality score (0-10 scale)
        success_factor = successful_stages / total_stages
        environment_factor = avg_environment_score / 10.0
        tool_diversity_factor = min(
            1.0, len(tools_used) / 4.0
        )  # Bonus for using multiple tools

        quality_score = (
            (success_factor * 6.0)
            + (environment_factor * 2.0)
            + (tool_diversity_factor * 2.0)
        )
        quality_score = min(10.0, max(0.0, quality_score))  # Clamp to 0-10

        aggregated_metrics = {
            "total_stages": total_stages,
            "successful_stages": successful_stages,
            "failed_stages": failed_stages,
            "success_rate": success_factor,
            "total_execution_time": total_execution_time,
            "average_execution_time": average_execution_time,
            "tools_used": tools_used,
            "tool_success_rates": tool_success_rates,
            "environment_score": avg_environment_score,
            "quality_score": quality_score,
        }

        return aggregated_metrics, quality_score

    def _generate_pipeline_recommendations(
        self,
        stage_results: List[StageResult],
        env_info: QualityEnvironmentInfo,
        aggregated_metrics: Dict[str, Any],
        pipeline_config: PipelineConfiguration,
    ) -> List[str]:
        """Generate pipeline-specific recommendations."""
        recommendations = []

        # Failed stage recommendations
        failed_results = [r for r in stage_results if not r.success]
        if failed_results:
            recommendations.append(
                f"Address {len(failed_results)} failed pipeline stages"
            )
            for result in failed_results:
                if result.error_message:
                    recommendations.append(
                        f"Fix {result.stage_name}: {result.error_message}"
                    )

        # Environment health recommendations
        if env_info.environment_health == "degraded":
            recommendations.extend(env_info.recommendations[:2])

        # Performance recommendations
        avg_time = aggregated_metrics.get("average_execution_time", 0)
        if avg_time > 60:  # More than 1 minute per stage
            recommendations.append("Consider optimizing slow-running quality tools")

        # Tool diversity recommendations
        tools_used = aggregated_metrics.get("tools_used", [])
        if len(tools_used) < 3:
            missing_core_tools = set(["ruff", "mypy", "bandit"]) - set(tools_used)
            if missing_core_tools:
                recommendations.append(
                    f"Add missing core tools: {', '.join(missing_core_tools)}"
                )

        # Success rate recommendations
        success_rate = aggregated_metrics.get("success_rate", 0)
        if success_rate < 0.8:
            recommendations.append(
                "Pipeline success rate below 80% - review tool configurations"
            )

        # Execution mode recommendations
        if pipeline_config.execution_mode == "sequential" and len(stage_results) > 3:
            parallel_safe_count = sum(
                1 for r in stage_results if r.success
            )  # Simplified check
            if parallel_safe_count > 2:
                recommendations.append(
                    "Consider parallel execution mode for better performance"
                )

        return recommendations

    def _apply_pipeline_optimizations(
        self, required_tools: List[str], base_optimization: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply pipeline-specific optimizations on top of base optimizations."""
        pipeline_optimizations = {
            "pipeline_level_optimizations": [],
            "execution_coordination": {},
            "resource_allocation": {},
        }

        # Add pipeline-level caching strategies
        if "ruff" in required_tools and "mypy" in required_tools:
            pipeline_optimizations["pipeline_level_optimizations"].append(
                "Coordinated caching for ruff and mypy"
            )

        # Resource allocation based on tool count
        if len(required_tools) > 3:
            pipeline_optimizations["resource_allocation"] = {
                "parallel_execution_recommended": True,
                "max_concurrent_tools": min(
                    len(required_tools), self.max_parallel_workers
                ),
            }

        # Execution coordination
        pipeline_optimizations["execution_coordination"] = {
            "dependency_aware": True,
            "fail_fast_optimization": True,
            "result_streaming": True,
        }

        return pipeline_optimizations

    def _create_failed_result(
        self,
        pipeline_config: PipelineConfiguration,
        start_time: str,
        start_timestamp: float,
        error_message: str,
        env_info: Optional[QualityEnvironmentInfo],
        optimization_result: Dict[str, Any],
    ) -> PipelineResult:
        """Create a failed pipeline result."""
        end_time = time.time()

        return PipelineResult(
            pipeline_id=pipeline_config.pipeline_id,
            configuration=pipeline_config,
            start_time=start_time,
            end_time=datetime.now().isoformat(),
            total_execution_time=end_time - start_timestamp,
            execution_mode_used=pipeline_config.execution_mode,
            stage_results=[],
            aggregated_metrics={},
            environment_info=env_info
            or QualityEnvironmentInfo(
                available_tools=set(),
                quality_tasks={},
                environment_health="degraded",
                recommendations=[error_message],
                tool_versions={},
                missing_tools=set(),
                performance_indicators={},
            ),
            optimization_applied=optimization_result,
            overall_success=False,
            quality_score=0.0,
            meets_threshold=False,
            recommendations=[
                error_message,
                "Check pipeline configuration and environment",
            ],
            failed_stages=[],
        )

    def _create_error_stage_result(
        self, stage: PipelineStage, error_message: str
    ) -> StageResult:
        """Create an error result for a failed stage."""
        return StageResult(
            stage_name=stage.stage_name,
            quality_tool=stage.quality_tool,
            success=False,
            execution_time=0.0,
            result_data={},
            quality_intelligence={},
            error_message=error_message,
        )
