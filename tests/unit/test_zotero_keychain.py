"""Unit tests for Zotero Local API key storage boundaries."""

from __future__ import annotations

import subprocess

from scholar_workflow.adapters.zotero_local import KEY_ENV_VAR, MacOSKeychainStore


def completed(args, returncode=0, stdout=""):
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr="")


def test_environment_key_takes_precedence(monkeypatch):
    monkeypatch.setenv(KEY_ENV_VAR, "environment-key")

    def must_not_run(*args, **kwargs):
        raise AssertionError("Keychain should not be queried")

    assert MacOSKeychainStore(must_not_run).get("server-1") == "environment-key"


def test_missing_keychain_item_returns_none(monkeypatch):
    monkeypatch.delenv(KEY_ENV_VAR, raising=False)
    store = MacOSKeychainStore(lambda args, **kwargs: completed(args, returncode=44))
    assert store.get("server-1") is None


def test_keychain_lookup_and_update_are_scoped_by_server(monkeypatch):
    monkeypatch.delenv(KEY_ENV_VAR, raising=False)
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        if args[1] == "find-generic-password":
            return completed(args, stdout="remembered-key\n")
        return completed(args)

    store = MacOSKeychainStore(runner)
    assert store.get("server-1") == "remembered-key"
    store.put("server-1", "new-key")
    store.delete("server-1")
    assert all("server-1" in call for call in calls)
    assert calls[1][-1] == "-U"
    assert calls[2][1] == "delete-generic-password"
