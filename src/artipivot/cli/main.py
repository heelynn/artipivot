"""ArtiPivot CLI — plugin management and server commands."""

from __future__ import annotations

import asyncio
import os
import uuid
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
    "function_calling": {
        "strategy": "function_calling",
        "tools": ["web_search"],
        "system_prompt": "Answer user questions concisely.",
    },
}


@plugin_app.command("init")
def plugin_init(
    name: str = typer.Argument(..., help="Plugin name"),
    template: str = typer.Option("react", help="Strategy template: react | function_calling"),
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
    manifest: str = typer.Option(
        None,
        help="Path to agents YAML. Default: ARTIPIVOT_AGENTS_MANIFEST env var, or .agents.yaml",
    ),
    env_file: str = typer.Option(".env", help=".env file path"),
):
    """Start the API server with full auto-initialization.

    Loads .env, reads the agent manifest YAML, builds all agents,
    and starts the server — all in one command.
    """
    from artipivot.bootstrap import bootstrap_sync
    from pathlib import Path

    import os
    resolved = manifest or os.environ.get("ARTIPIVOT_AGENTS_MANIFEST", ".agents.yaml")

    # Resolve project root — manifest is relative to project root
    manifest_path = Path(resolved)
    if manifest_path.parent != Path("."):
        project_root = manifest_path.parent
    else:
        # manifest is in cwd, find project root by looking for .agents.yaml or pyproject.toml
        cwd = Path.cwd()
        project_root = cwd
        # Walk up to find project root (contains .agents.yaml)
        for p in [cwd, *cwd.parents]:
            if (p / ".agents.yaml").exists() or (p / "pyproject.toml").exists():
                project_root = p
                break

    os.chdir(project_root)

    typer.echo(f"ArtiPivot starting...")
    typer.echo(f"  manifest:   {resolved}")
    typer.echo(f"  project:    {project_root}")
    typer.echo(f"  env file:   {env_file}")
    typer.echo(f"  log level:  {os.environ.get('ARTIPIVOT_LOG_LEVEL', 'INFO')}")
    typer.echo(f"  log format: {os.environ.get('ARTIPIVOT_LOG_FORMAT', 'json')}")
    typer.echo(f"  server:     http://{host}:{port}")

    app = bootstrap_sync(
        manifest_path=manifest,
        env_file=env_file,
    )

    import uvicorn

    uvicorn.run(app, host=host, port=port, reload=reload)


@app.command("chat")
def chat(
    agent_id: str = typer.Argument(..., help="Agent ID to talk to"),
    user_input: str = typer.Argument(..., help="Message to send"),
    manifest: str = typer.Option(
        None,
        help="Path to agents YAML. Default: ARTIPIVOT_AGENTS_MANIFEST env var, or .agents.yaml",
    ),
    env_file: str = typer.Option(".env", help=".env file path"),
    thread_id: str = typer.Option(None, help="Thread ID (auto-generated if omitted)"),
):
    """Chat with an agent — single-shot invocation from the CLI."""
    from artipivot.api.deps import get_gateway
    from artipivot.bootstrap import bootstrap_sync

    resolved = manifest or os.environ.get("ARTIPIVOT_AGENTS_MANIFEST", ".agents.yaml")
    tid = thread_id or uuid.uuid4().hex[:8]

    typer.echo(f"Initializing agent '{agent_id}' from {resolved} ...", err=True)

    bootstrap_sync(manifest_path=manifest, env_file=env_file)

    gateway = get_gateway()

    result = asyncio.run(
        gateway.invoke(agent_id, user_input, tid)
    )

    messages = result.get("messages", [])
    if messages:
        last = messages[-1]
        typer.echo(getattr(last, "content", str(last)))
    else:
        typer.echo("(no response)", err=True)


@app.command("agents")
def list_agents(
    manifest: str = typer.Option(
        None,
        help="Path to agents YAML. Default: ARTIPIVOT_AGENTS_MANIFEST env var, or .agents.yaml",
    ),
):
    """List registered agents from manifest."""
    from artipivot.gateway.loader import load_agent_manifest

    resolved = manifest or os.environ.get("ARTIPIVOT_AGENTS_MANIFEST", ".agents.yaml")
    loaded = load_agent_manifest(resolved)

    if not loaded.agents:
        typer.echo(f"No agents found in {resolved}")
        raise typer.Exit(1)

    typer.echo(f"Agents ({len(loaded.agents)}) from {resolved}:\n")
    for agent_id, agent_def in loaded.agents.items():
        model = agent_def.model
        model_str = f"{model.get('provider', '?')}/{model.get('name', '?')}"
        sub_agents = agent_def.sub_agent_refs or []
        typer.echo(f"  {agent_id}")
        typer.echo(f"    model:  {model_str}")
        typer.echo(f"    sub-agents: {', '.join(sub_agents) if sub_agents else '(none)'}")
        typer.echo(f"    intents:   {len(agent_def.intent_map)}")
        typer.echo()
