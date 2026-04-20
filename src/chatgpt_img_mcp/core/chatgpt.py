"""ChatGPT browser controller using CDP."""

import json
import logging
import time
from pathlib import Path
from typing import Any

from chatgpt_img_mcp.utils import cdp

logger = logging.getLogger(__name__)

# DOM selectors for ChatGPT (verified working)
SELECTOR_CHAT_INPUT = "#prompt-textarea"
SELECTOR_SEND_BUTTON = "[data-testid=send-button]"
SELECTOR_FILE_UPLOAD = "[data-testid=composer-plus-btn]"
SELECTOR_LOGIN_AREA = "#prompt-textarea"


class ChatGPTBrowser:
    """Controller for ChatGPT web interface via CDP."""

    def __init__(self, ws_url: str, port: int = 9225):
        self.ws_url = ws_url
        self.port = port
        self._logged_in = None

    def _evaluate(self, script: str, timeout: int = 30, await_promise: bool = False) -> Any:
        """Execute JavaScript and return result."""
        return cdp.evaluate_js(self.ws_url, script, timeout, await_promise=await_promise)

    def _insert_text(self, text: str) -> bool:
        """Insert text using CDP Input.insertText command."""
        return cdp.insert_text(self.ws_url, text)

    def _click(self, selector: str) -> bool:
        """Click an element by selector."""
        script = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (el && !el.disabled) {{
                el.click();
                return true;
            }}
            return false;
        }})()
        """
        return self._evaluate(script) is True

    def _wait(self, seconds: float) -> None:
        """Wait for a specified time."""
        time.sleep(seconds)

    def is_logged_in(self) -> bool:
        """Check if user is logged in to ChatGPT. Only caches positive results."""
        if self._logged_in is True:
            return True

        result = self._evaluate("""
        (function() {
            if (document.querySelector('#prompt-textarea')) return true;
            var text = document.body ? document.body.innerText : '';
            return text.includes('Chat history') && text.includes('New chat');
        })()
        """)
        logged_in = result is True
        if logged_in:
            self._logged_in = True
        logger.info(f"Login status: {logged_in}")
        return logged_in

    def wait_for_login(self, timeout: int = 120) -> bool:
        """Wait for user to log in."""
        start = time.time()
        while time.time() - start < timeout:
            if self.is_logged_in():
                return True
            time.sleep(2)
        return False

    def close_sidebar(self) -> bool:
        """Close the sidebar if open."""
        script = """
        (function() {
            var btn = document.querySelector("[data-testid=close-sidebar-button]");
            if (btn) {
                btn.click();
                return true;
            }
            return false;
        })()
        """
        return self._evaluate(script) is True

    def ensure_main_view(self) -> bool:
        """Ensure we're in the main chat view (sidebar closed)."""
        self.close_sidebar()
        self._wait(0.5)
        return True

    def type_message(self, message: str) -> bool:
        """Type a message into the chat input using CDP Input.insertText."""
        # Focus the input first
        self._evaluate("""
        (function() {
            var inp = document.querySelector("#prompt-textarea");
            if (inp) {
                inp.focus();
                return true;
            }
            return false;
        })()
        """)
        self._wait(0.2)

        # Use CDP Input.insertText for reliable typing
        return self._insert_text(message)

    def click_send(self, retries: int = 10, wait: float = 0.3) -> bool:
        """Click the send button, retrying while it's disabled (debounce)."""
        script = """
        (function() {
            var btn = document.querySelector("[data-testid=send-button]");
            if (btn && !btn.disabled) {
                btn.click();
                return true;
            }
            return false;
        })()
        """
        for _ in range(retries):
            if self._evaluate(script) is True:
                return True
            self._wait(wait)
        return False

    def send_message(self, message: str, wait_for_response: bool = True, timeout: int = 60) -> dict[str, Any]:
        """Send a message and optionally wait for response."""
        self.ensure_main_view()
        self._wait(0.5)

        # Clear and type the message
        self._evaluate("""
        (function() {
            var inp = document.querySelector("#prompt-textarea");
            if (inp) {
                inp.textContent = "";
                inp.innerHTML = "";
            }
        })()
        """)
        self._wait(0.2)

        if not self.type_message(message):
            return {"status": "error", "error": "Failed to type message"}

        self._wait(0.5)

        # Click send
        if not self.click_send():
            return {"status": "error", "error": "Failed to click send button"}

        if not wait_for_response:
            return {"status": "sent"}

        # Wait for response
        return self.wait_for_response(timeout)

    def _extract_response_text_js(self) -> str:
        """JavaScript that extracts assistant response text from React fiber state.

        ChatGPT renders assistant text via React virtual DOM — the <p> tags
        have data-start/data-end attrs but empty innerHTML. The actual text
        lives in the message object's content.parts array, reachable by
        walking up the React fiber tree from .text-message.
        """
        return """
        (function() {
            var turns = document.querySelectorAll('[data-testid^="conversation-turn-"]');
            if (turns.length < 2) return '';
            var last = turns[turns.length - 1];
            var textMsg = last.querySelector('.text-message');
            if (!textMsg) return '';
            var fiberKey = Object.keys(textMsg).find(k => k.startsWith('__reactFiber'));
            if (!fiberKey) return '';

            var current = textMsg[fiberKey];
            for (var depth = 0; depth < 50 && current; depth++) {
                var props = current.memoizedProps || current.pendingProps;
                if (props && props.message) {
                    var msg = props.message;
                    if (msg.content && msg.content.parts) {
                        return msg.content.parts.join('');
                    }
                }
                current = current.return;
            }
            return '';
        })()
        """

    def wait_for_response(self, timeout: int = 60) -> dict[str, Any]:
        """Wait for ChatGPT response to appear.

        Extracts assistant response text from React fiber state (not DOM
        innerText, which is empty for assistant turns). Also detects
        images via estuary src or image containers.
        """
        import time as time_module

        start = time.time()
        last_text = ""
        saw_turn = False

        while time.time() - start < timeout:
            result = self._evaluate("""
            (function() {
                var turns = document.querySelectorAll('[data-testid^="conversation-turn-"]');
                if (turns.length < 2) return null;

                var last = turns[turns.length - 1];
                var busy = last.querySelector('[aria-busy=true]');

                // Extract text from React fiber state (DOM innerText is empty for assistant turns)
                var textMsg = last.querySelector('.text-message');
                var fiberText = '';
                if (textMsg) {
                    var fiberKey = Object.keys(textMsg).find(k => k.startsWith('__reactFiber'));
                    if (fiberKey) {
                        var current = textMsg[fiberKey];
                        for (var depth = 0; depth < 50 && current; depth++) {
                            var props = current.memoizedProps || current.pendingProps;
                            if (props && props.message) {
                                var msg = props.message;
                                if (msg.content && msg.content.parts) {
                                    fiberText = msg.content.parts.join('');
                                }
                                break;
                            }
                            current = current.return;
                        }
                    }
                }

                // Check for visible estuary images
                var imgs = last.querySelectorAll('img[src*="estuary"]');
                var hasLargeImage = false;
                for (var i = 0; i < imgs.length; i++) {
                    var rect = imgs[i].getBoundingClientRect();
                    if (rect.width > 30) { hasLargeImage = true; break; }
                }
                var imgContainers = last.querySelectorAll('[id^="image-"]');
                if (imgContainers.length > 0) hasLargeImage = true;

                var hasContent = fiberText.length > 0 || hasLargeImage;

                // Detect transient states: "Analyzing" or "Analysis paused"
                // These appear with aria-busy=false but image is not ready yet.
                var allText = last.innerText || '';
                var isAnalyzing = /analyzing/i.test(allText) && !hasLargeImage;
                var isPaused = /analysis paused/i.test(allText) && !hasLargeImage;

                var done = !busy && hasContent && !isAnalyzing && !isPaused;

                return JSON.stringify({
                    done: done,
                    text: fiberText.substring(0, 500),
                    textLength: fiberText.length,
                    hasImages: hasLargeImage,
                    imgCount: imgs.length,
                    numTurns: turns.length,
                    busy: !!busy,
                    isAnalyzing: isAnalyzing,
                    isPaused: isPaused
                });
            })()
            """)
            if result:
                try:
                    data = json.loads(result) if isinstance(result, str) else result
                    if data.get("numTurns", 0) >= 2:
                        saw_turn = True
                    if data.get("done") and saw_turn:
                        return {
                            "status": "success",
                            "response": data.get("text", ""),
                            "length": data.get("textLength", 0),
                            "has_images": data.get("hasImages", False),
                        }
                    if data.get("text"):
                        last_text = data.get("text", "")
                except (json.JSONDecodeError, TypeError):
                    pass

            time_module.sleep(0.5)

        return {
            "status": "timeout",
            "partial": last_text[:500] if last_text else "",
        }

    def get_response_text(self) -> str:
        """Get the latest response text from React fiber state.

        ChatGPT assistant responses aren't in DOM innerText — they're
        stored in the React fiber message.content.parts array.
        """
        result = self._evaluate(self._extract_response_text_js())
        return result or ""

    def select_model(self, model_name: str) -> bool:
        """Select a model from the dropdown."""
        # Click model selector
        script = f"""
        (function() {{
            var btn = document.querySelector("[data-testid=model-switcher-dropdown-button]");
            if (btn) {{
                btn.click();
                return true;
            }}
            return false;
        }})()
        """
        if not self._evaluate(script):
            return False

        self._wait(0.5)

        # Find and click the model option
        escaped = model_name.replace("'", "\\'")
        lower_escaped = escaped.lower()
        script = f"""
        (function() {{
            var options = document.querySelectorAll("[role=menuitem]");
            for (var i = 0; i < options.length; i++) {{
                if (options[i].textContent.toLowerCase().includes('{lower_escaped}')) {{
                    options[i].click();
                    return true;
                }}
            }}
            return false;
        }})()
        """
        return self._evaluate(script) is True

    def upload_file(self, file_path: str) -> bool:
        """Upload a file with real bytes via the page's file input."""
        import base64
        import mimetypes

        path = Path(file_path).resolve()
        if not path.exists():
            logger.error(f"File not found: {path}")
            return False

        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        escaped_name = path.name.replace("\\", "\\\\").replace("'", "\\'")

        script = f"""
        (function() {{
            var input = document.querySelector('input[type="file"]');
            if (!input) return "no-input";

            var b64 = "{b64}";
            var bin = atob(b64);
            var len = bin.length;
            var bytes = new Uint8Array(len);
            for (var i = 0; i < len; i++) bytes[i] = bin.charCodeAt(i);

            var file = new File([bytes], '{escaped_name}', {{type: '{mime}'}});
            var dt = new DataTransfer();
            dt.items.add(file);
            input.files = dt.files;
            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return "uploaded";
        }})()
        """
        result = self._evaluate(script, timeout=60)
        return result == "uploaded"

    def find_generated_images(self) -> list[dict]:
        """Find generated images (DALL-E/estuary) in the chat."""
        result = self._evaluate("""
        (function() {
            var imgs = document.querySelectorAll("img[src*='estuary']");
            var images = [];
            var seen = {};
            for (var i = 0; i < imgs.length; i++) {
                var img = imgs[i];
                var r = img.getBoundingClientRect();
                // Skip tiny thumbnails and duplicates
                if (r.width < 30) continue;
                var key = img.src;
                if (seen[key]) continue;
                seen[key] = true;
                images.push({
                    src: img.src,
                    width: parseInt(img.getAttribute('width')) || Math.round(r.width),
                    height: parseInt(img.getAttribute('height')) || Math.round(r.height)
                });
            }
            return JSON.stringify(images);
        })()
        """)
        if result:
            try:
                return json.loads(result) if isinstance(result, str) else result
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    def click_image_to_zoom(self, image_index: int = 0) -> bool:
        """Click on a generated image to open the zoom/lightbox view."""
        script = f"""
        (function() {{
            var idx = {image_index};
            // Try clicking the imagegen container (role=button)
            var containers = document.querySelectorAll('[id^="image-"]');
            var clicked = 0;
            for (var i = 0; i < containers.length; i++) {{
                var btn = containers[i].querySelector('[role=button]');
                if (btn) {{
                    if (clicked === idx) {{ btn.click(); return true; }}
                    clicked++;
                }}
            }}
            // Fallback: click large estuary images directly
            var imgs = document.querySelectorAll("img[src*='estuary']");
            var seen = 0;
            for (var i = 0; i < imgs.length; i++) {{
                var r = imgs[i].getBoundingClientRect();
                if (r.width > 100) {{
                    if (seen === idx) {{ imgs[i].click(); return true; }}
                    seen++;
                }}
            }}
            return false;
        }})()
        """
        return self._evaluate(script) is True

    def click_download_button(self) -> bool:
        """Click the download/save button in the zoom view."""
        script = """
        (function() {
            // Find dialog/overlay
            var dialog = document.querySelector("[role=dialog]");
            if (!dialog) {
                // Try finding a fixed-position overlay with buttons
                var allFixed = document.querySelectorAll('*');
                for (var i = 0; i < allFixed.length; i++) {
                    var s = window.getComputedStyle(allFixed[i]);
                    if (s.position === 'fixed' && parseInt(s.zIndex) > 100) {
                        dialog = allFixed[i];
                        break;
                    }
                }
            }
            if (!dialog) return false;

            // Try Save/Download button by aria-label
            var labels = ['Save', 'Download', 'Download image'];
            for (var l = 0; l < labels.length; l++) {
                var btn = dialog.querySelector("button[aria-label='" + labels[l] + "']");
                if (btn) { btn.click(); return true; }
            }

            // Try by icon/text content
            var btns = dialog.querySelectorAll("button");
            for (var i = 0; i < btns.length; i++) {
                var text = (btns[i].innerText || '').toLowerCase();
                var ariaLabel = (btns[i].getAttribute('aria-label') || '').toLowerCase();
                if (text.includes('save') || text.includes('download') ||
                    ariaLabel.includes('save') || ariaLabel.includes('download')) {
                    btns[i].click();
                    return true;
                }
            }
            return false;
        })()
        """
        return self._evaluate(script) is True

    def close_zoom(self) -> bool:
        """Close the zoom/lightbox view."""
        self._evaluate("""
        document.dispatchEvent(new KeyboardEvent("keydown", {
            key: "Escape",
            code: "Escape",
            bubbles: true
        }))
        """)
        self._wait(0.5)
        return True

    def generate_image(self, prompt: str, wait_for: int = 120) -> dict[str, Any]:
        """Generate an image using ChatGPT."""
        self.ensure_main_view()
        self._wait(0.5)

        # Snapshot existing images so we can detect only NEW ones
        existing_srcs = {img["src"] for img in self.find_generated_images()}

        # Send the image generation prompt
        result = self.send_message(prompt, wait_for_response=True, timeout=wait_for)
        if result.get("status") == "error":
            return result

        # Wait for NEW images (not present before the prompt) to appear.
        # Use a longer timeout to account for "Analyzing" and "Analysis paused" states.
        start = time.time()
        while time.time() - start < 180:
            all_images = self.find_generated_images()
            new_images = [img for img in all_images if img["src"] not in existing_srcs]
            if new_images:
                return {
                    "status": "success",
                    "response": result.get("response", ""),
                    "images": new_images,
                    "count": len(new_images),
                }
            time.sleep(1)

        return {
            "status": "timeout",
            "response": result.get("response", ""),
            "images": [],
            "count": 0,
        }

    def new_chat(self) -> bool:
        """Start a new chat. Tries the sidebar button, then falls back to navigating to the root URL."""
        script = """
        (function() {
            var selectors = [
                '[data-testid=\"new-chat-button\"]',
                '[data-testid=\"create-new-chat-button\"]',
                'a[href=\"/\"]',
            ];
            for (var i = 0; i < selectors.length; i++) {
                var el = document.querySelector(selectors[i]);
                if (el) { el.click(); return true; }
            }
            return false;
        })()
        """
        if self._evaluate(script) is True:
            self._wait(1.0)
            # Verify the URL actually changed to a fresh chat (no /c/<id>)
            href = self._evaluate("window.location.pathname") or ""
            if not str(href).startswith("/c/"):
                return True

        # Fallback: navigate directly
        from chatgpt_img_mcp.utils.cdp import navigate_to
        navigate_to("https://chatgpt.com/", self.ws_url)
        self._wait(2.0)
        # Verify page loaded with an input ready
        ok = self._evaluate("!!document.querySelector('#prompt-textarea')")
        return ok is True

    def get_conversations(self) -> list[dict[str, Any]]:
        """Get list of conversations from sidebar.

        Each history row is an <li> containing an <a> (the link) and a
        "history-item-N-options" button. The button has empty innerText, so we
        must walk up to the <li> to get the actual conversation title.
        """
        result = self._evaluate("""
        (function() {
            var buttons = document.querySelectorAll("[data-testid^='history-item-']");
            var convos = [];
            var seen = {};
            for (var i = 0; i < buttons.length; i++) {
                var li = buttons[i].closest('li') || buttons[i].parentElement;
                if (!li) continue;
                var link = li.querySelector('a[href*="/c/"]');
                var title = (link ? link.innerText : li.innerText || '').trim();
                if (!title || title === 'New chat') continue;
                if (seen[title]) continue;
                seen[title] = true;
                convos.push({
                    title: title.substring(0, 100),
                    href: link ? link.getAttribute('href') : null,
                    testid: buttons[i].getAttribute('data-testid')
                });
            }
            return JSON.stringify(convos);
        })()
        """)
        if result:
            try:
                return json.loads(result) if isinstance(result, str) else result
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    def switch_conversation(self, title: str) -> bool:
        """Switch to a conversation by (partial) title.

        Walks each history-item options button up to its <li>, then clicks the
        <a href="/c/..."> link whose text matches.
        """
        # Ensure sidebar is open so history items exist in the DOM
        self._evaluate("""
        (function() {
            var btn = document.querySelector('[data-testid=open-sidebar-button]');
            if (btn) btn.click();
        })()
        """)
        self._wait(0.8)

        lower_escaped = title.replace("'", "\\'").lower()
        script = f"""
        (function() {{
            var buttons = document.querySelectorAll("[data-testid^='history-item-']");
            for (var i = 0; i < buttons.length; i++) {{
                var li = buttons[i].closest('li') || buttons[i].parentElement;
                if (!li) continue;
                var link = li.querySelector('a[href*="/c/"]');
                if (!link) continue;
                if (link.innerText.toLowerCase().includes('{lower_escaped}')) {{
                    link.click();
                    return true;
                }}
            }}
            return false;
        }})()
        """
        return self._evaluate(script) is True
