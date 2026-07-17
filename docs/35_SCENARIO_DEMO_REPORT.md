# Nafi live demo verification

Date: 15 July 2026  
Result: **35/35 scenarios passed**

## Scenario matrix

| # | Scenario | Result |
|---:|---|:---:|
| 1 | Signed-in chat establishes an online session | Pass |
| 2 | Chat-to-dashboard navigation | Pass |
| 3 | Dashboard cards render | Pass |
| 4 | Bank logos load | Pass |
| 5 | Arabic RTL and SAR selection persist after reload | Pass |
| 6 | Profile menu closes with Escape | Pass |
| 7 | Profile menu closes on outside click | Pass |
| 8 | Sign-out returns to the localized login screen | Pass |
| 9 | Signed-out chat route is protected | Pass |
| 10 | Signed-out dashboard route is protected | Pass |
| 11 | Empty or malformed login is blocked | Pass |
| 12 | Registration creates an online session that survives reload | Pass |
| 13 | Interaction backend session recovers after restart | Pass |
| 14 | Arabic balance question returns the grounded account balance | Pass |
| 15 | Contextual follow-up about other banks preserves conversation context | Pass |
| 16 | Unexpected flat-tire prompt receives a helpful response without leaking architecture | Pass |
| 17 | Prompt-injection request for another user's data is rejected | Pass |
| 18 | “Transfer two thousands riyals to Yousef” infers SAR 2,000 | Pass |
| 19 | Transfer with a missing destination asks only for the destination | Pass |
| 20 | Arabic-digit incorrect OTP returns a localized rejection | Pass |
| 21 | Pending confirmation survives dashboard navigation | Pass |
| 22 | Grouped amount `2,000` reaches confirmation as 2,000 | Pass |
| 23 | Decimal amount `2,500.50` reaches confirmation as 2,500.50 | Pass |
| 24 | Arabic amount `ألفين` is interpreted as 2,000 | Pass |
| 25 | Arabic investment request maps `عشر` to 10 and `أرامكو` to ARAMCO | Pass |
| 26 | Beneficiary confirmation fields are fully localized | Pass |
| 27 | Unknown beneficiary is detected before confirmation and OTP | Pass |
| 28 | Eligible SAR 1 transfer completes after OTP and produces a receipt | Pass |
| 29 | Illustrative dashboard data is clearly labeled and fake citations are absent | Pass |
| 30 | “Scan all” and notifications provide accessible feedback | Pass |
| 31 | Rapid English-to-Arabic switch keeps the session online and data grounded | Pass |
| 32 | Interaction outage shows Offline and automatically recovers after restart | Pass |
| 33 | Agent outage fails safely, recovers, and portfolio intent returns holdings | Pass |
| 34 | `127.0.0.1` origin establishes a session and can fetch account data | Pass |
| 35 | Realtime voice connects, enters Listening, and stops cleanly using the fixed male voice configuration | Pass |

## Defects fixed during the run

- Made clarification answers field-bound so a value supplied for one missing field cannot silently fill another.
- Improved grouped, decimal, English-word, and Arabic-number parsing.
- Added configured Arabic investment aliases and clearer multilingual intent distinctions.
- Added transfer preflight validation before confirmation, including beneficiary, balance, and limit checks.
- Prevented duplicate server errors when a guarded tool result was already recorded.
- Added durable terminal-event polling so a missed WebSocket event cannot leave the composer locked.
- Localized backend errors, OTP feedback, clarification fields, and all confirmation labels.
- Fixed loopback-origin API routing and allowed the `127.0.0.1` development origin.
- Added honest illustrative-data disclosure and accessible dashboard interaction feedback.
- Kept realtime speech on the configured `Charon` adult male voice in both supported languages.

## Regression evidence

- Agentic/backend suite: `244 passed, 8 skipped`
- Interaction backend suite: `39 passed`
- Ruff: passed
- TypeScript (`tsc --noEmit`): passed
- Next.js production build: passed (9 static pages)
- Git whitespace check: passed
- Final browser console warnings/errors: none

## Runtime handoff

- Frontend: `http://127.0.0.1:3000/chat`
- Interaction backend: port `8001`
- Agentic backend: port `9000`
- Port `8000` was left untouched for the user's other project.

The completed transfer scenario intentionally changed the demo account balance from SAR 25,431.50 to SAR 25,430.50 and produced receipt `receipt-bank-transfer-fa25212bbbe6408fa5be87b3b0c59ff9`.
