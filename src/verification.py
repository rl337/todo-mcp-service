"""
Verification system for agent work validation.

Provides programmatic access to test execution, code quality checks, and validation.
This enables agents to verify their work before marking tasks complete.
"""
import os
import subprocess
import logging
import tempfile
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class VerificationResult:
    """Result of a verification check."""
    
    def __init__(
        self,
        check_name: str,
        success: bool,
        message: str = "",
        details: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        suggestions: Optional[List[str]] = None
    ):
        self.check_name = check_name
        self.success = success
        self.message = message
        self.details = details
        self.duration_seconds = duration_seconds
        self.suggestions = suggestions or []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "check_name": self.check_name,
            "success": self.success,
            "message": self.message,
            "details": self.details,
            "duration_seconds": self.duration_seconds,
            "suggestions": self.suggestions
        }


class VerificationSystem:
    """Comprehensive verification system for agent work."""
    
    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize verification system.
        
        Args:
            project_root: Root directory of the project. Defaults to current working directory.
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.checks_script = self.project_root / "run_checks.sh"
    
    def verify_work(
        self,
        run_tests: bool = True,
        check_quality: bool = True,
        check_database: bool = True,
        check_service: bool = True,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Run comprehensive verification checks.
        
        Args:
            run_tests: Run unit and integration tests
            check_quality: Run code quality checks
            check_database: Test database schema
            check_service: Test service startup
            timeout: Maximum time to wait for checks (seconds)
            
        Returns:
            Dictionary with verification results:
            {
                "success": bool,
                "checks": [VerificationResult],
                "summary": {
                    "total": int,
                    "passed": int,
                    "failed": int,
                    "duration_seconds": float
                },
                "passed": bool,
                "message": str
            }
        """
        start_time = datetime.now()
        results: List[VerificationResult] = []
        
        logger.info("Starting verification checks")
        
        # Check if we're in the right directory
        if not (self.project_root / "src" / "main.py").exists():
            return {
                "success": False,
                "checks": [],
                "summary": {
                    "total": 0,
                    "passed": 0,
                    "failed": 1,
                    "duration_seconds": 0.0
                },
                "passed": False,
                "message": f"Not in project root. Expected src/main.py in {self.project_root}"
            }
        
        # Run checks via run_checks.sh if available
        if self.checks_script.exists() and self.checks_script.is_file():
            result = self._run_checks_script(timeout)
            results.append(result)
        
        # Run individual checks if requested
        if run_tests:
            results.append(self._run_tests(timeout))
        
        if check_quality:
            results.append(self._check_code_quality())
        
        if check_database:
            results.append(self._check_database_schema())
        
        if check_service:
            results.append(self._check_service_startup())
        
        # Calculate summary
        total = len(results)
        passed = sum(1 for r in results if r.success)
        failed = total - passed
        duration = (datetime.now() - start_time).total_seconds()
        
        all_passed = failed == 0
        
        summary = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "duration_seconds": duration
        }
        
        message = (
            f"Verification {'passed' if all_passed else 'failed'}: "
            f"{passed}/{total} checks passed"
        )
        
        logger.info(f"Verification complete: {message}")
        
        return {
            "success": True,
            "checks": [r.to_dict() for r in results],
            "summary": summary,
            "passed": all_passed,
            "message": message
        }
    
    def _run_checks_script(self, timeout: int) -> VerificationResult:
        """Run the run_checks.sh script."""
        start_time = datetime.now()
        try:
            logger.info("Running run_checks.sh")
            result = subprocess.run(
                ["bash", str(self.checks_script)],
                cwd=self.project_root,
                timeout=timeout,
                capture_output=True,
                text=True
            )
            duration = (datetime.now() - start_time).total_seconds()
            
            if result.returncode == 0:
                return VerificationResult(
                    check_name="run_checks.sh",
                    success=True,
                    message="All checks passed",
                    details=result.stdout[-1000:] if result.stdout else None,  # Last 1000 chars
                    duration_seconds=duration
                )
            else:
                suggestions = []
                if "test" in result.stderr.lower() or "test" in result.stdout.lower():
                    suggestions.append("Review test failures and fix broken tests")
                if "syntax" in result.stderr.lower():
                    suggestions.append("Fix syntax errors in Python files")
                if "import" in result.stderr.lower():
                    suggestions.append("Fix import errors - check dependencies")
                
                return VerificationResult(
                    check_name="run_checks.sh",
                    success=False,
                    message="Some checks failed",
                    details=result.stderr[-2000:] if result.stderr else result.stdout[-2000:],
                    duration_seconds=duration,
                    suggestions=suggestions
                )
        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            return VerificationResult(
                check_name="run_checks.sh",
                success=False,
                message=f"Checks timed out after {timeout} seconds",
                duration_seconds=duration,
                suggestions=["Increase timeout or check for hanging tests"]
            )
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error running checks script: {e}", exc_info=True)
            return VerificationResult(
                check_name="run_checks.sh",
                success=False,
                message=f"Error running checks: {str(e)}",
                duration_seconds=duration,
                suggestions=["Check that run_checks.sh is executable and dependencies are installed"]
            )
    
    def _run_tests(self, timeout: int) -> VerificationResult:
        """Run unit and integration tests."""
        start_time = datetime.now()
        try:
            logger.info("Running tests")
            result = subprocess.run(
                ["python3", "-m", "pytest", "tests/", "-v", "--tb=short"],
                cwd=self.project_root,
                timeout=timeout,
                capture_output=True,
                text=True
            )
            duration = (datetime.now() - start_time).total_seconds()
            
            if result.returncode == 0:
                # Parse test results from output
                lines = result.stdout.split("\n")
                passed = sum(1 for line in lines if "PASSED" in line or "passed" in line.lower())
                failed = sum(1 for line in lines if "FAILED" in line or "failed" in line.lower())
                
                return VerificationResult(
                    check_name="test_execution",
                    success=True,
                    message=f"Tests passed: {passed} passed, {failed} failed",
                    details=result.stdout[-1000:] if result.stdout else None,
                    duration_seconds=duration
                )
            else:
                suggestions = [
                    "Review test failures",
                    "Run specific failing tests to debug: pytest tests/test_<module>.py::test_<function> -v",
                    "Check that all dependencies are installed"
                ]
                
                return VerificationResult(
                    check_name="test_execution",
                    success=False,
                    message="Some tests failed",
                    details=result.stderr[-2000:] if result.stderr else result.stdout[-2000:],
                    duration_seconds=duration,
                    suggestions=suggestions
                )
        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            return VerificationResult(
                check_name="test_execution",
                success=False,
                message=f"Tests timed out after {timeout} seconds",
                duration_seconds=duration,
                suggestions=["Some tests may be hanging - check for infinite loops or blocking operations"]
            )
        except FileNotFoundError:
            duration = (datetime.now() - start_time).total_seconds()
            return VerificationResult(
                check_name="test_execution",
                success=False,
                message="pytest not found",
                duration_seconds=duration,
                suggestions=["Install pytest: pip install pytest pytest-asyncio"]
            )
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error running tests: {e}", exc_info=True)
            return VerificationResult(
                check_name="test_execution",
                success=False,
                message=f"Error running tests: {str(e)}",
                duration_seconds=duration,
                suggestions=["Check pytest installation and test directory structure"]
            )
    
    def _check_code_quality(self) -> VerificationResult:
        """Check code quality (syntax, imports)."""
        start_time = datetime.now()
        issues = []
        
        try:
            # Check Python files for syntax errors
            src_dir = self.project_root / "src"
            if src_dir.exists():
                for py_file in src_dir.glob("*.py"):
                    try:
                        result = subprocess.run(
                            ["python3", "-m", "py_compile", str(py_file)],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if result.returncode != 0:
                            issues.append(f"Syntax error in {py_file.name}: {result.stderr}")
                    except Exception as e:
                        issues.append(f"Error checking {py_file.name}: {str(e)}")
            
            # Check imports
            try:
                result = subprocess.run(
                    ["python3", "-c", "import sys; sys.path.insert(0, 'src'); from database import TodoDatabase; from main import app"],
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode != 0:
                    issues.append(f"Import errors: {result.stderr}")
            except Exception as e:
                issues.append(f"Error checking imports: {str(e)}")
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if issues:
                return VerificationResult(
                    check_name="code_quality",
                    success=False,
                    message=f"Found {len(issues)} code quality issues",
                    details="\n".join(issues),
                    duration_seconds=duration,
                    suggestions=[
                        "Fix syntax errors",
                        "Check import statements",
                        "Verify all dependencies are installed"
                    ]
                )
            else:
                return VerificationResult(
                    check_name="code_quality",
                    success=True,
                    message="Code quality checks passed",
                    duration_seconds=duration
                )
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error checking code quality: {e}", exc_info=True)
            return VerificationResult(
                check_name="code_quality",
                success=False,
                message=f"Error checking code quality: {str(e)}",
                duration_seconds=duration
            )
    
    def _check_database_schema(self) -> VerificationResult:
        """Test database schema."""
        start_time = datetime.now()
        try:
            # Create a temporary database and test schema
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
                test_db = tmp_db.name
            
            try:
                result = subprocess.run(
                    [
                        "python3", "-c",
                        f"""
import sys
sys.path.insert(0, 'src')
from database import TodoDatabase
import os

db = TodoDatabase('{test_db}')
import sqlite3
conn = sqlite3.connect('{test_db}')
cursor = conn.cursor()
tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
table_names = [t[0] for t in tables]
required_tables = ['tasks', 'task_relationships', 'change_history', 'projects']
missing = [t for t in required_tables if t not in table_names]
if missing:
    print(f"MISSING: {{missing}}")
    sys.exit(1)
else:
    print("SCHEMA_OK")
    sys.exit(0)
"""
                    ],
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                duration = (datetime.now() - start_time).total_seconds()
                
                if result.returncode == 0:
                    return VerificationResult(
                        check_name="database_schema",
                        success=True,
                        message="Database schema is correct",
                        duration_seconds=duration
                    )
                else:
                    return VerificationResult(
                        check_name="database_schema",
                        success=False,
                        message="Database schema validation failed",
                        details=result.stderr or result.stdout,
                        duration_seconds=duration,
                        suggestions=["Check database schema initialization code"]
                    )
            finally:
                if os.path.exists(test_db):
                    os.unlink(test_db)
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error checking database schema: {e}", exc_info=True)
            return VerificationResult(
                check_name="database_schema",
                success=False,
                message=f"Error checking database schema: {str(e)}",
                duration_seconds=duration
            )
    
    def _check_service_startup(self) -> VerificationResult:
        """Test service startup configuration."""
        start_time = datetime.now()
        try:
            # Check if service can be imported and basic validation
            result = subprocess.run(
                [
                    "python3", "-c",
                    """
import sys
sys.path.insert(0, 'src')
try:
    from main import app
    print("IMPORT_OK")
    sys.exit(0)
except Exception as e:
    print(f"IMPORT_ERROR: {e}")
    sys.exit(1)
"""
                ],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if result.returncode == 0:
                return VerificationResult(
                    check_name="service_startup",
                    success=True,
                    message="Service can be imported",
                    duration_seconds=duration
                )
            else:
                return VerificationResult(
                    check_name="service_startup",
                    success=False,
                    message="Service import failed",
                    details=result.stderr or result.stdout,
                    duration_seconds=duration,
                    suggestions=[
                        "Check for missing dependencies",
                        "Verify service configuration",
                        "Check for syntax errors in main.py"
                    ]
                )
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error checking service startup: {e}", exc_info=True)
            return VerificationResult(
                check_name="service_startup",
                success=False,
                message=f"Error checking service: {str(e)}",
                duration_seconds=duration
            )
