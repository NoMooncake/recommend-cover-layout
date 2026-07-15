---
name: recommend-cover-layout
description: Analyze fixed Chinese social-media cover copy and recommend the best matching visual structures from the user's Feishu cover-case library, then download and display the source examples with concrete layout guidance. Use when the user asks for an AI cover assistant, cover layout recommendations, thumbnail/封面排版 references, or wants to reuse collected high-performing cover examples based on wording length, line structure, topic, emotion, information density, or hook style.
---

# AI Cover Layout Assistant

Use the live Feishu library as the source of truth. Recommend structures from existing examples; do not invent a matching library item.

## Workflow

1. Capture the user's finalized cover copy exactly. Preserve explicit line breaks and punctuation. Do not rewrite it unless requested.
2. Run the bundled script to fetch the current Feishu Base and produce a broad shortlist:

   ```bash
   python3 scripts/cover_library.py recommend --text "<cover copy>" --top 8
   ```

   Resolve `scripts/cover_library.py` relative to this skill directory. For multiline text, pass the text through stdin with `--text -` if shell quoting would be fragile.
3. Read [matching-rubric.md](references/matching-rubric.md). Independently rerank the shortlist using the original copy, the script's feature analysis, and each record's real `关键字` and `适用场景`. The script score is recall-oriented, not the final judgment.
4. Select three structurally useful examples when possible. Prefer different viable directions over near-duplicates. Use fewer when the library has fewer honest matches.
5. Download only the selected examples:

   ```bash
   python3 scripts/cover_library.py download --cover-id 35 --cover-id 32 --cover-id 36 --output-dir .cover-layout-recommendations
   ```

6. Display every selected local image with an absolute Markdown image path. Never return only attachment tokens or record IDs.
7. For each recommendation, state:
   - the library cover number and match strength;
   - why its copy structure, visual hierarchy, topic, and emotion fit;
   - exactly how to map the user's existing words into headline, emphasis, support line, and optional badges;
   - what to borrow from the example and what not to copy literally.
8. End with one primary recommendation and a compact layout blueprint. Keep the user's wording unchanged unless they asked for copy editing.

## Commands

List the live library without scoring:

```bash
python3 scripts/cover_library.py list
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
- Prefer cases whose metadata describes layout and use case. Treat source-only descriptions as weaker evidence and verify them from the downloaded image before recommending.
- Do not state that an example has a specific click-through rate unless the library contains that number. Call it a collected reference case instead.
- Do not modify the Feishu library. This skill is read-only.
- If no example fits well, say so, show at most two nearest references, and describe the missing structure that should be added to the library.

## Failure Handling

- If `lark-cli` is unavailable, report that the Feishu CLI dependency is missing.
- If user authentication or scope is missing, surface the CLI's concise authentication guidance; do not switch to bot identity silently.
- If the document no longer contains an embedded Base, report the source document mismatch.
- Expect the fields `编号`, `封面`, `关键字`, and `适用场景`. If they changed, report the actual schema and ask to update the skill rather than guessing column order.
- If an attachment fails to download, keep the textual recommendation but clearly mark that its preview could not be retrieved.
