# V23 editorial back-matter proposal

This isolated review package proposes one new closing spread in the approved
V20 visual language. It does not alter the cover or any family material.

Source copy: `content/production/back-matter.json`.

## Pagination

- append after the final family;
- start on the next even, left-hand page;
- end on the following odd, right-hand page;
- keep the two pages together as one spread;
- final folios are assigned by the production paginator;
- if the preceding section does not end on an odd right-hand page, insert a
  non-content blank before this spread rather than splitting the conclusion.

The canonical reference has 246 PDF pages and no concluding section: its final
page is the physical handwriting of the last family. This proposal is therefore
labelled `От редакции` on both pages and requires manual copy approval before it
is included in the production book.

## Build and verify

```powershell
python scripts\build_back_matter_v23.py
node scripts\check_back_matter_v23.mjs
node scripts\render_print_prototype.mjs `
  --input design\prototypes\print-v23-back-matter\back-matter-v23.html `
  --output output\pdf\PRINT_V23_BACK_MATTER_PROPOSAL.pdf
```
