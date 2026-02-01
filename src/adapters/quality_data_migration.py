"""
Quality data migration utilities for Quality Assurance MCP Server.

This module provides tools for migrating baseline data between formats,
versions, and storage systems with comprehensive validation and rollback
capabilities.
"""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.models import OperationResult


class QualityDataMigrationAdapter:
    """
    Data migration adapter for quality baselines and assessments.
    
    Provides comprehensive migration capabilities:
    - Version migration between data format versions
    - Storage location migration (directory restructuring)
    - Data format migration (JSON to other formats)
    - Bulk operations with rollback support
    - Data integrity validation and repair
    """

    def __init__(self, source_root: Optional[str] = None, target_root: Optional[str] = None):
        """
        Initialize migration adapter with source and target paths.
        
        Args:
            source_root: Source data directory path
            target_root: Target data directory path
        """
        self.source_root = Path(source_root) if source_root else Path('./.claude/quality-baselines')
        self.target_root = Path(target_root) if target_root else Path('./.claude/quality-data')
        
        # Migration metadata
        self.migration_log = []
        self.rollback_info = []

    def migrate_legacy_baselines(
        self, 
        backup_before_migration: bool = True,
        validate_after_migration: bool = True
    ) -> OperationResult:
        """
        Migrate legacy baseline format to new data storage structure.
        
        Args:
            backup_before_migration: Create backup before migration
            validate_after_migration: Validate data integrity after migration
            
        Returns:
            OperationResult with migration summary
        """
        operation_start = datetime.now(UTC)
        
        try:
            # Check if source directory exists
            if not self.source_root.exists():
                return OperationResult(
                    success=False,
                    operation_type="migrate_legacy_baselines",
                    message=f"Source directory not found: {self.source_root}",
                    execution_time_ms=0.0,
                    timestamp=operation_start.isoformat()
                )
            
            # Create backup if requested
            backup_path = None
            if backup_before_migration:
                backup_path = self._create_migration_backup()
            
            # Ensure target directory exists
            self.target_root.mkdir(parents=True, exist_ok=True)
            target_baselines_dir = self.target_root / 'baselines'
            target_baselines_dir.mkdir(exist_ok=True)
            
            # Discover legacy baseline files
            legacy_files = list(self.source_root.glob('*.json'))
            migrated_count = 0
            errors = []
            
            for legacy_file in legacy_files:
                try:
                    # Load legacy baseline
                    with open(legacy_file, 'r') as f:
                        legacy_data = json.load(f)
                    
                    # Convert to new format if needed
                    migrated_data = self._convert_legacy_baseline_format(legacy_data)
                    
                    # Write to new location
                    target_file = target_baselines_dir / legacy_file.name
                    with open(target_file, 'w') as f:
                        json.dump(migrated_data, f, indent=2, default=str)
                    
                    # Log migration
                    self.migration_log.append({
                        'source_file': str(legacy_file),
                        'target_file': str(target_file),
                        'timestamp': datetime.now(UTC).isoformat(),
                        'status': 'migrated'
                    })
                    
                    migrated_count += 1
                    
                except Exception as e:
                    error_msg = f"Failed to migrate {legacy_file}: {str(e)}"
                    errors.append(error_msg)
                    self.migration_log.append({
                        'source_file': str(legacy_file),
                        'timestamp': datetime.now(UTC).isoformat(),
                        'status': 'error',
                        'error': error_msg
                    })
            
            # Validate migrated data if requested
            validation_results = None
            if validate_after_migration and migrated_count > 0:
                validation_results = self._validate_migrated_data()
            
            # Create metadata index
            if migrated_count > 0:
                self._create_migration_metadata()
            
            execution_time = (datetime.now(UTC) - operation_start).total_seconds() * 1000
            
            return OperationResult(
                success=len(errors) == 0,
                operation_type="migrate_legacy_baselines",
                message=f"Migrated {migrated_count} baselines with {len(errors)} errors",
                execution_time_ms=execution_time,
                timestamp=operation_start.isoformat(),
                details={
                    'migrated_count': migrated_count,
                    'error_count': len(errors),
                    'backup_created': backup_path is not None,
                    'backup_path': str(backup_path) if backup_path else None,
                    'validation_results': validation_results,
                    'source_directory': str(self.source_root),
                    'target_directory': str(self.target_root)
                },
                warnings=[] if len(errors) == 0 else ["Some files failed to migrate"],
                errors=errors
            )
            
        except Exception as e:
            execution_time = (datetime.now(UTC) - operation_start).total_seconds() * 1000
            error_msg = f"Migration failed: {str(e)}"
            
            return OperationResult(
                success=False,
                operation_type="migrate_legacy_baselines",
                message=error_msg,
                execution_time_ms=execution_time,
                timestamp=operation_start.isoformat(),
                errors=[error_msg]
            )

    def export_baselines_for_backup(
        self,
        export_format: str = "json",
        include_metadata: bool = True,
        compress_output: bool = False
    ) -> OperationResult:
        """
        Export all baselines for backup or transfer to another system.
        
        Args:
            export_format: Export format (json, csv, yaml)
            include_metadata: Include migration metadata
            compress_output: Create compressed archive
            
        Returns:
            OperationResult with export information
        """
        operation_start = datetime.now(UTC)
        
        try:
            # Create exports directory
            exports_dir = self.target_root / 'exports'
            exports_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
            export_file = exports_dir / f"quality_baselines_export_{timestamp}.{export_format}"
            
            # Collect all baseline data
            baselines_dir = self.target_root / 'baselines'
            if not baselines_dir.exists():
                baselines_dir = self.source_root
            
            baseline_files = list(baselines_dir.glob('*.json'))
            export_data = {
                'export_metadata': {
                    'timestamp': datetime.now(UTC).isoformat(),
                    'export_format': export_format,
                    'baseline_count': len(baseline_files),
                    'source_directory': str(baselines_dir),
                    'version': '1.0'
                },
                'baselines': []
            }
            
            # Load and add baselines
            for baseline_file in baseline_files:
                try:
                    with open(baseline_file, 'r') as f:
                        baseline_data = json.load(f)
                    export_data['baselines'].append(baseline_data)
                except Exception as e:
                    export_data['baselines'].append({
                        'error': f"Failed to load {baseline_file}: {str(e)}",
                        'file_path': str(baseline_file)
                    })
            
            # Include migration metadata if requested
            if include_metadata and self.migration_log:
                export_data['migration_history'] = self.migration_log
            
            # Write export file
            if export_format.lower() == 'json':
                with open(export_file, 'w') as f:
                    json.dump(export_data, f, indent=2, default=str)
            else:
                # For other formats, just export as JSON for now
                # Could be extended to support CSV, YAML, etc.
                with open(export_file, 'w') as f:
                    json.dump(export_data, f, indent=2, default=str)
            
            # Create compressed archive if requested
            archive_path = None
            if compress_output:
                import zipfile
                archive_path = export_file.with_suffix('.zip')
                with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.write(export_file, export_file.name)
                
                # Remove uncompressed file
                export_file.unlink()
                export_file = archive_path
            
            execution_time = (datetime.now(UTC) - operation_start).total_seconds() * 1000
            file_size = export_file.stat().st_size
            
            return OperationResult(
                success=True,
                operation_type="export_baselines_for_backup",
                message=f"Exported {len(baseline_files)} baselines to {export_file}",
                execution_time_ms=execution_time,
                timestamp=operation_start.isoformat(),
                details={
                    'export_file': str(export_file),
                    'file_size_bytes': file_size,
                    'baseline_count': len(baseline_files),
                    'compressed': compress_output,
                    'format': export_format
                }
            )
            
        except Exception as e:
            execution_time = (datetime.now(UTC) - operation_start).total_seconds() * 1000
            error_msg = f"Export failed: {str(e)}"
            
            return OperationResult(
                success=False,
                operation_type="export_baselines_for_backup",
                message=error_msg,
                execution_time_ms=execution_time,
                timestamp=operation_start.isoformat(),
                errors=[error_msg]
            )

    def import_baselines_from_backup(
        self,
        import_file: str,
        overwrite_existing: bool = False,
        validate_before_import: bool = True
    ) -> OperationResult:
        """
        Import baselines from backup file.
        
        Args:
            import_file: Path to import file
            overwrite_existing: Whether to overwrite existing baselines
            validate_before_import: Validate data before importing
            
        Returns:
            OperationResult with import information
        """
        operation_start = datetime.now(UTC)
        
        try:
            import_path = Path(import_file)
            if not import_path.exists():
                return OperationResult(
                    success=False,
                    operation_type="import_baselines_from_backup",
                    message=f"Import file not found: {import_file}",
                    execution_time_ms=0.0,
                    timestamp=operation_start.isoformat()
                )
            
            # Handle compressed files
            temp_file = None
            if import_path.suffix == '.zip':
                import zipfile
                temp_file = import_path.with_suffix('.temp.json')
                with zipfile.ZipFile(import_path, 'r') as zf:
                    # Extract first JSON file
                    json_files = [name for name in zf.namelist() if name.endswith('.json')]
                    if not json_files:
                        return OperationResult(
                            success=False,
                            operation_type="import_baselines_from_backup",
                            message="No JSON files found in archive",
                            execution_time_ms=0.0,
                            timestamp=operation_start.isoformat()
                        )
                    
                    with zf.open(json_files[0]) as zf_file:
                        with open(temp_file, 'wb') as f:
                            f.write(zf_file.read())
                
                import_path = temp_file
            
            # Load import data
            with open(import_path, 'r') as f:
                import_data = json.load(f)
            
            # Validate import data structure
            if 'baselines' not in import_data:
                return OperationResult(
                    success=False,
                    operation_type="import_baselines_from_backup",
                    message="Invalid import file format: missing 'baselines' key",
                    execution_time_ms=0.0,
                    timestamp=operation_start.isoformat()
                )
            
            baselines = import_data['baselines']
            
            # Validate data if requested
            if validate_before_import:
                validation_errors = self._validate_import_data(baselines)
                if validation_errors:
                    return OperationResult(
                        success=False,
                        operation_type="import_baselines_from_backup",
                        message="Import data validation failed",
                        execution_time_ms=0.0,
                        timestamp=operation_start.isoformat(),
                        errors=validation_errors
                    )
            
            # Ensure target directory exists
            baselines_dir = self.target_root / 'baselines'
            baselines_dir.mkdir(parents=True, exist_ok=True)
            
            # Import baselines
            imported_count = 0
            skipped_count = 0
            errors = []
            
            for baseline_data in baselines:
                try:
                    if 'error' in baseline_data:
                        # Skip error entries from export
                        continue
                    
                    baseline_id = baseline_data.get('baseline_id')
                    if not baseline_id:
                        errors.append("Baseline missing baseline_id")
                        continue
                    
                    target_file = baselines_dir / f"{baseline_id}.json"
                    
                    # Check if file exists and overwrite policy
                    if target_file.exists() and not overwrite_existing:
                        skipped_count += 1
                        continue
                    
                    # Write baseline file
                    with open(target_file, 'w') as f:
                        json.dump(baseline_data, f, indent=2, default=str)
                    
                    imported_count += 1
                    
                except Exception as e:
                    error_msg = f"Failed to import baseline: {str(e)}"
                    errors.append(error_msg)
            
            # Clean up temp file
            if temp_file and temp_file.exists():
                temp_file.unlink()
            
            execution_time = (datetime.now(UTC) - operation_start).total_seconds() * 1000
            
            return OperationResult(
                success=len(errors) == 0,
                operation_type="import_baselines_from_backup",
                message=f"Imported {imported_count} baselines, skipped {skipped_count}, {len(errors)} errors",
                execution_time_ms=execution_time,
                timestamp=operation_start.isoformat(),
                details={
                    'imported_count': imported_count,
                    'skipped_count': skipped_count,
                    'error_count': len(errors),
                    'import_file': import_file,
                    'overwrite_existing': overwrite_existing
                },
                warnings=[] if skipped_count == 0 else [f"Skipped {skipped_count} existing baselines"],
                errors=errors
            )
            
        except Exception as e:
            execution_time = (datetime.now(UTC) - operation_start).total_seconds() * 1000
            error_msg = f"Import failed: {str(e)}"
            
            return OperationResult(
                success=False,
                operation_type="import_baselines_from_backup",
                message=error_msg,
                execution_time_ms=execution_time,
                timestamp=operation_start.isoformat(),
                errors=[error_msg]
            )

    def repair_corrupted_data(self, dry_run: bool = True) -> OperationResult:
        """
        Attempt to repair corrupted baseline data files.
        
        Args:
            dry_run: If True, only report issues without fixing
            
        Returns:
            OperationResult with repair information
        """
        operation_start = datetime.now(UTC)
        
        try:
            baselines_dir = self.target_root / 'baselines'
            if not baselines_dir.exists():
                baselines_dir = self.source_root
            
            if not baselines_dir.exists():
                return OperationResult(
                    success=False,
                    operation_type="repair_corrupted_data",
                    message="No baselines directory found",
                    execution_time_ms=0.0,
                    timestamp=operation_start.isoformat()
                )
            
            baseline_files = list(baselines_dir.glob('*.json'))
            corrupted_files = []
            repaired_files = []
            errors = []
            
            for baseline_file in baseline_files:
                try:
                    with open(baseline_file, 'r') as f:
                        content = f.read().strip()
                    
                    if not content:
                        corrupted_files.append({
                            'file': str(baseline_file),
                            'issue': 'empty_file',
                            'repairable': False
                        })
                        continue
                    
                    # Try to parse JSON
                    try:
                        data = json.loads(content)
                    except json.JSONDecodeError as e:
                        # Try to repair common JSON issues
                        if not dry_run:
                            repaired_content = self._attempt_json_repair(content)
                            if repaired_content:
                                # Test if repaired JSON is valid
                                json.loads(repaired_content)
                                
                                # Create backup before repair
                                backup_file = baseline_file.with_suffix('.backup')
                                shutil.copy2(baseline_file, backup_file)
                                
                                # Write repaired content
                                with open(baseline_file, 'w') as f:
                                    f.write(repaired_content)
                                
                                repaired_files.append({
                                    'file': str(baseline_file),
                                    'issue': 'json_syntax_error',
                                    'backup': str(backup_file)
                                })
                                continue
                        
                        corrupted_files.append({
                            'file': str(baseline_file),
                            'issue': f'json_parse_error: {str(e)}',
                            'repairable': True
                        })
                        continue
                    
                    # Validate baseline data structure
                    required_fields = ['baseline_id', 'project_name', 'created_at', 'metrics']
                    missing_fields = [field for field in required_fields if field not in data]
                    
                    if missing_fields:
                        corrupted_files.append({
                            'file': str(baseline_file),
                            'issue': f'missing_required_fields: {missing_fields}',
                            'repairable': True
                        })
                    
                except Exception as e:
                    error_msg = f"Error checking {baseline_file}: {str(e)}"
                    errors.append(error_msg)
            
            execution_time = (datetime.now(UTC) - operation_start).total_seconds() * 1000
            
            status_msg = "dry-run completed" if dry_run else "repair completed"
            
            return OperationResult(
                success=len(errors) == 0,
                operation_type="repair_corrupted_data",
                message=f"Data repair {status_msg}: {len(corrupted_files)} issues found, {len(repaired_files)} repaired",
                execution_time_ms=execution_time,
                timestamp=operation_start.isoformat(),
                details={
                    'total_files_checked': len(baseline_files),
                    'corrupted_files': corrupted_files,
                    'repaired_files': repaired_files,
                    'error_count': len(errors),
                    'dry_run': dry_run
                },
                warnings=[] if len(corrupted_files) == 0 else [f"Found {len(corrupted_files)} corrupted files"],
                errors=errors
            )
            
        except Exception as e:
            execution_time = (datetime.now(UTC) - operation_start).total_seconds() * 1000
            error_msg = f"Repair operation failed: {str(e)}"
            
            return OperationResult(
                success=False,
                operation_type="repair_corrupted_data",
                message=error_msg,
                execution_time_ms=execution_time,
                timestamp=operation_start.isoformat(),
                errors=[error_msg]
            )

    # Private helper methods

    def _create_migration_backup(self) -> Path:
        """Create backup of source data before migration."""
        timestamp = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
        backup_dir = Path(f"{self.source_root}_backup_{timestamp}")
        
        shutil.copytree(self.source_root, backup_dir)
        
        self.rollback_info.append({
            'backup_path': str(backup_dir),
            'original_path': str(self.source_root),
            'timestamp': datetime.now(UTC).isoformat()
        })
        
        return backup_dir

    def _convert_legacy_baseline_format(self, legacy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert legacy baseline format to current format."""
        # For now, assume data is already in correct format
        # This could be extended to handle actual format conversions
        
        # Ensure required fields exist
        if 'created_at' not in legacy_data:
            legacy_data['created_at'] = datetime.now(UTC).isoformat()
        
        if 'expires_at' not in legacy_data:
            # Set expiration to 1 year from creation
            from datetime import timedelta
            created_at = datetime.fromisoformat(legacy_data['created_at'].replace('Z', '+00:00'))
            expires_at = created_at + timedelta(days=365)
            legacy_data['expires_at'] = expires_at.isoformat()
        
        if 'retention_days' not in legacy_data:
            legacy_data['retention_days'] = 365
        
        if 'tags' not in legacy_data:
            legacy_data['tags'] = []
        
        return legacy_data

    def _validate_migrated_data(self) -> Dict[str, Any]:
        """Validate migrated data integrity."""
        validation_results = {
            'total_files': 0,
            'valid_files': 0,
            'invalid_files': 0,
            'validation_errors': []
        }
        
        baselines_dir = self.target_root / 'baselines'
        baseline_files = list(baselines_dir.glob('*.json'))
        
        validation_results['total_files'] = len(baseline_files)
        
        for baseline_file in baseline_files:
            try:
                with open(baseline_file, 'r') as f:
                    data = json.load(f)
                
                # Basic validation
                required_fields = ['baseline_id', 'project_name', 'created_at', 'metrics']
                if all(field in data for field in required_fields):
                    validation_results['valid_files'] += 1
                else:
                    validation_results['invalid_files'] += 1
                    validation_results['validation_errors'].append(
                        f"{baseline_file.name}: missing required fields"
                    )
                    
            except Exception as e:
                validation_results['invalid_files'] += 1
                validation_results['validation_errors'].append(
                    f"{baseline_file.name}: {str(e)}"
                )
        
        return validation_results

    def _create_migration_metadata(self):
        """Create migration metadata file."""
        metadata_dir = self.target_root / 'metadata'
        metadata_dir.mkdir(exist_ok=True)
        
        migration_metadata = {
            'migration_timestamp': datetime.now(UTC).isoformat(),
            'source_directory': str(self.source_root),
            'target_directory': str(self.target_root),
            'migration_log': self.migration_log,
            'rollback_info': self.rollback_info
        }
        
        metadata_file = metadata_dir / 'migration_metadata.json'
        with open(metadata_file, 'w') as f:
            json.dump(migration_metadata, f, indent=2)

    def _validate_import_data(self, baselines: List[Dict[str, Any]]) -> List[str]:
        """Validate import data structure."""
        errors = []
        
        for i, baseline in enumerate(baselines):
            if 'error' in baseline:
                continue  # Skip error entries
                
            # Check required fields
            required_fields = ['baseline_id', 'project_name', 'created_at']
            missing_fields = [field for field in required_fields if field not in baseline]
            
            if missing_fields:
                errors.append(f"Baseline {i}: missing fields {missing_fields}")
        
        return errors

    def _attempt_json_repair(self, content: str) -> Optional[str]:
        """Attempt to repair common JSON syntax errors."""
        try:
            # Remove trailing commas
            import re
            
            # Remove trailing commas before closing braces/brackets
            content = re.sub(r',(\s*[}\]])', r'\1', content)
            
            # Ensure proper quote handling (basic attempt)
            # This is a very basic repair - could be expanded
            
            # Try to parse repaired content
            json.loads(content)
            return content
            
        except Exception:
            return None

    def rollback_migration(self) -> OperationResult:
        """Rollback migration using backup data."""
        if not self.rollback_info:
            return OperationResult(
                success=False,
                operation_type="rollback_migration",
                message="No rollback information available",
                execution_time_ms=0.0,
                timestamp=datetime.now(UTC).isoformat()
            )
        
        try:
            # Use most recent rollback info
            rollback_data = self.rollback_info[-1]
            backup_path = Path(rollback_data['backup_path'])
            
            if not backup_path.exists():
                return OperationResult(
                    success=False,
                    operation_type="rollback_migration",
                    message=f"Backup directory not found: {backup_path}",
                    execution_time_ms=0.0,
                    timestamp=datetime.now(UTC).isoformat()
                )
            
            # Remove target directory if it exists
            if self.target_root.exists():
                shutil.rmtree(self.target_root)
            
            # Restore from backup
            shutil.copytree(backup_path, self.source_root)
            
            return OperationResult(
                success=True,
                operation_type="rollback_migration",
                message="Migration rollback completed successfully",
                execution_time_ms=0.0,
                timestamp=datetime.now(UTC).isoformat(),
                details={
                    'backup_path': str(backup_path),
                    'restored_path': str(self.source_root)
                }
            )
            
        except Exception as e:
            error_msg = f"Rollback failed: {str(e)}"
            
            return OperationResult(
                success=False,
                operation_type="rollback_migration",
                message=error_msg,
                execution_time_ms=0.0,
                timestamp=datetime.now(UTC).isoformat(),
                errors=[error_msg]
            )

    def cleanup_migration_artifacts(self) -> OperationResult:
        """Clean up migration artifacts and temporary files."""
        try:
            cleaned_items = []
            
            # Remove backup directories
            for rollback_data in self.rollback_info:
                backup_path = Path(rollback_data['backup_path'])
                if backup_path.exists():
                    shutil.rmtree(backup_path)
                    cleaned_items.append(str(backup_path))
            
            # Clear rollback info
            self.rollback_info.clear()
            
            return OperationResult(
                success=True,
                operation_type="cleanup_migration_artifacts",
                message=f"Cleaned up {len(cleaned_items)} migration artifacts",
                execution_time_ms=0.0,
                timestamp=datetime.now(UTC).isoformat(),
                details={
                    'cleaned_items': cleaned_items
                }
            )
            
        except Exception as e:
            error_msg = f"Cleanup failed: {str(e)}"
            
            return OperationResult(
                success=False,
                operation_type="cleanup_migration_artifacts",
                message=error_msg,
                execution_time_ms=0.0,
                timestamp=datetime.now(UTC).isoformat(),
                errors=[error_msg]
            )