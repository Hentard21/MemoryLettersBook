# V23 compact intro test

V23 is an isolated introductory-block derivative. It does not edit the V20
Design Lock, V22, or any family template.

Artifacts:

- `PRINT_V23_COMPACT_INTRO_TEST.pdf` — seven review spreads;
- `interior-compact-v23.html` — generated source;
- `compact-intro-page-plan.json` — cover-excluded production pagination;
- `dom-check.json` — automated browser-layout result;
- `contact-sheet.png` — overview of all seven spreads;
- `renders/` — Poppler renders at 150 ppi.

Page 3 restores the complete project geography: heading, statistics and the
full Russia map share one page. Page 4 contains the verified complete text and
two official facsimile pages of Presidential Decree No. 962. The incorrect
wording from `книга0707.pdf` is retained only as a visual-hierarchy reference
and is never reproduced. The generated still life is explicitly decorative;
the official facsimiles remain the documentary source.

The former welcome-section divider has been replaced by the decree. This keeps
the two TOC pages together as a left/right spread and keeps the first locked
family spread starting on production-interior page 14 (left). The external
cover is not counted as an interior page.

Shumilov, Makarychev and Tengebaeva are compositionally placed on the side from
which their natural gaze points toward the complete address. Their raster
portraits are not mirrored, because mirroring would reverse medals, insignia
and name tapes.

Rebuild and verify in PowerShell:

```powershell
python scripts\build_compact_intro_v23.py
node scripts\check_compact_intro_v23.mjs `
  --input design\prototypes\print-v23\interior-compact-v23.html `
  --output design\prototypes\print-v23\dom-check.json
node scripts\render_print_prototype.mjs `
  --input design\prototypes\print-v23\interior-compact-v23.html `
  --output design\prototypes\print-v23\PRINT_V23_COMPACT_INTRO_TEST.pdf
```
