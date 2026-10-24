"""Read-only composition of existing asset authorities and local human summaries."""
from __future__ import annotations

import html
from pathlib import Path

from scholar_workflow.knowledge.fields import (
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
)


def knowledge_inventory(registry_path: Path) -> dict:
    """Use the registered Source/Field authority, without discovering directories."""
    registry = KnowledgeSourceRegistry(registry_path)
    try:
        document = registry.load_document()
        revision = registry.revision()
        fields = FieldService(registry).list_fields()
    except (FieldRegistryError, OSError, ValueError, TypeError):
        return {
            "status": "invalid", "revision": None, "sources": [],
            "diagnostics": [{"code": "knowledge_registry_invalid",
                             "message": "Knowledge registry is unavailable or invalid."}],
        }
    sources = []
    for registration in document.sources:
        folder = next(folder for folder in document.folders
                      if folder.folder_id == registration.folder_id)
        row = {
            "source_id": registration.source_id,
            "folder_id": registration.folder_id,
            "provider": registration.provider,
            "enabled": registration.enabled,
            "capabilities": list(registration.capabilities),
            "root": str(folder.root),
            "root_verified": False,
            "status": "disabled" if not registration.enabled else "available",
            "fields": [], "diagnostics": [],
        }
        if registration.enabled:
            try:
                row["root"] = str(registry.resolve(registration.source_id, capability="read"))
                row["root_verified"] = True
            except (FieldRegistryError, OSError, ValueError):
                row["status"] = "unavailable"
            declared = [field for field in fields
                        if field["source_id"] == registration.source_id]
            row["fields"] = [dict(field) for field in declared]
            if any(not field["available"] for field in declared):
                row["status"] = "unavailable"
            if row["status"] == "unavailable":
                row["diagnostics"] = [{
                    "code": "knowledge_source_unavailable",
                    "message": "Registered Source folder or Field manifest is unavailable or invalid.",
                }]
        sources.append(row)
    return {
        "status": ("uninitialized" if revision == "absent" else
                   "partial" if any(row["status"] == "unavailable" for row in sources) else
                   "available"),
        "revision": revision, "sources": sources, "diagnostics": [],
        "scope": "registered-identities-only; not reader or paper ownership verification",
    }


def _cell(value: object) -> str:
    return html.escape(" ".join(str(value if value is not None else "—").split())).replace("|", "\\|")


def research_inventory(root: Path) -> dict:
    """Derive a view of the actual subscription authority, never a duplicate store."""
    from scholar_workflow.research import ResearchError, read_sources

    try:
        return read_sources(root)
    except ResearchError:
        return {"schema_version": 1, "status": "unavailable", "revision": None,
                "channels": [], "diagnostics": [{"code": "research_registry_invalid",
                "message": "Research source registration is unavailable or invalid."}]}


def _status(value: str, zh: bool) -> str:
    labels = {
        "available": ("可查询", "Available"),
        "uninitialized": ("尚未登记", "Not initialized"),
        "invalid": ("登记信息无效", "Invalid"),
        "unavailable": ("不可用", "Unavailable"),
        "partial": ("部分不可用", "Partially available"),
        "disabled": ("已停用", "Disabled"),
        "created": ("已登记", "Registered"),
        "unchanged": ("无变更", "Unchanged"),
        "updated": ("已更新", "Updated"),
    }
    return labels.get(value, ("未知状态", "Unknown status"))[0 if zh else 1]


def _diagnostics(provider: dict, *, zh: bool) -> list[str]:
    lines = []
    diagnostics = list(provider.get("diagnostics", []))
    for source in provider.get("sources", []):
        diagnostics.extend(source.get("diagnostics", []))
    localized = {
        "knowledge_registry_invalid": "知识目录登记信息无法读取或格式无效。",
        "knowledge_source_unavailable": "已登记的知识目录或领域清单不可用，请检查目录是否移动、缺失或受限。",
        "server_ledger_unavailable": "服务器台账或其配置无法读取；知识目录查询不受此问题影响。",
        "invalid_server_ledger": "服务器台账无法读取、格式无效或路径不安全，请修正后重新检查。",
        "ledger_permissions": "服务器台账权限不够私密；本次只读检查没有修改权限。",
        "legacy_secret_present": "旧台账中含凭据内容，已隐藏；本次没有迁移或删除凭据。",
    }
    for diagnostic in diagnostics:
        if zh and isinstance(diagnostic, dict) and diagnostic.get("code") in localized:
            lines.append("- 诊断: " + localized[diagnostic["code"]])
            continue
        message = diagnostic.get("message", "Asset is unavailable.") if isinstance(
            diagnostic, dict) else str(diagnostic)
        lines.append(f"- {'技术诊断（原文）' if zh else 'Diagnostic'}: {_cell(message)}")
    return lines


def _server_lines(provider: dict, *, zh: bool) -> list[str]:
    lines = [f"{'状态' if zh else 'Status'}: {_status(provider['status'], zh)}", ""]
    servers = provider.get("servers", [])
    if not servers:
        lines += ["没有可用的服务器记录。" if zh else "No available server records.", ""]
    else:
        columns = (["别名", "主机", "用户", "端口", "用途", "凭据"] if zh else
                   ["Alias", "Host", "User", "Port", "Purpose", "Credentials"])
        lines += ["| " + " | ".join(columns) + " |", "|" + " --- |" * len(columns)]
        for server in servers:
            credential = ("旧秘密已隐藏" if zh else "Legacy secret hidden") if server.get(
                "legacy_secret_present") else (("外部引用" if zh else "External reference")
                                               if server.get("credential_ref") else "—")
            values = [server.get("alias"), server.get("host"), server.get("user"),
                      server.get("port", 22), server.get("purpose"), credential]
            lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
        lines.append("")
    lines.extend(_diagnostics(provider, zh=zh))
    return lines


def inventory_markdown(payload: dict, *, language: str) -> str:
    zh = language == "zh"
    lines = ["# 本地资产" if zh else "# Local assets", ""]
    for kind, provider in payload["providers"].items():
        if kind == "research":
            from scholar_workflow.research.presentation import sources_markdown
            lines.append(sources_markdown(provider, language=language).replace("# ", "## ", 1))
            continue
        lines += ["## 服务器" if zh and kind == "server" else
                  "## 知识库" if zh else "## Servers" if kind == "server" else "## Knowledge", ""]
        if kind == "server":
            lines.extend(_server_lines(provider, zh=zh))
        else:
            lines += [f"{'状态' if zh else 'Status'}: {_status(provider['status'], zh)}", ""]
            sources = provider.get("sources", [])
            if not sources:
                lines += ["没有已登记知识目录。" if zh else "No registered knowledge folders.", ""]
            else:
                columns = ["知识领域", "目录", "状态"] if zh else ["Fields", "Folder", "Status"]
                lines += ["| " + " | ".join(columns) + " |", "|" + " --- |" * len(columns)]
                for source in sources:
                    titles = ", ".join(str(field["title"]) for field in source["fields"]
                                       if field.get("title"))
                    titles = titles or ("未能读取领域" if zh else "Fields unavailable")
                    root = source.get("root")
                    if root and not source.get("root_verified"):
                        root += "（已登记，未校验）" if zh else " (registered, unverified)"
                    lines.append("| " + " | ".join(_cell(value) for value in [
                        titles, root, _status(source["status"], zh)]) + " |")
                lines.append("")
            lines.extend(_diagnostics(provider, zh=zh))
        lines.append("")
    if "knowledge" in payload["providers"]:
        lines += [("这里只查询已登记目录和领域，不是阅读器可用性或论文归属验证。" if zh else
                   "This is a registered folder/Field inventory, not reader or paper ownership verification."), ""]
    return "\n".join(lines)


def server_markdown(payload: dict, *, language: str) -> str:
    zh = language == "zh"
    lines = ["# 服务器登记" if zh else "# Server registration", ""]
    provider = dict(payload)
    if "server" in provider:
        provider["servers"] = [provider["server"]]
    lines.extend(_server_lines(provider, zh=zh))
    server = payload.get("server")
    if server:
        labels = {"key": ("SSH 密钥文件", "SSH key file"),
                  "jump": ("跳板机", "Jump host"),
                  "cuda_driver": ("CUDA 驱动", "CUDA driver"),
                  "credential_ref": ("凭据引用", "Credential reference"),
                  "notes": ("说明", "Notes")}
        for field, names in labels.items():
            if server.get(field):
                lines.append(f"- {names[0 if zh else 1]}: {_cell(server[field])}")
        environments = server.get("environments", [])
        if environments:
            lines += ["", "## 已记录环境" if zh else "## Recorded environments", ""]
            for environment in environments:
                values = [environment.get("name"),
                          f"Python {_cell(environment.get('python', '—'))}",
                          f"CUDA {_cell(environment.get('cuda', '—'))}"]
                lines.append("- " + " · ".join(_cell(value) for value in values))
    lines += ["", ("仅检查本地登记，未连接服务器。" if zh else
                    "Local registration only; no server connection was attempted."), ""]
    return "\n".join(lines)
