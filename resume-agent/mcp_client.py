"""
mcp_client.py: connection layer for the MCP gateway.

- get_auth_headers(): reads creds from SSM, gets a Cognito token, returns headers
- mcp_session():      async context manager that yields a live, initialized ClientSession
- execute_mcp():      standalone check that lists the gateway's tools

Run directly to test the connection:  python mcp_client.py
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import boto3
import httpx
import requests
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- config
TOKEN_URL = "https://my-domain-jxqkw81t.auth.us-east-1.amazoncognito.com/oauth2/token"
GATEWAY_URL = "https://resume-assistant-gw-dev-kw1qkgv35y.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

ssm = boto3.client("ssm", region_name=AWS_REGION)
_CLIENT_ID, _CLIENT_SECRET = None, None                    # cached after first read


# ---------------------------------------------------------------- auth
def get_client_creds():
    """Read client id/secret from SSM once, cache them, and return both."""
    global _CLIENT_ID, _CLIENT_SECRET
    client_id_param = (os.environ.get("CLIENT_ID_PARAM") or "").strip().strip("\"'")
    client_secret_param = os.environ.get("CLIENT_SECRET_PARAM" or "").strip().strip("\"'")
    logger.info("%s %s",client_id_param,client_secret_param)
    missing = [
        name
        for name, value in (
            ("CLIENT_ID_PARAM", client_id_param),
            ("CLIENT_SECRET_PARAM", client_secret_param),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): " + ", ".join(missing)
        )

    if not _CLIENT_ID:
        resp = ssm.get_parameter(Name=client_id_param, WithDecryption=True)
        _CLIENT_ID = resp["Parameter"]["Value"]
    if not _CLIENT_SECRET:
        resp = ssm.get_parameter(Name=client_secret_param, WithDecryption=True)
        _CLIENT_SECRET = resp["Parameter"]["Value"]

    return _CLIENT_ID, _CLIENT_SECRET


def fetch_access_token(client_id, client_secret, token_url=TOKEN_URL):
    response = requests.post(
        token_url,
        data={  # dict form lets requests URL-encode special characters safely
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def get_auth_headers():
    client_id, client_secret = get_client_creds()
    token = fetch_access_token(client_id, client_secret)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- session
@asynccontextmanager
async def mcp_session(url=GATEWAY_URL, headers=None):
    """Open transport + ClientSession, initialize, and yield the live session.

    The session stays open only while the caller is inside the `async with`.
    Note: in current mcp SDKs streamable_http_client has no `headers=` argument,
    so headers go on an httpx.AsyncClient that we pass in as `http_client`.
    """
    async with httpx.AsyncClient(
        headers=headers or {},
        timeout=httpx.Timeout(30.0, read=300.0),
        follow_redirects=True,
    ) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                logger.info("MCP session initialized")
                yield session


async def list_all_tools(session):
    tools, cursor = [], None
    while True:
        response = await session.list_tools(cursor)
        tools.extend(response.tools)
        cursor = response.nextCursor
        if not cursor:
            return tools


async def execute_mcp(url=GATEWAY_URL, headers=None):
    """Standalone check: connect and list the tools."""
    async with mcp_session(url, headers) as session:
        tools = await list_all_tools(session)

    print(f"Found {len(tools)} tools:")
    for tool in tools:
        print("-", tool.name)
    return tools


if __name__ == "__main__":
    asyncio.run(execute_mcp(headers=get_auth_headers()))