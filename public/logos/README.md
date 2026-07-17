# Bank logos

These official, full-colour bank assets were imported from the
`FinalVersion1.0` branch. `components/bank-logo.tsx` maps dashboard bank IDs and
names to these exact filenames and falls back to a generic bank icon for an
unknown institution.

| File          | Bank                      |
| ------------- | ------------------------- |
| `alrajhi.png` | Al Rajhi Bank             |
| `alinma.png`  | Alinma Bank               |
| `sab.png`     | SAB — Saudi Awwal Bank    |
| `snb.png`     | SNB — Saudi National Bank |
| `riyad.png`   | Riyad Bank                |
| `albilad.png` | Bank Albilad              |
| `fransi.png`  | Banque Saudi Fransi       |
| `anb.png`     | Arab National Bank        |

Do not alter the official branding. Logos render at `object-contain` on a white
tile (`tile: "#ffffff"` in the data), with **no CSS filters** — no `invert`,
`grayscale`, or `brightness` — so they display in their original colours.

Prefer transparent-background artwork; the tile is a square with `p-1.5`
padding. To use a different extension, update the path in
`components/bank-logo.tsx`.
