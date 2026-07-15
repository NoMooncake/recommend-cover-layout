#!/usr/bin/env python3
"""Maintain, shortlist, and preview cover cases from a Feishu document's embedded Base."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
SOURCE_FIELDS = ("编号", "封面", "关键字", "适用场景")
STRUCTURE_FIELD = "AI结构标注"
ANNOTATION_VERSION = 1
MACHINE_INDEX_MARKER = "--- 机器索引（请勿手动修改） ---"
ANNOTATION_REQUIRED = (
    "capacity", "line_range", "layout", "subject", "safe_areas", "hierarchy",
    "elements", "style", "hook", "content", "ocr", "summary",
)
CAPACITY_ORDER = ("micro", "short", "medium", "long", "dense")
CAPACITY_LABELS = {
    "micro": "极少字",
    "short": "少字",
    "medium": "中等文案",
    "long": "较长文案",
    "dense": "多字密集",
}
LAYOUT_LABELS = {
    "top_only": "文字集中在顶部",
    "top_bottom": "上下分区",
    "left_text_right_subject": "左文右人／物",
    "right_text_left_subject": "右文左人／物",
    "text_around_center_subject": "文字环绕中心主体",
    "bottom_caption": "底部标题",
    "full_scene_minimal_text": "完整场景配少量文字",
    "collage_note_board": "拼贴／便签板",
}
SUBJECT_LABELS = {
    "center_person": "人物居中",
    "left_person": "人物偏左",
    "right_person": "人物偏右",
    "center_product": "产品居中",
    "split_people_product": "人物与产品分区",
    "device_center": "设备居中",
    "full_scene": "完整场景",
    "collage": "拼贴画面",
}
AREA_LABELS = {
    "top": "顶部",
    "bottom": "底部",
    "left": "左侧",
    "right": "右侧",
    "upper_left": "左上",
    "upper_center": "上方中部",
    "upper_right": "右上",
    "center_overlay": "中部叠字",
    "around_subject": "主体周围",
    "none": "无明显文字区",
    "note_cards": "便签区域",
}


class LibraryError(RuntimeError):
    pass


def validate_annotation(annotation: dict[str, Any]) -> None:
    missing = [key for key in ANNOTATION_REQUIRED if key not in annotation]
    if missing:
        raise LibraryError(f"Annotation is missing required keys: {missing}")
    if annotation["capacity"] not in CAPACITY_ORDER:
        raise LibraryError(f"Invalid capacity: {annotation['capacity']}")
    line_range = annotation["line_range"]
    if (
        not isinstance(line_range, list) or len(line_range) != 2
        or not all(isinstance(value, int) and 0 <= value <= 6 for value in line_range)
        or line_range[0] > line_range[1]
    ):
        raise LibraryError("line_range must be [min, max] with integers from 0 to 6")
    for key in ("safe_areas", "hierarchy", "elements", "style", "hook", "content", "ocr"):
        if not isinstance(annotation[key], list) or not all(isinstance(value, str) for value in annotation[key]):
            raise LibraryError(f"{key} must be an array of strings")
    for key in ("layout", "subject", "summary"):
        if not isinstance(annotation[key], str) or not annotation[key].strip():
            raise LibraryError(f"{key} must be a non-empty string")


def parse_annotation(raw: Any, current_file_token: str) -> tuple[str, dict[str, Any] | None]:
    if raw is None or raw == "":
        return "missing", None
    if not isinstance(raw, str) or not raw.strip():
        return "invalid", None
    machine_json = raw.split(MACHINE_INDEX_MARKER, 1)[1].strip() if MACHINE_INDEX_MARKER in raw else raw.strip()
    try:
        annotation = json.loads(machine_json)
        if not isinstance(annotation, dict):
            return "invalid", None
        validate_annotation(annotation)
    except (json.JSONDecodeError, LibraryError):
        return "invalid", None
    if annotation.get("v") != ANNOTATION_VERSION:
        return "stale", annotation
    if annotation.get("file_token") != current_file_token:
        return "stale", annotation
    return "valid", annotation


def serialize_annotation(annotation: dict[str, Any]) -> str:
    """Put a readable Chinese summary before the compact machine index."""
    validate_annotation(annotation)
    line_min, line_max = annotation["line_range"]
    line_label = str(line_min) if line_min == line_max else f"{line_min}–{line_max}"
    safe_areas = "、".join(AREA_LABELS.get(value, value) for value in annotation["safe_areas"]) or "未标明"
    readable = [
        f"【结构概览】{annotation['summary']}",
        f"【文案承载】{CAPACITY_LABELS.get(annotation['capacity'], annotation['capacity'])}｜主标题 {line_label} 行",
        (
            f"【版式位置】{LAYOUT_LABELS.get(annotation['layout'], annotation['layout'])}"
            f"｜主体：{SUBJECT_LABELS.get(annotation['subject'], annotation['subject'])}｜可放字：{safe_areas}"
        ),
    ]
    machine_json = json.dumps(annotation, ensure_ascii=False, separators=(",", ":"))
    return "\n".join([*readable, MACHINE_INDEX_MARKER, machine_json])


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
    missing = [name for name in SOURCE_FIELDS if name not in actual_fields]
    if missing:
        raise LibraryError(f"Missing expected fields {missing}; actual fields: {actual_fields}")

    structure_field_present = STRUCTURE_FIELD in actual_fields
    query_fields = list(SOURCE_FIELDS)
    if structure_field_present:
        query_fields.append(STRUCTURE_FIELD)

    args = [
        "base", "+record-list", "--base-token", base_token, "--table-id", table_id,
        "--limit", "200", "--format", "json", "--as", "user",
    ]
    for field in query_fields:
        args.extend(["--field-id", field])
    payload = run_cli(args)
    data = payload["data"]
    if data.get("has_more"):
        raise LibraryError("The library exceeds 200 records; pagination support is required before global recommendation")

    records = []
    rows = data.get("data", [])
    record_ids = data.get("record_id_list", [])
    for index, row in enumerate(rows):
        values = dict(zip(query_fields, row))
        attachments = values.get("封面") or []
        attachment = attachments[0] if attachments else {}
        file_token = attachment.get("file_token", "")
        annotation_raw = values.get(STRUCTURE_FIELD) or ""
        annotation_status, annotation = parse_annotation(annotation_raw, file_token)
        records.append({
            "cover_id": str(values.get("编号", "")),
            "record_id": record_ids[index] if index < len(record_ids) else "",
            "file_token": file_token,
            "filename": attachment.get("name", ""),
            "keywords": values.get("关键字") or "",
            "applicable_scene": values.get("适用场景") or "",
            "annotation_status": annotation_status if structure_field_present else "field_missing",
            "structure_annotation": annotation,
        })
    return {
        "doc_url": doc_url,
        "base_token": base_token,
        "table_id": table_id,
        "structure_field_present": structure_field_present,
        "records": records,
    }


def audit_library(library: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, list[str]] = {status: [] for status in ("valid", "missing", "stale", "invalid", "field_missing")}
    for record in library["records"]:
        groups.setdefault(record["annotation_status"], []).append(record["cover_id"])
    return {
        "structure_field": STRUCTURE_FIELD,
        "field_present": library["structure_field_present"],
        "total": len(library["records"]),
        "counts": {status: len(ids) for status, ids in groups.items()},
        "records": groups,
        "ready": len(groups["valid"]) == len(library["records"]),
    }


def ensure_structure_field(doc_url: str) -> dict[str, Any]:
    library = fetch_library(doc_url)
    if library["structure_field_present"]:
        return {"created": False, "field": STRUCTURE_FIELD, "message": "Field already exists"}
    payload = run_cli([
        "base", "+field-create",
        "--base-token", library["base_token"],
        "--table-id", library["table_id"],
        "--json", json.dumps({
            "name": STRUCTURE_FIELD,
            "type": "text",
            "description": "上方为中文结构概览，下方为 Agent 机器索引；按字段名读取。",
        }, ensure_ascii=False),
        "--format", "json", "--as", "user",
    ])
    return {"created": True, "field": STRUCTURE_FIELD, "result": payload.get("data", {})}


def annotate_cover(
    doc_url: str,
    cover_id: str,
    annotation_json: str,
    force: bool = False,
) -> dict[str, Any]:
    ensure_structure_field(doc_url)
    library = fetch_library(doc_url)
    by_id = {record["cover_id"]: record for record in library["records"]}
    if cover_id not in by_id:
        raise LibraryError(f"Unknown cover ID: {cover_id}")
    return write_annotation(library, by_id[cover_id], annotation_json, force)


def write_annotation(
    library: dict[str, Any],
    record: dict[str, Any],
    annotation_json: str,
    force: bool = False,
) -> dict[str, Any]:
    cover_id = record["cover_id"]
    if record["annotation_status"] == "valid" and not force:
        return {"updated": False, "cover_id": cover_id, "message": "Valid annotation already exists"}
    try:
        annotation = json.loads(annotation_json)
    except json.JSONDecodeError as exc:
        raise LibraryError(f"Annotation is not valid JSON: {exc}") from exc
    if not isinstance(annotation, dict):
        raise LibraryError("Annotation must be a JSON object")
    annotation.pop("v", None)
    annotation.pop("file_token", None)
    annotation.pop("annotated_at", None)
    validate_annotation(annotation)
    annotation = {
        "v": ANNOTATION_VERSION,
        "file_token": record["file_token"],
        "annotated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **annotation,
    }
    payload = run_cli([
        "base", "+record-upsert",
        "--base-token", library["base_token"],
        "--table-id", library["table_id"],
        "--record-id", record["record_id"],
        "--json", json.dumps({STRUCTURE_FIELD: serialize_annotation(annotation)}, ensure_ascii=False),
        "--format", "json", "--as", "user",
    ])
    return {
        "updated": True,
        "cover_id": cover_id,
        "record_id": record["record_id"],
        "annotation": annotation,
        "result": payload.get("data", {}),
    }


def format_index(doc_url: str) -> dict[str, Any]:
    """Rewrite valid annotations into the readable display format without reanalysis."""
    library = fetch_library(doc_url)
    audit = audit_library(library)
    if not audit["ready"]:
        raise LibraryError(
            "Cannot reformat an incomplete or stale index: "
            + json.dumps(audit["records"], ensure_ascii=False)
        )
    results = []
    for record in library["records"]:
        annotation = record["structure_annotation"]
        payload = run_cli([
            "base", "+record-upsert",
            "--base-token", library["base_token"],
            "--table-id", library["table_id"],
            "--record-id", record["record_id"],
            "--json", json.dumps({STRUCTURE_FIELD: serialize_annotation(annotation)}, ensure_ascii=False),
            "--format", "json", "--as", "user",
        ])
        results.append({
            "cover_id": record["cover_id"],
            "record_id": record["record_id"],
            "updated": True,
            "result": payload.get("data", {}),
        })
    return {"updated": len(results), "results": results}


def annotate_batch(doc_url: str, annotations_json: str, force: bool = False) -> dict[str, Any]:
    ensure_structure_field(doc_url)
    library = fetch_library(doc_url)
    try:
        annotations = json.loads(annotations_json)
    except json.JSONDecodeError as exc:
        raise LibraryError(f"Batch annotations are not valid JSON: {exc}") from exc
    if not isinstance(annotations, dict):
        raise LibraryError("Batch annotations must be an object mapping cover IDs to annotation objects")
    by_id = {record["cover_id"]: record for record in library["records"]}
    results = []
    for cover_id, annotation in annotations.items():
        cover_id = str(cover_id)
        if cover_id not in by_id:
            raise LibraryError(f"Unknown cover ID in batch: {cover_id}")
        if not isinstance(annotation, dict):
            raise LibraryError(f"Annotation for cover {cover_id} must be an object")
        results.append(write_annotation(
            library,
            by_id[cover_id],
            json.dumps(annotation, ensure_ascii=False),
            force,
        ))
    return {
        "requested": len(annotations),
        "updated": sum(1 for result in results if result.get("updated")),
        "skipped": sum(1 for result in results if not result.get("updated")),
        "results": results,
    }


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
    annotation = record.get("structure_annotation") or {}
    annotation_text = json.dumps(annotation, ensure_ascii=False)
    haystack = f"{annotation_text} {record['keywords']} {record['applicable_scene']}".lower()
    score = 0.0
    reasons: list[str] = []
    total = analysis["visible_characters"]
    lines = analysis["probable_lines"]

    candidate_capacity = annotation.get("capacity")
    if candidate_capacity in CAPACITY_ORDER:
        distance = abs(CAPACITY_ORDER.index(analysis["length_class"]) - CAPACITY_ORDER.index(candidate_capacity))
        if distance == 0:
            score += 5.0
            reasons.append("文案容量完全匹配")
        elif distance == 1:
            score += 2.0
            reasons.append("文案容量相近")
        else:
            score -= min(4.0, float(distance))
            reasons.append("文案容量存在差距")
    line_range = annotation.get("line_range")
    if isinstance(line_range, list) and len(line_range) == 2:
        if line_range[0] <= lines <= line_range[1]:
            score += 4.0
            reasons.append("主文案行数匹配")
        else:
            line_distance = min(abs(lines - line_range[0]), abs(lines - line_range[1]))
            score -= min(3.0, float(line_distance))
            reasons.append("主文案行数需调整")

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

    hook_map: dict[str, tuple[str, ...]] = {
        "tutorial": ("how_to", "tutorial"),
        "problem-solution": ("problem_solution", "pain_relief", "choice_anxiety"),
        "result-promise": ("result_promise", "time_promise", "benefit"),
        "product-review": ("product_demo", "comparison", "novelty"),
        "knowledge": ("authority", "knowledge", "method"),
        "humor-surprise": ("humor", "surprise", "contrarian", "curiosity"),
    }
    annotation_hooks = set(annotation.get("hook") or [])
    for intent in analysis["intents"]:
        if annotation_hooks.intersection(hook_map.get(intent, ())):
            score += 2.5
            reasons.append(f"{intent} 钩子匹配")

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
    audit = audit_library(library)
    if not audit["ready"]:
        raise LibraryError(
            "Library annotations are incomplete or stale. Run `audit`, visually annotate affected covers, then retry: "
            + json.dumps(audit["records"], ensure_ascii=False)
        )
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
        "note": "Preliminary scores use the standardized visual index and optimize recall. Visually inspect and rerank before answering.",
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

    audit_parser = subparsers.add_parser("audit", help="Audit visual annotation coverage and freshness")
    audit_parser.add_argument("--doc-url", dest="sub_doc_url")

    ensure_parser = subparsers.add_parser("ensure-field", help=f"Create the named {STRUCTURE_FIELD} field when absent")
    ensure_parser.add_argument("--doc-url", dest="sub_doc_url")

    format_parser = subparsers.add_parser("format-index", help="Put readable Chinese summaries above machine indexes")
    format_parser.add_argument("--doc-url", dest="sub_doc_url")

    annotate_parser = subparsers.add_parser("annotate", help="Write one visually verified structure annotation")
    annotate_parser.add_argument("--doc-url", dest="sub_doc_url")
    annotate_parser.add_argument("--cover-id", required=True)
    annotate_parser.add_argument("--annotation", required=True, help="JSON object, or - to read stdin")
    annotate_parser.add_argument("--force", action="store_true", help="Overwrite a currently valid annotation")

    batch_parser = subparsers.add_parser("annotate-batch", help="Serially write a cover-ID to annotation JSON map")
    batch_parser.add_argument("--doc-url", dest="sub_doc_url")
    batch_parser.add_argument("--input", required=True, help="JSON file path, or - to read stdin")
    batch_parser.add_argument("--force", action="store_true", help="Overwrite currently valid annotations")

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
        if args.command == "ensure-field":
            result = ensure_structure_field(doc_url)
        elif args.command == "format-index":
            result = format_index(doc_url)
        elif args.command == "annotate":
            annotation_json = sys.stdin.read() if args.annotation == "-" else args.annotation
            result = annotate_cover(doc_url, args.cover_id, annotation_json, args.force)
        elif args.command == "annotate-batch":
            annotations_json = sys.stdin.read() if args.input == "-" else Path(args.input).expanduser().read_text()
            result = annotate_batch(doc_url, annotations_json, args.force)
        else:
            library = fetch_library(doc_url)
            if args.command == "list":
                result = library
            elif args.command == "audit":
                result = audit_library(library)
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
