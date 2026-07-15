# Nafi (نافع) — Complete Project Handoff

> **Read this first.** This is a full, self-contained context brief for the **Nafi** front-end. It is written so a brand-new Claude Code (or human) session can resume the work with **zero prior conversation**. Everything below reflects the **actual current state of the code in this repo** (verified file-by-file, not from memory).

**Table of contents**
1. What Nafi is
2. Original product requirements (the spec)
3. Tech stack
4. Run / build / deploy
5. Design system (all tokens)
6. Full file map
7. Component-by-component reference
8. Internationalization (full dictionary)
9. Data model (exact values)
10. Design-iteration history
11. Git / GitHub state ← important
12. Live vs local divergence
13. Known gotchas & open bugs
14. Suggested next steps

---

## 1. What Nafi Is

**Nafi (نافع)** is a **voice-first AI personal-finance assistant** — a Saudi FinTech product built for the **Amad Hackathon**. This repo is the **front-end**: a single-page, **bilingual (English / Arabic)** financial **dashboard** with a persistent floating voice assistant.

The dashboard uses a **"bento box"** layout — a responsive grid of rounded cards, each showing one slice of the user's finances: net worth, connected banks, open-banking services, a private stock portfolio, account activity & payments, and a favorite-recipients graph. A floating **"Ask Nafi"** button is the primary interaction: the user speaks, Nafi acts.

- **Voice-first** — floating action button (FAB), always visible.
- **Bilingual** — full EN ⇄ AR switch with correct RTL mirroring, Arabic-Indic numerals, Arabic dates.
- **Open banking** — Saudi banks: Al Rajhi, Alinma, SAB, SNB.
- **Currency** — USD ($), illustrative mock data.
- **Audience** — hackathon demo / investor-facing polish.

---

## 2. Original Product Requirements (the spec)

The five features below were explicitly requested and are **all implemented**:

1. **Persistent Voice Assistant** — replace any static bottom voice/command bar with a **floating action button** fixed **bottom-right** (`position: fixed`), always visible while scrolling. Single primary voice entry point.

2. **Strict Bilingual EN/AR** — a clean language toggle that switches the **entire** UI (headers, data, dates, numerals) with correct **LTR/RTL**. No mixed-language text, no broken layouts. Set `dir` + `lang` on `<html>`; use logical CSS utilities.

3. **Open-banking UI with real bank logos** — bank cards structured to accept **real, official, full-color** logos (Al Rajhi, Alinma, SAB, SNB) via image files. **No generic/abstract icons**; don't alter official branding.

4. **Personal stock portfolio tracker** — a dedicated card for a **private personal stock index** (value, day P&L, holdings, sparkline). **CRITICAL CONSTRAINT: contains NO data or reference to "Dr. Sulaiman Al Habib Medical Group"** or any healthcare/hospital name. Keep it that way.

5. **GitHub workflow** — push to the `Amad-Hackthon` repo on a **branch named `front-end`**, **never to `main`**.

---

## 3. Tech Stack

| Layer | Choice |
|---|---|
| Framework | **Next.js 15.3** (App Router) + **React 19.1** |
| Language | TypeScript 5 |
| Styling | **Tailwind CSS v4** (`@tailwindcss/postcss`, `@theme inline` in globals.css) |
| Icons | **lucide-react** |
| UI primitives | Hand-authored (`@radix-ui/react-slot`, `class-variance-authority`, `clsx`, `tailwind-merge`) |
| Font | **Inter** via `next/font/google` (`--font-inter`) |
| Charts | **None** — hand-written inline SVG sparkline. ⚠️ `recharts` + `react-is` are still in `package.json` but **not imported anywhere** — safe to remove. |
| i18n | **Custom**, client-side React Context (`lib/i18n.tsx`) — no external i18n library |
| Output | **Static export** (`output: "export"` → `./out`) |
| Hosting | **Cloudflare Workers** static assets (`wrangler`) |

---

## 4. Run / Build / Deploy

```bash
# install (React 19 — use --legacy-peer-deps if a peer conflict appears)
npm install

# dev server (auto-port; 3000 is often busy on this machine)
npm run dev

# production static export → ./out
npm run build

# deploy ./out to Cloudflare Workers
npx wrangler deploy
```

- **Live URL:** https://nafi.rahhal.workers.dev — worker `nafi`, Cloudflare account `rahhal`.
- **Build size:** home route ≈ **118 kB** first-load JS (was ~209 kB with Recharts).
- `.claude/launch.json` sets `autoPort: true` (port 3000 frequently taken).
- **Cloudflare config** (`wrangler.jsonc`): serves `./out`, `compatibility_date` `2026-07-01`, `not_found_handling: "404-page"`.

`package.json` scripts: `dev` → `next dev`, `build` → `next build`, `start` → `next start`.

---

## 5. Design System — Navy Bento

All colors are CSS variables in `app/globals.css` (`:root`), exposed to Tailwind via `@theme inline`. Radius base `--radius: 1rem`.

| Token | Value | Use |
|---|---|---|
| `--background` | `#0d1119` | Page canvas |
| `--foreground` | `#e9eef6` | Primary text |
| `--card` | `#171e2b` | Bento card surface |
| `--card-2` | `#1f2836` | Inner tiles inside cards (`bg-card-2`) |
| `--popover` | `#1a2130` | FAB tooltip / popovers |
| `--primary` | `#6f8dff` | Soft blue accent, focus ring, gradients |
| `--primary-foreground` | `#0b0f18` | Text on primary |
| `--muted` | `#1f2836` | Muted surfaces |
| `--muted-foreground` | `#8b99ad` | Secondary text |
| `--faint` | `#5d6a7e` | Tertiary text / `[cite]` tags |
| `--orange` | `#d97b4c` | "Recent Transactions" CTA gradient |
| `--purple` | `#8f82ea` | "Upcoming Payments" CTA gradient |
| `--positive` | `#55b394` | Gains / positive deltas / sparkline |
| `--negative` | `#e2726a` | Losses / negative deltas |
| `--border` | `#273246` | Hairlines (usually as `border-white/[0.06]`) |
| `--ring` | `#6f8dff` | Focus ring |

**Other design details:**
- `color-scheme: dark` on `<html>` (no manual `.dark` class toggling needed).
- **Body vignette:** two radial gradients (top-center + top-right navy glows), `background-attachment: fixed`.
- **Bento cards** (`BentoCard`): `rounded-2xl`, `border-white/[0.06]`, `bg-card`, `p-5 sm:p-6`, with an inset top highlight + soft drop shadow.
- **Voice equalizer:** `@keyframes eq` scales bars `scaleY(0.35) → 1`; exposed as `--animate-eq` / `animate-eq`.
- `.no-scrollbar` utility hides scrollbars.

---

## 6. Full File Map

**App flow:** `/` (server-backed login/create account) → `/chat` (voice-first chat) → `/dashboard` (bento). Authenticated users can move between chat and dashboard; the dashboard's **VoiceFAB** links back to `/chat`.

```
app/
  layout.tsx              Root layout — Inter font, metadata, wraps <Providers> (LanguageProvider)
  page.tsx                / — authenticated login/register gate (renders <LoginScreen>)
  chat/page.tsx           /chat — voice-first chat (renders <ChatScreen>)
  globals.css             Navy theme tokens + @theme inline + keyframes + vignette
  (dash)/                 Route group for the authenticated dashboard area (URLs have no "(dash)")
    layout.tsx            Dashboard chrome: skip-link, TopHeader, <main>, VoiceFAB
    dashboard/page.tsx    /dashboard — composes the bento grid (composition only)
    accounts/page.tsx     /accounts  — placeholder (uses PlaceholderPage)
    advisor/page.tsx      /advisor   — placeholder
    settings/page.tsx     /settings  — placeholder

components/
  layout/
    providers.tsx         Wraps the whole app in LanguageProvider (all screens bilingual)
  auth/
    login-screen.tsx      Server-backed login/register form (successful auth→/chat)
  chat/
    chat-screen.tsx       Secure backend chat + realtime voice + task/confirmation UI
  nafi/                   ← THE DASHBOARD (edit here)
    top-header.tsx        Brand mark + "Nafi/نافع" + LanguageToggle + bell + avatar
    net-worth-card.tsx    $10,649,382 gradient number, delta badge, as-of date
    connected-banks-card.tsx    2-col grid of bank rows (BankLogo + localized name + code)
    integrated-services-card.tsx  Open-banking pill chips + "Scan all" button
    portfolio-card.tsx    Private portfolio — sparkline + holdings table  ← NO hospital data
    account-activity-card.tsx  Orange "Recent" + purple "Upcoming" CTAs + 2×2 metrics
    recipients-graph-card.tsx  Node graph: Quick Contacts → recipients → banks (SVG); mobile stacks
    voice-fab.tsx         Persistent floating voice button (Space / tap toggles)
    bank-logo.tsx         <img src={bank.logo}> on a white tile
    bento-card.tsx        BentoCard surface + CardTitle (title / tag / action)
    brand-logo.tsx        SVG wave-and-arrow mark (optional gradient)
  i18n/
    language-toggle.tsx   EN / ع segmented toggle (pinned dir="ltr")
  placeholder-page.tsx    Shared centered placeholder for stub routes

lib/
  i18n.tsx                i18n system: LanguageProvider, useLang, useFormat, useLocalize (§8)
  nafiData.ts             ALL mock data (§9)
  nafea-api.ts            Browser API/WebSocket client for the interaction service
  utils.ts                cn() — clsx + tailwind-merge

public/logos/             al-rajhi.svg, alinma.svg, sab.svg, snb.svg (PLACEHOLDERS) + README.md
.claude/launch.json       Dev-server launch config (autoPort)
next.config.ts            output: "export"
wrangler.jsonc            Cloudflare static-assets config
```

### Archived implementations

The unused finance-card prototype is preserved under `legacy/nafi-finance-ui/`. The original Vite
voice client is preserved under `legacy/vite-voice-ui/`. Neither directory is part of the active
Next.js build; edit `components/nafi/*` and `components/chat/*` instead.

---

## 7. Component-by-Component Reference

**`app/layout.tsx`** — `RootLayout`. Loads Inter, sets site metadata (title template `"%s · Nafi"`, default `"Nafi — Voice-First AI Financial Assistant"`), renders `<html lang="en">` → `<body class="font-sans">` → `<AppShell>`. ⚠️ `viewport.themeColor` is currently `#fdfbf7` (leftover cream from the old light theme) — should be `#0d1119` (see §13).

**`app/page.tsx`** — `OverviewPage`. Pure composition, no logic. Grid `grid-cols-1 gap-4 lg:grid-cols-12`:
- Row 1: `NetWorthCard` (lg:col-span-6) · `ConnectedBanksCard` (6)
- Row 2: `IntegratedServicesCard` (12)
- Row 3: `PortfolioCard` (6) · `AccountActivityCard` (6)
- Row 4: `RecipientsGraphCard` (12)
- Sets `metadata.title = "Overview"`.

**`components/layout/app-shell.tsx`** — `AppShell`. Wraps everything in `LanguageProvider`. Renders a skip-to-content link, a centered column (`max-w-[1180px]`, gap-5, responsive padding) containing `TopHeader` + `<main id="main-content">`, and the `VoiceFAB` outside the column (so it floats over the viewport). **No sidebar, no bottom nav, no static bottom bar.**

**`components/nafi/top-header.tsx`** — `TopHeader` (client). Left: `BrandLogo gradient` + wordmark (`"نافع"` if AR else `"Nafi"`). Right: `LanguageToggle`, a notification bell (with an orange unread dot), and a profile avatar showing `user.initial` on a primary→purple gradient. All `aria-label`s localized via `t()`.

**`components/nafi/net-worth-card.tsx`** — `NetWorthCard` (client). Title `t("netWorth")`. Big amount `fmt.money(netWorth.amount)` = **$10,649,382**, rendered as white→slate gradient clipped text, `dir="ltr"`, `tabular-nums`. Below: `t("aggregatedFunds")` + `[cite: 17]` tag + a positive `TrendingUp` delta badge `fmt.pct(3.2)`. Footer: `t("asOf")` + localized `fmt.date(asOfDate)`.

**`components/nafi/connected-banks-card.tsx`** — `ConnectedBanksCard` (client). Title `t("connectedBanks")`. 2-col grid of `BankRow`s over `connectedBanks`. Each row: `BankLogo` (38px) + localized bank name + optional `(code)` in mono + a localized sub-line (`sub`/`subAr`, falling back to the name).

**`components/nafi/integrated-services-card.tsx`** — `IntegratedServicesCard` (client). Title `t("integratedServices")` with a `t("scanAll")` + `Plus` action button. Body: flex-wrap **pill chips** over `integratedServices`, each a rounded-full chip with `BankLogo` (30px) + localized name + `(code)`. Uses logical padding `ps/pe`.

**`components/nafi/portfolio-card.tsx`** — `PortfolioCard` (client). **The private portfolio.** Title `t("portfolio")` (= "My Stock Portfolio") + a `t("privateIndex")` pill. Shows `fmt.money(portfolio.value)` = **$1,284,500**, a green `fmt.pct` day change + total-return line, and an inline **`Sparkline`** (local component — hand-rolled `<svg>` path + gradient fill from `portfolio.spark`, no chart lib). Then a **holdings** list: ticker (mono) · localized name · `weight%` · colored `dayPercent` (green/red). **Holdings are Aramco / Al Rajhi / SABIC / stc — no healthcare names.**

**`components/nafi/account-activity-card.tsx`** — `AccountActivityCard` (client). Title `t("accountActivity")` + `[17]` tag. Two gradient CTA panels side by side:
- **Recent** (orange gradient) — `t("recentTransactions")`, list from `activity.recent`; each item's label is `t("transferTo", {name})` or `t("depositFrom", {name})` with a direction icon (arrows use `rtl:-scale-x-100`) + `[cite: N]`.
- **Upcoming** (purple gradient) — `t("upcomingPayments")`, list from `activity.upcoming` (utilities/phone icons + localized labels).
Below: a **2×2 metrics grid** from `activity.metrics` — each shows a localized label + value (money via `fmt.money`, else `fmt.num`).

**`components/nafi/recipients-graph-card.tsx`** — `RecipientsGraphCard` (client). Title `t("favoriteRecipients")` + `[34]` tag. **Desktop (`sm:` up):** a 280px-tall relative canvas with an absolutely-positioned **SVG connector overlay** (6 bezier/line paths, `viewBox 0 0 100 100`, `rtl:-scale-x-100`) linking: **Quick Contacts** node (start, vertically centered) → three **RecipientBox**es (middle column, rows at `ROW_Y = [16, 50, 84]%`) → **ArrowRight** icons → **BankNode**s (end column). Positioned with logical `insetInlineStart/End` so it mirrors in RTL. **Mobile (`sm:hidden`):** simple stacked rows (RecipientBox → arrow → BankLogo). Local helpers: `RecipientBox` (avatar initials + localized name), `BankNode` (BankLogo 40px + localized bank name).

**`components/nafi/voice-fab.tsx`** — `VoiceFAB` (client). Fixed `bottom-6 right-6 z-50`, `dir="ltr"`. A 56px gradient (primary→purple) round button. **Idle:** shows `BrandLogo` + a slow `animate-ping` breathing ring; tooltip pill appears on hover showing `t("askNafi")`. **Active:** shows a 5-bar equalizer (`BARS = [0.4,0.75,1,0.6,0.85]`, staggered `animate-eq` delays) + persistent `t("listening")` pill. Toggled by **click** or **Space** (Space ignored while typing in inputs/textareas/contenteditable). `aria-pressed` reflects state.

**`components/nafi/bank-logo.tsx`** — `BankLogo`. Renders `<img src={bank.logo}>` (`object-contain p-1.5`, `loading="lazy"`, `decoding="async"`) on a tile of `bank.tile` background (white), `size` px square, `rounded-xl ring-1 ring-black/5`. **Server component (no "use client").** Swapping the file in `public/logos/` changes the logo with zero code change.

**`components/nafi/bento-card.tsx`** — `BentoCard` (surface: rounded-2xl, hairline border, inset highlight, drop shadow) and `CardTitle` (takes an already-localized `title` string + optional mono `tag` + optional `action` node). Both are server components.

**`components/nafi/brand-logo.tsx`** — `BrandLogo`. Inline SVG "wave-and-arrow" mark (a zig-zag equalizer wave + an up-right arrow). `gradient` prop switches stroke to a blue→violet linear gradient (`#6f8dff → #a78bfa`); otherwise `currentColor`.

**`components/i18n/language-toggle.tsx`** — `LanguageToggle` (client). Segmented `EN` / `ع` pill, `role="group"`, pinned `dir="ltr"` so it never flips. Buttons call `setLang("en"|"ar")`; active side highlighted; `aria-pressed` set.

**`components/placeholder-page.tsx`** — `PlaceholderPage`. Shared centered empty-state (icon + title + description) used by the `accounts`/`advisor`/`settings` stub routes.

---

## 8. Internationalization (`lib/i18n.tsx`)

Client-side i18n via React Context. `LanguageProvider` holds `lang` state (default `"en"`) and, on change, sets `document.documentElement.lang` and `.dir`.

**Hooks:**
- **`useLang()`** → `{ lang, setLang, dir, locale, t }`. `t(key, vars?)` looks up the EN/AR dictionary and interpolates `{name}`-style vars; falls back to EN then to the raw key.
- **`useFormat()`** → `{ money, num, pct, date }`, all `Intl`-based on `locale` (`en-US` / `ar-SA`). `money` prefixes `$` with locale-grouped digits (0 fraction). `pct` adds a leading `+` for non-negatives and a `%` suffix (1 fraction). In Arabic these emit **Arabic-Indic numerals** and **Arabic month/date names**.
- **`useLocalize()`** → `loc(en, ar?)` — returns the AR string in Arabic mode (if provided), else EN. Used for data-driven names.

**RTL techniques used across components:** logical utilities (`ps/pe`, `ms/me`, `text-start/end`, `insetInlineStart/End`), `rtl:-scale-x-100` on the node-graph SVG and all directional arrows, and `dir="ltr"` pinned on inherently-LTR bits (numbers, codes, the language toggle, the FAB container).

**Full dictionary** (key → EN / AR):

| key | EN | AR |
|---|---|---|
| brandTagline | Voice-first finance | الإدارة المالية بالصوت |
| netWorth | Your Net Worth | صافي ثروتك |
| aggregatedFunds | Aggregated Funds | إجمالي الأموال |
| asOf | as of | كما في |
| connectedBanks | Connected Banks | البنوك المرتبطة |
| integratedServices | Integrated Bank Services | الخدمات المصرفية المدمجة |
| scanAll | Scan all | مسح الكل |
| portfolio | My Stock Portfolio | محفظتي للأسهم |
| privateIndex | Private index | مؤشر خاص |
| today | Today | اليوم |
| totalReturn | Total return | العائد الكلي |
| holdings | Holdings | المكوّنات |
| weight | Weight | الوزن |
| accountActivity | Account Activity & Payments | النشاط والمدفوعات |
| recentTransactions | Recent Transactions | العمليات الأخيرة |
| upcomingPayments | Upcoming Payments | المدفوعات القادمة |
| utilities | Utilities | فواتير الخدمات |
| phoneBill | Phone bill | فاتورة الجوال |
| transferTo | Transfer to {name} | تحويل إلى {name} |
| depositFrom | Deposit from {name} | إيداع من {name} |
| linkedAccounts | Linked accounts | حسابات مرتبطة |
| monthlySpend | Monthly spend | الإنفاق الشهري |
| activeTransfers | Active Transfers | تحويلات نشطة |
| linkedBankTypes | Linked bank types | أنواع البنوك |
| favoriteRecipients | Favorite Recipients & Linked Banks | المستفيدون والبنوك المرتبطة |
| quickContacts | Quick Contacts | جهات سريعة |
| askNafi | Ask Nafi | اسأل نافع |
| listening | Listening… | يستمع… |
| notifications | Notifications | الإشعارات |
| profile | Profile | الملف الشخصي |
| language | Language | اللغة |

> To add a string: add the key to **both** `en` and `ar` in `lib/i18n.tsx`, then use `t("key")`. For data-driven names, store an `xAr` field and read it with `useLocalize()`.

---

## 9. Data Model (`lib/nafiData.ts`)

All mock data lives here. Every user-facing string carries an EN + AR pair. Amounts are illustrative USD.

- **`user`** — `Ibrahim Al-Otaibi` / `إبراهيم العتيبي`, `initial: "I"`.
- **`asOfDate`** — `2026-07-14`.
- **`netWorth`** — `{ amount: 10_649_382, cite: 17, deltaPercent: 3.2 }`.
- **`connectedBanks`** (`Bank[]`) — Al Rajhi (`code 890`), Alinma, SAB (Saudi Awwal Bank), SNB (Saudi National Bank). Each: `logo` path in `/logos/*.svg`, `tile: "#ffffff"`.
- **`integratedServices`** (`Bank[]`) — Al Rajhi (`890`), Alinma (`132`).
- **`portfolio`** — `value: 1_284_500`, `dayPercent: 1.24`, `totalReturnPercent: 22.6`, `spark: [20-point trendline]`, `holdings`:
  | ticker | name | weight | day% |
  |---|---|---|---|
  | 2222 | Saudi Aramco / أرامكو السعودية | 34 | +0.6 |
  | 1120 | Al Rajhi Bank / مصرف الراجحي | 26 | +1.4 |
  | 2010 | SABIC / سابك | 22 | −0.8 |
  | 7010 | stc / إس تي سي | 18 | +2.1 |

  **⚠️ Deliberately NO healthcare / hospital names (no "Dr. Sulaiman Al Habib"). Preserve this.**
- **`activity`** — `cite: 17`; `recent` = [transfer→Yousef (cite 31), deposit←Mishari (cite 17)]; `upcoming` = [utilities, phone]; `metrics` = linkedAccounts 4, monthlySpend $2,100, activeTransfers 2, linkedBankTypes 2.
- **`recipients`** (`Recipient[]`) — Reema Al-Dosari→Al Rajhi, Mishari Al-Saud→Alinma, Yousef Al-Fahad→SNB (each with `nameAr` + a `bank`).
- **`contactsCount`** — `34`.
- **Types exported:** `BankId`, `Bank`, `Holding`, `Recipient`.

The `[cite: N]` numbers rendered on cards are an intentional design motif (mimicking sourced/aggregated data), not real citations.

---

## 10. Design-Iteration History

The UI went through **nine** complete redesigns before landing on the current navy bento. Don't resurrect the dead ones.

| # | Direction | Outcome |
|---|---|---|
| 1 | Neon green/blue dark (sidebar + bottom nav + mic FAB) | Deployed first, superseded |
| 2 | Charcoal + gold/copper premium | Kept briefly |
| 3 | Alinma 2025 rebrand (navy + copper + lavender) | Rejected by user |
| 4 | Reverted to charcoal + gold | Kept briefly |
| 5 | Glassmorphic bento (charcoal + gold glass) | Superseded |
| 6 | **Oxford-blue / royal-indigo** + `mockData.ts` | **Deployed — this is what's LIVE now** |
| 7 | Editorial financial terminal (off-black, sage/sand, command bar) | Superseded |
| 8 | "White & Brown" light theme (Alinma-inspired) + dev configurator | Deployed once, rolled back |
| 9 | **Deep-navy bento reference** (this repo) | **Current LOCAL code** |

**Cloudflare deploy/rollback history:** `553669ba` (first) · `e82676f5` (indigo) · `1632a03b` (indigo redeploy — **currently live**) · `a2a45cac` (White & Brown). The live site was rolled back to `1632a03b` at the user's request ("خله الانديقو" = keep the indigo).

---

## 11. Git / GitHub State  ← IMPORTANT

- **Team repo:** `https://github.com/Pb22j/Amad-Hackthon` (private, shared, multiple contributors, several branches: `main`, `AgenticToolsV1`, `GPT-sol-generated`, `VoiceAssistant`, `database-setup`, `feat/agentic_layer`, `integration`).
- **This front-end lives on branch `front-end`:** https://github.com/Pb22j/Amad-Hackthon/tree/front-end
- **`main` was NOT touched.** Do not push to `main` — open a PR if integrating.
- Local `origin` → `https://github.com/Pb22j/Amad-Hackthon.git`.
- Commit author email is the GitHub **noreply** (`297511080+mohammed57770@users.noreply.github.com`) to satisfy GitHub's email-privacy push protection (a plain gmail address is rejected on push).

**Push flow from here:**
```bash
git add -A
git commit -m "..."
git push origin front-end
```

**Notes:**
- A throwaway empty repo `mohammed57770/Amad-Hackthon` was created by mistake earlier and is **unused** (can be deleted).
- **Git-ignored runtime config:** `.env.backend` for both Python services and `.env.local` for Next.js. Their tracked templates are `.env.backend.example` and `.env.frontend.example`.

---

## 12. Live vs Local Divergence

**The live site ≠ this code.** Live currently serves the older **Oxford-blue/indigo bento** (Cloudflare version `1632a03b`), kept by user choice. This repo is the newer **navy bento** with all five features. The indigo source was deleted locally — recoverable only via `wrangler rollback`, not from the working tree.

**If you redeploy** (`npm run build && npx wrangler deploy`), live switches to this navy bento. **Confirm with the user before redeploying**, since they deliberately chose to keep indigo live.

---

## 13. Known Gotchas & Open Bugs

**Bugs / inconsistencies to fix:**
- 🧹 **`recharts` + `react-is`** are still dependencies but unused — remove to slim the tree.
- 🔐 **Login remains a demo gate** — chat now uses the authenticated interaction backend, but `login-screen.tsx` still does not provide production identity/authentication.
- 🧱 **`legacy/` is intentionally excluded from the active Next.js TypeScript project** — use it only for historical reference or migration work.

**Environment gotchas:**
- ⚠️ **Never run `npm run build` while `next dev` is running** — it clobbers `.next` and causes transient `Cannot find module './xxx.js'` 500s. Stop dev first, or build only at the end. Recovery: stop server → `rm -rf .next` → restart.
- ⚠️ **SVG elements reject a `dir` prop** in TS (`SVGProps` has no `dir`). Use a wrapper `<div dir=…>` or `rtl:-scale-x-100`.
- ⚠️ **Browser-automation synthetic clicks** (preview tooling) don't always reach React handlers here; programmatic `element.click()` does. The toggle/FAB work fine for real users — a tooling quirk, not a bug.
- ⚠️ **GitHub email-privacy push protection** blocks pushes exposing a private email — commits use the `users.noreply.github.com` address.
- ⚠️ After a Cloudflare deploy/rollback, the browser may show a **cached** old version — hard-refresh (`Cmd+Shift+R`).

---

## 14. Suggested Next Steps

- [ ] Drop **real official bank logos** into `public/logos/` (same filenames) — currently placeholders.
- [ ] Remove **`recharts` + `react-is`** from `package.json` (unused).
- [x] Replace the demo login gate with backend-verified banking credentials and revocable sessions.
- [ ] Flesh out the placeholder routes (`accounts`, `advisor`, `settings`).
- [ ] Remove the archived `legacy/` implementations after the product team confirms they are no longer needed.
- [ ] Decide whether to **redeploy** the navy bento to Cloudflare (live is still indigo by choice — §12).
- [ ] Open a **PR** from `front-end` → `main` on the team repo when ready to integrate.

---

*Front-end: Next.js 15 + React 19 + Tailwind v4, static-exported to Cloudflare. Bilingual EN/AR, voice-first, deep-navy bento. Lives on branch `front-end` of `Pb22j/Amad-Hackthon`. Live site is still the older indigo version by user choice.*
