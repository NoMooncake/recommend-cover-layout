# Matching rubric

Use this rubric after the script returns a recall-oriented shortlist. The final answer should reflect visual judgment, not merely the numeric script score.

## Priority order

1. Copy shape (35%): total visible characters, intended line count, longest line, long-short contrast, and whether the example has enough text-safe area.
2. Information hierarchy (25%): one hook versus multiple points; headline/support/badge relationships; whether numbers, product names, or contrast words need separate emphasis.
3. Topic and object needs (15%): tutorial, product, software, finance, knowledge, story, review, or problem-solving; required person, device, screenshot, product, or scene.
4. Emotion and hook (15%): curiosity, surprise, urgency, authority, humor, pain relief, result promise, or calm explanation.
5. Visual feasibility (10%): subject placement, contrast, background complexity, and whether the exact copy remains legible on a phone feed.

Do not let topic overlap override a severe copy-shape mismatch.

## Copy-shape classes

- Micro: 1–6 visible characters. Favor a single oversized phrase and a strong image.
- Short: 7–12 characters. Favor one or two large lines.
- Medium: 13–22 characters. Favor two to three levels or a headline plus support line.
- Long: 23–36 characters. Favor three to four lines, long-short rhythm, or a separated explanation strip.
- Dense: more than 36 characters or multiple explicit points. Favor a step strip, badges, notes, or a collage; do not force all text into one headline block.

For Chinese copy, count Chinese characters, Latin letters, and digits as visible characters; ignore spaces and ordinary punctuation.

## Match labels

- Strong: structure and emotion both fit; only content substitution is needed.
- Good: the hierarchy fits, with one visible adjustment such as moving the subject or splitting a long line.
- Exploratory: useful inspiration but requires meaningful structural adaptation.

Never call a topical match Strong when the user's longest line cannot fit the example's main text area.

## Output pattern

Start with a one-sentence diagnosis of the copy: length class, probable lines, hook, and emotion.

For each selected example:

1. Show the image.
2. Give `案例 #编号 · Strong/Good/Exploratory`.
3. Explain the structural match in one short paragraph.
4. Provide a mapping such as:

   ```text
   主标题：……
   强调词：……
   辅助行：……
   画面主体：……
   ```

5. Name one concrete risk, such as excessive line length, subject collision, or weak contrast.

Finish with `首选：案例 #编号` and a compact blueprint. Do not rewrite finalized copy unless requested.
