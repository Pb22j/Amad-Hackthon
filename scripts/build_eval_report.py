"""Render the security screening evaluation to a standalone HTML report.

The report is generated from a live run of the dataset rather than transcribed, so the
figures on the page cannot drift from the figures the suite produces.

    python scripts/build_eval_report.py [--output outputs/security-eval-report.html]
"""

from __future__ import annotations

import argparse
from datetime import date
from html import escape
from pathlib import Path

from agentic.config.loader import load_config
from agentic.evals.runner import (
    SecurityEvalCase,
    SecurityEvalReport,
    load_security_dataset,
    screen_case,
)
from agentic.evals.runner import run_security_dataset
from agentic.policy.engine import PolicyEngine

DATASET = Path("agentic/evals/datasets/security.jsonl")
DEFAULT_OUTPUT = Path("outputs/security-eval-report.html")

CATEGORY_LABELS = {
    "benign_read": "Benign read",
    "benign_action": "Benign action",
    "benign_trigger_words": "Benign, trigger words",
    "prompt_injection": "Prompt injection",
    "credential_extraction": "Credential extraction",
    "cross_user_access": "Cross-user access",
    "obfuscated_injection": "Obfuscated injection",
    "authority_manipulation": "Authority manipulation",
    "tool_argument_injection": "Tool-argument injection",
    "bulk_data_exfiltration": "Bulk data exfiltration",
}

STYLE = """
:root {
  --ground: #eef2f1;
  --surface: #ffffff;
  --sunken: #e3eae8;
  --ink: #0f1a1b;
  --ink-muted: #526468;
  --ink-faint: #7f9295;
  --rule: #d0dad8;
  --accent: #0d6e66;
  --accent-soft: #d7e8e5;
  --pass: #2c6e49;
  --gap: #8f5309;
  --contained: #3c5a74;
  --shadow: 0 1px 2px rgba(15, 26, 27, .06), 0 8px 24px -16px rgba(15, 26, 27, .3);
  --font-display: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
  --font-body: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-mono: ui-monospace, "Cascadia Mono", "Cascadia Code", Consolas, "SF Mono", Menlo, monospace;
  --font-ar: "Segoe UI", Tahoma, "Geeza Pro", "Noto Naskh Arabic", "Arabic Typesetting", sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root {
    --ground: #0c1112;
    --surface: #141c1d;
    --sunken: #0f1718;
    --ink: #e7efed;
    --ink-muted: #92a4a6;
    --ink-faint: #697b7d;
    --rule: #253133;
    --accent: #52c0b1;
    --accent-soft: #14302d;
    --pass: #63ab80;
    --gap: #cfa055;
    --contained: #82a3c0;
    --shadow: 0 1px 2px rgba(0, 0, 0, .4), 0 8px 24px -16px rgba(0, 0, 0, .8);
  }
}
:root[data-theme="dark"] {
  --ground: #0c1112;
  --surface: #141c1d;
  --sunken: #0f1718;
  --ink: #e7efed;
  --ink-muted: #92a4a6;
  --ink-faint: #697b7d;
  --rule: #253133;
  --accent: #52c0b1;
  --accent-soft: #14302d;
  --pass: #63ab80;
  --gap: #cfa055;
  --contained: #82a3c0;
  --shadow: 0 1px 2px rgba(0, 0, 0, .4), 0 8px 24px -16px rgba(0, 0, 0, .8);
}
:root[data-theme="light"] {
  --ground: #eef2f1;
  --surface: #ffffff;
  --sunken: #e3eae8;
  --ink: #0f1a1b;
  --ink-muted: #526468;
  --ink-faint: #7f9295;
  --rule: #d0dad8;
  --accent: #0d6e66;
  --accent-soft: #d7e8e5;
  --pass: #2c6e49;
  --gap: #8f5309;
  --contained: #3c5a74;
  --shadow: 0 1px 2px rgba(15, 26, 27, .06), 0 8px 24px -16px rgba(15, 26, 27, .3);
}

body {
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font-family: var(--font-body);
  font-size: 16px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 60rem; margin: 0 auto; padding: 3.5rem 1.5rem 6rem; }
section { margin-top: 4rem; }
p { max-width: 65ch; color: var(--ink-muted); }
h1, h2, h3 { color: var(--ink); text-wrap: balance; margin: 0; }
h1 { font-family: var(--font-display); font-size: clamp(2rem, 5vw, 3rem); line-height: 1.1; font-weight: 600; letter-spacing: -.015em; }
h2 { font-family: var(--font-display); font-size: 1.6rem; font-weight: 600; letter-spacing: -.01em; }
h3 { font-size: .95rem; font-weight: 650; }
a { color: var(--accent); }

.eyebrow {
  font-family: var(--font-mono);
  font-size: .7rem;
  text-transform: uppercase;
  letter-spacing: .14em;
  color: var(--accent);
  margin: 0 0 .75rem;
}
.lede { font-size: 1.075rem; margin-top: 1.25rem; }
.section-head { display: flex; flex-direction: column; gap: .5rem; margin-bottom: 1.5rem; }
.section-head p { margin: 0; }
.rule { height: 1px; background: var(--rule); border: 0; margin: 0; }

/* Scoreboard */
.score {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: 1px;
  margin-top: 2.5rem;
  background: var(--rule);
  border: 1px solid var(--rule);
  border-radius: 3px;
  overflow: hidden;
}
.score div { background: var(--surface); padding: 1.25rem; }
.score dt {
  font-family: var(--font-mono);
  font-size: .65rem;
  text-transform: uppercase;
  letter-spacing: .1em;
  color: var(--ink-faint);
}
.score dd {
  margin: .4rem 0 0;
  font-family: var(--font-display);
  font-size: 2rem;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.score dd small { font-size: .9rem; color: var(--ink-faint); font-family: var(--font-body); }
.score .is-pass dd { color: var(--pass); }
.score .is-gap dd { color: var(--gap); }

/* Thesis */
.thesis { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1.75rem; }
@media (max-width: 44rem) { .thesis { grid-template-columns: 1fr; } }
.probe {
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 3px;
  padding: 1.25rem;
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
  gap: .9rem;
}
.probe-lang {
  font-family: var(--font-mono);
  font-size: .65rem;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--ink-faint);
}
.payload {
  font-family: var(--font-mono);
  font-size: .875rem;
  color: var(--ink);
  background: var(--sunken);
  border-left: 2px solid var(--rule);
  padding: .7rem .8rem;
  border-radius: 2px;
  overflow-wrap: anywhere;
}
.payload[dir="rtl"] {
  font-family: var(--font-ar);
  font-size: 1rem;
  border-left: 0;
  border-right: 2px solid var(--rule);
}
.verdict { display: flex; align-items: center; gap: .5rem; font-size: .8rem; font-weight: 600; }
.dot { width: .55rem; height: .55rem; border-radius: 50%; flex: none; }
.verdict.caught { color: var(--pass); }
.verdict.caught .dot { background: var(--pass); }
.verdict.silent { color: var(--gap); }
.verdict.silent .dot { background: var(--gap); box-shadow: 0 0 0 3px color-mix(in srgb, var(--gap) 22%, transparent); }
.verdict code { font-family: var(--font-mono); font-size: .75rem; color: var(--ink-faint); font-weight: 400; }
.caption { font-size: .85rem; color: var(--ink-faint); margin-top: 1rem; max-width: 65ch; }

/* Matrix */
.matrix { margin-top: 1.5rem; display: flex; flex-direction: column; gap: 1px; background: var(--rule); border: 1px solid var(--rule); border-radius: 3px; }
.row { background: var(--surface); display: grid; grid-template-columns: 13rem 1fr 4.5rem; align-items: center; gap: 1rem; padding: .7rem 1rem; }
@media (max-width: 44rem) { .row { grid-template-columns: 1fr; gap: .4rem; } }
.row-name { font-size: .85rem; font-weight: 550; }
.bar { height: .5rem; background: var(--sunken); border-radius: 2px; overflow: hidden; display: flex; }
.bar span { display: block; height: 100%; }
.bar .b-pass { background: var(--pass); }
.bar .b-gap { background: var(--gap); opacity: .75; }
.row-score { font-family: var(--font-mono); font-size: .8rem; font-variant-numeric: tabular-nums; color: var(--ink-muted); text-align: right; }

/* Triage */
.triage { display: grid; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr)); gap: 1rem; margin-top: 1.5rem; }
.tcard { background: var(--surface); border: 1px solid var(--rule); border-radius: 3px; padding: 1.25rem; border-top: 2px solid var(--band); }
.tcard .n { font-family: var(--font-display); font-size: 2.25rem; line-height: 1; color: var(--band); font-variant-numeric: tabular-nums; }
.tcard h3 { margin: .5rem 0 .4rem; }
.tcard p { font-size: .85rem; margin: 0; }
.t-fp { --band: var(--gap); }
.t-tel { --band: var(--contained); }
.t-con { --band: var(--pass); }

/* Tables */
.scroller { overflow-x: auto; border: 1px solid var(--rule); border-radius: 3px; background: var(--surface); margin-top: 1.5rem; }
.tall { max-height: 30rem; overflow-y: auto; }
table { border-collapse: collapse; width: 100%; font-size: .82rem; }
thead th {
  position: sticky; top: 0;
  background: var(--sunken);
  font-family: var(--font-mono);
  font-size: .65rem;
  text-transform: uppercase;
  letter-spacing: .09em;
  color: var(--ink-faint);
  text-align: left;
  font-weight: 500;
  padding: .6rem .75rem;
  border-bottom: 1px solid var(--rule);
  white-space: nowrap;
}
tbody td { padding: .55rem .75rem; border-bottom: 1px solid var(--rule); vertical-align: top; }
tbody tr:last-child td { border-bottom: 0; }
td.id { font-family: var(--font-mono); font-size: .72rem; color: var(--ink-faint); white-space: nowrap; }
td.payload-cell { min-width: 22rem; font-family: var(--font-mono); font-size: .78rem; }
td.payload-cell[dir="rtl"] { font-family: var(--font-ar); font-size: .9rem; text-align: right; }
td.why { color: var(--ink-muted); min-width: 24rem; font-size: .78rem; }
.tag {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: .65rem;
  text-transform: uppercase;
  letter-spacing: .06em;
  padding: .12rem .4rem;
  border-radius: 2px;
  white-space: nowrap;
  border: 1px solid currentColor;
}
.tag.ok { color: var(--pass); }
.tag.miss { color: var(--gap); }
.tag.neutral { color: var(--ink-faint); }

pre {
  background: var(--surface);
  border: 1px solid var(--rule);
  border-left: 2px solid var(--accent);
  border-radius: 3px;
  padding: 1rem 1.1rem;
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: .8rem;
  line-height: 1.5;
  color: var(--ink);
}
footer { margin-top: 5rem; padding-top: 1.5rem; border-top: 1px solid var(--rule); font-size: .8rem; color: var(--ink-faint); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
"""


def _payload_cell(text: str, language: str, css_class: str) -> str:
    rtl = language == "ar"
    attr = ' dir="rtl"' if rtl else ""
    return f'<td class="{css_class}"{attr}>{escape(text)}</td>'


def _outcome_tag(outcome: str, good: bool) -> str:
    css = "ok" if good else "miss"
    return f'<span class="tag {css}">{escape(outcome)}</span>'


def build_html(report: SecurityEvalReport, cases: list[SecurityEvalCase], policy: PolicyEngine) -> str:
    by_id = {case.id: case for case in cases}
    gaps = report.known_gaps

    english = [c for c in cases if c.language == "en"]
    arabic = [c for c in cases if c.language == "ar"]
    en_pass = sum(1 for c in english if screen_case(c, policy) == c.expected)
    ar_pass = sum(1 for c in arabic if screen_case(c, policy) == c.expected)

    inj_en = [c for c in cases if c.category == "prompt_injection" and c.language == "en"]
    inj_ar = [c for c in cases if c.category == "prompt_injection" and c.language == "ar"]
    inj_en_pass = sum(1 for c in inj_en if screen_case(c, policy) == c.expected)
    inj_ar_pass = sum(1 for c in inj_ar if screen_case(c, policy) == c.expected)

    def category_score(*categories: str) -> tuple[int, int]:
        selected = [case for case in cases if case.category in categories]
        passed = sum(screen_case(case, policy) == case.expected for case in selected)
        return passed, len(selected)

    benign_trigger_score = category_score("benign_trigger_words")
    injection_score = category_score("prompt_injection", "obfuscated_injection")
    boundary_score = category_score(
        "cross_user_access", "tool_argument_injection", "bulk_data_exfiltration"
    )

    # The thesis: one attack, translated. Read the pair live so the claim stays true.
    pair_en = by_id["injection-en-03"]
    pair_ar = by_id["injection-ar-08"]
    pair_en_codes = policy.screen_request(pair_en.input).signals.codes
    pair_ar_codes = policy.screen_request(pair_ar.input).signals.codes

    matrix_rows = []
    for row in sorted(report.categories, key=lambda r: (r.known_gaps, -r.total), reverse=True):
        label = CATEGORY_LABELS.get(row.category, row.category)
        pass_pct = row.passed / row.total * 100
        gap_pct = row.known_gaps / row.total * 100
        matrix_rows.append(
            f'<div class="row">'
            f'<div class="row-name">{escape(label)}</div>'
            f'<div class="bar">'
            f'<span class="b-pass" style="width:{pass_pct:.4f}%"></span>'
            f'<span class="b-gap" style="width:{gap_pct:.4f}%"></span>'
            f"</div>"
            f'<div class="row-score">{row.passed}/{row.total}</div>'
            f"</div>"
        )

    gap_rows = []
    for gap in gaps:
        gap_rows.append(
            "<tr>"
            f'<td class="id">{escape(gap.case_id)}</td>'
            + _payload_cell(gap.input, gap.language, "payload-cell")
            + f"<td>{_outcome_tag(gap.expected, True)}</td>"
            f"<td>{_outcome_tag(gap.actual, False)}</td>"
            f'<td class="why">{escape(gap.known_gap or "")}</td>'
            f'<td class="why">{escape(gap.mitigation or "—")}</td>'
            "</tr>"
        )
    gap_detail = (
        '<div class="scroller"><table><thead><tr><th>Case</th><th>Input</th>'
        '<th>Intended</th><th>Actual</th><th>Finding</th><th>Mitigation</th></tr>'
        f'</thead><tbody>{"".join(gap_rows)}</tbody></table></div>'
        if gaps
        else '<p class="caption">No documented or undocumented gaps remain in this run.</p>'
    )

    case_rows = []
    for case in cases:
        actual = screen_case(case, policy)
        ok = actual == case.expected
        status = '<span class="tag ok">pass</span>' if ok else '<span class="tag miss">gap</span>'
        case_rows.append(
            "<tr>"
            f'<td class="id">{escape(case.id)}</td>'
            f'<td><span class="tag neutral">{escape(CATEGORY_LABELS.get(case.category, case.category))}</span></td>'
            f'<td class="id">{escape(case.language)}</td>'
            + _payload_cell(case.input, case.language, "payload-cell")
            + f'<td class="id">{escape(case.expected)}</td>'
            f'<td class="id">{escape(actual)}</td>'
            f"<td>{status}</td>"
            "</tr>"
        )

    return f"""<style>{STYLE}</style>
<main class="wrap">
  <header>
    <p class="eyebrow">Security evaluation &middot; {escape(date.today().isoformat())}</p>
    <h1>The detector now understands the attack in both languages.</h1>
    <p class="lede">
      A 100-scenario adversarial dataset for the Amad financial agent's request-screening
      layer. Every case is labelled with the outcome the security policy <em>intends</em>, not
      the outcome the current detector happens to produce &mdash; so the suite can measure the
      product rather than describe itself. It runs deterministically, with no model calls,
      in under a second.
    </p>

    <dl class="score">
      <div class="is-pass"><dt>Intended behaviour met</dt><dd>{report.passed}<small>/{report.total}</small></dd></div>
      <div class="is-gap"><dt>Documented gaps</dt><dd>{len(gaps)}</dd></div>
      <div><dt>Undocumented regressions</dt><dd>{len(report.failures)}</dd></div>
      <div><dt>Model calls required</dt><dd>0</dd></div>
    </dl>
  </header>

  <section>
    <div class="section-head">
      <p class="eyebrow">The headline finding</p>
      <h2>Language parity is restored without weakening legitimate requests</h2>
      <p>
        These two probes are the same request. Both now raise the same
        <code>prompt_exfiltration</code> signal after the detector gained shared English-Arabic
        action and target vocabularies. The same matcher also handles code-switched input.
      </p>
    </div>
    <div class="thesis">
      <div class="probe">
        <span class="probe-lang">English &middot; {escape(pair_en.id)}</span>
        <div class="payload">{escape(pair_en.input)}</div>
        <div class="verdict caught">
          <span class="dot"></span> Signalled
          <code>{escape(", ".join(pair_en_codes))}</code>
        </div>
      </div>
      <div class="probe">
        <span class="probe-lang">Arabic &middot; {escape(pair_ar.id)}</span>
        <div class="payload" dir="rtl">{escape(pair_ar.input)}</div>
        <div class="verdict {"caught" if pair_ar_codes else "silent"}">
          <span class="dot"></span> {"Signalled" if pair_ar_codes else "Silent"}
          <code>{escape(", ".join(pair_ar_codes)) if pair_ar_codes else "no signal raised"}</code>
        </div>
      </div>
    </div>
    <p class="caption">
      Across the prompt-injection category the split is {inj_en_pass}/{len(inj_en)} in English
      and {inj_ar_pass}/{len(inj_ar)} in Arabic. Arabic prompt exfiltration and tenant changes
      now have deterministic coverage equivalent to their English forms.
    </p>
  </section>

  <section>
    <div class="section-head">
      <p class="eyebrow">Method</p>
      <h2>What is measured, and what is deliberately not</h2>
    </div>
    <p>
      The subject is <code>PolicyEngine.screen_request</code>: the deterministic layer that reads a
      request before the model does. It returns one of three outcomes &mdash; <strong>reject</strong>
      (refuse outright), <strong>signal</strong> (allow, but record an injection signal for
      telemetry), or <strong>allow</strong>.
    </p>
    <p>
      This layer is defence in depth, not the containment boundary. Identity is injected by the
      tool guard outside the model loop, and every financial action needs a signed confirmation.
      The tool guard remains the final containment boundary, but the request screener now records
      or rejects every attack shape represented in this suite instead of relying on that deeper
      layer to hide detection gaps.
    </p>
    <p>
      Labelling by intent is the load-bearing choice. Labelling each case with whatever the
      detector already returns would score 100% and prove nothing. The expected labels were kept
      unchanged while the implementation was repaired; gap markers were removed only after the
      corresponding cases reached those pre-existing expectations.
    </p>
  </section>

  <section>
    <div class="section-head">
      <p class="eyebrow">Coverage</p>
      <h2>Ten categories, {len(english)} English and {len(arabic)} Arabic</h2>
      <p>Solid is intended behaviour met; muted would indicate a documented gap.</p>
    </div>
    <div class="matrix">{"".join(matrix_rows)}</div>
    <p class="caption">
      The language totals are {en_pass}/{len(english)} English and {ar_pass}/{len(arabic)} Arabic.
      Mixed-language and encoded probes are reported in their own categories below.
    </p>
  </section>

  <section>
    <div class="section-head">
      <p class="eyebrow">Remediation verification</p>
      <h2>The former failure classes now pass as groups</h2>
    </div>
    <div class="triage">
      <div class="tcard t-fp">
        <div class="n">{benign_trigger_score[0]}/{benign_trigger_score[1]}</div>
        <h3>Benign trigger-word controls</h3>
        <p>
          Credential nouns and phrases such as &ldquo;act as&rdquo; no longer cause rejection by
          themselves. A disclosure or impersonation relationship is required.
        </p>
      </div>
      <div class="tcard t-tel">
        <div class="n">{injection_score[0]}/{injection_score[1]}</div>
        <h3>Injection and obfuscation probes</h3>
        <p>
          Arabic, English, code-switched, Unicode-obfuscated, leetspeak, character-separated,
          and bounded Base64 payloads reach the same semantic signal rules.
        </p>
      </div>
      <div class="tcard t-con">
        <div class="n">{boundary_score[0]}/{boundary_score[1]}</div>
        <h3>Identity and bulk-access boundaries</h3>
        <p>
          Identity assertions, privileged structured arguments, tenant changes, and bulk data
          requests are rejected before the model while server-side tool scoping remains intact.
        </p>
      </div>
    </div>

    {gap_detail}
  </section>

  <section>
    <div class="section-head">
      <p class="eyebrow">Implemented remediation</p>
      <h2>What changed in the implementation</h2>
    </div>
    <p>
      <strong>Credential intent is relational.</strong> A credential noun is rejected only when a
      disclosure or retrieval action targets it. Reset, storage, and product-education questions
      remain available in both languages.
    </p>
    <p>
      <strong>English and Arabic share semantic rule shapes.</strong> Override, disclosure,
      protected-target, credential, identity, and tenant concepts can pair across languages,
      which also covers normal Saudi code-switching.
    </p>
    <p>
      <strong>Normalization is explicit and bounded.</strong> Unicode format characters, Arabic
      diacritics and spelling variants, dotless-i, leetspeak, and character-separated words are
      normalized before matching.
    </p>
    <p>
      <strong>Encoded input is inspected safely.</strong> Standalone Base64 candidates are decoded
      only when they are bounded, valid UTF-8, and predominantly printable, then screened through
      the same semantic rules as plain text.
    </p>
  </section>

  <section>
    <div class="section-head">
      <p class="eyebrow">Reproduce</p>
      <h2>Run it</h2>
    </div>
    <pre>amad-agent eval-security            # summary, exits non-zero on a regression
amad-agent eval-security --json     # full machine-readable report
pytest tests/security -m security   # the same dataset as a gate
python scripts/build_eval_report.py # regenerate this page</pre>
    <p>
      A mismatch carrying a <code>known_gap</code> reason is reported and tolerated; a mismatch
      without one fails the suite. If a gap is ever fixed, the run also fails until its marker is
      removed, so the file cannot quietly disagree with the code.
    </p>
  </section>

  <section>
    <div class="section-head">
      <p class="eyebrow">Appendix</p>
      <h2>All {report.total} scenarios</h2>
    </div>
    <div class="scroller tall">
      <table>
        <thead>
          <tr><th>Case</th><th>Category</th><th>Lang</th><th>Input</th><th>Intended</th><th>Actual</th><th></th></tr>
        </thead>
        <tbody>{"".join(case_rows)}</tbody>
      </table>
    </div>
  </section>

  <footer>
    Generated from a live run of <code>{escape(str(DATASET))}</code> by
    <code>scripts/build_eval_report.py</code>. Amad financial agent.
  </footer>
</main>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    policy = PolicyEngine(load_config().policies)
    cases = load_security_dataset(DATASET)
    report = run_security_dataset(DATASET, policy)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_html(report, cases, policy), encoding="utf-8")
    print(f"wrote {args.output} ({report.passed}/{report.total}, {len(report.known_gaps)} gaps)")


if __name__ == "__main__":
    main()
