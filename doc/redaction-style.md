# Redaction cover style

Every opaque cover the engine paints on images and flattened PDF pages (detected text, uncertain
areas, faces/codes/plates/signatures/stamps, user-drawn areas) uses one look, defined in
`api/app/documents/redaction_style.py`. Clients that let users draw their own covers should match it.

## Tokens

| Token | Value | Use |
|---|---|---|
| Ink top | `#1E1B4B` | top of the vertical gradient (deep indigo) |
| Ink bottom | `#0F1729` | bottom of the gradient (brand ink, marketing `--text`) |
| Hatch | `#4F46E5` mixed at 22% | 45° diagonal lines, period = max(5 px, height / 3), line = period / 3 |
| Rim | `#6366F1` mixed at 45% | 1 px inner border (keeps covers on adjacent lines visually apart) |
| Label | `#EEF0FF` | entity-type tag, uppercase, font size 0.42 × cover height, only if ≥ 9 px and it fits |
| Pill radius | 0.35 × cover height | text covers |
| Area radius | 0.12 × shorter side, max 14 px | areas; grown by radius / 2 so the corners still contain the box |

All fills are fully opaque. Edges are anti-aliased (4× supersampling) only outside the box that
must be hidden; that box is always forced to 100% fill.

## Text cover geometry (security rules)

- One cover per line run: words of one entity on one line form one shape (no gaps at word
  boundaries); runs of one line closer than two radii merge; a cover never spans two lines.
- Height: normalized per line, from the glyph rows actually measured in the pixels of all the
  words on that OCR line (rows proven empty are dropped; nothing measurable keeps the OCR box),
  plus the existing padding: 15% of the height (≥ 3 px) and, on tilted photos, the tilt margins
  (0.3 × OCR box height left/right, box width / 2 × sin 1° above/below).
- Width: rounded **up** to a multiple of 1.5 × the line's glyph height, plus a jitter in
  [0, 0.2 × glyph height) derived only from the bucket index, so texts of different lengths in
  one bucket get identical widths. Never narrower than the padded text; clipped to the image.
- The extra width goes into free room on the right, then on the left, before visible
  neighbouring words; with no room left it is split evenly (a neighbour may lose a letter).
- Label: the entity type only (NOME, CF, DATA, IBAN, INDIRIZZO, TEL, EMAIL, …), never content;
  omitted when the merged run mixes types, on vertical text, or when it does not fit.

Face blur/pixelate and the uncertain-area behaviour are unchanged; only the fill style differs.
Use `cover_share()` / `visible_ink()` in tests to tell covered pixels from dark ink.
