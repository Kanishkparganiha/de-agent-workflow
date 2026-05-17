import sys
import os
import asyncio

# Allow direct execution: python mcp_server/server.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from database import init_db
from tools.query_tool import handle_run_query
from tools.schema_tool import handle_list_tables
from tools.quality_tool import handle_data_quality
from tools.pipeline_tool import handle_validate_config, handle_generate_config

app = Server("de-copilot")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="run_query",
            description="Execute a SELECT SQL query against the data warehouse and return results",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL SELECT query to execute"},
                    "limit": {"type": "integer", "description": "Max rows to return (default 100)", "default": 100},
                },
                "required": ["sql"],
            },
        ),
        types.Tool(
            name="list_tables",
            description="List all available tables with their schemas, column types, and row counts",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="check_data_quality",
            description="Run data quality checks on a table: null rates per column, row count, freshness, duplicate primary keys",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Table to check"},
                    "date_column": {"type": "string", "description": "Column to use for freshness check (default: created_at)"},
                },
                "required": ["table_name"],
            },
        ),
        types.Tool(
            name="validate_pipeline_config",
            description="Validate a pipeline YAML config against the team's data contract schema. Returns errors and warnings.",
            inputSchema={
                "type": "object",
                "properties": {
                    "config_yaml": {"type": "string", "description": "Full pipeline config as a YAML string"},
                },
                "required": ["config_yaml"],
            },
        ),
        types.Tool(
            name="generate_pipeline_config",
            description="Generate a validated pipeline config YAML from a natural language description and table parameters",
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "What the pipeline should do"},
                    "source_table": {"type": "string", "description": "Source table name"},
                    "target_table": {"type": "string", "description": "Target table name"},
                    "transform_type": {
                        "type": "string",
                        "enum": ["aggregate", "filter", "join", "enrich"],
                        "description": "Primary transform type",
                    },
                },
                "required": ["description", "source_table", "target_table"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "run_query":
        return await handle_run_query(arguments)
    elif name == "list_tables":
        return await handle_list_tables()
    elif name == "check_data_quality":
        return await handle_data_quality(arguments)
    elif name == "validate_pipeline_config":
        return await handle_validate_config(arguments)
    elif name == "generate_pipeline_config":
        return await handle_generate_config(arguments)
    else:
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    init_db()
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
