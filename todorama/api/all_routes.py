"""
Route definitions file - all routes have been extracted to dedicated modules.

This file now only exports the router for backward compatibility.
All routes have been moved to:
- todorama/api/routes/tasks.py
- todorama/api/routes/templates.py
- todorama/api/routes/projects.py
- todorama/api/routes/tags.py
- todorama/api/routes/admin.py
- todorama/api/routes/tenancy.py
"""
from todorama.adapters.http_framework import HTTPFrameworkAdapter

# Initialize adapter and router for backward compatibility
# The router is exported but contains no routes (all routes are in dedicated modules)
http_adapter = HTTPFrameworkAdapter()
router_adapter = http_adapter.create_router()
router = router_adapter.router  # Export router for app/factory.py


# ============================================================================
# Task Routes - Extracted to todorama/api/routes/tasks.py
# ============================================================================

# ============================================================================
# Project Routes - Extracted to todorama/api/routes/projects.py
# ============================================================================

# ============================================================================
# Template Routes - Extracted to todorama/api/routes/templates.py
# ============================================================================

# ============================================================================
# Tag Routes - Extracted to todorama/api/routes/tags.py
# ============================================================================

# Note: Task import and bulk operations are now handled by TaskEntity methods
# via the command router: /api/Task/import/json, /api/Task/bulk/complete, etc.
# No FastAPI routes needed here - entities handle routing programmatically.

# ============================================================================
# Analytics Routes - Extracted to todorama/api/routes/admin.py
# ============================================================================

# ============================================================================
# API Key Management Routes - Extracted to todorama/api/routes/admin.py
# ============================================================================

# ============================================================================
# Organization Routes - Extracted to todorama/api/routes/tenancy.py
# ============================================================================

# ============================================================================
# Team Routes - Extracted to todorama/api/routes/tenancy.py
# ============================================================================

# ============================================================================
# Authentication Routes - Extracted to todorama/api/routes/tenancy.py
# ============================================================================

# ============================================================================
# Role Routes - Extracted to todorama/api/routes/tenancy.py
# ============================================================================


