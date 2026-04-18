# cgpt-img

Browser automation for ChatGPT's web interface. Generate images, send messages, and manage conversations from the command line, an MCP server, or a Claude Code skill. Uses the Chrome DevTools Protocol against an already-logged-in Edge/Chrome session — no API key, no headless spoofing.

## Features

- `cgpt` CLI — 13 commands (chat, generate, upload, download, history, switch, model, status, …)
- MCP server (`cgpt-mcp`) — exposes the same functionality as 11 tools over stdio/http/sse
- Claude Code skill — lets agents use the CLI with a bundled SKILL.md
- React-fiber extraction for assistant responses (ChatGPT's assistant DOM innerText is empty)
- Browser-context `fetch()` for image download (carries auth cookies — no 403)
- Multiline prompt support via `--file` / `--stdin` (Shift+Enter soft breaks in ProseMirror)

## Requirements

- Python 3.11+
- Microsoft Edge or Google Chrome
- An active ChatGPT account you're willing to log in to in the browser

## Install

```bash
git clone https://github.com/mahrukh-n8n/cgpt-img.git
cd cgpt-img
pip install -e .
```

This installs two console scripts:
- `cgpt` — the CLI
- `cgpt-mcp` — the MCP server

## Quick start

```bash
# 1. Launch a browser with remote debugging, logged in to ChatGPT
cgpt login                 # on first run: log in manually, then Ctrl+C and re-run status

# 2. Verify
cgpt status

# 3. Chat
cgpt chat "What is 2+3? Reply with just the number."

# 4. Generate and download an image
cgpt chat-new
cgpt generate "a cute cat wearing a top hat"
cgpt download              # saved to ~/Desktop/chatgpt_image.png
```

## All CLI commands

```
login         Launch browser and connect to ChatGPT.
status        Check connection and login status.
chat          Send a message and get the response.
chat-new      Start a new chat.
chat-history  List recent conversations.
chat-switch   Switch to a conversation by title.
text          Extract the last assistant response.
generate      Generate an image.
images        List generated images in the current chat.
download      Download a generated image (direct browser fetch, cookies included).
upload        Upload a file to the current chat.
model         Switch the active model.
version       Show version.
```

Multiline prompts (shells treat `\n` as Enter — use `--file` or `--stdin`):

```bash
cgpt chat --file prompt.txt
cgpt generate --stdin < prompt.txt
```

## Using as an MCP server

`cgpt-mcp` speaks the Model Context Protocol over stdio by default. Add it to any MCP-compatible client (Claude Desktop, Cursor, Claude Code, …).

### Claude Desktop

Edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "chatgpt-img": {
      "command": "cgpt-mcp"
    }
  }
}
```

### Claude Code

```bash
claude mcp add chatgpt-img cgpt-mcp
```

Or edit `~/.claude.json` / `.mcp.json`:

```json
{
  "mcpServers": {
    "chatgpt-img": {
      "command": "cgpt-mcp",
      "args": []
    }
  }
}
```

### HTTP / SSE transport

```bash
cgpt-mcp --transport http --port 8000
cgpt-mcp --transport sse  --port 8000
```

### Exposed tools (11)

`login`, `get_status`, `chat_send`, `generate_image`, `upload_file`, `model_select`, `conversations_list`, `chat_switch`, `chat_new`, `download_image`, `chat_history`

## Installing the Claude Code skill

The skill lets Claude Code agents invoke `cgpt` directly with guidance on multiline prompts, troubleshooting, etc.

```bash
mkdir -p ~/.claude/skills/chatgpt-img
cp -r skills/chatgpt-img/* ~/.claude/skills/chatgpt-img/
```

Then inside Claude Code:

```
/skill chatgpt-img
```

The skill auto-triggers on requests like "generate an image", "ask ChatGPT", "download the ChatGPT image".

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CGPT_CDP_PORT` | `9225` | Chrome remote-debugging port |
| `CGPT_MCP_TRANSPORT` | `stdio` | MCP transport |
| `CGPT_MCP_PORT` | `8000` | MCP port for http/sse |
| `CGPT_DEBUG` | — | Set to `true` for debug logging |

## How it works

1. Launches (or attaches to) Edge/Chrome with `--remote-debugging-port=9225`.
2. Finds the ChatGPT tab, connects via a CDP WebSocket.
3. Types prompts with `Input.insertText`, bridging `\n` into Shift+Enter key events for ProseMirror.
4. Waits for the response by reading React fiber state (`memoizedProps.message.content.parts`) — the DOM innerText is empty for assistant turns.
5. Downloads images by running `fetch(src).then(blob)` inside the page (so session cookies apply), then transferring the data URL back over CDP.

## Troubleshooting

- **"No browser found"** — run `cgpt login`, or launch Edge with `--remote-debugging-port=9225` manually.
- **"Not logged in"** — log in to ChatGPT in the opened browser window, then re-run `cgpt status`.
- **Empty responses** — React fiber extraction handles this normally; if it fails, reload the tab.
- **Send button fails** — the CLI retries for 3 s while it's debounced; if persistent, the page likely lost focus.

## License

MIT
