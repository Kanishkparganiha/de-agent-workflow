import asyncio
import json
import os
import re

from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .prompts import SYSTEM_PROMPT

OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434") + "/v1"
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

_ollama = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")

KNOWN_TOOLS = {
    "list_tables", "run_query", "check_data_quality",
    "generate_pipeline_config", "validate_pipeline_config",
}
MAX_ITERATIONS = 10

# After these tools there's nothing more to do — force a final answer
TERMINAL_TOOLS = {"run_query", "validate_pipeline_config"}


def _parse_tool_call(text: str):
    """Return (name, args) if a valid known tool call is found, else None."""
    tool_m = re.search(r"<tool>\s*(\w+)\s*</tool>", text)
    if not tool_m:
        return None
    name = tool_m.group(1).strip()
    if name not in KNOWN_TOOLS:
        return None

    args_tag = text.find("<args>", tool_m.end())
    search_from = (args_tag + len("<args>")) if args_tag != -1 else tool_m.end()
    brace_start = text.find("{", search_from)
    if brace_start == -1:
        return name, {}
    return name, (_extract_json(text, brace_start) or {})


def _extract_json(text: str, start: int) -> dict | None:
    """Parse the first complete JSON object from position `start`."""
    depth, in_string, escape = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False; continue
        if in_string:
            if ch == "\\": escape = True
            elif ch == '"': in_string = False
            continue
        if ch == '"': in_string = True
        elif ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try: return json.loads(text[start:i + 1])
                except json.JSONDecodeError: return None
    return None


def _next_instruction(tool_name: str, tables_checked: list[str], all_tables: list[str]) -> str:
    """Return the instruction to append after a tool result."""
    if tool_name == "list_tables":
        if all_tables:
            return (
                f"Tables are: {', '.join(all_tables)}. "
                f"Now call check_data_quality for '{all_tables[0]}'."
            )
        return "Now write your final answer."

    if tool_name == "check_data_quality":
        remaining = [t for t in all_tables if t not in tables_checked]
        if remaining:
            return f"Now call check_data_quality for '{remaining[0]}'."
        return "You have checked all tables. Write your final answer summarising the quality issues found. Do NOT call any more tools."

    if tool_name == "generate_pipeline_config":
        return "Now call validate_pipeline_config with that YAML as the config_yaml argument."

    if tool_name in TERMINAL_TOOLS:
        return "Write your final answer based on the data above. Do NOT call any more tools."

    return "Continue. If you have all the information needed, write your final answer without tool tags."


async def run_agent(user_message: str) -> str:
    server_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "mcp_server", "server.py",
    )

    async with stdio_client(StdioServerParameters(command="python", args=[server_path])) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]

            all_tables: list[str] = []
            tables_checked: list[str] = []
            last_generated_yaml: str = ""

            for _ in range(MAX_ITERATIONS):
                response = _ollama.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    max_tokens=512,
                    temperature=0.0,
                )
                reply = response.choices[0].message.content or ""

                tool_call = _parse_tool_call(reply)
                if tool_call is None:
                    return reply.strip()

                name, args = tool_call

                # Always use the stored YAML for validation — the model can't reliably
                # JSON-encode the full multi-line YAML in its args string.
                if name == "validate_pipeline_config" and last_generated_yaml:
                    args = {"config_yaml": last_generated_yaml}

                print(f"  → {name}({_fmt_args(args)})")

                result = await session.call_tool(name, args)
                result_text = "\n".join(
                    c.text for c in result.content if hasattr(c, "text")
                ) if result.content else "(no result)"

                # Track state for guided prompting and YAML carry-forward
                if name == "generate_pipeline_config":
                    last_generated_yaml = result_text
                if name == "list_tables":
                    try:
                        all_tables = [t["table"] for t in json.loads(result_text)]
                    except (json.JSONDecodeError, KeyError):
                        pass
                elif name == "check_data_quality" and "table_name" in args:
                    tables_checked.append(args["table_name"])

                # For validate, compose the final answer directly — don't ask the model to
                # synthesize again, since small models ignore "stop calling tools".
                if name == "validate_pipeline_config":
                    try:
                        vr = json.loads(result_text)
                        status = "✓ VALID" if vr.get("valid") else "✗ INVALID"
                        warnings = "\n".join(f"  ⚠ {w}" for w in vr.get("warnings", []))
                        errors = "\n".join(f"  ✗ {e}" for e in vr.get("errors", []))
                        extra = f"\n{warnings}" if warnings else ""
                        extra += f"\n{errors}" if errors else ""
                        return (
                            f"Generated pipeline config ({status}):\n\n"
                            f"{last_generated_yaml}\n"
                            f"Validation: {vr.get('summary', result_text)}{extra}"
                        )
                    except json.JSONDecodeError:
                        return f"Pipeline config:\n\n{last_generated_yaml}\n\nValidation result:\n{result_text}"

                instruction = _next_instruction(name, tables_checked, all_tables)

                messages.append({"role": "assistant", "content": reply})
                messages.append({
                    "role": "user",
                    "content": f"Result of {name}:\n{result_text}\n\n{instruction}",
                })

            return "(max iterations reached)"


def _fmt_args(args: dict) -> str:
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        val = str(v)
        if len(val) > 60:
            val = val[:57] + "..."
        parts.append(f"{k}={val!r}")
    return ", ".join(parts)
