# Bank logos

⚠️ **These four files are missing — drop them here.** The neutral placeholders
were removed; `lib/nafiData.ts` now points at the PNG filenames below, so until
the real assets land the bank tiles render as broken images.

Use the official, full-colour logo for each bank, with these **exact**
filenames. No code change is needed — `BankLogo` reads the path from
`lib/nafiData.ts`.

| File          | Bank                      |
| ------------- | ------------------------- |
| `alrajhi.png` | Al Rajhi Bank             |
| `alinma.png`  | Alinma Bank               |
| `sab.png`     | SAB — Saudi Awwal Bank    |
| `snb.png`     | SNB — Saudi National Bank |

Do not alter the official branding. Logos render at `object-contain` on a white
tile (`tile: "#ffffff"` in the data), with **no CSS filters** — no `invert`,
`grayscale`, or `brightness` — so they display in their original colours.

Prefer transparent-background artwork; the tile is a square with `p-1.5`
padding. To use a different extension, update the `logo` path in
`lib/nafiData.ts`.
