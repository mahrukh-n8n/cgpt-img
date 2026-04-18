"""Chrome DevTools Protocol utilities for ChatGPT MCP."""

import contextlib
import json
import logging
import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import websocket

logger = logging.getLogger(__name__)

CDP_DEFAULT_PORT = 9225
CDP_PORT_RANGE = range(9225, 9235)
CHATGPT_URL = "https://chatgpt.com/"

_cached_ws: websocket.WebSocket | None = None
_cached_ws_url: str | None = None


def _normalize_ws_url(url: str | None) -> str | None:
    """Normalize WebSocket URLs to use 127.0.0.1 instead of localhost."""
    if url and "://localhost:" in url:
        return url.replace("://localhost:", "://127.0.0.1:")
    return url


def get_storage_dir() -> Path:
    """Get the storage directory for auth and config."""
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "chatgpt-img-mcp"


def get_browser_path() -> str | None:
    """Find Edge or Chrome browser path."""
    if platform.system() == "Windows":
        paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Users\{}\AppData\Local\Microsoft\Edge\Application\msedge.exe".format(os.environ.get("USERNAME", "User")),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for path in paths:
            if Path(path).exists():
                return path
    elif platform.system() == "Darwin":
        candidates = ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
        for path in candidates:
            if Path(path).exists():
                return path
    return None


def find_available_port(starting_from: int = 9225, max_attempts: int = 10) -> int:
    """Find an available port."""
    for offset in range(max_attempts):
        port = starting_from + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No available ports in range {starting_from}-{starting_from + max_attempts - 1}")


def get_debugger_url(port: int = CDP_DEFAULT_PORT) -> str | None:
    """Get the WebSocket debugger URL for Chrome/Edge."""
    try:
        response = httpx.get(f"http://localhost:{port}/json/version", timeout=10)
        data = response.json()
        return _normalize_ws_url(data.get("webSocketDebuggerUrl"))
    except Exception:
        return None


def get_pages(port: int = CDP_DEFAULT_PORT) -> list[dict]:
    """Get all browser pages."""
    try:
        response = httpx.get(f"http://localhost:{port}/json", timeout=10)
        return response.json()
    except Exception:
        return []


def find_chatgpt_page(port: int = CDP_DEFAULT_PORT) -> dict | None:
    """Find the ChatGPT page in the browser."""
    pages = get_pages(port)
    for page in pages:
        if "chatgpt.com" in page.get("url", ""):
            return page
    return None


def launch_browser(port: int = CDP_DEFAULT_PORT, profile_dir: str | None = None) -> subprocess.Popen | None:
    """Launch Edge/Chrome with remote debugging."""
    browser_path = get_browser_path()
    if not browser_path:
        logger.error("No supported browser found")
        return None

    if profile_dir is None:
        profile_dir = str(get_storage_dir() / "browser-profile")
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    args = [
        browser_path,
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile_dir}",
    ]

    try:
        return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        logger.error(f"Failed to launch browser: {e}")
        return None


def execute_cdp_command(ws_url: str, method: str, params: dict | None = None) -> dict:
    """Execute a CDP command via WebSocket."""
    global _cached_ws, _cached_ws_url

    if ws_url != _cached_ws_url or not _cached_ws:
        if _cached_ws:
            with contextlib.suppress(Exception):
                _cached_ws.close()
        try:
            _cached_ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
            _cached_ws_url = ws_url
        except Exception as e:
            logger.error(f"Failed to connect to CDP: {e}")
            raise

    ws = _cached_ws
    command = {"id": 1, "method": method, "params": params or {}}
    ws.send(json.dumps(command))

    while True:
        try:
            response = json.loads(ws.recv())
            if response.get("id") == 1:
                return response.get("result", {})
        except Exception:
            continue


def navigate_to(url: str, ws_url: str) -> None:
    """Navigate to a URL."""
    execute_cdp_command(ws_url, "Page.enable")
    execute_cdp_command(ws_url, "Page.navigate", {"url": url})
    time.sleep(2)


def get_page_html(ws_url: str) -> str:
    """Get page HTML."""
    execute_cdp_command(ws_url, "Runtime.enable")
    result = execute_cdp_command(ws_url, "Runtime.evaluate", {"expression": "document.documentElement.outerHTML"})
    return result.get("result", {}).get("value", "")


def get_page_text(ws_url: str) -> str:
    """Get page inner text."""
    result = execute_cdp_command(ws_url, "Runtime.evaluate", {"expression": "document.body ? document.body.innerText : ''"})
    return result.get("result", {}).get("value", "")


def evaluate_js(ws_url: str, script: str, timeout: int = 30, await_promise: bool = False) -> Any:
    """Execute JavaScript and return result. Set await_promise=True to resolve Promises."""
    params: dict[str, Any] = {"expression": script, "returnByValue": True}
    if await_promise:
        params["awaitPromise"] = True
    result = execute_cdp_command(ws_url, "Runtime.evaluate", params)
    nested = result.get("result", {})
    return nested.get("value")


def insert_text(ws_url: str, text: str, char_delay: float = 0.01) -> bool:
    """Insert text into the focused element using CDP Input.insertText.

    Newlines are translated to Shift+Enter key events so ProseMirror (ChatGPT's
    editor) renders soft line breaks instead of swallowing raw "\\n" characters
    and leaving the send button disabled.
    """
    import time
    try:
        ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
        ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
        try:
            ws.settimeout(1)
            ws.recv()
        except Exception:
            pass

        def _send(payload: dict) -> None:
            ws.send(json.dumps(payload))
            try:
                ws.settimeout(0.5)
                ws.recv()
            except Exception:
                pass

        segments = text.split("\n")
        for seg_idx, segment in enumerate(segments):
            if seg_idx > 0:
                # Shift+Enter → soft line break in ProseMirror
                shift_modifier = 8
                for event_type in ("keyDown", "keyUp"):
                    _send({
                        "id": 3,
                        "method": "Input.dispatchKeyEvent",
                        "params": {
                            "type": event_type,
                            "modifiers": shift_modifier,
                            "key": "Enter",
                            "code": "Enter",
                            "windowsVirtualKeyCode": 13,
                            "nativeVirtualKeyCode": 13,
                        },
                    })
                time.sleep(char_delay)

            for char in segment:
                _send({"id": 2, "method": "Input.insertText", "params": {"text": char}})
                time.sleep(char_delay)

        ws.close()
        return True
    except Exception as e:
        logger.error(f"Failed to insert text: {e}")
        return False


def click_element(ws_url: str, selector: str) -> bool:
    """Click an element by selector."""
    script = f"""
    (function() {{
        const el = document.querySelector('{selector}');
        if (el) {{
            el.click();
            return true;
        }}
        return false;
    }})()
    """
    return evaluate_js(ws_url, script) is True


def find_element(ws_url: str, selector: str) -> dict | None:
    """Find an element and return its info."""
    script = f"""
    (function() {{
        const el = document.querySelector('{selector}');
        if (!el) return null;
        const rect = el.getBoundingClientRect();
        return {{
            found: true,
            tagName: el.tagName,
            className: el.className,
            id: el.id,
            placeholder: el.placeholder || el.getAttribute('placeholder'),
            ariaLabel: el.getAttribute('aria-label'),
            dataTestid: el.getAttribute('data-testid'),
            disabled: el.disabled,
            rect: {{ w: rect.width, h: rect.height, x: rect.left, y: rect.top }}
        }};
    }})()
    """
    result = evaluate_js(ws_url, script)
    if result and result != "null":
        try:
            return json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            return {"found": True, "raw": str(result)}
    return None


def set_input_value(ws_url: str, selector: str, value: str) -> bool:
    """Set value of an input/textarea."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n")
    script = f"""
    (function() {{
        const el = document.querySelector('{selector}');
        if (!el) return false;

        if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {{
            el.value = '{escaped}';
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }} else {{
            el.textContent = '{escaped}';
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
        return true;
    }})()
    """
    return evaluate_js(ws_url, script) is True


def type_text(ws_url: str, selector: str, text: str) -> bool:
    """Type text into an element (simulates keyboard typing)."""
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    script = f"""
    (function() {{
        const el = document.querySelector('{selector}');
        if (!el) return false;
        el.focus();

        // Clear existing content
        if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {{
            el.value = '';
        }} else {{
            el.textContent = '';
        }}

        // Type character by character
        const chars = '{escaped}'.split('');
        for (const char of chars) {{
            const event = new InputEvent('input', {{
                bubbles: true,
                inputType: 'insertText',
                data: char
            }});
            if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {{
                el.value += char;
            }} else {{
                el.textContent += char;
            }}
            el.dispatchEvent(event);
        }}
        return true;
    }})()
    """
    return evaluate_js(ws_url, script) is True


def upload_file(ws_url: str, selector: str, file_path: str) -> bool:
    """Upload a file to an input element."""
    file_path_escaped = file_path.replace("\\", "\\\\").replace("'", "\\'")
    script = f"""
    (function() {{
        const input = document.querySelector('{selector}');
        if (!input || input.tagName !== 'INPUT' || input.type !== 'file') return false;

        const dt = new DataTransfer();
        dt.items.add(new File([new ArrayBuffer(0)], '{file_path_escaped.split('/').pop().split('\\\\').pop()}', {{}}));
        input.files = dt.files;
        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return true;
    }})()
    """
    return evaluate_js(ws_url, script) is True


def wait_for_element(ws_url: str, selector: str, timeout: int = 30) -> bool:
    """Wait for an element to appear."""
    start = time.time()
    while time.time() - start < timeout:
        result = find_element(ws_url, selector)
        if result and result.get("found"):
            return True
        time.sleep(0.5)
    return False


def wait_for_text(ws_url: str, text: str, timeout: int = 30) -> bool:
    """Wait for text to appear on page."""
    start = time.time()
    while time.time() - start < timeout:
        page_text = get_page_text(ws_url)
        if text.lower() in page_text.lower():
            return True
        time.sleep(0.5)
    return False


def get_cookies(ws_url: str) -> list[dict]:
    """Get all cookies from the page."""
    result = execute_cdp_command(ws_url, "Network.getAllCookies")
    return result.get("cookies", [])


def close_ws() -> None:
    """Close the WebSocket connection."""
    global _cached_ws, _cached_ws_url
    if _cached_ws:
        with contextlib.suppress(Exception):
            _cached_ws.close()
    _cached_ws = None
    _cached_ws_url = None
