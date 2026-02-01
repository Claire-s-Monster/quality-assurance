"""
Core business logic for Pixi Shell MCP Server.

This module implements the secure pixi task execution service,
providing thread-safe operations with comprehensive validation.
"""

import os
import time
from pathlib import Path
from typing import Any

from core.models import (
    PixiExecutionContext,
    PixiHealthCheck,
    PixiOperationResult,
    PixiProjectInfo,
    PixiTaskDefinition,
    PixiTaskResult,
    PixiEnvironmentInfo,
    PixiDependency,
)
from core.ports import (
    PixiExecutorPort,
    PixiProjectPort,
    LoggingPort,
    ValidationPort,
)


class PixiShellService:
    """
    Core service for secure pixi task execution.
    
    Provides thread-safe operations with comprehensive validation,
    environment management, and task execution.
    """

    def __init__(
        self,
        pixi_executor: PixiExecutorPort,
        pixi_project: PixiProjectPort,
        logging: LoggingPort,
        validation: ValidationPort,
    ):
        self.pixi_executor = pixi_executor
        self.pixi_project = pixi_project
        self.logging = logging
        self.validation = validation

    def run_task(
        self,
        task_name: str,
        args: list[str] | None = None,
        working_dir: str | None = None,
        timeout: int = 300
    ) -> dict[str, Any]:
        """
        Execute a pixi task with arguments.
        
        Returns: {"success": bool, "stdout": str, "stderr": str, "exit_code": int, "execution_time": float}
        """
        start_time = time.time()
        working_dir = working_dir or os.getcwd()
        
        try:
            # Validate pixi project
            if not self.pixi_project.is_pixi_project(working_dir):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Directory {working_dir} is not a pixi project (no pixi.toml found)",
                    "exit_code": 1,
                    "execution_time": time.time() - start_time,
                    "task_name": task_name,
                    "working_dir": working_dir
                }
            
            # Check if task exists
            available_tasks = self.pixi_project.get_available_tasks(working_dir)
            if task_name not in available_tasks:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Task '{task_name}' not found. Available tasks: {', '.join(available_tasks.keys())}",
                    "exit_code": 1,
                    "execution_time": time.time() - start_time,
                    "task_name": task_name,
                    "working_dir": working_dir
                }
            
            # Create execution context
            context = PixiExecutionContext(
                working_dir=working_dir,
                timeout=timeout,
                capture_output=True
            )
            
            # Execute task
            result = self.pixi_executor.run_task(task_name, args or [], context)
            
            self.logging.log_info(f"Pixi task executed: {task_name}", {
                "success": result.success,
                "exit_code": result.exit_code,
                "execution_time": result.execution_time,
                "working_dir": working_dir
            })
            
            return {
                "success": result.success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "execution_time": result.execution_time,
                "task_name": result.task_name,
                "working_dir": result.working_dir,
                "command_line": result.command_line
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Task execution failed: {str(e)}"
            
            self.logging.log_error(error_msg, {
                "task_name": task_name,
                "args": args,
                "working_dir": working_dir,
                "error": str(e)
            })
            
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg,
                "exit_code": 1,
                "execution_time": execution_time,
                "task_name": task_name,
                "working_dir": working_dir
            }

    def list_tasks(self, working_dir: str | None = None) -> dict[str, Any]:
        """
        List all available pixi tasks with descriptions.
        
        Returns: {"tasks": {"test": "Run pytest", "lint": "Run ruff", ...}}
        """
        working_dir = working_dir or os.getcwd()
        
        try:
            if not self.pixi_project.is_pixi_project(working_dir):
                return {
                    "tasks": {},
                    "error": f"Directory {working_dir} is not a pixi project"
                }
            
            available_tasks = self.pixi_project.get_available_tasks(working_dir)
            
            self.logging.log_info(f"Listed pixi tasks", {
                "task_count": len(available_tasks),
                "working_dir": working_dir
            })
            
            return {"tasks": available_tasks}
            
        except Exception as e:
            error_msg = f"Failed to list tasks: {str(e)}"
            self.logging.log_error(error_msg, {
                "working_dir": working_dir,
                "error": str(e)
            })
            
            return {
                "tasks": {},
                "error": error_msg
            }

    def task_exists(self, task_name: str, working_dir: str | None = None) -> bool:
        """
        Check if a pixi task exists.
        
        Returns: True if task exists, False otherwise
        """
        working_dir = working_dir or os.getcwd()
        
        try:
            if not self.pixi_project.is_pixi_project(working_dir):
                return False
            
            available_tasks = self.pixi_project.get_available_tasks(working_dir)
            return task_name in available_tasks
            
        except Exception as e:
            self.logging.log_error(f"Error checking task existence: {str(e)}", {
                "task_name": task_name,
                "working_dir": working_dir
            })
            return False

    def install(self, working_dir: str | None = None) -> dict[str, Any]:
        """
        Install/sync pixi environment and dependencies.
        
        Returns: {"success": bool, "stdout": str, "stderr": str, "execution_time": float}
        """
        start_time = time.time()
        working_dir = working_dir or os.getcwd()
        
        try:
            if not self.pixi_project.is_pixi_project(working_dir):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Directory {working_dir} is not a pixi project",
                    "execution_time": time.time() - start_time
                }
            
            context = PixiExecutionContext(
                working_dir=working_dir,
                timeout=600,  # Longer timeout for installations
                capture_output=True
            )
            
            result = self.pixi_executor.install(context)
            
            self.logging.log_info("Pixi install completed", {
                "success": result.success,
                "execution_time": result.execution_time,
                "working_dir": working_dir
            })
            
            return {
                "success": result.success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "execution_time": result.execution_time
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Pixi install failed: {str(e)}"
            
            self.logging.log_error(error_msg, {
                "working_dir": working_dir,
                "error": str(e)
            })
            
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg,
                "execution_time": execution_time
            }

    def get_info(self, working_dir: str | None = None) -> dict[str, Any]:
        """
        Get pixi project information and environment status.
        
        Returns: Project information including dependencies, tasks, environment status
        """
        working_dir = working_dir or os.getcwd()
        
        try:
            if not self.pixi_project.is_pixi_project(working_dir):
                return {
                    "is_pixi_project": False,
                    "error": f"Directory {working_dir} is not a pixi project"
                }
            
            project_info = self.pixi_project.get_project_info(working_dir)
            
            return {
                "is_pixi_project": True,
                "project_name": project_info.project_name,
                "project_path": project_info.project_path,
                "python_version": project_info.python_version,
                "environment_path": project_info.environment_path,
                "has_lock_file": project_info.has_lock_file,
                "dependencies": project_info.dependencies,
                "dev_dependencies": project_info.dev_dependencies,
                "available_tasks": project_info.available_tasks,
                "channels": project_info.channels,
                "platforms": project_info.platforms,
                "environment_status": project_info.environment_status,
                "last_updated": project_info.last_updated
            }
            
        except Exception as e:
            error_msg = f"Failed to get project info: {str(e)}"
            self.logging.log_error(error_msg, {
                "working_dir": working_dir,
                "error": str(e)
            })
            
            return {
                "is_pixi_project": False,
                "error": error_msg
            }

    def execute_command(
        self,
        command: list[str],
        working_dir: str | None = None,
        capture_output: bool = True,
        timeout: int = 300
    ) -> dict[str, Any]:
        """
        Execute arbitrary command in pixi environment.
        
        Returns: Command execution result
        """
        start_time = time.time()
        working_dir = working_dir or os.getcwd()
        
        try:
            if not self.pixi_project.is_pixi_project(working_dir):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Directory {working_dir} is not a pixi project",
                    "exit_code": 1,
                    "execution_time": time.time() - start_time
                }
            
            context = PixiExecutionContext(
                working_dir=working_dir,
                timeout=timeout,
                capture_output=capture_output
            )
            
            result = self.pixi_executor.execute_command(command, context)
            
            self.logging.log_info("Pixi command executed", {
                "command": " ".join(command),
                "success": result.success,
                "execution_time": result.execution_time,
                "working_dir": working_dir
            })
            
            return {
                "success": result.success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "execution_time": result.execution_time,
                "command": " ".join(command)
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Command execution failed: {str(e)}"
            
            self.logging.log_error(error_msg, {
                "command": command,
                "working_dir": working_dir,
                "error": str(e)
            })
            
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg,
                "exit_code": 1,
                "execution_time": execution_time,
                "command": " ".join(command)
            }

    def add_dependency(
        self,
        package: str,
        channel: str | None = None,
        is_dev: bool = False,
        working_dir: str | None = None
    ) -> dict[str, Any]:
        """
        Add a dependency to pixi project.
        
        Returns: Operation result
        """
        working_dir = working_dir or os.getcwd()
        
        try:
            if not self.pixi_project.is_pixi_project(working_dir):
                return {
                    "success": False,
                    "message": f"Directory {working_dir} is not a pixi project"
                }
            
            result = self.pixi_project.add_dependency(package, channel, is_dev, working_dir)
            
            self.logging.log_info("Dependency added", {
                "package": package,
                "channel": channel,
                "is_dev": is_dev,
                "success": result.success,
                "working_dir": working_dir
            })
            
            return {
                "success": result.success,
                "message": result.message,
                "data": result.data
            }
            
        except Exception as e:
            error_msg = f"Failed to add dependency: {str(e)}"
            self.logging.log_error(error_msg, {
                "package": package,
                "working_dir": working_dir,
                "error": str(e)
            })
            
            return {
                "success": False,
                "message": error_msg
            }

    def remove_dependency(
        self,
        package: str,
        is_dev: bool = False,
        working_dir: str | None = None
    ) -> dict[str, Any]:
        """
        Remove a dependency from pixi project.
        
        Returns: Operation result
        """
        working_dir = working_dir or os.getcwd()
        
        try:
            if not self.pixi_project.is_pixi_project(working_dir):
                return {
                    "success": False,
                    "message": f"Directory {working_dir} is not a pixi project"
                }
            
            result = self.pixi_project.remove_dependency(package, is_dev, working_dir)
            
            self.logging.log_info("Dependency removed", {
                "package": package,
                "is_dev": is_dev,
                "success": result.success,
                "working_dir": working_dir
            })
            
            return {
                "success": result.success,
                "message": result.message,
                "data": result.data
            }
            
        except Exception as e:
            error_msg = f"Failed to remove dependency: {str(e)}"
            self.logging.log_error(error_msg, {
                "package": package,
                "working_dir": working_dir,
                "error": str(e)
            })
            
            return {
                "success": False,
                "message": error_msg
            }

    def list_dependencies(self, working_dir: str | None = None) -> dict[str, Any]:
        """
        List all project dependencies with versions.
        
        Returns: Dependencies information
        """
        working_dir = working_dir or os.getcwd()
        
        try:
            if not self.pixi_project.is_pixi_project(working_dir):
                return {
                    "dependencies": {},
                    "dev_dependencies": {},
                    "error": f"Directory {working_dir} is not a pixi project"
                }
            
            project_info = self.pixi_project.get_project_info(working_dir)
            
            return {
                "dependencies": project_info.dependencies,
                "dev_dependencies": project_info.dev_dependencies,
                "channels": project_info.channels,
                "platforms": project_info.platforms
            }
            
        except Exception as e:
            error_msg = f"Failed to list dependencies: {str(e)}"
            self.logging.log_error(error_msg, {
                "working_dir": working_dir,
                "error": str(e)
            })
            
            return {
                "dependencies": {},
                "dev_dependencies": {},
                "error": error_msg
            }

    def get_project_status(self, working_dir: str | None = None) -> dict[str, Any]:
        """
        Get comprehensive project status.
        
        Returns: Project health and status information
        """
        working_dir = working_dir or os.getcwd()
        
        try:
            health_check = self.pixi_project.check_health(working_dir)
            
            return {
                "is_pixi_project": health_check.is_pixi_project,
                "pixi_executable_found": health_check.pixi_executable_found,
                "environment_exists": health_check.environment_exists,
                "environment_synced": health_check.environment_synced,
                "lock_file_exists": health_check.lock_file_exists,
                "is_healthy": health_check.is_healthy(),
                "issues": health_check.issues,
                "recommendations": health_check.recommendations,
                "checked_at": health_check.checked_at
            }
            
        except Exception as e:
            error_msg = f"Failed to get project status: {str(e)}"
            self.logging.log_error(error_msg, {
                "working_dir": working_dir,
                "error": str(e)
            })
            
            return {
                "is_pixi_project": False,
                "is_healthy": False,
                "issues": [error_msg],
                "recommendations": ["Check if pixi is installed and directory contains pixi.toml"],
                "error": error_msg
            }

    def init_project(
        self,
        path: str,
        template: str | None = None
    ) -> dict[str, Any]:
        """
        Initialize a new pixi project.
        
        Returns: Initialization result
        """
        try:
            result = self.pixi_project.init_project(path, template)
            
            self.logging.log_info("Pixi project initialized", {
                "path": path,
                "template": template,
                "success": result.success
            })
            
            return {
                "success": result.success,
                "message": result.message,
                "project_path": path
            }
            
        except Exception as e:
            error_msg = f"Failed to initialize project: {str(e)}"
            self.logging.log_error(error_msg, {
                "path": path,
                "template": template,
                "error": str(e)
            })
            
            return {
                "success": False,
                "message": error_msg,
                "project_path": path
            }