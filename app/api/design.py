"""Shared design system for every server-rendered page.

One CSS baseline + one page shell so the landing page, dashboard and report
pages look like a single product. No external assets, no frameworks.
"""

from __future__ import annotations

BASE_CSS = """
:root {
  --paper: #FAF9F5; --card: #FFFFFF; --ink: #17160F; --muted: #6E6B60;
  --line: #E5E2D8; --accent: #0E7A5F; --accent-soft: #E4F1EC;
  --code-bg: #1C1B14; --code-ink: #DBD8C9;
  --crit: #B91C1C; --crit-bg: #FBEDEC; --high: #C2410C; --high-bg: #FBF0E7;
  --med: #92650A; --med-bg: #FAF3DE; --low: #1E56C6; --low-bg: #EAEFFB;
  --pass: #15803D; --pass-bg: #E8F3EA;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink);
  font: 16px/1.65 -apple-system, "Segoe UI", Roboto, sans-serif; }
.mono { font-family: ui-monospace, "Cascadia Code", Consolas, monospace; }
.wrap { max-width: 1060px; margin: 0 auto; padding: 0 24px; }
a { color: inherit; }

nav.top { border-bottom: 1px solid var(--line); }
nav.top .wrap { display: flex; align-items: baseline; justify-content: space-between;
  padding-top: 18px; padding-bottom: 18px; }
.brand { font-family: ui-monospace, Consolas, monospace; font-size: 15px;
  font-weight: 600; letter-spacing: .02em; text-decoration: none; }
.brand span { color: var(--accent); }
.navlinks { display: flex; gap: 26px; }
.navlinks a { font-family: ui-monospace, Consolas, monospace; font-size: 13px;
  color: var(--muted); text-decoration: none; }
.navlinks a:hover { color: var(--ink); }

.kicker { font-family: ui-monospace, Consolas, monospace; font-size: 12px;
  letter-spacing: .14em; text-transform: uppercase; color: var(--accent);
  margin: 0 0 14px; }
h1.display { font-family: Georgia, "Times New Roman", serif; font-weight: 400;
  font-size: clamp(34px, 5.2vw, 58px); line-height: 1.08;
  letter-spacing: -0.015em; margin: 0 0 22px; }
.lede { font-size: 18px; color: var(--muted); max-width: 640px; margin: 0 0 34px; }

.btn { display: inline-block; background: var(--ink); color: var(--paper);
  font-family: ui-monospace, Consolas, monospace; font-size: 14px;
  padding: 13px 22px; border: 1px solid var(--ink); border-radius: 6px;
  text-decoration: none; cursor: pointer; }
.btn:hover { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn.ghost { background: transparent; color: var(--ink); border-color: var(--line); }
.btn.ghost:hover { border-color: var(--ink); background: transparent; }
.btn[disabled] { opacity: .5; cursor: wait; }

section.band { border-top: 1px solid var(--line); padding: 58px 0; }
h2.section { font-family: Georgia, serif; font-weight: 400; font-size: 28px;
  margin: 0 0 8px; }
h2.section .num { font-family: ui-monospace, Consolas, monospace; font-size: 13px;
  color: var(--accent); vertical-align: super; margin-right: 10px; }
.section-sub { color: var(--muted); margin: 0 0 34px; max-width: 560px; }

.grid { display: grid; gap: 1px; background: var(--line);
  border: 1px solid var(--line); }
.grid > div { background: var(--card); padding: 22px 24px; }
.cols-3 { grid-template-columns: repeat(3, 1fr); }
.cell-num { font-family: ui-monospace, Consolas, monospace; font-size: 12px;
  color: var(--accent); letter-spacing: .1em; }
.cell-title { font-weight: 600; font-size: 15px; margin: 8px 0 6px; }
.cell-body { font-size: 14px; color: var(--muted); line-height: 1.55; }

.term { background: var(--code-bg); color: var(--code-ink); border-radius: 8px;
  padding: 20px 24px; font-family: ui-monospace, Consolas, monospace;
  font-size: 13.5px; line-height: 2; overflow-x: auto; }
.term .p { color: #8BA98F; user-select: none; }
.term .c { color: #7E7B6C; }

.badge { display: inline-block; font-family: ui-monospace, Consolas, monospace;
  font-size: 11px; font-weight: 600; letter-spacing: .08em;
  text-transform: uppercase; padding: 3px 9px; border-radius: 4px; }
.b-critical { color: var(--crit); background: var(--crit-bg); }
.b-high { color: var(--high); background: var(--high-bg); }
.b-medium { color: var(--med); background: var(--med-bg); }
.b-low { color: var(--low); background: var(--low-bg); }
.b-pass, .b-completed { color: var(--pass); background: var(--pass-bg); }
.b-fail, .b-failed { color: var(--crit); background: var(--crit-bg); }
.b-running { color: var(--med); background: var(--med-bg); }

table.data { width: 100%; border-collapse: collapse; background: var(--card);
  border: 1px solid var(--line); }
table.data th { font-family: ui-monospace, Consolas, monospace; font-size: 11px;
  letter-spacing: .1em; text-transform: uppercase; color: var(--muted);
  text-align: left; padding: 12px 16px; border-bottom: 1px solid var(--line); }
table.data td { padding: 12px 16px; font-size: 14px; vertical-align: top;
  border-bottom: 1px solid var(--line); }
table.data tr:last-child td { border-bottom: none; }
td.mono, .id { font-family: ui-monospace, Consolas, monospace; font-size: 13px; }
.dim { color: var(--muted); }

.field { margin-bottom: 22px; }
.field label { display: block; font-family: ui-monospace, Consolas, monospace;
  font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--muted); margin-bottom: 8px; }
.field input[type=text], .field input[type=url] { width: 100%; padding: 12px 14px;
  border: 1px solid var(--line); border-radius: 6px; background: var(--card);
  font-size: 15px; color: var(--ink); }
.field input:focus { outline: none; border-color: var(--accent); }
.field .hint { font-size: 13px; color: var(--muted); margin-top: 6px; }
.error-text { color: var(--crit); font-size: 14px; margin-top: 14px;
  font-family: ui-monospace, Consolas, monospace; }

.statgrid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px;
  background: var(--line); border: 1px solid var(--line); }
.statgrid > div { background: var(--card); padding: 18px 22px; }
.stat-n { font-family: ui-monospace, Consolas, monospace; font-size: 30px;
  line-height: 1.1; }
.stat-l { font-size: 12.5px; color: var(--muted); margin-top: 4px; }

footer.bottom { border-top: 1px solid var(--line); margin-top: 72px; }
footer.bottom .wrap { display: flex; justify-content: space-between; gap: 16px;
  flex-wrap: wrap; padding-top: 26px; padding-bottom: 34px;
  font-family: ui-monospace, Consolas, monospace; font-size: 12.5px;
  color: var(--muted); }
@media (max-width: 760px) {
  .cols-3 { grid-template-columns: 1fr; }
  .statgrid { grid-template-columns: repeat(2, 1fr); }
}
"""

_NAV = """
<nav class="top"><div class="wrap">
  <a class="brand" href="/">api-test-agent<span>_</span></a>
  <div class="navlinks">
    <a href="/dashboard">dashboard</a>
    <a href="/docs">api docs</a>
    <a href="/reports">reports.json</a>
  </div>
</div></nav>
"""

_FOOTER = """
<footer class="bottom"><div class="wrap">
  <div>local-first &middot; no Docker required</div>
  <div>works with any OpenAI-compatible LLM &middot; Groq (free) by default</div>
  <div>MIT license</div>
</div></footer>
"""


def shell(title: str, body: str, head_extra: str = "") -> str:
    """Wrap page content in the shared document shell (nav + footer)."""
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{title}</title><style>{BASE_CSS}</style>{head_extra}</head>"
        f"<body>{_NAV}{body}{_FOOTER}</body></html>"
    )
