import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_connection
from mcp import types


async def handle_run_query(arguments: dict) -> list[types.TextContent]:
    sql = arguments["sql"].strip()
    limit = int(arguments.get("limit", 100))

    if not sql.upper().startswith("SELECT"):
        return [types.TextContent(type="text", text=json.dumps({
            "error": "Only SELECT queries are permitted"
        }))]

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchmany(limit)
        columns = [desc[0] for desc in cursor.description]

        result = {
            "columns": columns,
            "rows": [dict(zip(columns, row)) for row in rows],
            "row_count": len(rows),
            "truncated": len(rows) == limit,
        }
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]
    finally:
        conn.close()
