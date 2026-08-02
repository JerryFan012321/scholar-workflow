"""macOS launchd auto-start for the loopback link service.

The link service (`serve-links`) must stay running for Obsidian/Notion PDF links to
resolve. Rather than relying on a manually launched foreground process, we install a
per-user LaunchAgent that starts it at login and restarts it if it dies (KeepAlive).

`render_plist` is pure (string in → string out) so it is unit-testable without touching
the filesystem or launchctl. The CLI command writes the file and (optionally) loads it.
"""
from __future__ import annotations
from pathlib import Path
from xml.sax.saxutils import escape

LABEL = "com.scholar-workflow.link-service"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def render_plist(executable: str, log_dir: str, home_env: str | None = None) -> str:
    """Render the LaunchAgent plist. `executable` is the absolute path to the
    scholar-workflow entry point; it is run with the `serve-links` subcommand.
    `home_env` (SCHOLAR_WORKFLOW_HOME) is injected only when set, so launchd's clean
    environment still finds a non-default config."""
    env_block = ""
    if home_env:
        env_block = (
            "    <key>EnvironmentVariables</key>\n"
            "    <dict>\n"
            f"      <key>SCHOLAR_WORKFLOW_HOME</key><string>{escape(home_env)}</string>\n"
            "    </dict>\n"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "  <dict>\n"
        f"    <key>Label</key><string>{LABEL}</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        f"      <string>{escape(executable)}</string>\n"
        "      <string>serve-links</string>\n"
        "    </array>\n"
        "    <key>RunAtLoad</key><true/>\n"
        "    <key>KeepAlive</key><true/>\n"
        f"{env_block}"
        f"    <key>StandardOutPath</key><string>{escape(log_dir)}/link-service.log</string>\n"
        f"    <key>StandardErrorPath</key><string>{escape(log_dir)}/link-service.err</string>\n"
        "  </dict>\n"
        "</plist>\n"
    )
