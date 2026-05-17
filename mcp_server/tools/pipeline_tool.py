import json
import re
import sys
import os

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_connection
from mcp import types

VALID_SOURCE_TYPES = ['s3', 'redshift', 'dynamodb', 'kinesis']
VALID_SOURCE_FORMATS = ['parquet', 'csv', 'json', 'avro']
VALID_TARGET_TYPES = ['s3', 'redshift']
VALID_WRITE_MODES = ['append', 'overwrite', 'upsert']
VALID_TRANSFORM_TYPES = ['filter', 'aggregate', 'join', 'enrich', 'deduplicate']


async def handle_validate_config(arguments: dict) -> list[types.TextContent]:
    config_yaml = arguments["config_yaml"]

    try:
        config = yaml.safe_load(config_yaml)
    except yaml.YAMLError as e:
        return [types.TextContent(type="text", text=json.dumps({
            "valid": False, "errors": [f"YAML parse error: {e}"], "warnings": []
        }))]

    if not isinstance(config, dict):
        return [types.TextContent(type="text", text=json.dumps({
            "valid": False, "errors": ["Config must be a YAML mapping"], "warnings": []
        }))]

    errors = []
    warnings = []

    # Required top-level sections
    for section in ['pipeline', 'source', 'target']:
        if section not in config:
            errors.append(f"Missing required section: '{section}'")

    # pipeline section
    pipeline = config.get('pipeline', {}) or {}
    for field in ['name', 'version', 'owner']:
        if field not in pipeline:
            errors.append(f"pipeline.{field} is required")

    if 'name' in pipeline:
        if not re.match(r'^[a-z][a-z0-9_]*$', str(pipeline['name'])):
            errors.append(f"pipeline.name must be snake_case (got: '{pipeline['name']}')")

    if 'schedule' in pipeline:
        parts = str(pipeline['schedule']).split()
        if len(parts) != 5:
            errors.append(f"pipeline.schedule must be a valid 5-field cron expression (got: '{pipeline['schedule']}')")

    # source section
    source = config.get('source', {}) or {}
    if 'type' not in source:
        errors.append("source.type is required")
    elif source['type'] not in VALID_SOURCE_TYPES:
        errors.append(f"source.type must be one of {VALID_SOURCE_TYPES} (got: '{source['type']}')")

    if 'location' not in source:
        errors.append("source.location is required")

    if 'format' in source and source['format'] not in VALID_SOURCE_FORMATS:
        errors.append(f"source.format must be one of {VALID_SOURCE_FORMATS} (got: '{source['format']}')")

    # target section
    target = config.get('target', {}) or {}
    if 'type' not in target:
        errors.append("target.type is required")
    elif target['type'] not in VALID_TARGET_TYPES:
        errors.append(f"target.type must be one of {VALID_TARGET_TYPES} (got: '{target['type']}')")

    if 'location' not in target:
        errors.append("target.location is required")

    if 'write_mode' not in target:
        errors.append("target.write_mode is required")
    elif target['write_mode'] not in VALID_WRITE_MODES:
        errors.append(f"target.write_mode must be one of {VALID_WRITE_MODES} (got: '{target['write_mode']}')")

    # transforms section
    transforms = config.get('transforms')
    if not transforms:
        warnings.append("No transforms defined — pipeline will copy source to target as-is")
    else:
        for i, t in enumerate(transforms):
            if 'type' not in t:
                errors.append(f"transforms[{i}].type is required")
            elif t['type'] not in VALID_TRANSFORM_TYPES:
                errors.append(f"transforms[{i}].type must be one of {VALID_TRANSFORM_TYPES}")

    # data_quality section
    if 'data_quality' not in config:
        warnings.append("No data_quality section — recommend adding quality checks before deploying")

    result = {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": (
            f"VALID — passes all {len(VALID_SOURCE_TYPES) + len(VALID_TRANSFORM_TYPES)} contract checks"
            if not errors
            else f"INVALID — {len(errors)} error(s) must be resolved before deployment"
        ),
    }
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_generate_config(arguments: dict) -> list[types.TextContent]:
    description = arguments["description"]
    source_table = arguments["source_table"]
    target_table = arguments["target_table"]
    transform_type = arguments.get("transform_type", "aggregate")

    # Pull schema from DB to make the config realistic
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({source_table})")
        col_meta = cursor.fetchall()
        col_names = [c[1] for c in col_meta]
        pk_cols = {c[1] for c in col_meta if c[5] == 1}
    except Exception:
        col_names = []
        pk_cols = set()
    finally:
        conn.close()

    # Classify columns — exclude PKs from group_by candidates
    date_cols = [c for c in col_names if 'date' in c and 'created' not in c]
    id_cols = [c for c in col_names if c.endswith('_id') and c not in pk_cols]
    # Classify numeric columns by appropriate aggregate function
    avg_cols = [c for c in col_names if any(k in c for k in ['rate', 'avg_', 'time', 'minutes'])]
    sum_cols = [c for c in col_names if any(k in c for k in ['count', 'delivered', 'attempted', 'headcount', 'variance', 'amount'])]

    partition_key = date_cols[0] if date_cols else 'created_at'
    group_by = (id_cols + date_cols)[:3] if id_cols else date_cols[:2]

    # Build transforms
    if transform_type == "aggregate":
        def _metric_name(prefix: str, col: str) -> str:
            return col if col.startswith(prefix) else f"{prefix}{col}"

        metrics = (
            [{"name": _metric_name("avg_", c), "function": "AVG", "column": c} for c in avg_cols[:2]] +
            [{"name": _metric_name("total_", c), "function": "SUM", "column": c} for c in sum_cols[:2]]
        )
        if not metrics:
            metrics = [{"name": "record_count", "function": "COUNT", "column": "*"}]

        transforms = [
            {
                "type": "filter",
                "config": {"column": partition_key, "operator": ">=", "value": "CURRENT_DATE - INTERVAL '7 days'"},
            },
            {
                "type": "aggregate",
                "config": {"group_by": group_by, "metrics": metrics},
            },
        ]
    elif transform_type == "filter":
        transforms = [
            {"type": "filter", "config": {"column": partition_key, "operator": ">=", "value": "CURRENT_DATE - INTERVAL '7 days'"}}
        ]
    elif transform_type == "join":
        join_key = id_cols[0] if id_cols else "id"
        transforms = [
            {"type": "join", "config": {"join_table": "lookup_table", "join_type": "LEFT", "on": join_key}}
        ]
    else:
        transforms = [
            {"type": "enrich", "config": {"lookup_table": "reference_data", "key": id_cols[0] if id_cols else "id"}}
        ]

    not_null_cols = (id_cols + date_cols)[:3] or [c for c in col_names if c not in pk_cols][:2]

    config = {
        "pipeline": {
            "name": re.sub(r'[^a-z0-9_]', '_', target_table.lower()),
            "version": "1.0.0",
            "owner": "utr-data-eng@amazon.com",
            "schedule": "0 6 * * *",
            "sla_minutes": 30,
        },
        "source": {
            "type": "redshift",
            "location": source_table,
            "format": "parquet",
            "partition_key": partition_key,
        },
        "transforms": transforms,
        "target": {
            "type": "redshift",
            "location": target_table,
            "write_mode": "upsert",
            "partition_by": [partition_key],
        },
        "data_quality": {
            "not_null_columns": not_null_cols,
            "row_count_min": 1,
            "freshness_check": True,
        },
    }

    config_yaml = yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return [types.TextContent(type="text", text=config_yaml)]
