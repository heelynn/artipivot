"""ArtiPivot CLI — plugin management and server commands."""

from __future__ import annotations

import os
from pathlib import Path

import typer

app = typer.Typer(name="artipivot", help="ArtiPivot CLI")
plugin_app = typer.Typer(help="Plugin management")
app.add_typer(plugin_app, name="plugin")

TEMPLATES = {
    "react": {
        "strategy": "react",
        "tools": ["web_search"],
        "system_prompt": "You are a helpful assistant.",
        "strategy_config": {"max_iterations": 5},
    },
    "cot": {
        "strategy": "cot",
        "tools": ["web_search"],
        "system_prompt": "You are a research assistant.",
        "strategy_config": {"max_plan_steps": 3},
    },
    "function_calling": {
        "strategy": "function_calling",
        "tools": ["web_search"],
        "system_prompt": "Answer user questions concisely.",
    },
}


@plugin_app.command("init")
def plugin_init(
    name: str = typer.Argument(..., help="Plugin name"),
    template: str = typer.Option("react", help="Strategy template: react | cot | function_calling"),
):
    """Generate a plugin directory with manifest."""
    plugin_dir = Path("plugins") / name
    if plugin_dir.exists():
        typer.echo(f"Error: {plugin_dir} already exists", err=True)
        raise typer.Exit(1)

    plugin_dir.mkdir(parents=True)

    tmpl = TEMPLATES.get(template, TEMPLATES["react"])

    # Generate manifest.yaml
    manifest = f"""# Plugin: {name}
plugin_type: sub_agent
name: {name}
version: "1.0"
manifest:
  strategy: {tmpl['strategy']}
  tools:
"""
    for t in tmpl["tools"]:
        manifest += f"    - {t}\n"
    manifest += f"""  system_prompt: "{tmpl['system_prompt']}"
  strategy_config:
"""
    for k, v in tmpl.get("strategy_config", {}).items():
        manifest += f"    {k}: {v}\n"

    (plugin_dir / "manifest.yaml").write_text(manifest)
    typer.echo(f"Created plugin: {plugin_dir}")
    typer.echo(f"  manifest.yaml — strategy: {tmpl['strategy']}")


@plugin_app.command("publish")
def plugin_publish(
    name: str = typer.Argument(..., help="Plugin name"),
    agent_id: str = typer.Option("code_agent", help="Target agent ID"),
    version: str = typer.Option("1.0", help="Plugin version"),
):
    """Publish a plugin to the running ArtiPivot server."""
    import yaml
    from pathlib import Path

    manifest_path = Path("plugins") / name / "manifest.yaml"
    if not manifest_path.exists():
        typer.echo(f"Error: {manifest_path} not found", err=True)
        raise typer.Exit(1)

    with open(manifest_path) as f:
        data = yaml.safe_load(f)

    typer.echo(f"Publishing plugin '{name}' v{version} → agent '{agent_id}'")
    typer.echo(f"  strategy: {data.get('manifest', {}).get('strategy', 'unknown')}")
    typer.echo(f"  tools: {data.get('manifest', {}).get('tools', [])}")
    typer.echo("  (API publishing requires a running server)")


@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8000, help="Bind port"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
):
    """Start the API server."""
    import uvicorn

    uvicorn.run(
        "artipivot.api.server:create_app",
        host=host,
        port=port,
        factory=True,
        reload=reload,
    )


@app.command("agents")
def list_agents():
    """List registered agents (requires running server)."""
    typer.echo("Listing agents requires a running server.")
    typer.echo("Start with: artipivot serve")
