# Visual annotation schema

Store one human-readable Chinese overview followed by one compact JSON object in the named Feishu Base field `AI结构标注`. The script creates the overview and owns `v` and `file_token`; provide the remaining fields after visually inspecting the current image.

The stored cell must put the readable content first:

```text
【结构概览】顶部两行结果型大标题，人物居中展示设备，底部产品对照。
【文案承载】中等文案｜主标题 2–3 行
【版式位置】上下分区｜主体：人物居中｜可放字：顶部、底部
--- 机器索引（请勿手动修改） ---
{"v":1,"file_token":"...","capacity":"medium",...}
```

The parser remains compatible with legacy cells containing pure JSON. Do not ask users to edit the machine index manually.

## Required shape

```json
{
  "capacity": "medium",
  "line_range": [2, 3],
  "layout": "top_bottom",
  "subject": "center_person",
  "safe_areas": ["top", "bottom"],
  "hierarchy": ["topic", "main_hook", "support"],
  "elements": ["person", "device"],
  "style": ["dark_background", "yellow_white_type", "high_contrast"],
  "hook": ["result_promise", "how_to"],
  "content": ["ai_tool", "tutorial"],
  "ocr": ["合上盖子", "也能运行"],
  "summary": "顶部两行结果型大标题，人物居中展示设备，底部产品对照。"
}
```

## Controlled values

- `capacity`: `micro`, `short`, `medium`, `long`, or `dense`.
- `line_range`: two integers from 0 to 6 describing the practical number of prominent copy lines, excluding account and platform chrome.
- `layout`: prefer `top_only`, `top_bottom`, `left_text_right_subject`, `right_text_left_subject`, `text_around_center_subject`, `bottom_caption`, `full_scene_minimal_text`, or `collage_note_board`.
- `subject`: concise snake-case such as `center_person`, `left_person`, `right_person`, `center_product`, `split_people_product`, `device_center`, `full_scene`, or `collage`.
- `safe_areas`: use spatial terms such as `top`, `bottom`, `left`, `right`, `upper_left`, `upper_right`, `center_overlay`, or `around_subject`.
- `hierarchy`: list generic roles, not the literal wording: `eyebrow`, `topic`, `main_hook`, `emphasis`, `support`, `badge`, `benefit_points`, `steps`, `question_cards`.
- `elements`, `style`, `hook`, and `content`: concise snake-case tags. Reuse existing tags when possible.
- `ocr`: only prominent text that belongs to the cover design. Exclude account names, likes, dates, and platform captions unless the caption is structurally part of the example being modeled.
- `summary`: one Chinese sentence describing reusable composition and hierarchy.

## Annotation rules

1. Inspect the image itself. Use `关键字` and `适用场景` to clarify intent or confirm observations.
2. Describe reusable layout, not the topic alone.
3. Mark screenshot platform captions as `bottom_caption` when the reusable example depends on that region; otherwise exclude them from OCR and line count.
4. Keep arrays small and discriminative. Avoid synonyms that duplicate the same meaning.
5. Do not copy a prior annotation when the attachment `file_token` changed. Reinspect the current image.
