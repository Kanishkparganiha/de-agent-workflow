import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_connection
from mcp import types

FRESHNESS_SLA_HOURS = 24


async def handle_data_quality(arguments: dict) -> list[types.TextContent]:
    table_name = arguments["table_name"]
    date_column = arguments.get("date_column")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        issues = []
        stats = {"table": table_name}

        # Row count
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        row_count = cursor.fetchone()[0]
        stats["row_count"] = row_count

        if row_count == 0:
            issues.append("CRITICAL: Table is empty")
            return [types.TextContent(type="text", text=json.dumps({
                "stats": stats, "issues": issues, "summary": "CRITICAL — table is empty"
            }))]

        # Column metadata
        cursor.execute(f"PRAGMA table_info({table_name})")
        col_meta = cursor.fetchall()
        col_names = [c[1] for c in col_meta]
        pk_cols = [c[1] for c in col_meta if c[5] == 1]

        # Null rates per column
        null_rates = {}
        for col in col_names:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {col} IS NULL")
            null_count = cursor.fetchone()[0]
            rate = null_count / row_count
            null_rates[col] = {"null_count": null_count, "null_rate": round(rate, 4)}
            if rate > 0.01:
                issues.append(f"Column '{col}' has {null_count} nulls ({rate:.1%} null rate)")
        stats["null_rates"] = null_rates

        # Freshness check
        freshness_col = date_column or "created_at"
        if freshness_col in col_names:
            cursor.execute(f"SELECT MAX({freshness_col}) FROM {table_name}")
            max_ts = cursor.fetchone()[0]
            stats["most_recent_record"] = max_ts
            if max_ts:
                try:
                    last_update = datetime.fromisoformat(str(max_ts).replace('Z', ''))
                    hours_stale = (datetime.now() - last_update).total_seconds() / 3600
                    stats["hours_since_update"] = round(hours_stale, 1)
                    if hours_stale > FRESHNESS_SLA_HOURS:
                        issues.append(
                            f"Freshness SLA breach: last updated {hours_stale:.1f}h ago "
                            f"(SLA: {FRESHNESS_SLA_HOURS}h)"
                        )
                except (ValueError, TypeError):
                    pass

        # Duplicate primary key check
        if pk_cols:
            pk_str = ", ".join(pk_cols)
            cursor.execute(f"""
                SELECT COUNT(*) FROM (
                    SELECT {pk_str} FROM {table_name}
                    GROUP BY {pk_str} HAVING COUNT(*) > 1
                )
            """)
            dup_count = cursor.fetchone()[0]
            stats["duplicate_pk_count"] = dup_count
            if dup_count > 0:
                issues.append(f"Found {dup_count} duplicate primary key value(s)")

        summary = (
            f"HEALTHY — all checks passed ({row_count} rows)"
            if not issues
            else f"WARNING — {len(issues)} issue(s) found ({row_count} rows)"
        )

        return [types.TextContent(type="text", text=json.dumps({
            "stats": stats,
            "issues": issues,
            "summary": summary,
        }, default=str))]

    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]
    finally:
        conn.close()
