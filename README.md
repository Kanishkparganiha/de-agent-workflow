# de-agent-workflow

An agentic data engineering framework that lets you talk to your data pipelines in natural language. Built on [Model Context Protocol (MCP)](https://modelcontextprotocol.io) with a local LLM — no cloud API needed.

---

## What It Does

```
$ python main.py "which sites had delivery rate below 90% last week?"

  → run_query(sql='SELECT site_id, COUNT(*) FROM site_metrics WHERE delivery_rate < 0.9 ...')

LAX2 had 8 days below 90% delivery rate last week. DEN1 had 4 days.
LAX2 is a chronic underperformer — recommend investigating route density and driver capacity.
```

```
$ python main.py "build me a pipeline that aggregates daily delivery rates by site"

  → generate_pipeline_config(source_table='site_metrics', target_table='site_summary', ...)
  → validate_pipeline_config(...)

Generated pipeline config (✓ VALID — passes all 9 contract checks):

pipeline:
  name: site_summary
  version: 1.0.0
  schedule: "0 6 * * *"
  sla_minutes: 30
...
```

---

## Architecture

```
User (natural language)
        │
        ▼
   agent/agent.py          ReAct agentic loop
   Ollama LLM              Reason → Act → Observe → Repeat
        │
        │  parses <tool>name</tool><args>{...}</args>
        ▼
mcp_server/server.py       MCP Server (stdio transport)
        │
        ├── list_tables          → SQLite schema + row counts
        ├── run_query            → execute SELECT, return JSON rows
        ├── check_data_quality   → null rates, freshness, duplicates
        ├── generate_pipeline_config  → NL description → YAML config
        └── validate_pipeline_config  → check YAML against data contract
                │
                ▼
         SQLite DB (mimics Redshift)
         site_metrics · labor_events · pipeline_runs
```

---

## Key Concepts

### Model Context Protocol (MCP)
MCP is a standard protocol for AI models to call external tools. The server declares tools with JSON Schema definitions — name, description, input params. Any MCP-compatible client (Claude Desktop, Cursor, VS Code) can connect and call them without custom integration per client.

- **Transport:** stdio locally, HTTP/SSE for remote servers
- **Why it matters:** Standardises the interface between LLMs and DE systems — swap the model or the tool implementation independently

### ReAct Agentic Loop
ReAct (Reason + Act) is a prompting pattern where the model alternates between reasoning and tool use:

```
1. User sends a natural language question
2. LLM decides which tool to call → outputs <tool>name</tool><args>{...}</args>
3. Agent parses the tag, calls the MCP tool, gets the result
4. Result is appended to conversation context
5. LLM reasons over the result → calls another tool or gives the final answer
6. Repeat until done
```

Used here instead of OpenAI-style structured function calling because small local models (3B params) handle text-format tool calls more reliably.

### Config-Driven Pipelines
Instead of engineers writing custom code per pipeline, pipelines are defined as YAML configs validated against a data contract. The agent bridges natural language intent and the config framework:

```
Natural language → generate_pipeline_config → YAML → validate_pipeline_config → deploy-ready config
```

---

## File Structure

```
de-agent-workflow/
├── main.py                          # CLI entry point
├── agent/
│   ├── agent.py                     # ReAct agentic loop
│   └── prompts.py                   # System prompt + tool definitions
├── mcp_server/
│   ├── server.py                    # MCP server (stdio transport)
│   ├── database.py                  # SQLite init + seed data
│   └── tools/
│       ├── query_tool.py            # run_query
│       ├── schema_tool.py           # list_tables
│       ├── quality_tool.py          # check_data_quality
│       └── pipeline_tool.py        # generate + validate pipeline config
├── contracts/
│   └── pipeline_schema.yaml         # Data contract — what a valid pipeline looks like
├── config/
│   └── example_pipeline.yaml        # Working example config
└── data/
    └── seed.sql                     # Table schemas + seed data structure
```

---

## Setup

**Requirements:** Python 3.12+, [Ollama](https://ollama.com) running locally

```bash
# 1. Clone
git clone https://github.com/Kanishkparganiha/de-agent-workflow.git
cd de-agent-workflow

# 2. Install dependencies
python3 -m venv venv && source venv/bin/activate
python3 -m pip install -r requirements.txt

# 3. Pull a local model
ollama pull llama3.2:3b        # lightweight, runs on CPU
# ollama pull qwen2.5:7b       # better reasoning, recommended if you have the RAM

# 4. Run
python3 main.py "what tables do we have and which ones have data quality issues?"
```

The SQLite database is created and seeded automatically on first run.

---

## Demo Queries

```bash
# Data quality audit across all tables
python main.py "what tables do we have and which ones have data quality issues?"

# Analytical query over real data
python main.py "which sites had delivery rate below 90% last week?"

# Natural language → validated pipeline config
python main.py "build me a pipeline that aggregates daily delivery rates by site"

# Pipeline health check
python main.py "show me the last 5 failed pipeline runs"
```

---

## MCP Tools

| Tool | Input | Output |
|---|---|---|
| `list_tables` | — | Table names, columns, row counts |
| `run_query` | `sql`, `limit` | Query results as JSON rows |
| `check_data_quality` | `table_name` | Null rates, row count, freshness, duplicate PKs |
| `generate_pipeline_config` | `description`, `source_table`, `target_table`, `transform_type` | Pipeline YAML |
| `validate_pipeline_config` | `config_yaml` | Valid/invalid + errors + warnings |

---

## Using as an MCP Server

Connect any MCP-compatible client directly to the server:

```json
// Claude Desktop config (~/.claude/claude_desktop_config.json)
{
  "mcpServers": {
    "de-agent-workflow": {
      "command": "python",
      "args": ["/path/to/de-agent-workflow/mcp_server/server.py"]
    }
  }
}
```

---

## References

- [Model Context Protocol — Official Docs](https://modelcontextprotocol.io/docs)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)
- [Ollama](https://ollama.com)
- [Anthropic Tool Use Docs](https://docs.anthropic.com/en/docs/tool-use)
