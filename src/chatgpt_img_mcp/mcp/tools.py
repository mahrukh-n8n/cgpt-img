"""MCP Tools for ChatGPT Image Generation."""

import functools
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from chatgpt_img_mcp.core.chatgpt import ChatGPTBrowser
from chatgpt_img_mcp.utils import (
    CDP_DEFAULT_PORT,
    CHATGPT_URL,
    close_ws,
    find_chatgpt_page,
    get_debugger_url,
    get_pages,
    launch_browser,
)

logger = logging.getLogger("chatgpt_img_mcp.tools")

mcp = FastMCP(name="chatgpt-img")

# Global state
_browser: ChatGPTBrowser | None = None
_browser_lock = threading.Lock()
_port = int(os.environ.get("CGPT_CDP_PORT", str(CDP_DEFAULT_PORT)))


def _get_browser() -> ChatGPTBrowser | None:
    global _browser
    return _browser


def _set_browser(browser: ChatGPTBrowser | None) -> None:
    global _browser
    _browser = browser


def _logged_tool():
    """Decorator for logging tool calls."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tool_name = func.__name__
            params = {k: v for k, v in kwargs.items() if v is not None}
            logger.info(f"MCP Tool: {tool_name}({json.dumps(params, default=str)[:200]})")
            try:
                result = func(*args, **kwargs)
                logger.info(f"MCP Tool: {tool_name} -> {str(result)[:200]}")
                return result
            except Exception as e:
                logger.error(f"MCP Tool: {tool_name} ERROR: {e}")
                return {"status": "error", "error": str(e)}

        return wrapper

    return decorator


def _ensure_browser() -> tuple[ChatGPTBrowser, bool]:
    """Ensure browser is connected and return (browser, was_created)."""
    global _browser, _port

    with _browser_lock:
        if _browser is not None:
            return _browser, False

        ws_url = get_debugger_url(_port)
        if not ws_url:
            process = launch_browser(_port)
            if not process:
                raise RuntimeError("Failed to launch browser")
            time.sleep(3)
            ws_url = get_debugger_url(_port)

        if not ws_url:
            raise RuntimeError("Failed to connect to browser")

        page = find_chatgpt_page(_port)
        if not page:
            from chatgpt_img_mcp.utils.cdp import navigate_to

            navigate_to(CHATGPT_URL, ws_url)
            time.sleep(3)
            page = find_chatgpt_page(_port)

        if not page:
            raise RuntimeError("Failed to find ChatGPT page")

        ws_url = page.get("webSocketDebuggerUrl")
        _browser = ChatGPTBrowser(ws_url, _port)
        return _browser, True


# === MCP Tools ===


@mcp.tool()
@_logged_tool()
def login(profile: str | None = None) -> dict[str, Any]:
    """Authenticate with ChatGPT by connecting to the browser.

    Args:
        profile: Optional Edge profile name (default: Mahrukh on Windows)

    Returns:
        Login status and browser connection info.
    """
    global _port

    profile_dir = None
    if profile and os.name == "nt":
        profile_dir = rf"C:\Users\{os.environ.get('USERNAME', 'User')}\AppData\Local\Microsoft\Edge\User Data\{profile}"

    with _browser_lock:
        process = launch_browser(_port, profile_dir)
        if not process:
            return {"status": "error", "error": "Failed to launch browser"}

        time.sleep(5)

        page = find_chatgpt_page(_port)
        if not page:
            return {"status": "error", "error": "ChatGPT page not found"}

        ws_url = page.get("webSocketDebuggerUrl")
        browser = ChatGPTBrowser(ws_url, _port)
        _set_browser(browser)

        if not browser.is_logged_in():
            return {
                "status": "login_required",
                "message": "Please log in to ChatGPT in the browser window. Call login() again once done.",
                "instructions": "1. Log in to ChatGPT in the browser\n2. Call login() again or use get_status() to check",
            }

        return {
            "status": "success",
            "message": "Connected to ChatGPT",
            "logged_in": True,
        }


@mcp.tool()
@_logged_tool()
def get_status() -> dict[str, Any]:
    """Check the current status of the ChatGPT MCP connection.

    Returns:
        Connection status, login status, and browser info.
    """
    global _port

    try:
        browser = _get_browser()

        if browser is None:
            ws_url = get_debugger_url(_port)
            if ws_url:
                page = find_chatgpt_page(_port)
                if page:
                    ws_url = page.get("webSocketDebuggerUrl")
                    browser = ChatGPTBrowser(ws_url, _port)
                    _set_browser(browser)

        if browser is None:
            return {
                "status": "disconnected",
                "logged_in": None,
                "message": "Not connected to browser",
            }

        logged_in = browser.is_logged_in()
        return {
            "status": "connected",
            "logged_in": logged_in,
            "message": "Connected to ChatGPT" if logged_in else "Connected but not logged in",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
@_logged_tool()
def chat_send(message: str, wait_for_response: bool = True, timeout: int = 60) -> dict[str, Any]:
    """Send a text message to ChatGPT and get the response.

    Args:
        message: The message to send
        wait_for_response: Wait for ChatGPT response (default: True)
        timeout: Timeout in seconds for response (default: 60)

    Returns:
        Response from ChatGPT or status.
    """
    try:
        browser, _ = _ensure_browser()
    except RuntimeError as e:
        return {"status": "error", "error": str(e)}

    if not browser.is_logged_in():
        return {"status": "error", "error": "Not logged in. Call login() first."}

    result = browser.send_message(message, wait_for_response, timeout)
    return result


@mcp.tool()
@_logged_tool()
def generate_image(
    prompt: str,
    reference_images: list[str] | None = None,
    reference_urls: list[str] | None = None,
    model: str | None = None,
    wait_timeout: int = 120,
) -> dict[str, Any]:
    """Generate an image using ChatGPT.

    Args:
        prompt: The image generation prompt
        reference_images: Local file paths of reference images
        reference_urls: URLs of reference images
        model: Optional model to select (e.g., "DALL-E", "GPT-4o")
        wait_timeout: Timeout in seconds (default: 120)

    Returns:
        Generated image info or status.
    """
    try:
        browser, _ = _ensure_browser()
    except RuntimeError as e:
        return {"status": "error", "error": str(e)}

    if not browser.is_logged_in():
        return {"status": "error", "error": "Not logged in. Call login() first."}

    if model:
        browser.select_model(model)
        time.sleep(0.5)

    if reference_images:
        for img_path in reference_images:
            if Path(img_path).exists():
                browser.upload_file(img_path)
                time.sleep(1)

    full_prompt = prompt
    if reference_urls:
        full_prompt = f"{prompt}\n\nPlease look at these reference images: {', '.join(reference_urls)}"

    result = browser.send_message(full_prompt, wait_for_response=True, timeout=wait_timeout)

    if result.get("status") == "error":
        return result

    # Wait for images to appear
    for _attempt in range(30):
        time.sleep(2)
        images = browser.find_generated_images()
        if images:
            return {
                "status": "success",
                "response": result.get("response", ""),
                "images": [{"src": img["src"], "width": img["width"], "height": img["height"]} for img in images],
                "images_count": len(images),
            }

    return {
        "status": "success",
        "response": result.get("response", ""),
        "message": "Response received. Image may be loading.",
    }


@mcp.tool()
@_logged_tool()
def upload_file(file_path: str) -> dict[str, Any]:
    """Upload a file (image or document) to ChatGPT.

    Args:
        file_path: Path to the file to upload

    Returns:
        Upload status.
    """
    try:
        browser, _ = _ensure_browser()
    except RuntimeError as e:
        return {"status": "error", "error": str(e)}

    if not browser.is_logged_in():
        return {"status": "error", "error": "Not logged in. Call login() first."}

    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "error": f"File not found: {file_path}"}

    success = browser.upload_file(str(path))
    if success:
        return {"status": "success", "file": file_path, "message": "File uploaded"}
    return {"status": "error", "error": "Failed to upload file"}


@mcp.tool()
@_logged_tool()
def model_select(model_name: str) -> dict[str, Any]:
    """Select a ChatGPT model.

    Args:
        model_name: Model name (e.g., "GPT-4o", "DALL-E 3", "o3")

    Returns:
        Selection status.
    """
    try:
        browser, _ = _ensure_browser()
    except RuntimeError as e:
        return {"status": "error", "error": str(e)}

    if not browser.is_logged_in():
        return {"status": "error", "error": "Not logged in. Call login() first."}

    success = browser.select_model(model_name)
    if success:
        return {"status": "success", "model": model_name}
    return {"status": "error", "error": f"Failed to select model: {model_name}"}


@mcp.tool()
@_logged_tool()
def conversations_list() -> dict[str, Any]:
    """List recent ChatGPT conversations.

    Returns:
        List of conversations.
    """
    try:
        browser, _ = _ensure_browser()
    except RuntimeError as e:
        return {"status": "error", "error": str(e)}

    if not browser.is_logged_in():
        return {"status": "error", "error": "Not logged in. Call login() first."}

    conversations = browser.get_conversations()
    return {"status": "success", "conversations": conversations, "count": len(conversations)}


@mcp.tool()
@_logged_tool()
def chat_switch(conversation_title: str) -> dict[str, Any]:
    """Switch to a conversation.

    Args:
        conversation_title: Title or partial title of conversation to switch to

    Returns:
        Switch status.
    """
    try:
        browser, _ = _ensure_browser()
    except RuntimeError as e:
        return {"status": "error", "error": str(e)}

    if not browser.is_logged_in():
        return {"status": "error", "error": "Not logged in. Call login() first."}

    success = browser.switch_conversation(conversation_title)
    if success:
        return {"status": "success", "conversation": conversation_title}
    return {"status": "error", "error": f"Conversation not found: {conversation_title}"}


@mcp.tool()
@_logged_tool()
def chat_new() -> dict[str, Any]:
    """Start a new chat conversation.

    Returns:
        Status.
    """
    try:
        browser, _ = _ensure_browser()
    except RuntimeError as e:
        return {"status": "error", "error": str(e)}

    if not browser.is_logged_in():
        return {"status": "error", "error": "Not logged in. Call login() first."}

    success = browser.new_chat()
    if success:
        return {"status": "success", "message": "New chat started"}
    return {"status": "error", "error": "Failed to start new chat"}


@mcp.tool()
@_logged_tool()
def download_image(image_index: int = 0) -> dict[str, Any]:
    """Download an image from the current chat.

    This opens the image in zoom view and clicks the download button.

    Args:
        image_index: Index of the image to download (default: 0 for first image)

    Returns:
        Download status.
    """
    try:
        browser, _ = _ensure_browser()
    except RuntimeError as e:
        return {"status": "error", "error": str(e)}

    if not browser.is_logged_in():
        return {"status": "error", "error": "Not logged in. Call login() first."}

    images = browser.find_generated_images()
    if not images:
        return {"status": "error", "error": "No generated images found in current chat"}

    if image_index >= len(images):
        return {"status": "error", "error": f"Image index {image_index} out of range (found {len(images)} images)"}

    if not browser.click_image_to_zoom():
        return {"status": "error", "error": "Failed to click image"}

    time.sleep(2)

    if not browser.click_download_button():
        browser.close_zoom()
        return {"status": "error", "error": "Failed to find download button"}

    time.sleep(1)
    browser.close_zoom()

    return {
        "status": "success",
        "message": "Image download triggered",
        "image": images[image_index],
    }


@mcp.tool()
@_logged_tool()
def chat_history(conversation_title: str | None = None) -> dict[str, Any]:
    """Get history of a conversation or all recent conversations.

    Args:
        conversation_title: Optional - specific conversation to get history for

    Returns:
        Chat history or conversation list.
    """
    try:
        browser, _ = _ensure_browser()
    except RuntimeError as e:
        return {"status": "error", "error": str(e)}

    if not browser.is_logged_in():
        return {"status": "error", "error": "Not logged in. Call login() first."}

    if conversation_title:
        browser.switch_conversation(conversation_title)
        time.sleep(1)

    from chatgpt_img_mcp.utils.cdp import get_page_text

    global _browser
    if _browser:
        text = get_page_text(_browser.ws_url)
        return {"status": "success", "history": text[:5000], "conversation": conversation_title}

    return {"status": "error", "error": "Browser not connected"}