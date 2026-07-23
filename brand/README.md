# Tawn brand assets

**Identity: Cairn × Sandstone & Lapis** (selected 2026-07-07, exploration round 3).

This directory holds only the finalized assets — pull from here wherever the
brand is needed (web viewer, CLI, Telegram, docs). Exploration history lives in
`docs/brand-exploration/`.

The mark is a cairn — three stones stacked by your own hand so future-you stays
found. *Taw* means "the mark"; every note and decision is a stone on the pile,
and the lapis capstone is the newest mark. The palette is humanity's first
permanent record: marks on sandstone, written in lapis.

## Files

| File | Use |
|---|---|
| `tawn-mark.svg` | Primary mark, light grounds, ≥48 px |
| `tawn-mark-dark.svg` | Primary mark, dark grounds, ≥48 px |
| `tawn-glyph.svg` | Small-size master (ground baked in): 512 Telegram avatar, 192/180 PWA/touch, 32/16 favicon |
| `tawn-wordmark.svg` / `-dark` | Wordmark alone, light / dark grounds |
| `tawn-lockup.svg` / `-dark` | Mark + wordmark horizontal lockup, light / dark grounds |
| `tokens.css` | Full color + type token system (light + dark), shared by web viewer, CLI theme, Telegram asset generation |

## Core rules

- **Lapis is scarce.** Capstone, focused entity, prompt, primary action — nothing else. Never a status color.
- **Wordmark** is the custom-drawn monoline `tawn` in the SVGs above — never retyped in a font; the final **n** takes lapis in full-color versions, whole word ink/bone in one-color contexts. `Tawn` capitalized appears in prose only. General Sans remains the display face for headings/UI.
- **Stones never recolor.** Ink on light, bone on dark. Don't rotate, outline, gradient, or add a fourth stone.
- **Domain hues tag, never flood** — kiln (work), jade (wealth), violet (research), madder (academic). A wealth card is sandstone with a jade chip, not a green card.
- **Warn is the staleness contract** — every fact past TTL renders with `--tawn-warn`.
- Regenerate raster assets from these SVGs; never screenshot-scale.
- Avatar/app-icon ground is always sandstone-night `#191510` — no photos, no gradients.

Exploration history: round 3 (ten candidate marks with paired palettes) in
`../docs/brand-exploration/round3/`; bound-nodes rounds 1–2 in
`../docs/taw-symbol-*.svg` and `../docs/superpowers/taw-symbol-v3.svg`.
