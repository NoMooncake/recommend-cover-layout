#!/usr/bin/env python3
"""Fetch, shortlist, and preview cover cases from a Feishu document's embedded Base."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any


DEFAULT_DOC_URL = "https://xinyouduzhong.feishu.cn/docx/E7pZdhudNo2glpxILQFcLxBgnEc"
EXPECTED_FIELDS = ("编号", "封面", "关键字", "适用场景")


class LibraryError(RuntimeError):
    pass


def run_cli(args: list[str], cwd: Path | None = None) -> dict[str, Any]:
    if not shutil.which("lark-cli"):
        raise LibraryError("lark-cli is not installed or not on PATH")
    env = os.environ.copy()
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    proc = subprocess.run(
        ["lark-cli", *args],
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise LibraryError(f"lark-cli failed ({proc.returncode}): {detail}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise LibraryError(f"lark-cli returned non-JSON output: {proc.stdout[:500]}") from exc
    if not payload.get("ok"):
        raise LibraryError(json.dumps(payload, ensure_ascii=False))
    return payload


def resolve_base(doc_url: str) -> tuple[str, str]:
    payload = run_cli(["docs", "+fetch", "--doc", doc_url, "--detail", "simple", "--format", "json"])
    content = payload["data"]["document"].get("content", "")
    match = re.search(r'<bitable\b[^>]*\btable-id="([^"]+)"[^>]*\btoken="([^"]+)"', content)
    if not match:
        match = re.search(r'<bitable\b[^>]*\btoken="([^"]+)"[^>]*\btable-id="([^"]+)"', content)
        if not match:
            raise LibraryError("The Feishu document does not contain an embedded Base table")
        base_token, table_id = match.group(1), match.group(2)
        return base_token, table_id
    table_id, base_token = match.group(1), match.group(2)
    return base_token, table_id


def fetch_library(doc_url: str) -> dict[str, Any]:
    base_token, table_id = resolve_base(doc_url)
    schema = run_cli([
        "base", "+field-list", "--base-token", base_token, "--table-id", table_id,
        "--format", "json", "--as", "user",
    ])
    actual_fields = [field.get("name") for field in schema["data"].get("fields", [])]
    missing = [name for name in EXPECTED_FIELDS if name not in actual_fields]
    if missing:
        raise LibraryError(f"Missing expected fields {missing}; actual fields: {actual_fields}")

    args = [
        "base", "+record-list", "--base-token", base_token, "--table-id", table_id,
        "--limit", "200", "--format", "json", "--as", "user",
    ]
    for field in EXPECTED_FIELDS:
        args.extend(["--field-id", field])
    payload = run_cli(args)
    data = payload["data"]
    if data.get("has_more"):
        raise LibraryError("The library exceeds 200 records; pagination support is required before global recommendation")

    records = []
    rows = data.get("data", [])
    record_ids = data.get("record_id_list", [])
    for index, row in enumerate(rows):
        values = dict(zip(EXPECTED_FIELDS, row))
        attachments = values.get("封面") or []
        attachment = attachments[0] if attachments else {}
        records.append({
            "cover_id": str(values.get("编号", "")),
            "record_id": record_ids[index] if index < len(record_ids) else "",
            "file_token": attachment.get("file_token", ""),
            "filename": attachment.get("name", ""),
            "keywords": values.get("关键字") or "",
            "applicable_scene": values.get("适用场景") or "",
        })
    return {"doc_url": doc_url, "base_token": base_token, "table_id": table_id, "records": records}


def visible_length(text: str) -> int:
    return len(re.findall(r"[\u3400-\u9fffA-Za-z0-9]", text))


def analyze_copy(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise LibraryError("Cover copy is empty")
    lengths = [visible_length(line) for line in lines]
    total = sum(lengths)
    if len(lines) > 1:
        probable_lines = len(lines)
    else:
        probable_lines = max(1, min(5, math.ceil(total / 9)))
    if total <= 6:
        length_class = "micro"
    elif total <= 12:
        length_class = "short"
    elif total <= 22:
        length_class = "medium"
    elif total <= 36:
        length_class = "long"
    else:
        length_class = "dense"

    lower = text.lower()
    has_question = bool(re.search(r"[?？]", text)) or any(x in text for x in ("怎么", "如何", "到底", "能不能", "吗"))
    has_exclamation = bool(re.search(r"[!！]", text))
    has_number = bool(re.search(r"\d", text))
    has_list = bool(re.search(r"(^|\s)[1-9][.、)]", text)) or any(x in text for x in ("步骤", "流程", "要点", "招", "个方法"))
    long_short = len(lengths) > 1 and max(lengths) - min(lengths) >= 4

    intent_groups: dict[str, tuple[str, ...]] = {
        "ai-tech": ("ai", "codex", "claude", "skill", "模型", "智能", "自动化"),
        "tutorial": ("教程", "学会", "上手", "攻略", "怎么", "如何", "实操", "零基础", "小白"),
        "problem-solution": ("解决", "修复", "故障", "报错", "焦虑", "失败", "问题", "脏点", "不能", "不再"),
        "result-promise": ("分钟", "一键", "跑通", "做成", "生成", "提升", "告别", "终于", "实测"),
        "product-review": ("测评", "体验", "相机", "设备", "产品", "滤镜", "开源", "键盘"),
        "knowledge": ("方法", "表达", "工作流", "投研", "选题", "内容", "课程", "复盘"),
        "humor-surprise": ("笑疯", "离谱", "震惊", "牛", "居然", "竟然", "太", "？", "?"),
    }
    intents = [name for name, terms in intent_groups.items() if any(term in lower for term in terms)]
    return {
        "original_text": text,
        "explicit_lines": lines,
        "line_lengths": lengths,
        "visible_characters": total,
        "length_class": length_class,
        "probable_lines": probable_lines,
        "long_short_contrast": long_short,
        "has_question_hook": has_question,
        "has_exclamation": has_exclamation,
        "has_number": has_number,
        "has_list_or_steps": has_list,
        "intents": intents,
    }


def score_record(record: dict[str, Any], analysis: dict[str, Any]) -> tuple[float, list[str]]:
    haystack = f"{record['keywords']} {record['applicable_scene']}".lower()
    score = 0.0
    reasons: list[str] = []
    total = analysis["visible_characters"]
    lines = analysis["probable_lines"]

    if lines >= 3 and any(x in haystack for x in ("三行", "四行", "多行", "信息密度", "步骤", "流程")):
        score += 4.0
        reasons.append("多行/高信息密度结构")
    if analysis["long_short_contrast"] and any(x in haystack for x in ("长短", "长句", "短词", "核心钩子")):
        score += 5.0
        reasons.append("长短句节奏")
    if total >= 23 and any(x in haystack for x in ("文字多", "长句", "信息密度", "高信息密度", "多个要点")):
        score += 3.0
        reasons.append("可承载较长文案")
    if total <= 12 and any(x in haystack for x in ("少字", "大字", "超大", "结果型标题", "产品名")):
        score += 2.5
        reasons.append("适合短文案大字")
    if analysis["has_list_or_steps"] and any(x in haystack for x in ("步骤", "流程", "要点", "小点", "便签", "拼贴", "多案例")):
        score += 3.5
        reasons.append("要点/步骤结构")
    if analysis["has_question_hook"] and any(x in haystack for x in ("好奇", "问题", "反常识", "钩子", "痛点", "挑战")):
        score += 2.0
        reasons.append("疑问或好奇钩子")
    if analysis["has_exclamation"] and any(x in haystack for x in ("冲击", "高对比", "夸张", "惊喜", "利益驱动")):
        score += 1.5
        reasons.append("强情绪表达")
    if analysis["has_number"] and any(x in haystack for x in ("时间", "步骤", "流程", "数字", "结果", "要点")):
        score += 1.5
        reasons.append("数字可作为视觉锚点")

    exact_lines = [
        line.lower() for line in analysis["explicit_lines"]
        if visible_length(line) >= 4 and line.lower() in haystack
    ]
    if exact_lines:
        score += min(8.0, 4.0 * len(exact_lines))
        reasons.append("库中描述含相同文案片段")

    def compact(value: str) -> str:
        return "".join(re.findall(r"[\u3400-\u9fffa-z0-9]", value.lower()))

    copy_compact = compact(analysis["original_text"])
    meta_compact = compact(haystack)
    copy_trigrams = {copy_compact[i:i + 3] for i in range(max(0, len(copy_compact) - 2))}
    meta_trigrams = {meta_compact[i:i + 3] for i in range(max(0, len(meta_compact) - 2))}
    shared_trigrams = copy_trigrams & meta_trigrams
    if shared_trigrams:
        lexical_score = min(6.0, len(shared_trigrams) * 0.75)
        score += lexical_score
        reasons.append(f"文案语块重合 {len(shared_trigrams)} 处")

    group_terms: dict[str, tuple[str, ...]] = {
        "ai-tech": ("ai", "codex", "claude", "skill", "技术", "软件"),
        "tutorial": ("教程", "上手", "攻略", "零基础", "小白", "实操", "课程"),
        "problem-solution": ("解决", "修复", "故障", "问题", "痛点", "焦虑", "攻略"),
        "result-promise": ("结果", "承诺", "一键", "跑通", "实测", "告别", "彻底"),
        "product-review": ("测评", "产品", "相机", "设备", "滤镜", "开源", "键盘"),
        "knowledge": ("方法论", "知识", "工作流", "投研", "选题", "内容", "教程"),
        "humor-surprise": ("轻喜剧", "夸张", "好奇", "惊喜", "调侃", "挑战"),
    }
    for intent in analysis["intents"]:
        if any(term in haystack for term in group_terms[intent]):
            score += 2.0
            reasons.append(f"{intent} 主题")

    entities = set(re.findall(r"[a-z][a-z0-9.+-]{1,}", analysis["original_text"].lower()))
    generic = {"ai", "the", "how", "to"}
    exact = sorted(entity for entity in entities - generic if entity in haystack)
    if exact:
        score += min(4.0, 2.0 * len(exact))
        reasons.append("具体产品词匹配: " + ", ".join(exact))

    if not record.get("file_token"):
        score -= 10.0
        reasons.append("缺少可预览图片")
    return score, reasons


def ranked_library(library: dict[str, Any], text: str, top: int) -> dict[str, Any]:
    analysis = analyze_copy(text)
    ranked = []
    for record in library["records"]:
        score, reasons = score_record(record, analysis)
        ranked.append({**record, "preliminary_score": round(score, 2), "score_reasons": reasons})
    ranked.sort(key=lambda item: (-item["preliminary_score"], int(item["cover_id"] or 999999)))
    return {
        "source": {key: library[key] for key in ("doc_url", "base_token", "table_id")},
        "analysis": analysis,
        "candidate_count": len(ranked),
        "shortlist": ranked[:top],
        "note": "Preliminary scores optimize recall. Visually inspect and rerank before answering.",
    }


def safe_filename(record: dict[str, Any]) -> str:
    suffix = Path(record.get("filename") or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        suffix = ".jpg"
    return f"cover-{record['cover_id']}{suffix}"


def download_covers(library: dict[str, Any], cover_ids: list[str], output_dir: str) -> dict[str, Any]:
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    by_id = {record["cover_id"]: record for record in library["records"]}
    downloaded = []
    for cover_id in cover_ids:
        if cover_id not in by_id:
            raise LibraryError(f"Unknown cover ID: {cover_id}")
        record = by_id[cover_id]
        if not record.get("file_token") or not record.get("record_id"):
            raise LibraryError(f"Cover {cover_id} has no downloadable attachment")
        filename = safe_filename(record)
        payload = run_cli([
            "base", "+record-download-attachment",
            "--base-token", library["base_token"],
            "--table-id", library["table_id"],
            "--record-id", record["record_id"],
            "--file-token", record["file_token"],
            "--output", f"./{filename}", "--overwrite", "--format", "json", "--as", "user",
        ], cwd=destination)
        saved = destination / filename
        returned = payload.get("data", {}).get("saved_path")
        if returned:
            saved = Path(returned).resolve()
        downloaded.append({"cover_id": cover_id, "path": str(saved), "keywords": record["keywords"]})
    return {"output_dir": str(destination), "downloaded": downloaded}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doc-url", default=DEFAULT_DOC_URL)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List all live cover records")
    list_parser.add_argument("--doc-url", dest="sub_doc_url")

    recommend_parser = subparsers.add_parser("recommend", help="Analyze copy and return a broad shortlist")
    recommend_parser.add_argument("--doc-url", dest="sub_doc_url")
    recommend_parser.add_argument("--text", required=True, help="Cover copy, or - to read stdin")
    recommend_parser.add_argument("--top", type=int, default=8)

    download_parser = subparsers.add_parser("download", help="Download selected cover examples")
    download_parser.add_argument("--doc-url", dest="sub_doc_url")
    download_parser.add_argument("--cover-id", action="append", required=True)
    download_parser.add_argument("--output-dir", default=".cover-layout-recommendations")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    doc_url = args.sub_doc_url or args.doc_url
    try:
        library = fetch_library(doc_url)
        if args.command == "list":
            result: dict[str, Any] = library
        elif args.command == "recommend":
            text = sys.stdin.read() if args.text == "-" else args.text
            result = ranked_library(library, text, max(1, min(args.top, 20)))
        else:
            result = download_covers(library, args.cover_id, args.output_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except LibraryError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
