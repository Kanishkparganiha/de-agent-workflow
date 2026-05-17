#!/usr/bin/env python3
import asyncio
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.agent import run_agent

DEMO_QUERIES = [
    'what tables do we have and which ones have data quality issues?',
    'which sites had delivery rate below 90% last week?',
    'build me a pipeline that aggregates daily delivery rates by site',
]


def main():
    if len(sys.argv) < 2:
        print("DE Copilot — Agentic Data Engineering Assistant")
        print("=" * 50)
        print("\nUsage:  python main.py \"your question here\"")
        print("\nTry:")
        for q in DEMO_QUERIES:
            print(f'  python main.py "{q}"')
        sys.exit(0)

    query = " ".join(sys.argv[1:])
    print(f'\nQuery: "{query}"\n')
    print("─" * 50)

    result = asyncio.run(run_agent(query))

    print("─" * 50)
    print(result)


if __name__ == "__main__":
    main()
