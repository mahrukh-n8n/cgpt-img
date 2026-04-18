# cgpt-img

Browser automation for ChatGPT. One install, one command to register with Claude Code / Claude Desktop / Cursor, one command to install the bundled Claude skill. Uses Chrome DevTools Protocol against your real logged-in Edge/Chrome — no API key needed.

Ships as:
- **`cgpt`** — CLI (13 commands)
- **`cgpt-mcp`** — MCP server (11 tools, stdio/http/sse)
- **Claude Code skill** bundled inside the package

## Install

**Recommended (uv):**
```bash
uv tool install git+https://github.com/mahrukh-n8n/cgpt-img.git
```

**pipx:**
```bash
pipx install git+https://github.com/mahrukh-n8n/cgpt-img.git
```

**pip:**
```bash
pip install --user git+https://github.com/mahrukh-n8n/cgpt-img.git
```

**From source:**
```bash
git clone https://github.com/mahrukh-n8n/cgpt-img.git
cd cgpt-img
pip install --user -e .
```

## Register with AI tools (auto)

No manual JSON editing. The CLI writes the config for you:

```bash
cgpt setup add claude-code       # ~/.claude.json
cgpt setup add claude-desktop    # Claude Desktop config (OS-specific)
cgpt setup add cursor            # ~/.cursor/mcp.json
```

Show detected config paths:
```bash
cgpt setup list
```

Just print the JSON (for manual paste):
```bash
cgpt setup add json
```

Restart the AI tool after registering.

## Install the Claude Code skill (auto)

```bash
cgpt skill install claude-code   # → ~/.claude/skills/chatgpt-img/SKILL.md
```

Inside Claude Code:
```
/skill chatgpt-img
```

## First-time auth

```bash
cgpt login            # Launches Edge/Chrome with remote debugging on port 9225
# → log in to ChatGPT in the opened window
cgpt status           # Verify you're connected and logged in
```

## Quick use

```bash
cgpt chat "What is 2+3? Reply with just the number."
cgpt chat-new
cgpt generate "a cute cat wearing a top hat"
cgpt download         # → ~/Desktop/chatgpt_image.png
```

## CLI commands

```
login                Launch browser and connect to ChatGPT.
status               Check connection and login status.
chat                 Send a message, get the response.
chat-new             Start a new chat.
chat-history         List recent conversations.
chat-switch          Switch to a conversation by title.
text                 Extract the last assistant response.
generate             Generate an image.
images               List generated images in the current chat.
download             Download a generated image (browser fetch with cookies).
upload               Upload a file to the current chat.
model                Switch the active model.
version              Show version.
setup add <target>   Register cgpt-mcp with claude-code / claude-desktop / cursor / json.
setup list           Show config paths for all targets.
skill install        Install the Claude Code skill.
```

### Multiline prompts

Shells treat `\n` as Enter. Don't inline multiline text — use `--file` or `--stdin`:

```bash
cgpt chat --file prompt.txt
cgpt generate --stdin < prompt.txt
```

## MCP tools exposed

`login`, `get_status`, `chat_send`, `generate_image`, `upload_file`, `model_select`, `conversations_list`, `chat_switch`, `chat_new`, `download_image`, `chat_history`

## Transport

```bash
cgpt-mcp                                   # stdio (default)
cgpt-mcp --transport http --port 8000
cgpt-mcp --transport sse  --port 8000
```

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `CGPT_CDP_PORT` | `9225` | Chrome remote-debugging port |
| `CGPT_MCP_TRANSPORT` | `stdio` | MCP transport |
| `CGPT_MCP_PORT` | `8000` | MCP port for http/sse |
| `CGPT_DEBUG` | — | Set `true` for debug logging |

## How it works

1. Launches (or attaches to) Edge/Chrome with `--remote-debugging-port=9225`.
2. Connects to the ChatGPT tab via a CDP WebSocket.
3. Types prompts with `Input.insertText`, mapping `\n` to Shift+Enter key events for ProseMirror.
4. Reads assistant responses from React fiber state (`memoizedProps.message.content.parts`) — the DOM innerText is empty for assistant turns.
5. Downloads images with `fetch(src).then(blob)` inside the page so session cookies apply.

## Troubleshooting

- **"No browser found"** — run `cgpt login`, or launch Edge manually with `--remote-debugging-port=9225`.
- **"Not logged in"** — log in to ChatGPT in the browser window, then re-run `cgpt status`.
- **Empty responses** — React fiber extraction handles this; if it fails, reload the tab.
- **Send button fails** — the CLI retries for ~3s; if persistent, the page lost focus.

## License

MIT
