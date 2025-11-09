"""
Import service - business logic for task import operations.
This layer contains no HTTP framework dependencies.
Handles JSON/CSV parsing, validation, duplicate detection, and relationship creation.
"""
import csv
import io
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from todorama.database import TodoDatabase

logger = logging.getLogger(__name__)


class ImportService:
    """Service for task import business logic."""
    
    def __init__(self, db: TodoDatabase):
        """Initialize import service with database dependency."""
        self.db = db
    
    def import_json(
        self,
        tasks: List[Dict[str, Any]],
        agent_id: str,
        project_id: Optional[int] = None,
        handle_duplicates: str = "error"
    ) -> Dict[str, Any]:
        """
        Import tasks from JSON format.
        
        Args:
            tasks: List of task dictionaries to import
            agent_id: Agent ID for task creation
            project_id: Optional project ID (can be overridden per task)
            handle_duplicates: "skip" to skip duplicates, "error" to raise errors
            
        Returns:
            Dictionary with import results:
            {
                "success": True,
                "created": int,
                "skipped": int,
                "error_count": int,
                "imported_count": int,
                "task_ids": List[int],
                "imported_task_ids": List[int],
                "skipped_tasks": List[Dict],
                "errors": List[Dict]
            }
        """
        imported = []
        skipped = []
        errors = []
        import_id_map = {}  # Map import_id to task_id for relationship creation
        seen_titles = set()  # Track titles seen in this import batch
        
        for task_data in tasks:
            try:
                title = task_data.get("title", "").strip()
                
                # Check for duplicates if handle_duplicates is "skip"
                if handle_duplicates == "skip":
                    # First check within the import batch
                    if title in seen_titles:
                        skipped.append({"title": title, "reason": "duplicate in batch"})
                        continue
                    
                    # Then check against existing tasks in database
                    if title:
                        existing = self.db.query_tasks(
                            search=title,
                            project_id=project_id or task_data.get("project_id"),
                            limit=10
                        )
                        # Filter to exact title match
                        exact_match = [t for t in existing if t.get("title", "").strip() == title]
                        if exact_match:
                            skipped.append({"title": title, "reason": "duplicate"})
                            continue
                    
                    # Mark this title as seen
                    seen_titles.add(title)
                
                # Parse due_date if provided
                due_date_obj = None
                if task_data.get("due_date"):
                    try:
                        due_date_str = task_data["due_date"]
                        if due_date_str.endswith('Z'):
                            due_date_obj = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                        else:
                            due_date_obj = datetime.fromisoformat(due_date_str)
                    except (ValueError, AttributeError):
                        pass
                
                task_id = self.db.create_task(
                    title=task_data["title"],
                    task_type=task_data["task_type"],
                    task_instruction=task_data["task_instruction"],
                    verification_instruction=task_data["verification_instruction"],
                    agent_id=agent_id,
                    project_id=project_id or task_data.get("project_id"),
                    priority=task_data.get("priority"),
                    estimated_hours=task_data.get("estimated_hours"),
                    notes=task_data.get("notes"),
                    due_date=due_date_obj
                )
                imported.append(task_id)
                
                # Store import_id mapping for relationship creation
                if task_data.get("import_id"):
                    import_id_map[task_data["import_id"]] = task_id
                    
            except Exception as e:
                logger.error(f"Failed to import task '{task_data.get('title', 'Unknown')}': {str(e)}", exc_info=True)
                errors.append({"task": task_data.get("title", "Unknown"), "error": str(e)})
        
        # Create relationships if import_id and parent_import_id are provided
        for task_data in tasks:
            if task_data.get("parent_import_id") and task_data.get("import_id"):
                parent_id = import_id_map.get(task_data["parent_import_id"])
                child_id = import_id_map.get(task_data["import_id"])
                relationship_type = task_data.get("relationship_type", "subtask")
                
                if parent_id and child_id:
                    try:
                        self.db.create_relationship(
                            parent_task_id=parent_id,
                            child_task_id=child_id,
                            relationship_type=relationship_type,
                            agent_id=agent_id
                        )
                    except Exception as e:
                        # Relationship creation failed, but task was created
                        logger.error(f"Failed to create relationship {parent_id}->{child_id}: {str(e)}", exc_info=True)
                        errors.append({"relationship": f"{parent_id}->{child_id}", "error": str(e)})
        
        return {
            "success": True,
            "created": len(imported),
            "skipped": len(skipped),
            "error_count": len(errors),
            "imported_count": len(imported),
            "task_ids": imported,  # Alias for imported_task_ids
            "imported_task_ids": imported,
            "skipped_tasks": skipped,
            "errors": errors
        }
    
    def import_csv(
        self,
        csv_content: str,
        agent_id: str,
        project_id: Optional[int] = None,
        handle_duplicates: str = "error",
        field_mapping: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Import tasks from CSV format.
        
        Args:
            csv_content: CSV content as string
            agent_id: Agent ID for task creation
            project_id: Optional project ID
            handle_duplicates: "skip" to skip duplicates, "error" to raise errors
            field_mapping: Optional mapping from CSV column names to task fields
                          e.g., {"title": "Task Title", "task_type": "Type"}
            
        Returns:
            Dictionary with import results:
            {
                "success": True,
                "created": int,
                "skipped": int,
                "error_count": int,
                "imported_count": int,
                "task_ids": List[int],
                "imported_task_ids": List[int],
                "skipped_tasks": List[Dict],
                "errors": List[Dict]
            }
        """
        csv_file = io.StringIO(csv_content)
        reader = csv.DictReader(csv_file)
        
        imported = []
        skipped = []
        errors = []
        
        for row in reader:
            try:
                # Apply field mapping if provided
                mapped_row = {}
                if field_mapping:
                    for target_field, source_field in field_mapping.items():
                        mapped_row[target_field] = row.get(source_field, "")
                    # Copy unmapped fields as-is
                    for key, value in row.items():
                        if key not in field_mapping.values():
                            mapped_row[key] = value
                else:
                    mapped_row = row
                
                title = mapped_row.get("title", "").strip()
                task_type = mapped_row.get("task_type", "concrete")
                task_instruction = mapped_row.get("task_instruction", "")
                verification_instruction = mapped_row.get("verification_instruction", "")
                
                # Validate required fields
                if not title:
                    errors.append({"row": "Unknown", "error": "Missing required field: title"})
                    continue
                if not task_instruction:
                    errors.append({"row": title, "error": "Missing required field: task_instruction"})
                    continue
                if not verification_instruction:
                    errors.append({"row": title, "error": "Missing required field: verification_instruction"})
                    continue
                
                # Check for duplicates if handle_duplicates is "skip"
                if handle_duplicates == "skip" and title:
                    existing = self.db.query_tasks(
                        search=title,
                        project_id=project_id or (int(mapped_row["project_id"]) if mapped_row.get("project_id") else None),
                        limit=10
                    )
                    # Filter to exact title match
                    exact_match = [t for t in existing if t.get("title", "").strip() == title]
                    if exact_match:
                        skipped.append({"title": title, "reason": "duplicate"})
                        continue
                
                # Parse optional fields
                parsed_project_id = project_id
                if not parsed_project_id and mapped_row.get("project_id"):
                    try:
                        parsed_project_id = int(mapped_row["project_id"])
                    except (ValueError, TypeError):
                        pass
                
                parsed_estimated_hours = None
                if mapped_row.get("estimated_hours"):
                    try:
                        parsed_estimated_hours = float(mapped_row["estimated_hours"])
                    except (ValueError, TypeError):
                        pass
                
                parsed_due_date = None
                if mapped_row.get("due_date"):
                    try:
                        parsed_due_date = datetime.fromisoformat(mapped_row["due_date"])
                    except (ValueError, AttributeError):
                        pass
                
                task_id = self.db.create_task(
                    title=title,
                    task_type=task_type,
                    task_instruction=task_instruction,
                    verification_instruction=verification_instruction,
                    agent_id=agent_id,
                    project_id=parsed_project_id,
                    priority=mapped_row.get("priority"),
                    estimated_hours=parsed_estimated_hours,
                    notes=mapped_row.get("notes"),
                    due_date=parsed_due_date
                )
                imported.append(task_id)
            except Exception as e:
                logger.error(f"Failed to import CSV row '{row.get('title', 'Unknown')}': {str(e)}", exc_info=True)
                errors.append({"row": row.get("title", "Unknown"), "error": str(e)})
        
        return {
            "success": True,
            "created": len(imported),
            "skipped": len(skipped),
            "error_count": len(errors),
            "imported_count": len(imported),
            "task_ids": imported,  # Add task_ids alias for consistency
            "imported_task_ids": imported,
            "skipped_tasks": skipped,
            "errors": errors
        }
