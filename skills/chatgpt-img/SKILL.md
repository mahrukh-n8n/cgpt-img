---
name: chatgpt-img
description: Generate images and interact with ChatGPT via browser automation. Use when the user wants to generate images, chat with ChatGPT, list conversations, switch chats, or download images through the ChatGPT web interface. Triggers include requests to "generate an image", "create a picture", "ask ChatGPT", "chat with GPT", "download ChatGPT image", or any task requiring ChatGPT web interaction.
allowed-tools: Bash(python -m chatgpt_img_mcp.cli:*), Bash(cgpt:*), Write, Read
---

# ChatGPT Image Generation & Chat

Automate ChatGPT web interface via CDP (Chrome DevTools Protocol). Generate images, send messages, download results — all through a connected browser session.

## Prerequisites

Edge or Chrome must be running with remote debugging enabled on port 9225, with a ChatGPT session logged in. If not already running, use `cgpt login` to launch the browser.

## Core Workflow

```bash
# Step 1: Ensure browser is connected and logged in
cgpt login

# Step 2: (optional) Start a fresh chat — generate uses the current chat
cgpt chat-new

# Step 3: Generate an image (sends prompt, waits for result)
cgpt generate "a sunset over mountains"

# Step 4: Download the generated image to Desktop
cgpt download
```

## CLI Commands

```bash
# Authentication
cgpt login [--profile Mahrukh]    # Launch Edge and connect to ChatGPT
cgpt status                       # Check connection and login status

# Chat
cgpt chat "your message here"      # Send message, get response (text)
cgpt chat "..." --file prompt.txt  # Multiline: read message from file
cgpt chat --stdin < prompt.txt     # Multiline: read from stdin
cgpt chat-new                      # Start a new conversation
cgpt chat-history                  # List recent conversations
cgpt chat-switch "title"           # Switch to a conversation by title
cgpt text                          # Extract last assistant response

# Image generation
cgpt generate "prompt"             # Generate image with prompt
cgpt generate --file prompt.txt    # Multiline prompt from file
cgpt generate --stdin              # Multiline prompt from stdin
cgpt images                        # List generated images in current chat
cgpt download                      # Download last generated image

# Model
cgpt model "GPT-4o"              # Switch model

# Upload
cgpt upload /path/to/file         # Upload a file to ChatGPT
```

## IMPORTANT: Multiline Prompts

Shells (bash, PowerShell, cmd) interpret `\n` in pasted/inlined strings as Enter — which submits the command early. Do **NOT** pass multiline prompts as inline arguments. Instead:

```bash
# Write the prompt to a temp file, then reference it
cat > /tmp/prompt.txt <<'EOF'
Line 1 of the prompt
Line 2 with more detail
Line 3 of instructions
EOF

cgpt generate --file /tmp/prompt.txt
# or
cgpt chat --file /tmp/prompt.txt
```

Agent rule of thumb: if the prompt contains a newline, always use `--file` or `--stdin`. Never try to quote-escape multiline strings on the command line.

## Common Patterns

### Generate and Save an Image

```bash
cgpt generate "a cute cat wearing a top hat"
cgpt download
# Image saved to Desktop/chatgpt_image.png
```

### Chat Conversation

```bash
cgpt chat "What is 2+3? Reply with just the number."
# Returns the response text via React fiber extraction

cgpt chat-new
cgpt chat "Explain quantum computing in one paragraph."
```

### Generate with Model Selection

```bash
cgpt model "DALL-E"
cgpt generate "abstract art with neon colors"
```

### Check Status

```bash
cgpt status
# Shows: connected, logged in, current model
```

## How It Works

The CLI connects to Edge/Chrome via CDP WebSocket on port 9225. It:
1. Finds the ChatGPT page among browser tabs
2. Navigates to a new chat via `Page.navigate`
3. Types prompts using `Input.insertText` (bypasses React/ProseMirror)
4. Clicks send button via DOM click
5. Extracts assistant responses from **React fiber state** (`memoizedProps.message.content.parts`) — NOT from DOM innerText, which is empty for assistant turns
6. Finds generated images via `img[src*="estuary"]` selectors
7. Downloads images via browser `fetch()` with `awaitPromise=True` (carries auth cookies)

## Troubleshooting

- **"ChatGPT page not found"**: Open `chatgpt.com` in the browser, or run `cgpt login`
- **"Not logged in"**: Log in to ChatGPT in the browser window, then run `cgpt status`
- **Empty response text**: The React fiber extraction handles this. If it fails, the page may need a reload.
- **Image download 403**: Direct HTTP downloads fail (no cookies). The CLI uses browser-context `fetch()` instead.
- **Rate limiting**: ChatGPT rate-limits rapid requests. Space out image generation calls.

## Environment Variables

```bash
CGPT_CDP_PORT=9225       # CDP debugging port (default: 9225)
CGPT_DEBUG=true          # Enable debug logging
CGPT_PROFILE=Mahrukh     # Edge profile name
```

## Direct Python Usage

For complex workflows not covered by the CLI, use the Python API directly:

```bash
python -c "
from chatgpt_img_mcp.core.chatgpt import ChatGPTBrowser
from chatgpt_img_mcp.utils import find_chatgpt_page

page = find_chatgpt_page()
browser = ChatGPTBrowser(page['webSocketDebuggerUrl'])
result = browser.generate_image('a sunset over mountains')
print(result)
"
```

## Available Python Methods

| Method | Description |
|--------|-------------|
| `ChatGPTBrowser(ws_url, port)` | Connect to browser page |
| `.is_logged_in()` | Check login status |
| `.send_message(msg, wait, timeout)` | Send text, get response |
| `.generate_image(prompt, timeout)` | Generate image, return URLs |
| `.find_generated_images()` | Find estuary images in chat |
| `.click_image_to_zoom()` | Open image in lightbox |
| `.click_download_button()` | Click Save in lightbox |
| `.close_zoom()` | Close lightbox |
| `.select_model(name)` | Switch model |
| `.new_chat()` | Start fresh conversation |
| `.get_conversations()` | List sidebar conversations |
| `.switch_conversation(title)` | Switch to a conversation |
| `.upload_file(path)` | Upload file to chat |
| `.get_response_text()` | Extract last response via fiber |