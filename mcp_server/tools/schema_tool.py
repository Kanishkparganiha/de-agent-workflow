import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_connection
from mcp import types


async def handle_list_tables() -> list[types.TextContent]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]

        result = []
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [
                {"name": row[1], "type": row[2], "not_null": bool(row[3]), "primary_key": bool(row[5])}
                for row in cursor.fetchall()
            ]
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cursor.fetchone()[0]

            result.append({
                "table": table,
                "row_count": row_count,
                "columns": columns,
            })

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    finally:
        conn.close()
