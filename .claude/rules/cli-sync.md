---
name: cli-sync
description: Every feature must be exposed as a CLI command with help text
globs:
alwaysApply: true
---

# CLI Sync Rule

Every piece of functionality added to this project MUST have a corresponding CLI command in `src/chatgpt_img_mcp/cli.py` using Typer.

**Why:** The CLI is the primary interface for the skill. If a feature exists in `ChatGPTBrowser` or `tools.py` but not in `cli.py`, it's unreachable from the skill.

**How to apply:**
- When adding a method to `ChatGPTBrowser` or a tool to `tools.py`, add a matching Typer command to `cli.py`
- Every command must have a descriptive `help=` string
- Every argument and option must have `help=` text
- The command name must be intuitive (e.g., `generate`, `chat`, `download`, `images`)
- Run `cgpt --help` after changes to verify the command appears
- If the command involves file output, support `--output` / `-o` flag
- If the command needs a browser, use `_get_browser()` which handles connection errors