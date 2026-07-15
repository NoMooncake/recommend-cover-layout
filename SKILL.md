---
name: recommend-cover-layout
description: Maintain an automatic visual-structure index for the user's Feishu cover-case library, analyze fixed Chinese social-media cover copy, recommend the best matching layouts, and display source examples with concrete placement guidance. Use when the user asks for an AI cover assistant, cover layout recommendations, thumbnail/封面排版 references, visual indexing of newly collected covers, or wants to reuse high-performing examples based on wording length, line structure, topic, emotion, information density, or hook style.
---

# AI Cover Layout Assistant

Use the live Feishu library as the source of truth. Maintain the named `AI结构标注` field as a visual index; do not rely on its column position. Keep its human-readable Chinese overview at the top and its machine JSON index below the marker. Recommend structures from existing examples and do not invent a matching library item.

## Workflow

1. Capture the user's finalized cover copy exactly. Preserve explicit line breaks and punctuation. Do not rewrite it unless requested.
2. Audit the live library before every recommendation:

   ```bash
   python3 scripts/cover_library.py audit
   ```

   The parser accepts both legacy pure JSON cells and the current Chinese-first display format.

3. If `missing`, `stale`, or `invalid` annotations exist, complete them before recommending:
   - Run `python3 scripts/cover_library.py ensure-field` if the named field is absent.
   - Download only the affected covers.
   - Visually inspect each image and read [annotation-schema.md](references/annotation-schema.md).
   - Use existing `关键字` and `适用场景` as supporting evidence, not as a substitute for looking at the image.
   - Write a schema-valid annotation with `annotate`; the script inserts the current image token and schema version. Never overwrite a valid annotation unless the image changed or the user explicitly requests a reanalysis.

   ```bash
   python3 scripts/cover_library.py annotate --cover-id 46 --annotation '<JSON object>'
   ```

4. Run the bundled script to produce a broad shortlist only after the audit is complete:

   ```bash
   python3 scripts/cover_library.py recommend --text "<cover copy>" --top 8
   ```

   Resolve `scripts/cover_library.py` relative to this skill directory. For multiline text, pass the text through stdin with `--text -` if shell quoting would be fragile.
5. Read [matching-rubric.md](references/matching-rubric.md). Independently rerank the shortlist using the original copy, the script's feature analysis, `AI结构标注`, and the source metadata. The script score is recall-oriented, not the final judgment.
6. Select three structurally useful examples when possible. Prefer different viable directions over near-duplicates. Use fewer when the library has fewer honest matches.
7. Download only the selected examples:

   ```bash
   python3 scripts/cover_library.py download --cover-id 35 --cover-id 32 --cover-id 36 --output-dir .cover-layout-recommendations
   ```

8. Display every selected local image with an absolute Markdown image path. Never return only attachment tokens or record IDs.
9. For each recommendation, state:
   - the library cover number and match strength;
   - why its copy structure, visual hierarchy, topic, and emotion fit;
   - exactly how to map the user's existing words into headline, emphasis, support line, and optional badges;
   - what to borrow from the example and what not to copy literally.
10. End with one primary recommendation and a compact layout blueprint. Keep the user's wording unchanged unless they asked for copy editing.

## Commands

List the live library without scoring:

```bash
python3 scripts/cover_library.py list
```

Audit annotation coverage and image-token freshness:

```bash
python3 scripts/cover_library.py audit
```

Reformat valid legacy cells so Chinese explanations appear before machine fields, without reanalyzing images:

```bash
python3 scripts/cover_library.py format-index
```

Read cover copy from stdin:

```bash
printf '%s' "<cover copy>" | python3 scripts/cover_library.py recommend --text - --top 8
```

Override the configured source only when the user provides another Feishu document:

```bash
python3 scripts/cover_library.py recommend --doc-url "<docx URL>" --text "<cover copy>"
```

## Recommendation Rules

- Weight copy-shape compatibility above topical similarity. A thematically similar cover with the wrong amount of text is a weak match.
- Treat explicit user line breaks as intentional. If there are none, recommend a line split rather than assuming the copy is one visual line.
- Use image composition to resolve conflicts: check whether the example reserves enough space for the user's longest line and required subject.
- Give the standardized `AI结构标注` more weight than free-form source metadata. Treat `关键字` and `适用场景` as supporting evidence.
- Treat an annotation as stale when its stored image token differs from the current attachment token; reanalyze the image before matching.
- Do not state that an example has a specific click-through rate unless the library contains that number. Call it a collected reference case instead.
- Modify only the named `AI结构标注` field for annotation maintenance. Do not alter source images, keywords, applicable scenes, or other fields.
- Keep the field readable for people: write `结构概览`, `文案承载`, and `版式位置` in Chinese first; keep compact JSON only below `--- 机器索引（请勿手动修改） ---`.
- If no example fits well, say so, show at most two nearest references, and describe the missing structure that should be added to the library.

## Failure Handling

- If `lark-cli` is unavailable, report that the Feishu CLI dependency is missing.
- If user authentication or scope is missing, surface the CLI's concise authentication guidance; do not switch to bot identity silently.
- If the document no longer contains an embedded Base, report the source document mismatch.
- Expect the source fields `编号`, `封面`, `关键字`, and `适用场景`; create or maintain the named `AI结构标注` field. If source fields changed, report the actual schema rather than guessing column order.
- If an attachment fails to download, keep the textual recommendation but clearly mark that its preview could not be retrieved.
