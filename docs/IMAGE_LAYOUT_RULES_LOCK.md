# Image layout rules lock

Status: locked for the V21 mass-layout draft. These rules implement the approved V20 visual system; they do not create a new design.

## Source priority

1. A family may use only assets listed in its canonical `content/production/families/<hero_id>.json` manifest.
2. A manually approved transparent flagship is preferred over its white-background production source. The master is never overwritten.
3. Archive photographs retain their background by default. Drawings and handwriting remain documentary assets.
4. A missing or disputed asset is recorded as `review_required`; another family's image is never substituted.

## Flagship placement

- Use only the approved hero flagship on the family opening page.
- Place it with `contain`, approximately waist-up, anchored to the page bottom in the manner of the approved Anastasia/Evgeny templates.
- Cropping is permitted only below the waist or at the outer clothing edge. Faces, hair, hands, awards, patches, weapons, straps and held objects must remain intact.
- Transparent PNG is allowed only after manual or CutItOut QA. Automatic background removal is not applied to archive photographs.
- The title, region line, map, emblem, award and quotation stay outside the face area and the 22 mm inner safe zone.

## Archive photographs and drawings

- Layout selection uses aspect ratio and item count. `contain` is the default; `cover` is prohibited unless a manually recorded crop is face-safe.
- One or two strong images may be larger. Low-resolution or large-group images are intentionally smaller.
- Three to five items use a balanced grid. More items trigger the extended template or a continuation page.
- Photographs never touch without a visible paper/background interval. Captions may bridge a photograph and the surrounding text only when they do not cover a face.
- A drawing is never treated as a photograph. It keeps a light neutral background and the child's original line quality.

## Handwriting and transcription

- Every registered physical manuscript is shown as a visible scan and is paired with its clean reader transcription.
- The scan may also appear as a quiet background texture, but the visible evidence image cannot be replaced by texture alone.
- Public text uses `…` for an unreadable or lost fragment. Editorial brackets and review markers stay in the hidden ledger/report.
- Body transcription text must remain at least 11 pt in the mass draft. Overflow adds a continuation; text is not silently clipped or reduced below the minimum.

## Placement ledger

Every placement records source file, family, role, output page, x/y/width/height in millimetres, fit mode, crop policy and effective DPI. An unplaced source must have an explicit `review_required` or `missing` record; it may not disappear silently.

## DPI policy

- 250 ppi or higher: acceptable.
- 180–249 ppi: warning and replacement queue.
- Below 180 ppi in a large placement: blocking unless the owner has explicitly accepted the source-quality limit for the draft.

The generator may reduce a weak image's physical size to improve effective DPI. It must not invent detail or replace documentary content.
