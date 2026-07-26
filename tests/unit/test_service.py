"""Unit tests for the launchd plist renderer (pure, no filesystem/launchctl)."""
from __future__ import annotations
from scholar_workflow.workflows.service import LABEL, render_plist


def test_plist_has_label_program_and_keepalive():
    xml = render_plist("/opt/sw/bin/scholar-workflow", "/home/.config/sw")
    assert f"<string>{LABEL}</string>" in xml
    assert "<string>/opt/sw/bin/scholar-workflow</string>" in xml
    assert "<string>serve-links</string>" in xml
    assert "<key>RunAtLoad</key><true/>" in xml
    assert "<key>KeepAlive</key><true/>" in xml
    assert "/home/.config/sw/link-service.log" in xml


def test_env_block_only_when_home_set():
    without = render_plist("/x", "/l")
    assert "SCHOLAR_WORKFLOW_HOME" not in without
    with_home = render_plist("/x", "/l", home_env="/custom/home")
    assert "SCHOLAR_WORKFLOW_HOME" in with_home
    assert "<string>/custom/home</string>" in with_home


def test_paths_are_xml_escaped():
    xml = render_plist("/Applications/My App/sw", "/l", home_env="/a&b")
    assert "My App" in xml and "&amp;" in xml
    assert "/a&b" not in xml  # raw ampersand must be escaped
