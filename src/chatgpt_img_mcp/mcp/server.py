"""MCP Server for ChatGPT Image Generation."""

import functools
import logging
import os
import threading
from typing import Any

from chatgpt_img_mcp import __version__
# Import the shared FastMCP instance that all @mcp.tool() decorators registered against.
# Importing tools has the side effect of registering them on this instance.
from chatgpt_img_mcp.mcp.tools import mcp  # noqa: F401

mcp.instructions = """ChatGPT Image MCP - Generate images via ChatGPT web interface.

**Auth:** Run `cgpt login` first, or the server will attempt to connect to your existing Edge/Chrome with ChatGPT open.

**Tools:**
- `chat_send`: Send a text message and get response
- `generate_image`: Generate an image (upload optional reference images)
- `upload_file`: Upload a file to ChatGPT
- `model_select`: Select a model (GPT-4o, DALL-E, etc.)
- `conversations_list`: List recent conversations
- `chat_switch`: Switch to a conversation
- `chat_new`: Start a new conversation
- `chat_history`: Get chat history
- `download_image`: Download a generated image
- `login`: Authenticate with ChatGPT
- `get_status`: Check connection status
"""

logger = logging.getLogger("chatgpt_img_mcp.mcp")


def main():
    """Run the MCP server."""
    import argparse

    parser = argparse.ArgumentParser(description="ChatGPT Image MCP Server")
    parser.add_argument(
        "--transport",
        "-t",
        choices=["stdio", "http", "sse"],
        default=os.environ.get("CGPT_MCP_TRANSPORT", "stdio"),
        help="Transport protocol",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=int(os.environ.get("CGPT_MCP_PORT", "8000")),
        help="Port for HTTP/SSE",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.environ.get("CGPT_DEBUG", "").lower() == "true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    if args.transport == "stdio":
        mcp.run(show_banner=False)
    elif args.transport == "http":
        mcp.run(transport="streamable-http", host="127.0.0.1", port=args.port, show_banner=False)
    elif args.transport == "sse":
        mcp.run(transport="sse", host="127.0.0.1", port=args.port, show_banner=False)


if __name__ == "__main__":
    main()
