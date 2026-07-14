# Bank logos

These are **neutral placeholders**. Drop the official, full-colour logo for each
bank here using the exact same filename, and the UI will render it automatically
(no code changes needed). Do not alter the official branding.

| File            | Bank                          |
| --------------- | ----------------------------- |
| `al-rajhi.svg`  | Al Rajhi Bank                 |
| `alinma.svg`    | Alinma Bank                   |
| `sab.svg`       | SAB — Saudi Awwal Bank        |
| `snb.svg`       | SNB — Saudi National Bank     |

SVG is preferred (crisp at any size). PNG works too — if you use a different
extension, update the `logo` path in `lib/nafiData.ts`. Logos render on a white
tile (`bg-white`) via `object-contain`, so both light and dark marks display
correctly.
