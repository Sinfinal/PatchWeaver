from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.retriever.repair_chain import RepairChainResolver

DEFAULT_FIXTURE_FILES = [
    PROJECT_ROOT / "evaluations" / "fixtures" / "challenge_dev.json",
    PROJECT_ROOT / "evaluations" / "fixtures" / "holdout.json",
    PROJECT_ROOT / "evaluations" / "fixtures" / "contest_samples.json",
    PROJECT_ROOT / "evaluations" / "fixtures" / "source_fetch_stable.json",
]

TRIVIAL_CODE_LINES = {
    "",
    "{",
    "}",
    "(",
    ")",
    "[",
    "]",
    ";",
    "break;",
    "default:",
    "fallthrough;",
    "fallthrough",
}

CONTROL_KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
    "case",
}

SECTION_SLUGS = {
    "基本信息": "basic-info",
    "漏洞描述": "description",
    "官方修补办法": "official-fix",
    "代表性代码差异": "diff-snippets",
    "PatchWeaver 工程记录": "patchweaver",
    "来源证据": "sources",
    "检索标签": "tags",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build RAG-ready CVE corpus from PatchWeaver sources.")
    parser.add_argument("--cve", action="append", dest="cves", help="CVE ID to include. Can be repeated.")
    parser.add_argument(
        "--fixture-file",
        action="append",
        dest="fixture_files",
        type=Path,
        help="Fixture JSON file containing cve_id fields. Can be repeated.",
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=PROJECT_ROOT / "data" / "patchweaver.db",
        help="SQLite database used to locate local task workspaces.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "cache" / "rag_corpus_fetch",
        help="Cache directory for upstream metadata and patch fetches.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "rag_corpus",
        help="Directory where the RAG corpus should be written.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on the number of CVEs to process.",
    )
    return parser.parse_args()


def load_cves(*, explicit_cves: list[str] | None, fixture_files: list[Path] | None, limit: int | None) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    for cve in explicit_cves or []:
        normalized = cve.strip().upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)

    files = fixture_files or DEFAULT_FIXTURE_FILES
    for path in files:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            cve_id = str(item.get("cve_id") or "").strip().upper()
            if not cve_id or cve_id in seen:
                continue
            seen.add(cve_id)
            ordered.append(cve_id)

    return ordered[:limit] if limit else ordered


def load_latest_task_index(database_path: Path) -> dict[str, dict[str, str]]:
    if not database_path.exists():
        return {}

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT task_id, cve_id, workspace_dir, status
            FROM tasks
            ORDER BY updated_at DESC, task_id DESC
            """
        ).fetchall()

    index: dict[str, dict[str, str]] = {}
    for row in rows:
        cve_id = str(row["cve_id"]).strip().upper()
        if cve_id in index:
            continue
        index[cve_id] = {
            "task_id": str(row["task_id"]),
            "workspace_dir": str(row["workspace_dir"]),
            "status": str(row["status"]),
        }
    return index


def safe_json_load(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_if_exists(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def normalize_description(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.split())


def extract_record_title(cvelist_record: dict[str, Any]) -> str | None:
    cna = ((cvelist_record.get("containers") or {}).get("cna") or {})
    title = cna.get("title")
    return title.strip() if isinstance(title, str) and title.strip() else None


def extract_record_description(nvd_record: dict[str, Any], cvelist_record: dict[str, Any]) -> str:
    descriptions = nvd_record.get("descriptions") or []
    for item in descriptions:
        value = item.get("value")
        if isinstance(value, str) and value.strip():
            return normalize_description(value)

    cna = ((cvelist_record.get("containers") or {}).get("cna") or {})
    for item in cna.get("descriptions") or []:
        value = item.get("value")
        if isinstance(value, str) and value.strip():
            return normalize_description(value)
    return ""


def extract_problem_types(cvelist_record: dict[str, Any]) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    cna = ((cvelist_record.get("containers") or {}).get("cna") or {})
    for item in cna.get("problemTypes") or []:
        for description in item.get("descriptions") or []:
            value = str(description.get("description") or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            results.append(value)
    return results


def parse_patch(raw_patch_text: str) -> dict[str, Any]:
    subject = None
    files: list[str] = []
    contexts: list[str] = []
    seen_files: set[str] = set()
    seen_contexts: set[str] = set()
    snippets: list[dict[str, Any]] = []
    in_diff = False
    in_hunk = False

    current_file: str | None = None
    current_context: str | None = None
    current_changes: list[str] = []

    def flush_changes() -> None:
        nonlocal current_changes
        if not current_changes or len(snippets) >= 4:
            current_changes = []
            return
        removed_lines = [line[1:].strip() for line in current_changes if line.startswith("-")]
        added_lines = [line[1:].strip() for line in current_changes if line.startswith("+")]
        snippets.append(
            {
                "file": current_file,
                "context": current_context,
                "changes": current_changes[:12],
                "removed_lines": removed_lines,
                "added_lines": added_lines,
            }
        )
        current_changes = []

    for line in raw_patch_text.splitlines():
        if line.startswith("Subject:") and subject is None:
            subject = re.sub(r"^\[PATCH[^\]]*\]\s*", "", line.removeprefix("Subject:").strip())
            continue
        if line.startswith("diff --git "):
            in_diff = True
            in_hunk = False
            flush_changes()
            parts = line.split()
            if len(parts) >= 4:
                current_file = parts[3][2:] if parts[3].startswith("b/") else parts[3]
                if current_file not in seen_files:
                    seen_files.add(current_file)
                    files.append(current_file)
            current_context = None
            continue
        if not in_diff:
            continue
        if line.startswith("@@"):
            in_hunk = True
            flush_changes()
            match = re.match(r"@@ .* @@\s*(.*)", line)
            current_context = (match.group(1).strip() if match else "") or None
            if current_context and current_context not in seen_contexts:
                seen_contexts.add(current_context)
                contexts.append(current_context)
            continue
        if line.startswith(("+++", "---", "index ", "new file mode ", "deleted file mode ", "rename from ", "rename to ")):
            continue
        if line.startswith(r"\ No newline at end of file"):
            continue
        if not in_hunk:
            continue
        if line.startswith("+") or line.startswith("-"):
            current_changes.append(line)

    flush_changes()

    return {
        "subject": subject or "",
        "files": files,
        "contexts": contexts[:8],
        "snippets": snippets,
    }


def build_repair_actions(patch_info: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    seen: set[str] = set()
    all_removed: list[str] = []
    all_added: list[str] = []
    files: list[str] = []
    contexts: list[str] = []

    for snippet in patch_info.get("snippets") or []:
        all_removed.extend(line for line in snippet.get("removed_lines") or [] if is_meaningful_code_line(line))
        all_added.extend(line for line in snippet.get("added_lines") or [] if is_meaningful_code_line(line))
        file_name = snippet.get("file")
        context = snippet.get("context")
        if isinstance(file_name, str) and file_name and file_name not in files:
            files.append(file_name)
        if isinstance(context, str) and context and context not in contexts:
            contexts.append(context)

    patch_scope = infer_patch_scope(files=files, contexts=contexts)
    for action in infer_patch_level_actions(scope=patch_scope, removed=all_removed, added=all_added):
        if action in seen:
            continue
        seen.add(action)
        actions.append(action)
        if len(actions) >= 4:
            return actions

    for snippet in patch_info.get("snippets") or []:
        file_name = snippet.get("file") or "unknown-file"
        context = snippet.get("context") or "global"
        removed = [line for line in snippet.get("removed_lines") or [] if is_meaningful_code_line(line)]
        added = [line for line in snippet.get("added_lines") or [] if is_meaningful_code_line(line)]
        scope = f"在 `{file_name}` 的 `{context}` 上下文中"

        for action in infer_snippet_actions(scope=scope, context=context, removed=removed, added=added):
            if action in seen:
                continue
            seen.add(action)
            actions.append(action)
            if len(actions) >= 4:
                return actions
        if len(actions) >= 4:
            break
    return actions


def trim_line(text: str, *, limit: int = 96) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def is_meaningful_code_line(text: str) -> bool:
    normalized = " ".join(text.split())
    if normalized in TRIVIAL_CODE_LINES:
        return False
    if re.fullmatch(r"[-+*/=<>!&|%^~?:;,(){}\[\]\s]+", normalized):
        return False
    return bool(normalized)


def extract_calls(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    calls: list[str] = []
    for line in lines:
        for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", line):
            call = match.group(1)
            if call in CONTROL_KEYWORDS or call in seen:
                continue
            seen.add(call)
            calls.append(call)
    return calls


def first_meaningful_line(lines: list[str]) -> str | None:
    for line in lines:
        if is_meaningful_code_line(line):
            return trim_line(line)
    return None


def infer_patch_scope(*, files: list[str], contexts: list[str]) -> str:
    if len(files) == 1 and len(contexts) == 1:
        return f"在 `{files[0]}` 的 `{contexts[0]}` 上下文中"
    if len(files) == 1:
        return f"在 `{files[0]}` 中"
    return "在该补丁中"


def infer_patch_level_actions(*, scope: str, removed: list[str], added: list[str]) -> list[str]:
    actions: list[str] = []
    removed_calls = set(extract_calls(removed))
    added_calls = set(extract_calls(added))
    common_lines = [line for line in removed if line in added]

    if "drm_bridge_add" in removed_calls and "drm_bridge_add" in added_calls:
        actions.append(f"{scope}将 `drm_bridge_add()` 后移到初始化收尾阶段，在 I2C mux 和外围依赖就绪后再注册 bridge。")

    if (
        any("return -EINVAL" in line for line in added)
        and any("NF_" in line or "verdict" in line.lower() for line in removed + added)
    ):
        nf_cases: list[str] = []
        for line in added:
            match = re.search(r"case\s+(NF_[A-Z0-9_]+)\s*:", line)
            if match and match.group(1) not in nf_cases:
                nf_cases.append(match.group(1))
        if nf_cases:
            actions.append(f"{scope}收紧 verdict 参数校验，仅允许 `{', '.join(nf_cases)}` 分支，其余直接返回 `-EINVAL`。")
        else:
            actions.append(f"{scope}补充非法分支拦截逻辑，对异常输入直接返回 `-EINVAL`。")

    for line in common_lines:
        calls = extract_calls([line])
        if not calls:
            continue
        call = calls[0]
        if call == "drm_bridge_add":
            continue
        actions.append(f"{scope}调整 `{call}()` 的调用顺序，使资源初始化与释放顺序保持一致。")
        break

    return actions


def infer_snippet_actions(*, scope: str, context: str, removed: list[str], added: list[str]) -> list[str]:
    actions: list[str] = []
    removed_calls = set(extract_calls(removed))
    added_calls = set(extract_calls(added))
    context_lower = context.lower()

    if (
        "drm_bridge_add" in removed_calls
        and "drm_bridge_add" in added_calls
    ):
        actions.append(f"{scope}将 `drm_bridge_add()` 后移到初始化收尾阶段，在依赖资源就绪后再注册 bridge。")

    if (
        any("return -EINVAL" in line for line in added)
        and any("NF_" in line or "verdict" in line.lower() for line in removed + added)
    ):
        nf_cases: list[str] = []
        for line in added:
            match = re.search(r"case\s+(NF_[A-Z0-9_]+)\s*:", line)
            if match and match.group(1) not in nf_cases:
                nf_cases.append(match.group(1))
        if nf_cases:
            actions.append(f"{scope}收紧 verdict 参数校验，仅允许 `{', '.join(nf_cases)}` 分支，其余直接返回 `-EINVAL`。")
        else:
            actions.append(f"{scope}补充非法分支拦截逻辑，对异常输入直接返回 `-EINVAL`。")

    ret_assignment = next((re.search(r"\bret\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", line) for line in added), None)
    if ret_assignment and any("if (ret)" in line or "return ret" in line for line in added):
        actions.append(
            f"{scope}为 `{ret_assignment.group(1)}()` 增加返回值检查，失败时立即退出，避免后续流程在未完成初始化时继续执行。"
        )

    removed_focus = first_meaningful_line(removed)
    added_focus = first_meaningful_line(added)
    if removed_focus and added_focus and removed_focus == added_focus:
        moved_calls = extract_calls([removed_focus])
        if moved_calls:
            call = moved_calls[0]
            if "remove" in context_lower or "release" in context_lower:
                actions.append(f"{scope}调整 `{call}()` 的清理顺序，使资源回收顺序与对象生命周期一致。")
            else:
                actions.append(f"{scope}调整 `{call}()` 的调用位置，使其与新的初始化顺序保持一致。")

    if not actions and removed_focus and added_focus:
        actions.append(f"{scope}将 `{removed_focus}` 调整为 `{added_focus}`。")
    elif not actions and added_focus:
        actions.append(f"{scope}新增 `{added_focus}`。")
    elif not actions and removed_focus:
        actions.append(f"{scope}移除 `{removed_focus}`。")

    return actions


def find_latest_attempt_no(report_payload: dict[str, Any], workspace_dir: Path) -> int | None:
    build_summary = report_payload.get("build_summary") or {}
    latest_attempt_id = str(build_summary.get("latest_attempt_id") or "").strip()
    match = re.search(r"-A(\d+)$", latest_attempt_id)
    if match:
        return int(match.group(1))

    attempts_dir = workspace_dir / "attempts"
    if not attempts_dir.exists():
        return None
    attempt_nos: list[int] = []
    for item in attempts_dir.iterdir():
        if item.is_dir() and item.name.isdigit():
            attempt_nos.append(int(item.name))
    return max(attempt_nos) if attempt_nos else None


def collect_workspace_artifacts(workspace_dir: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"exists": workspace_dir.exists()}
    if not workspace_dir.exists():
        return result

    report_payload = safe_json_load(workspace_dir / "reports" / "report.json")
    if not isinstance(report_payload, dict):
        report_payload = {}

    latest_attempt_no = find_latest_attempt_no(report_payload, workspace_dir)
    latest_attempt_dir = workspace_dir / "attempts" / f"{latest_attempt_no:03d}" if latest_attempt_no is not None else None

    artifact_paths = {
        "task_context": workspace_dir / "task_context.json",
        "patch_bundle": workspace_dir / "input" / "patch_bundle.json",
        "source_evidence": workspace_dir / "input" / "source_evidence.json",
        "raw_patch": workspace_dir / "input" / "raw_patch.patch",
        "normalized_patch": workspace_dir / "normalized" / "normalized.patch",
        "semantic_card": workspace_dir / "analysis" / "semantic_card.json",
        "constraint_report": workspace_dir / "analysis" / "constraint_report.json",
        "report_json": workspace_dir / "reports" / "report.json",
        "report_md": workspace_dir / "reports" / "report.md",
        "rewrite_plan": latest_attempt_dir / "rewrite" / "rewrite_plan.json" if latest_attempt_dir else None,
        "rewrite_reason": latest_attempt_dir / "rewrite" / "rewrite_reason.json" if latest_attempt_dir else None,
        "rewritten_patch": latest_attempt_dir / "rewrite" / "rewritten.patch" if latest_attempt_dir else None,
        "failure_record": latest_attempt_dir / "logs" / "failure_record.json" if latest_attempt_dir else None,
        "validation_report": latest_attempt_dir / "artifacts" / "validation_report.json" if latest_attempt_dir else None,
    }

    result["latest_attempt_no"] = latest_attempt_no
    result["report"] = report_payload
    result["files"] = {name: str(path) for name, path in artifact_paths.items() if path is not None and path.exists()}
    return result


def copy_workspace_bundle(*, workspace_dir: Path, destination_dir: Path, workspace_payload: dict[str, Any]) -> None:
    for relative_name, source in workspace_payload.get("files", {}).items():
        source_path = Path(source)
        destination_name = source_path.name
        if relative_name in {"rewrite_plan", "rewrite_reason", "rewritten_patch", "failure_record", "validation_report"}:
            destination_name = f"latest_{destination_name}"
        copy_if_exists(source_path, destination_dir / destination_name)


def relative_card_path(output_dir: Path, card_path: Path) -> str:
    return str(card_path.resolve().relative_to(output_dir.resolve())).replace("\\", "/")


def build_card_markdown(
    *,
    cve_id: str,
    title: str,
    description: str,
    problem_types: list[str],
    resolve_payload: dict[str, Any],
    patch_info: dict[str, Any],
    repair_actions: list[str],
    workspace_payload: dict[str, Any],
    metadata_payload: dict[str, Any],
) -> str:
    lines: list[str] = [
        f"# {cve_id} 修复知识卡",
        "",
        "## 基本信息",
        f"- CVE: {cve_id}",
        f"- 标题: {title or '未获取标题'}",
        f"- 漏洞类型: {', '.join(problem_types) if problem_types else '未结构化标注'}",
        f"- 影响文件: {', '.join(metadata_payload.get('affected_files') or []) or '待补充'}",
        f"- 上游提交: {metadata_payload.get('upstream_commit') or 'None'}",
        f"- stable 提交: {metadata_payload.get('stable_commit') or 'None'}",
        "",
        "## 漏洞描述",
        description or "未获取到正式描述。",
        "",
        "## 官方修补办法",
        f"- 补丁主题: {metadata_payload.get('commit_message') or patch_info.get('subject') or '未获取主题'}",
        f"- 代码上下文: {', '.join(patch_info.get('contexts') or []) or '未解析出 hunk 上下文'}",
    ]

    if repair_actions:
        lines.append("- 建议落地动作:")
        for item in repair_actions:
            lines.append(f"  - {item}")
    else:
        lines.append("- 建议落地动作: 当前仅拿到原始补丁，需人工结合 patch hunk 做更细粒度摘要。")

    if patch_info.get("snippets"):
        lines.extend(["", "## 代表性代码差异"])
        for index, snippet in enumerate(patch_info["snippets"][:3], start=1):
            file_name = snippet.get("file") or "unknown-file"
            context = snippet.get("context") or "global"
            lines.append(f"### 差异 {index}: `{file_name}` / `{context}`")
            lines.append("```diff")
            lines.extend(snippet.get("changes") or [])
            lines.append("```")
            lines.append("")

    lines.extend(
        [
            "## PatchWeaver 工程记录",
            f"- 是否命中本地任务: {'是' if workspace_payload.get('exists') else '否'}",
        ]
    )
    if workspace_payload.get("exists"):
        report_payload = workspace_payload.get("report") or {}
        attempt_digest = report_payload.get("attempt_digest") or []
        failure_types = [str(item.get("failure_type") or "") for item in attempt_digest if isinstance(item, dict)]
        failure_types = [item for item in failure_types if item]
        lines.extend(
            [
                f"- 本地任务状态: {metadata_payload.get('task_status') or 'unknown'}",
                f"- 本地任务 ID: {metadata_payload.get('task_id') or 'unknown'}",
                f"- 最新尝试轮: {workspace_payload.get('latest_attempt_no') or 'unknown'}",
                f"- 失败类型轨迹: {', '.join(failure_types) if failure_types else '未记录'}",
                f"- 下一步建议: {report_payload.get('next_action') or '未提供'}",
            ]
        )
        known_limits = report_payload.get("known_limits") or []
        if known_limits:
            lines.append("- 当前限制:")
            for item in known_limits:
                lines.append(f"  - {item}")
    else:
        lines.append("- 当前仓库没有该 CVE 的本地工作区，仅保留官方修复语料。")

    lines.extend(["", "## 来源证据"])
    for item in metadata_payload.get("source_urls") or []:
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## 检索标签",
            f"- subsystem: {metadata_payload.get('subsystem') or 'unknown'}",
            f"- failure_types: {', '.join(metadata_payload.get('failure_types') or []) or 'none'}",
            f"- target_kernel: {metadata_payload.get('target_kernel') or 'unknown'}",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


def infer_subsystem(affected_files: list[str]) -> str:
    if not affected_files:
        return "unknown"
    first = affected_files[0]
    return first.split("/", 1)[0] if "/" in first else first


def build_metadata_payload(
    *,
    cve_id: str,
    title: str,
    description: str,
    problem_types: list[str],
    resolve_payload: dict[str, Any],
    patch_info: dict[str, Any],
    workspace_payload: dict[str, Any],
) -> dict[str, Any]:
    source_evidence = resolve_payload.get("source_evidence") or []
    source_urls = [str(item.url) for item in source_evidence]
    report_payload = workspace_payload.get("report") or {}
    attempt_digest = report_payload.get("attempt_digest") or []
    failure_types = [str(item.get("failure_type") or "") for item in attempt_digest if isinstance(item, dict)]
    failure_types = [item for item in failure_types if item]

    report_summary = report_payload.get("task_summary") or {}
    task_id = report_summary.get("task_id") if isinstance(report_summary, dict) else None
    target_kernel = report_summary.get("target_kernel") if isinstance(report_summary, dict) else None

    return {
        "cve_id": cve_id,
        "title": title,
        "description": description,
        "problem_types": problem_types,
        "commit_message": resolve_payload.get("commit_message") or patch_info.get("subject"),
        "upstream_commit": resolve_payload.get("upstream_commit"),
        "stable_commit": resolve_payload.get("stable_commit"),
        "affected_files": resolve_payload.get("affected_files") or patch_info.get("files") or [],
        "contexts": patch_info.get("contexts") or [],
        "subsystem": infer_subsystem(resolve_payload.get("affected_files") or patch_info.get("files") or []),
        "source_urls": source_urls,
        "task_id": task_id,
        "task_status": report_payload.get("final_status") if isinstance(report_payload, dict) else None,
        "target_kernel": target_kernel,
        "failure_types": failure_types,
        "workspace_available": bool(workspace_payload.get("exists")),
    }


def chunk_card(card_text: str, *, cve_id: str, metadata_payload: dict[str, Any], card_path: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    matches = list(re.finditer(r"^##\s+(.+)$", card_text, flags=re.MULTILINE))
    leading = card_text[: matches[0].start()].strip() if matches else card_text.strip()
    if leading:
        chunks.append(
            {
                "chunk_id": f"{cve_id}#overview#001",
                "cve_id": cve_id,
                "section": "overview",
                "card_path": str(card_path),
                "text": leading,
                "metadata": metadata_payload,
            }
        )

    for index, match in enumerate(matches, start=1):
        title = match.group(1).strip()
        body_start = match.end()
        body_end = matches[index].start() if index < len(matches) else len(card_text)
        body = card_text[body_start:body_end].strip()
        if not body:
            continue
        slug = SECTION_SLUGS.get(title)
        if slug is None:
            fallback = slugify(title)
            slug = fallback if fallback != "section" else f"section-{index:03d}"
        chunks.append(
            {
                "chunk_id": f"{cve_id}#{slug}#{index:03d}",
                "cve_id": cve_id,
                "section": title,
                "card_path": str(card_path),
                "text": f"{title}\n{body}",
                "metadata": metadata_payload,
            }
        )
    return chunks


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return normalized.strip("-") or "section"


def build_readme(*, cves: list[str]) -> str:
    lines = [
        "# PatchWeaver RAG Corpus",
        "",
        "该目录存放可直接进入知识库/向量库的 CVE 修复语料。",
        "",
        "## 目录说明",
        "- `cards/*.md`: 人工可读的 CVE 修复知识卡。",
        "- `cards/*.metadata.json`: 与知识卡对应的结构化元数据。",
        "- `chunks/all_chunks.jsonl`: 推荐直接送入向量数据库的统一切片文件。",
        "- `chunks/<CVE>.jsonl`: 按单个 CVE 拆分的切片文件。",
        "- `raw/<CVE>/official/*`: NVD、cvelistV5、source evidence、原始补丁等官方语料。",
        "- `raw/<CVE>/workspace/*`: 本地 PatchWeaver 任务命中的工程产物，仅在仓库已有任务时出现。",
        "- `manifest.json`: 当前语料清单。",
        "",
        "## 当前语料规模",
        f"- CVE 数量: {len(cves)}",
        f"- CVE 列表: {', '.join(cves)}",
        "",
        "## 建议入库文件",
        "- 首选: `chunks/all_chunks.jsonl`",
        "- 如果需要按漏洞分批导入，可使用 `chunks/<CVE>.jsonl`",
        "",
        "## 重建命令",
        "```powershell",
        r".\.venv\Scripts\python.exe .\scripts\build_rag_corpus.py",
        "```",
        "",
        "## 扩充语料",
        "- 追加指定 CVE: `--cve CVE-2024-1086 --cve CVE-2022-0185`",
        "- 追加新的种子文件: `--fixture-file path\\to\\seed.json`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def build_repair_summary(
    *,
    entries: list[dict[str, Any]],
) -> str:
    lines = [
        "# Linux Kernel CVE Repair Summary",
        "",
        "This file aggregates the repair guidance for each generated knowledge card.",
        "",
    ]

    for entry in entries:
        metadata_payload = entry["metadata"]
        patch_info = entry["patch_info"]
        repair_actions = entry["repair_actions"]
        lines.extend(
            [
                f"## {metadata_payload.get('cve_id')}",
                f"- Title: {metadata_payload.get('title') or ''}",
                f"- Affected files: {', '.join(metadata_payload.get('affected_files') or [])}",
                f"- Card: cards/{entry['card_filename']}",
                "",
                f"- 补丁主题: {metadata_payload.get('commit_message') or patch_info.get('subject') or '未获取主题'}",
                f"- 代码上下文: {', '.join(patch_info.get('contexts') or []) or '未解析出 hunk 上下文'}",
            ]
        )
        if repair_actions:
            lines.append("- 建议落地动作:")
            for item in repair_actions:
                lines.append(f"  - {item}")
        else:
            lines.append("- 建议落地动作: 当前仅拿到原始补丁，需人工结合 patch hunk 做更细粒度摘要。")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    raw_dir = output_dir / "raw"
    cards_dir = output_dir / "cards"
    chunks_dir = output_dir / "chunks"
    raw_dir.mkdir(parents=True, exist_ok=True)
    cards_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    cves = load_cves(explicit_cves=args.cves, fixture_files=args.fixture_files, limit=args.limit)
    task_index = load_latest_task_index(args.database_path.resolve())
    resolver = RepairChainResolver(cache_dir=args.cache_dir.resolve())

    manifest_items: list[dict[str, Any]] = []
    all_chunks: list[dict[str, Any]] = []
    repair_summary_entries: list[dict[str, Any]] = []

    for cve_id in cves:
        cve_root = raw_dir / cve_id
        official_dir = cve_root / "official"
        workspace_dir = cve_root / "workspace"
        official_dir.mkdir(parents=True, exist_ok=True)

        resolve_payload = resolver.resolve(cve_id)
        fetch_trace = resolve_payload.get("fetch_trace") or {}
        nvd_record = resolver._fetch_nvd_record(cve_id)  # noqa: SLF001 - internal project script
        cvelist_record = resolver._fetch_cvelist_record(cve_id)  # noqa: SLF001 - internal project script

        write_json(official_dir / "nvd_record.json", nvd_record)
        write_json(official_dir / "cvelist_record.json", cvelist_record)
        write_json(official_dir / "source_evidence.json", [item.model_dump(mode="json") for item in resolve_payload.get("source_evidence") or []])
        write_json(official_dir / "fetch_trace.json", fetch_trace)
        write_text(official_dir / "raw_patch.patch", str(resolve_payload.get("raw_patch_text") or ""))

        task_row = task_index.get(cve_id)
        workspace_payload = {"exists": False, "files": {}}
        if task_row:
            workspace_payload = collect_workspace_artifacts(Path(task_row["workspace_dir"]))
            if workspace_payload.get("exists"):
                copy_workspace_bundle(
                    workspace_dir=Path(task_row["workspace_dir"]),
                    destination_dir=workspace_dir,
                    workspace_payload=workspace_payload,
                )

        title = extract_record_title(cvelist_record) or str(resolve_payload.get("commit_message") or cve_id)
        description = extract_record_description(nvd_record, cvelist_record)
        problem_types = extract_problem_types(cvelist_record)
        patch_info = parse_patch(str(resolve_payload.get("raw_patch_text") or ""))
        repair_actions = build_repair_actions(patch_info)
        metadata_payload = build_metadata_payload(
            cve_id=cve_id,
            title=title,
            description=description,
            problem_types=problem_types,
            resolve_payload=resolve_payload,
            patch_info=patch_info,
            workspace_payload=workspace_payload,
        )

        card_text = build_card_markdown(
            cve_id=cve_id,
            title=title,
            description=description,
            problem_types=problem_types,
            resolve_payload=resolve_payload,
            patch_info=patch_info,
            repair_actions=repair_actions,
            workspace_payload=workspace_payload,
            metadata_payload=metadata_payload,
        )
        card_path = cards_dir / f"{cve_id}.md"
        metadata_path = cards_dir / f"{cve_id}.metadata.json"
        write_text(card_path, card_text)
        write_json(metadata_path, metadata_payload)

        chunks = chunk_card(card_text, cve_id=cve_id, metadata_payload=metadata_payload, card_path=card_path)
        chunk_path = chunks_dir / f"{cve_id}.jsonl"
        write_text(chunk_path, "\n".join(json.dumps(item, ensure_ascii=False) for item in chunks) + "\n")
        all_chunks.extend(chunks)

        manifest_items.append(
            {
                "cve_id": cve_id,
                "card_path": relative_card_path(output_dir, card_path),
                "metadata_path": relative_card_path(output_dir, metadata_path),
                "chunk_path": relative_card_path(output_dir, chunk_path),
                "task_id": metadata_payload.get("task_id"),
                "workspace_available": metadata_payload.get("workspace_available"),
                "affected_files": metadata_payload.get("affected_files"),
                "upstream_commit": metadata_payload.get("upstream_commit"),
                "stable_commit": metadata_payload.get("stable_commit"),
            }
        )
        repair_summary_entries.append(
            {
                "card_filename": card_path.name,
                "metadata": metadata_payload,
                "patch_info": patch_info,
                "repair_actions": repair_actions,
            }
        )

    write_json(output_dir / "manifest.json", {"items": manifest_items})
    write_text(output_dir / "README.md", build_readme(cves=[item["cve_id"] for item in manifest_items]))
    write_text(output_dir / "repair_summary.md", build_repair_summary(entries=repair_summary_entries))
    write_text(chunks_dir / "all_chunks.jsonl", "\n".join(json.dumps(item, ensure_ascii=False) for item in all_chunks) + "\n")
    print(json.dumps({"status": "passed", "cve_count": len(manifest_items), "output_dir": str(output_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
