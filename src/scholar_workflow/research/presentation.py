"""Human-readable research subscriptions and incremental observations."""
from __future__ import annotations

import html
from datetime import datetime
from urllib.parse import quote

_KINDS = {"rss": ("RSS", "RSS"), "atom": ("Atom", "Atom"),
          "webpage": ("指定网页", "Selected webpage"),
          "github_releases": ("代码发布", "Code releases"),
          "hf_models": ("模型列表", "Model list")}
_STATES = {"new": ("新增", "New"), "updated": ("内容变化", "Changed"),
           "discovered": ("首次发现", "Initially discovered"),
           "unread": ("未读", "Unread"), "read": ("已读", "Read"),
           "selected": ("已选待归档", "Selected, not archived"),
           "ignored": ("已忽略", "Ignored"), "failed": ("检查失败", "Check failed"),
           "baseline": ("已建立基线", "Baseline recorded"),
           "observed": ("已检查", "Checked"), "not_modified": ("未变", "Not modified"),
           "unchanged": ("无变更", "Unchanged"), "available": ("可查询", "Available"),
           "uninitialized": ("尚未登记", "Not initialized"),
           "not_checked": ("尚未检查", "Not checked"),
           "configuration_changed": ("配置已变，待重查", "Configuration changed; check again"),
           "disabled": ("已停用", "Disabled"), "invalid": ("记录无效", "Invalid records"),
           "unavailable": ("不可用", "Unavailable"), "partial": ("部分失败", "Partial failure"),
           "created": ("已登记", "Registered"), "enabled": ("已启用", "Enabled")}
_REASONS = {
    "network_error": ("网络请求失败", "Network request failed"),
    "http_error": ("来源返回错误响应", "Unsuccessful source response"),
    "limit_exceeded": ("超过本次读取范围，未提交部分结果", "Acquisition limit reached; partial results not committed"),
    "incomplete_pagination": ("分页未完整读完", "Incomplete pagination"),
    "unsafe_url": ("地址不符合公开 HTTPS 边界", "URL outside public HTTPS boundary"),
    "invalid_response": ("来源响应格式不受支持或缺项", "Malformed or incomplete source response"),
    "unsafe_xml": ("XML 包含不允许的实体声明", "Disallowed XML declarations"),
    "unsupported_content": ("页面没有可读取的正文或格式不受支持", "Unsupported content or no readable text"),
    "invalid_channel": ("渠道配置不符合读取要求", "Invalid channel configuration"),
    "unsupported_proxy": ("代理类型不受支持，未绕过代理直连", "Unsupported proxy scheme; no direct fallback"),
    "unsupported_client": ("调用客户端不符合安全要求，未读取来源", "Client cannot provide safe acquisition"),
    "baseline_required": ("首次收到未变响应，仍需完整基线", "Unchanged response without a baseline"),
    "acquisition_failed": ("未能完整读取来源", "Source acquisition incomplete"),
}


def cell(value: object) -> str:
    text = html.escape(" ".join(str(value if value is not None else "—").split()))
    for character in ("\\", "|", "[", "]", "*", "_", "`"):
        text = text.replace(character, "\\" + character)
    return text


def label(value: str, zh: bool) -> str:
    return _STATES.get(value, ("待检查", "Not checked"))[0 if zh else 1]


def link(title: str, url: str) -> str:
    return f"[{cell(title)}]({quote(url, safe=':/?&=%~+-._')})"


def sources_markdown(payload: dict, *, language: str = "zh") -> str:
    zh = language == "zh"
    lines = ["# 研究来源" if zh else "# Research sources", ""]
    channels = payload.get("channels", [])
    if not channels and payload.get("channel"):
        channels = [payload["channel"]]
    lines += [("登记状态：" if zh else "Registration: ") +
              label(payload.get("status", "available"), zh), ""]
    if payload.get("status") in {"invalid", "unavailable"}:
        lines += ["登记无法读取，不能判断有哪些渠道；本次没有初始化或修改记录。" if zh else
                  "Cannot determine registered channels from the invalid records; no records were initialized or changed.", ""]
        return "\n".join(lines)
    if not channels:
        lines += ["尚无已登记渠道。查询没有创建记录。" if zh else
                  "No registered channels. This read did not initialize records.", ""]
    else:
        columns = (["渠道", "发布者", "类型", "关注方向", "状态"] if zh else
                   ["Channel", "Publisher", "Type", "Interests", "State"])
        lines += ["| " + " | ".join(columns) + " |", "|" + " --- |" * len(columns)]
        for row in channels:
            values = [link(row["name"], row["url"]), cell(row["publisher"]),
                      cell(_KINDS.get(row["kind"], (row["kind"], row["kind"]))[0 if zh else 1]),
                      cell(", ".join(row.get("topics", [])) or "—"),
                      label("enabled" if row.get("enabled", True) else "disabled", zh)]
            lines.append("| " + " | ".join(values) + " |")
        lines.append("")
    if payload.get("diagnostics"):
        lines += ["部分登记无法读取；请检查机器响应中的诊断。" if zh else
                  "Some records are unavailable; inspect diagnostics in the JSON response.", ""]
    lines += ["登记不等于已检查，也不会自动归档、下载模型或运行代码。" if zh else
              "Registration is not a successful check, ingestion, model download or code execution.", ""]
    return "\n".join(lines)


def updates_markdown(payload: dict, *, language: str = "zh") -> str:
    zh = language == "zh"
    lines = ["# 研究动态" if zh else "# Research updates", ""]
    if payload.get("status") in {"invalid", "unavailable"}:
        lines += ["登记或动态记录无法读取，不能将其当作空列表。请先修复记录。" if zh else
                  "Source or observation records cannot be read. This is not an empty result; repair the records first.", ""]
        return "\n".join(lines)
    channels = payload.get("channels", [])
    checks = {row["channel_id"]: row for row in payload.get("check_results", [])}
    names = {row["channel_id"]: row for row in channels}
    lines += ["## 来源检查" if zh else "## Source checks", ""]
    if not channels:
        lines += ["尚无已登记渠道。" if zh else "No registered channels.", ""]
    else:
        columns = (["渠道", "状态", "最后成功检查", "说明"] if zh else
                   ["Channel", "State", "Last successful check", "Detail"])
        lines += ["| " + " | ".join(columns) + " |", "| --- | --- | --- | --- |"]
        for row in channels:
            check = checks.get(row["channel_id"], {})
            state = "disabled" if not row.get("enabled", True) else check.get("status", row.get("status", ""))
            if state == "uninitialized":
                state = "not_checked"
            diagnostic = row.get("diagnostic") or {}
            reason = _REASONS.get(diagnostic.get("code"), ("—", "—"))[0 if zh else 1]
            lines.append("| " + " | ".join([
                link(row["name"], row["url"]), label(state, zh),
                cell(row.get("last_success_at")), reason]) + " |")
        lines.append("")
    if any(check.get("status") == "baseline" for check in checks.values()):
        lines += ["首次检查只为本次可见内容建立基线，不代表已覆盖全部历史。" if zh else
                  "The first check records this observed window, not all historical content.", ""]
    if any(check.get("status") == "failed" for check in checks.values()) or any(
            row.get("status") == "failed" for row in channels):
        lines += ["检查失败的渠道仍保留旧记录；失败不表示没有更新。详情见 JSON 诊断。" if zh else
                  "Failed channels retain previous observations. Failure does not mean no updates; see JSON diagnostics.", ""]
    events = payload.get("events", [])
    lines += ["## 动态" if zh else "## Updates", ""]
    if not events:
        lines += ["本次没有可列出的动态。请结合上方基线、检查状态和范围判断。" if zh else
                  "No events to list in this result. Check the baseline, status and observation scope above.", ""]
    else:
        columns = (["发现时间", "发布者／渠道", "资料", "变化", "处理"] if zh else
                   ["Observed", "Publisher / channel", "Resource", "Change", "Disposition"])
        lines += ["| " + " | ".join(columns) + " |", "|" + " --- |" * len(columns)]
        for event in sorted(events, key=lambda item: datetime.fromisoformat(item["observed_at"]),
                            reverse=True):
            item = event["item"]
            source = event.get("source") or names.get(event["channel_id"], {})
            values = [cell(event.get("observed_at")),
                      cell(" / ".join(filter(None, [source.get("publisher"), source.get("name")]))) or "—",
                      link(item["title"], item["url"]), label(event["kind"], zh),
                      label(event.get("disposition", "unread"), zh)]
            lines.append("| " + " | ".join(values) + " |")
        lines.append("")
    lines += ["内容变化待审阅，不等于科学进步、模型已开放或已验证。选中不等于已归档。" if zh else
              "Changes require review; they do not prove scientific progress, model availability or validation. Selected is not archived.", ""]
    return "\n".join(lines)
