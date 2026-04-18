"""Auto-install helpers: register MCP with AI tools and install the Claude skill."""

from __future__ import annotations

import json
import os
import platform
import shutil
from importlib import resources
from pathlib import Path

MCP_SERVER_NAME = "chatgpt-img"
MCP_COMMAND = "cgpt-mcp"


def _mcp_entry() -> dict:
    return {"command": MCP_COMMAND, "args": []}


# ---------- MCP config file locations ----------

def _claude_desktop_config_path() -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "Claude" / "claude_desktop_config.json"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def _claude_code_config_path() -> Path:
    return Path.home() / ".claude.json"


def _cursor_config_path() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


CONFIG_PATHS = {
    "claude-desktop": _claude_desktop_config_path,
    "claude-code": _claude_code_config_path,
    "cursor": _cursor_config_path,
}


# ---------- MCP registration ----------

def register_mcp(target: str) -> tuple[bool, str]:
    """Add chatgpt-img to the given target's MCP config. Returns (ok, message)."""
    if target == "json":
        return True, json.dumps({"mcpServers": {MCP_SERVER_NAME: _mcp_entry()}}, indent=2)

    if target not in CONFIG_PATHS:
        return False, f"Unknown target: {target}. Choose from: {', '.join(list(CONFIG_PATHS) + ['json'])}"

    path = CONFIG_PATHS[target]()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            config = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            return False, f"Existing config at {path} is not valid JSON. Fix or remove it first."
    else:
        config = {}

    config.setdefault("mcpServers", {})[MCP_SERVER_NAME] = _mcp_entry()
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return True, f"Registered '{MCP_SERVER_NAME}' in {path}"


# ---------- Skill installation ----------

SKILL_TARGETS = {
    "claude-code": Path.home() / ".claude" / "skills" / "chatgpt-img",
}


def install_skill(target: str = "claude-code") -> tuple[bool, str]:
    """Copy the bundled SKILL.md to the target's skills directory."""
    if target not in SKILL_TARGETS:
        return False, f"Unknown skill target: {target}. Choose from: {', '.join(SKILL_TARGETS)}"

    dest = SKILL_TARGETS[target]
    dest.mkdir(parents=True, exist_ok=True)

    # Locate the packaged skill
    try:
        src_files = resources.files("chatgpt_img_mcp.skills") / "chatgpt-img"
    except (ModuleNotFoundError, FileNotFoundError):
        return False, "Bundled skill not found — reinstall the package."

    copied: list[str] = []
    for entry in src_files.iterdir():
        name = entry.name
        target_file = dest / name
        target_file.write_bytes(entry.read_bytes())
        copied.append(name)

    return True, f"Installed skill to {dest} ({', '.join(copied)})"
