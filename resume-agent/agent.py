"""
agent.py: the agent (harness). Uses the MCP session from mcp_client.py.

Run:  python agent.py "your question here"
"""

import asyncio
import importlib
import logging
import os
import sys
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_aws import ChatBedrockConverse
from langchain_mcp_adapters.tools import load_mcp_tools

from mcp_client import get_auth_headers, mcp_session

load_dotenv()
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL = os.getenv("AWS_BEDROCK_MODEL_ID") or os.getenv("BEDROCK_MODEL_ID") or "us.amazon.nova-2-lite-v1:0"
if MODEL.startswith("bedrock_converse:"):
    MODEL = MODEL.split(":", 1)[1]

SYSTEM_PROMPT = "You are a helpful assistant. Use the available tools when you need information."


def get_weather(city: str) -> str:
    """Return a placeholder weather report for the requested city."""
    return f"It's always sunny in {city}"


async def run_agent(question: str):
    # The session must stay open for the whole agent run, so everything happens inside it.
    async with mcp_session(headers=get_auth_headers()) as session:
        mcp_tools = await load_mcp_tools(session)
        print("MCP tools:", [t.name for t in mcp_tools])

        agent = create_agent(
            model=ChatBedrockConverse(model=MODEL, region_name=AWS_REGION),
            tools=[*mcp_tools],
            system_prompt=SYSTEM_PROMPT,
        )

        try:
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": question}]}
            )
        except Exception as exc:
            message = str(exc)
            if "ModelErrorException" in message:
                raise RuntimeError(
                    "Bedrock returned a model error while generating a tool-use response. "
                    f"Current model: {MODEL}. Region: {AWS_REGION}. "
                    "Check that the model supports tool use with the supplied tools and try again."
                ) from exc
            if "Operation not allowed" in message or "ValidationException" in message:
                raise RuntimeError(
                    "Bedrock model access is blocked for this AWS account/region or the configured model is invalid. "
                    f"Current model: {MODEL}. Region: {AWS_REGION}. "
                    "Enable the model in the Bedrock console or set AWS_BEDROCK_MODEL_ID to a model enabled for this account."
                ) from exc
            raise

        for msg in result["messages"]:
            for call in getattr(msg, "tool_calls", None) or []:
                logger.info(f"Tool called: {call['name']} {call['args']}")
        return result["messages"][-1].content_blocks
    
@app.entrypoint
async def invoke(payload,context):
    question = (payload or {}).get("prompt")
    if not question or not str(question).strip():
        return {"error":"missing prompt"}
    try:
        answer = await run_agent(str(question).strip())
        return {"answer": answer}
    except Exception:
        logger.exception("Agent invocation failed")
        raise

if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", "8080")))