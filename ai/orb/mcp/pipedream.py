"""pipedream.piper

Utility for orchestrating calls between Pipedream and the OpenAI Responses API.

This module performs the equivalent of the shell script shared in the README
(using curl and jq) but entirely in Python:

1. Exchange the Pipedream client id/secret for an OAuth access token.
2. Discover the `name_slug` for the gmail app (or any other search query).
3. Invoke OpenAI's `responses` endpoint, passing a remote MCP block that
   forwards authentication headers to Pipedream's hosted MCP server.

The implementation is packaged as composable functions so that it can be
imported by other code or executed directly from the command-line:

$ python -m backend.ai.pipedream.piper  "Summarize my most recently created gmail doc ..."

Environment variables expected (these mirror the variables in the original
bash example):

PIPEDREAM_CLIENT_ID       – OAuth client id for Pipedream
PIPEDREAM_CLIENT_SECRET   – OAuth client secret for Pipedream
PIPEDREAM_PROJECT_ID      – Pipedream project id hosting the workflow
PIPEDREAM_ENVIRONMENT     – Pipedream environment name (e.g. "prod")
OPENAI_API_KEY            – The OpenAI API key to use

The module raises a RuntimeError with a helpful message when any variable is
missing.
"""
from __future__ import annotations

import json
import os
from typing import Dict, Optional, Tuple

import requests
from openai import OpenAI

__all__ = [
    "get_pipedream_access_token",
    "find_app_slug",
    "build_mcp_tool_block",
    "call_openai_responses",
]

PD_OAUTH_TOKEN_URL = "https://api.pipedream.com/v1/oauth/token"
PD_APPS_ENDPOINT = "https://api.pipedream.com/v1/apps"
MCP_SERVER_URL = "https://remote.mcp.pipedream.net"

# ---------------------------------------------------------------------------
# CONSTANTS & DEFAULTS
# ---------------------------------------------------------------------------

# The latest TypeScript example queries the Notion app by default.
DEFAULT_APP_QUERY = "notion"

# The model remains configurable but defaults to GPT-4.1.
DEFAULT_MODEL = "gpt-4.1"


class MissingEnvError(RuntimeError):
    """Raised when an expected environment variable is missing."""


def _require_env(var_name: str) -> str:
    """Return the value of *var_name* or raise a MissingEnvError."""
    value = os.getenv(var_name)
    if not value:
        raise MissingEnvError(
            f"Expected environment variable '{var_name}' to be set but it was not found."
        )
    return value


# ---------------------------------------------------------------------------
# 1) PIPEDREAM AUTHENTICATION
# ---------------------------------------------------------------------------

def get_pipedream_access_token(force_refresh: bool = False) -> str:
    """Obtain an OAuth access token from Pipedream.

    A short-lived token is cached for the lifetime of the process so repeated
    calls can reuse it. Set *force_refresh* to **True** to skip the cache.
    """
    if not force_refresh and hasattr(get_pipedream_access_token, "_cached_token"):
        return getattr(get_pipedream_access_token, "_cached_token")  # type: ignore[attr-defined]

    client_id = _require_env("PIPEDREAM_CLIENT_ID")
    client_secret = _require_env("PIPEDREAM_CLIENT_SECRET")

    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    resp = requests.post(PD_OAUTH_TOKEN_URL, json=payload, timeout=15)
    resp.raise_for_status()
    access_token = resp.json().get("access_token")
    if not access_token:
        raise RuntimeError("Pipedream OAuth response did not include 'access_token'.")

    # Cache the token for subsequent calls
    setattr(get_pipedream_access_token, "_cached_token", access_token)  # type: ignore[attr-defined]
    return access_token


# ---------------------------------------------------------------------------
# 2) APP DISCOVERY
# ---------------------------------------------------------------------------

def find_app_slug(access_token: str, query: str = DEFAULT_APP_QUERY) -> Tuple[str, str]:
    """Return the *name_slug* and *name* for the first app that matches *query*."""
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(f"{PD_APPS_ENDPOINT}?q={query}", headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    if not data:
        raise RuntimeError(f"No Pipedream apps found for query '{query}'.")
    app = data[0]
    return app["name_slug"], app["name"]


# ---------------------------------------------------------------------------
# 3) BUILD MCP TOOL BLOCK
# ---------------------------------------------------------------------------

def build_mcp_tool_block(
    access_token: str,
    app_slug: str,
    app_name: str,
    *,
    external_user_id: Optional[str] = None,
) -> Dict[str, object]:
    """Construct the MCP tool block expected by the Responses API.

    Parameters
    ----------
    access_token:
        OAuth token obtained from Pipedream.
    app_slug / app_name:
        Values returned by :func:`find_app_slug`.
    external_user_id:
        Unique identifier for the end-user in your system. If ``None`` we fall
        back to the *PIPEDREAM_EXTERNAL_USER_ID* environment variable or the
        hard-coded default ``"test-123"``.
    """
    project_id = "proj_1jsJW52"
    environment = "development"

    if external_user_id is None:
        external_user_id = os.getenv("PIPEDREAM_EXTERNAL_USER_ID", "test-123")

    return {
        "type": "mcp",
        "server_label": "pipedream",
        "server_url": MCP_SERVER_URL,
        "headers": {
            "Authorization": f"Bearer {access_token}",
            "x-pd-project-id": project_id,
            "x-pd-environment": environment,
            "x-pd-external-user-id": external_user_id,
            "x-pd-app-slug": app_slug,
        },
        "require_approval": "never",
    }


# ---------------------------------------------------------------------------
# 4) OPENAI RESPONSES INVOCATION
# ---------------------------------------------------------------------------

def call_openai_responses(
    prompt: str,
    model: str = DEFAULT_MODEL,
    tool_block: Optional[Dict[str, object]] = None,
    **client_kwargs,
) -> str:
    """Call the Responses endpoint and return the model's output text."""
    client = OpenAI(**client_kwargs)

    if tool_block is None:
        raise ValueError("tool_block must be provided to call the MCP server.")

    response_obj = client.responses.create(
        model=model,
        input=prompt,
        tools=[tool_block],
    )

    # The "output" attribute contains the assistant's final answer.
    return response_obj.output


# ---------------------------------------------------------------------------
# COMMAND-LINE INTERFACE FOR QUICK TESTING
# ---------------------------------------------------------------------------

def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Demo interaction with Pipedream via MCP tool (Python version)."
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        default=[
            "Summarize my most recently created Notion doc for me and help draft an email to our customers.",
        ],
        help="Prompt to send to the model.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="OpenAI model to use.",
    )
    parser.add_argument(
        "--app-query",
        default=DEFAULT_APP_QUERY,
        help="Search term for the Pipedream app (e.g. 'notion', 'gmail').",
    )
    parser.add_argument(
        "--external-user-id",
        default=None,
        help="Unique identifier for the end-user. Overrides PIPEDREAM_EXTERNAL_USER_ID.",
    )
    args = parser.parse_args()

    prompt = " ".join(args.prompt).strip()

    try:
        print("🔑  Obtaining Pipedream access token…", end=" ")
        access_token = get_pipedream_access_token()
        print("done! ✅")

        print(f"🔎  Searching for '{args.app_query}' app slug…", end=" ")
        app_slug, app_name = find_app_slug(access_token, query=args.app_query)
        print(f"found '{app_slug}' ({app_name}). ✅")

        tool_block = build_mcp_tool_block(
            access_token,
            app_slug,
            app_name,
            external_user_id=args.external_user_id,
        )

        print("🤖  Requesting model response…")
        output = call_openai_responses(prompt, model=args.model, tool_block=tool_block)
        print("\n===== MODEL OUTPUT =====\n")
        print(output)

    except MissingEnvError as env_err:
        print(f"Environment error: {env_err}")
    except Exception as exc:
        print(f"Unexpected error: {exc}")


if __name__ == "__main__":
    _cli()
