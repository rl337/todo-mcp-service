#!/bin/bash
# Fix database schema by adding missing priority column
# This script fixes permissions and runs the migration

set -e

DB_PATH="/home/rlee/june_data/todo-mcp-service/data/todos.db"
DB_DIR="$(dirname "$DB_PATH")"

echo "🔧 Fixing todorama database schema..."

# Step 1: Stop the service
echo "1. Stopping todorama service..."
pkill -f "uvicorn.*todorama" || echo "   Service not running"
sleep 2

# Step 2: Fix database permissions
echo "2. Fixing database permissions..."
if [ -f "$DB_PATH" ]; then
    # Check current owner
    CURRENT_OWNER=$(stat -c "%U:%G" "$DB_PATH")
    echo "   Current owner: $CURRENT_OWNER"
    
    if [ "$CURRENT_OWNER" != "rlee:rlee" ]; then
        echo "   Changing ownership to rlee:rlee..."
        sudo chown rlee:rlee "$DB_PATH" || {
            echo "   ⚠️  Could not change ownership (need sudo). Please run:"
            echo "      sudo chown rlee:rlee $DB_PATH"
            exit 1
        }
        echo "   ✅ Ownership changed"
    else
        echo "   ✅ Ownership already correct"
    fi
    
    # Fix permissions
    chmod 664 "$DB_PATH" || {
        echo "   ⚠️  Could not change permissions"
        exit 1
    }
    echo "   ✅ Permissions set to 664"
else
    echo "   ⚠️  Database file not found: $DB_PATH"
    exit 1
fi

# Step 3: Run migration to add priority column
echo "3. Running database migration..."
cd "$(dirname "$0")"

python3 << 'PYTHON_SCRIPT'
import sqlite3
import sys

db_path = '/home/rlee/june_data/todo-mcp-service/data/todos.db'

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if priority column exists
    cursor.execute('PRAGMA table_info(tasks)')
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'priority' not in columns:
        print("   Adding priority column...")
        cursor.execute('''
            ALTER TABLE tasks 
            ADD COLUMN priority TEXT DEFAULT 'medium' 
            CHECK(priority IN ('low', 'medium', 'high', 'critical'))
        ''')
        cursor.execute("UPDATE tasks SET priority = 'medium' WHERE priority IS NULL")
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks(task_status, priority)')
        conn.commit()
        print("   ✅ Priority column added successfully")
        
        # Verify
        cursor.execute('PRAGMA table_info(tasks)')
        columns = [row[1] for row in cursor.fetchall()]
        print(f"   ✅ Schema now has {len(columns)} columns")
        if 'priority' in columns:
            print("   ✅ Priority column confirmed")
    else:
        print("   ✅ Priority column already exists")
    
    conn.close()
    sys.exit(0)
except sqlite3.OperationalError as e:
    if "readonly" in str(e).lower():
        print(f"   ❌ Database is read-only: {e}")
        print("   Please check file permissions and ownership")
        sys.exit(1)
    else:
        print(f"   ❌ Database error: {e}")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ Error: {e}")
    sys.exit(1)
PYTHON_SCRIPT

if [ $? -ne 0 ]; then
    echo "   ❌ Migration failed"
    exit 1
fi

echo ""
echo "✅ Database schema fixed successfully!"
echo ""
echo "4. You can now start the service with:"
echo "   cd /home/rlee/dev/todorama-mcp-service"
echo "   ./start_service.sh"
echo ""

