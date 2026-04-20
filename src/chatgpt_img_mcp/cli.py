"""CLI for ChatGPT Image MCP."""

import json
import os
import sys
import time

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from chatgpt_img_mcp import __version__
from chatgpt_img_mcp.core.chatgpt import ChatGPTBrowser
from chatgpt_img_mcp.install import CONFIG_PATHS, SKILL_TARGETS, install_skill, register_mcp
from chatgpt_img_mcp.utils import (
    CDP_DEFAULT_PORT,
    CHATGPT_URL,
    find_chatgpt_page,
    get_debugger_url,
    launch_browser,
)

app = typer.Typer(
    name="cgpt",
    help="ChatGPT Image MCP — Generate images and chat with ChatGPT via browser automation.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


def _get_browser(port: int = None) -> ChatGPTBrowser:
    """Get or create a browser connection. Exits on failure."""
    port = port or int(os.environ.get("CGPT_CDP_PORT", str(CDP_DEFAULT_PORT)))

    ws_url = get_debugger_url(port)
    if not ws_url:
        console.print("[red]No browser found. Run [bold]cgpt login[/bold] first.[/red]")
        raise typer.Exit(1)

    page = find_chatgpt_page(port)
    if not page:
        console.print("[yellow]No ChatGPT page found. Navigating...[/yellow]")
        from chatgpt_img_mcp.utils.cdp import navigate_to
        navigate_to(CHATGPT_URL, ws_url)
        time.sleep(3)
        page = find_chatgpt_page(port)
        if not page:
            console.print("[red]Could not find ChatGPT page.[/red]")
            raise typer.Exit(1)

    return ChatGPTBrowser(page["webSocketDebuggerUrl"], port)


@app.command()
def login(
    profile: str = typer.Option(None, "--profile", "-p", help="Edge profile name"),
    port: int = typer.Option(None, "--port", help="CDP port"),
):
    """Launch browser and connect to ChatGPT."""
    port = port or int(os.environ.get("CGPT_CDP_PORT", str(CDP_DEFAULT_PORT)))
    console.print(f"[bold]ChatGPT Image MCP v{__version__}[/bold]")

    profile_dir = None
    if profile and os.name == "nt":
        profile_dir = rf"C:\Users\{os.environ.get('USERNAME', 'User')}\AppData\Local\Microsoft\Edge\User Data\{profile}"
        console.print(f"Using profile: {profile}")
    elif not profile:
        for p in ["Mahrukh", "Default"]:
            path = rf"C:\Users\{os.environ.get('USERNAME', 'User')}\AppData\Local\Microsoft\Edge\User Data\{p}" if os.name == "nt" else None
            if path and os.path.exists(path):
                profile_dir = path
                console.print(f"Using profile: {p}")
                break

    console.print("[yellow]Launching Edge with remote debugging...[/yellow]")
    process = launch_browser(port, profile_dir)
    if not process:
        console.print("[red]Failed to launch browser.[/red]")
        raise typer.Exit(1)

    time.sleep(5)

    page = find_chatgpt_page(port)
    if not page:
        ws_url = get_debugger_url(port)
        if ws_url:
            from chatgpt_img_mcp.utils.cdp import navigate_to
            navigate_to(CHATGPT_URL, ws_url)
            time.sleep(3)
            page = find_chatgpt_page(port)

    if not page:
        console.print("[red]Could not open ChatGPT.[/red]")
        raise typer.Exit(1)

    browser = ChatGPTBrowser(page["webSocketDebuggerUrl"], port)
    if browser.is_logged_in():
        console.print(Panel("[green]Logged in to ChatGPT![/green]", title="Success"))
    else:
        console.print(Panel(
            "[yellow]Browser launched. Log in to ChatGPT in the browser, then run [bold]cgpt status[/bold].[/yellow]",
            title="Login Required",
        ))


@app.command()
def status(port: int = typer.Option(None, "--port", "-P", help="CDP port")):
    """Check connection and login status."""
    try:
        browser = _get_browser(port)
    except SystemExit:
        return

    logged_in = browser.is_logged_in()
    if logged_in:
        model_info = browser._evaluate("""
        (function() {
            var btn = document.querySelector('[data-testid=model-switcher-dropdown-button]');
            return btn ? btn.innerText.trim() : 'unknown';
        })()
        """)
        table = Table(title="ChatGPT Status")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Connection", "Connected")
        table.add_row("Logged in", "Yes")
        table.add_row("Model", str(model_info or "unknown"))
        console.print(table)
    else:
        console.print(Panel("[yellow]Connected but not logged in[/yellow]", title="Status"))


@app.command()
def chat(
    message: str = typer.Argument(None, help="Message to send (omit if using --file or --stdin)"),
    file: str = typer.Option(None, "--file", "-f", help="Read message from file (supports multiline)"),
    stdin: bool = typer.Option(False, "--stdin", help="Read message from stdin (supports multiline)"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for response"),
    timeout: int = typer.Option(60, "--timeout", "-t", help="Timeout in seconds"),
    port: int = typer.Option(None, "--port", "-P", help="CDP port"),
):
    """Send a message to ChatGPT and get the response."""
    if file:
        message = open(file, encoding="utf-8").read()
    elif stdin:
        message = sys.stdin.read()
    if not message:
        console.print("[red]No message provided. Pass as argument, --file, or --stdin.[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Sending: {message[:80]}{'...' if len(message) > 80 else ''}[/dim]")
    browser = _get_browser(port)

    if not browser.is_logged_in():
        console.print("[red]Not logged in. Run [bold]cgpt login[/bold] first.[/red]")
        raise typer.Exit(1)

    with console.status("Waiting for response..."):
        result = browser.send_message(message, wait_for_response=wait, timeout=timeout)

    if result.get("status") == "success":
        response = result.get("response", "")
        if response:
            console.print(Panel(response[:2000], title="Response"))
        if result.get("has_images"):
            console.print("[dim](Images were also generated)[/dim]")
    elif result.get("status") == "timeout":
        console.print(Panel(result.get("partial", "No response received"), title="Timeout", border_style="yellow"))
    else:
        console.print(f"[red]Error: {result.get('error', 'Unknown')}[/red]")


@app.command(name="chat-new")
def chat_new(port: int = typer.Option(None, "--port", "-P", help="CDP port")):
    """Start a new chat conversation."""
    browser = _get_browser(port)

    if not browser.is_logged_in():
        console.print("[red]Not logged in.[/red]")
        raise typer.Exit(1)

    if browser.new_chat():
        console.print("[green]Started new chat[/green]")
    else:
        console.print("[yellow]Could not start new chat (click New Chat button manually)[/yellow]")


@app.command()
def generate(
    prompt: str = typer.Argument(None, help="Image generation prompt (omit if using --file or --stdin)"),
    file: str = typer.Option(None, "--file", "-f", help="Read prompt from file (supports multiline)"),
    stdin: bool = typer.Option(False, "--stdin", help="Read prompt from stdin (supports multiline)"),
    timeout: int = typer.Option(120, "--timeout", "-t", help="Timeout in seconds"),
    model: str = typer.Option(None, "--model", "-m", help="Model to use (e.g. DALL-E, GPT-4o)"),
    port: int = typer.Option(None, "--port", "-P", help="CDP port"),
):
    """Generate an image using ChatGPT."""
    if file:
        prompt = open(file, encoding="utf-8").read()
    elif stdin:
        prompt = sys.stdin.read()
    if not prompt:
        console.print("[red]No prompt provided. Pass as argument, --file, or --stdin.[/red]")
        raise typer.Exit(1)

    browser = _get_browser(port)

    if not browser.is_logged_in():
        console.print("[red]Not logged in.[/red]")
        raise typer.Exit(1)

    if model:
        browser.select_model(model)
        time.sleep(0.5)

    console.print(f"[bold]Generating:[/bold] {prompt}")
    with console.status("Waiting for image generation..."):
        result = browser.generate_image(prompt, wait_for=timeout)

    if result.get("status") == "success":
        images = result.get("images", [])
        response = result.get("response", "")
        if response:
            console.print(f"[dim]ChatGPT said: {response[:200]}[/dim]")
        console.print(f"[green]Generated {len(images)} image(s)[/green]")
        for i, img in enumerate(images):
            console.print(f"  [{i}] {img.get('src', '')[:80]}... ({img.get('width')}x{img.get('height')})")
    elif result.get("status") == "timeout":
        response = result.get("response", "")
        if response:
            console.print(f"[dim]ChatGPT said: {response[:200]}[/dim]")
        console.print("[yellow]Timed out waiting for image[/yellow]")
    else:
        console.print(f"[red]Error: {result.get('error', 'Unknown')}[/red]")


@app.command()
def download(
    index: int = typer.Option(0, "--index", "-i", help="Image index (0-based)"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path"),
    port: int = typer.Option(None, "--port", "-P", help="CDP port"),
):
    """Download a generated image from the current chat.

    Uses browser-context fetch() to carry auth cookies. Falls back to
    clicking the Save button in the zoom dialog.
    """
    import base64

    browser = _get_browser(port)

    if not browser.is_logged_in():
        console.print("[red]Not logged in.[/red]")
        raise typer.Exit(1)

    images = browser.find_generated_images()
    if not images:
        console.print("[red]No generated images found in current chat.[/red]")
        raise typer.Exit(1)

    if index >= len(images):
        console.print(f"[red]Index {index} out of range ({len(images)} images found)[/red]")
        raise typer.Exit(1)

    image_src = images[index]["src"]
    console.print(f"[dim]Downloading from: {image_src[:80]}...[/dim]")

    # Method 1: Browser fetch with awaitPromise (carries auth cookies)
    with console.status("Downloading via browser..."):
        fetch_js = (
            'fetch("' + image_src + '").then(function(r) { return r.blob(); })'
            '.then(function(blob) { return new Promise(function(resolve) {'
            ' var reader = new FileReader(); reader.onload = function() { resolve(reader.result); };'
            ' reader.readAsDataURL(blob); }); })'
            '.catch(function(e) { return "ERROR:" + e.message; })'
        )
        fetch_result = browser._evaluate(fetch_js, timeout=60, await_promise=True)

    if fetch_result and str(fetch_result).startswith("data:"):
        b64_data = str(fetch_result).split(",", 1)[1]
        img_bytes = base64.b64decode(b64_data)

        if not output:
            desktop = os.path.expanduser("~/Desktop")
            output = os.path.join(desktop, "chatgpt_image.png")

        with open(output, "wb") as f:
            f.write(img_bytes)
        console.print(f"[green]Saved to: {output} ({len(img_bytes)} bytes)[/green]")
    else:
        # Method 2: Click zoom + Save button
        console.print("[yellow]Direct fetch failed. Trying zoom + save button...[/yellow]")
        if browser.click_image_to_zoom(index):
            time.sleep(2)
            if browser.click_download_button():
                time.sleep(2)
                browser.close_zoom()
                downloads = os.path.expanduser("~/Downloads")
                console.print(f"[green]Download triggered. Check {downloads}[/green]")
            else:
                browser.close_zoom()
                console.print("[red]Could not find Save button in zoom view[/red]")
        else:
            console.print("[red]Could not click image to zoom[/red]")


@app.command(name="chat-history")
def chat_history(
    port: int = typer.Option(None, "--port", "-P", help="CDP port"),
):
    """List recent ChatGPT conversations."""
    browser = _get_browser(port)

    if not browser.is_logged_in():
        console.print("[red]Not logged in.[/red]")
        raise typer.Exit(1)

    # Open sidebar to access history
    browser._evaluate("""
    (function() {
        var btn = document.querySelector('[data-testid=open-sidebar-button]');
        if (btn) btn.click();
    })()
    """)
    time.sleep(1)

    conversations = browser.get_conversations()
    if not conversations:
        console.print("[yellow]No conversations found[/yellow]")
    else:
        table = Table(title="Recent Conversations")
        table.add_column("#", style="dim")
        table.add_column("Title", style="cyan")
        for i, conv in enumerate(conversations):
            table.add_row(str(i), conv.get("title", "Untitled"))
        console.print(table)

    # Close sidebar
    browser.close_sidebar()


@app.command(name="chat-switch")
def chat_switch(
    title: str = typer.Argument(..., help="Conversation title (partial match)"),
    port: int = typer.Option(None, "--port", "-P", help="CDP port"),
):
    """Switch to a conversation by title."""
    browser = _get_browser(port)

    if not browser.is_logged_in():
        console.print("[red]Not logged in.[/red]")
        raise typer.Exit(1)

    if browser.switch_conversation(title):
        console.print(f"[green]Switched to: {title}[/green]")
    else:
        console.print(f"[red]Conversation not found: {title}[/red]")


@app.command()
def model(
    name: str = typer.Argument(..., help="Model name (e.g. GPT-4o, DALL-E 3, o3)"),
    port: int = typer.Option(None, "--port", "-P", help="CDP port"),
):
    """Switch the ChatGPT model."""
    browser = _get_browser(port)

    if not browser.is_logged_in():
        console.print("[red]Not logged in.[/red]")
        raise typer.Exit(1)

    if browser.select_model(name):
        console.print(f"[green]Switched to model: {name}[/green]")
    else:
        console.print(f"[red]Could not find model: {name}[/red]")


@app.command()
def upload(
    file_path: str = typer.Argument(..., help="Path to file to upload"),
    port: int = typer.Option(None, "--port", "-P", help="CDP port"),
):
    """Upload a file to the current ChatGPT chat."""
    from pathlib import Path

    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)

    browser = _get_browser(port)

    if not browser.is_logged_in():
        console.print("[red]Not logged in.[/red]")
        raise typer.Exit(1)

    if browser.upload_file(str(path.resolve())):
        console.print(f"[green]Uploaded: {path.name}[/green]")
    else:
        console.print(f"[red]Failed to upload: {path.name}[/red]")


@app.command()
def images(port: int = typer.Option(None, "--port", "-P", help="CDP port")):
    """List generated images in the current chat."""
    browser = _get_browser(port)

    if not browser.is_logged_in():
        console.print("[red]Not logged in.[/red]")
        raise typer.Exit(1)

    found = browser.find_generated_images()
    if not found:
        console.print("[yellow]No generated images found in current chat[/yellow]")
    else:
        table = Table(title="Generated Images")
        table.add_column("#", style="dim")
        table.add_column("URL", style="cyan", max_width=60)
        table.add_column("Size")
        for i, img in enumerate(found):
            table.add_row(
                str(i),
                img.get("src", "")[:80],
                f"{img.get('width', '?')}x{img.get('height', '?')}",
            )
        console.print(table)


@app.command()
def text(port: int = typer.Option(None, "--port", "-P", help="CDP port")):
    """Extract the last assistant response text from the current chat."""
    browser = _get_browser(port)

    if not browser.is_logged_in():
        console.print("[red]Not logged in.[/red]")
        raise typer.Exit(1)

    response_text = browser.get_response_text()
    if response_text:
        console.print(Panel(response_text[:3000], title="Last Response"))
    else:
        console.print("[yellow]No response text found[/yellow]")


@app.command()
def version():
    """Show version information."""
    console.print(f"[bold]ChatGPT Image MCP v{__version__}[/bold]")


setup_app = typer.Typer(help="Register cgpt-mcp with AI tools (Claude Code, Claude Desktop, Cursor).")
skill_app = typer.Typer(help="Install the Claude Code skill that uses cgpt.")
app.add_typer(setup_app, name="setup")
app.add_typer(skill_app, name="skill")


@setup_app.command("add")
def setup_add(
    target: str = typer.Argument(
        ...,
        help=f"Target: {', '.join(list(CONFIG_PATHS) + ['json'])}",
    ),
):
    """Register the chatgpt-img MCP server with an AI tool."""
    ok, msg = register_mcp(target)
    if target == "json":
        console.print(msg)
        return
    if ok:
        console.print(f"[green]{msg}[/green]")
        console.print("[dim]Restart the AI tool to pick up the new server.[/dim]")
    else:
        console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)


@setup_app.command("list")
def setup_list():
    """Show detected config paths for each supported target."""
    table = Table(title="MCP Config Targets")
    table.add_column("Target", style="cyan")
    table.add_column("Config path")
    table.add_column("Exists", style="dim")
    for name, path_fn in CONFIG_PATHS.items():
        p = path_fn()
        table.add_row(name, str(p), "yes" if p.exists() else "no")
    console.print(table)


@skill_app.command("install")
def skill_install(
    target: str = typer.Argument("claude-code", help=f"Target: {', '.join(SKILL_TARGETS)}"),
):
    """Install the bundled Claude skill into the target's skills directory."""
    ok, msg = install_skill(target)
    if ok:
        console.print(f"[green]{msg}[/green]")
    else:
        console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()