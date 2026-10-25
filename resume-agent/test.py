"""
debug_tools.py: see exactly what the model is given, and test the tool WITHOUT any LLM.

Run:  python debug_tools.py
"""

import asyncio
import json
import os

from dotenv import load_dotenv

from mcp_client import GATEWAY_URL, get_auth_headers, list_all_tools, mcp_session

load_dotenv()
MCP_URL = os.getenv("MCP_URL")


def pick_arg_name(schema: dict) -> str:
    props = schema.get("properties", {})
    if "query" in props:
        return "query"
    required = schema.get("required", [])
    return required[0] if required else next(iter(props))


async def main():
    headers = {} if MCP_URL else get_auth_headers()
    async with mcp_session(url=MCP_URL or GATEWAY_URL, headers=headers) as session:
        for t in await list_all_tools(session):
            print("=" * 60)
            print("NAME       :", t.name)
            print("DESCRIPTION:", t.description)
            print("SCHEMA     :", json.dumps(t.inputSchema, indent=2))

            arg = pick_arg_name(t.inputSchema)
            print(f"\nDirect call with {arg!r} = 'skills' (no LLM involved)...")
            result = await session.call_tool(t.name, {arg: "skills"})
            print("isError:", result.isError)
            for c in result.content:
                if c.type == "text":
                    print(c.text[:800])


if __name__ == "__main__":
    asyncio.run(main())