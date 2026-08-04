"""Server-rendered pages: the landing page (``/``) and dashboard (``/dashboard``)."""

from __future__ import annotations

from html import escape
from typing import Any

from app.api.design import shell

_LANDING_BODY = """
<header class="wrap" style="padding: 88px 0 66px">
  <p class="kicker">openapi in &rarr; verdict out</p>
  <h1 class="display">Your API makes promises.<br>This agent checks every one.</h1>
  <p class="lede">Point it at an OpenAPI spec and a base URL. An LLM plans
  realistic test scenarios &mdash; nominal, edge and negative &mdash; executes them
  against the live API, and reports every broken promise.</p>
  <a class="btn" href="/dashboard">Run an analysis &rarr;</a>
  <a class="btn ghost" href="/docs" style="margin-left: 10px">API reference</a>
</header>

<section class="band"><div class="wrap">
  <h2 class="section"><span class="num">01</span>The pipeline</h2>
  <p class="section-sub">A six-node LangGraph workflow. Deterministic where it
  can be, LLM-powered where it counts.</p>
  <div class="grid cols-3">
    <div><div class="cell-num">1 &mdash; parse</div>
      <div class="cell-title">Read the contract</div>
      <div class="cell-body">Validates the OpenAPI 3.x document, resolves $refs,
      extracts endpoints, schemas and auth. Pure Python.</div></div>
    <div><div class="cell-num">2 &mdash; plan</div>
      <div class="cell-title">Decide what to test</div>
      <div class="cell-body">The LLM designs nominal, edge and negative cases
      per endpoint &mdash; missing fields, wrong types, boundary values.</div></div>
    <div><div class="cell-num">3 &mdash; generate</div>
      <div class="cell-title">Write real requests</div>
      <div class="cell-body">Concrete calls with realistic fake data that
      respects formats, enums and min/max constraints.</div></div>
    <div><div class="cell-num">4 &mdash; execute</div>
      <div class="cell-title">Hit the live API</div>
      <div class="cell-body">httpx with retries and rate limiting. Every run
      also exports a standalone pytest suite you can re-run.</div></div>
    <div><div class="cell-num">5 &mdash; validate</div>
      <div class="cell-title">Compare with the spec</div>
      <div class="cell-body">Status codes and response bodies checked against
      the declared contract, latency against your threshold.</div></div>
    <div><div class="cell-num">6 &mdash; report</div>
      <div class="cell-title">Deliver the verdict</div>
      <div class="cell-body">Coverage, pass/fail per case, anomalies ranked by
      severity &mdash; as JSON and a readable report page.</div></div>
  </div>
</div></section>

<section class="band"><div class="wrap">
  <h2 class="section"><span class="num">02</span>What it catches</h2>
  <p class="section-sub">Real findings from real runs &mdash; including bugs in
  the public Swagger Petstore.</p>
  <table class="data">
    <tr><th style="width:120px">severity</th><th style="width:220px">anomaly</th><th>meaning</th></tr>
    <tr><td><span class="badge b-critical">critical</span></td>
        <td class="mono">server_error</td>
        <td class="dim">5xx crashes the spec never mentions &mdash; missing error handling</td></tr>
    <tr><td><span class="badge b-high">high</span></td>
        <td class="mono">schema_mismatch</td>
        <td class="dim">response bodies that violate the declared schema &mdash; broken contract</td></tr>
    <tr><td><span class="badge b-medium">medium</span></td>
        <td class="mono">undocumented_status</td>
        <td class="dim">status codes returned but absent from the documentation</td></tr>
    <tr><td><span class="badge b-low">low</span></td>
        <td class="mono">slow_response</td>
        <td class="dim">latency above a configurable threshold</td></tr>
  </table>
</div></section>

<section class="band"><div class="wrap">
  <h2 class="section"><span class="num">03</span>Three commands, no Docker</h2>
  <p class="section-sub">Ships with a deliberately buggy demo API so the whole
  loop is demonstrable offline.</p>
  <div class="term">
    <div><span class="p">$</span> pip install -r requirements.txt</div>
    <div><span class="p">$</span> uvicorn app.demo_api.main:app --port 8001
      &nbsp;<span class="c"># buggy demo target</span></div>
    <div><span class="p">$</span> uvicorn app.api.main:app --port 8000
      &nbsp;<span class="c"># this agent</span></div>
  </div>
</div></section>
"""

_DASHBOARD_SCRIPT = """
const form = document.getElementById('analyze-form');
document.getElementById('prefill-demo').addEventListener('click', () => {
  form.spec_url.value = 'http://127.0.0.1:8001/openapi.json';
  form.target_url.value = 'http://127.0.0.1:8001';
});
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = document.getElementById('submit-btn');
  const errorBox = document.getElementById('form-error');
  errorBox.textContent = '';
  button.disabled = true;
  button.textContent = 'starting…';
  try {
    const response = await fetch('/analyze', { method: 'POST', body: new FormData(form) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || ('HTTP ' + response.status));
    window.location.href = payload.html_url;
  } catch (error) {
    errorBox.textContent = 'error: ' + error.message;
    button.disabled = false;
    button.textContent = 'Analyze →';
  }
});
"""


def _run_rows(reports: list[dict[str, Any]]) -> str:
    if not reports:
        return (
            '<tr><td colspan="5" class="dim">No analyses yet &mdash; '
            "launch your first one above.</td></tr>"
        )
    rows = []
    for run in reports:
        rid = escape(run["report_id"])
        status = escape(run["status"])
        created = escape(str(run["created_at"])[:19].replace("T", " "))
        target = escape(run["target_url"])
        rows.append(
            "<tr>"
            f'<td class="mono"><a href="/reports/{rid}/html">{rid}</a></td>'
            f'<td class="dim">{created}</td>'
            f'<td class="mono">{target}</td>'
            f'<td><span class="badge b-{status}">{status}</span></td>'
            f'<td class="mono"><a href="/reports/{rid}/html">report</a> &middot; '
            f'<a href="/reports/{rid}">json</a></td>'
            "</tr>"
        )
    return "".join(rows)


def render_landing() -> str:
    """The product landing page served at ``/``."""
    return shell("API Test Agent — test any API against its OpenAPI spec", _LANDING_BODY)


def render_dashboard(reports: list[dict[str, Any]]) -> str:
    """The dashboard: analysis launcher + history of past runs."""
    body = f"""
<header class="wrap" style="padding: 56px 0 40px">
  <p class="kicker">dashboard</p>
  <h1 class="display" style="font-size: clamp(28px, 3.6vw, 40px)">Run an analysis</h1>
</header>

<div class="wrap" style="display: grid; grid-template-columns: minmax(0, 560px);">
  <form id="analyze-form">
    <div class="field">
      <label for="spec_url">openapi spec url</label>
      <input type="url" id="spec_url" name="spec_url"
             placeholder="http://127.0.0.1:8001/openapi.json">
      <div class="hint">&hellip;or upload the spec as a file instead:
        <input type="file" name="spec_file" accept=".json,.yaml,.yml"
               style="margin-top: 6px; display: block; font-size: 13px"></div>
    </div>
    <div class="field">
      <label for="target_url">target api base url &mdash; required</label>
      <input type="url" id="target_url" name="target_url" required
             placeholder="http://127.0.0.1:8001">
    </div>
    <div class="field">
      <label for="auth_headers">auth headers &mdash; optional json</label>
      <input type="text" id="auth_headers" name="auth_headers"
             placeholder='{{"Authorization": "Bearer &hellip;"}}'>
    </div>
    <button type="submit" class="btn" id="submit-btn">Analyze &rarr;</button>
    <button type="button" class="btn ghost" id="prefill-demo"
            style="margin-left: 10px">Use demo target</button>
    <div class="error-text" id="form-error"></div>
  </form>
</div>

<section class="band" style="margin-top: 48px"><div class="wrap">
  <h2 class="section">Past runs</h2>
  <p class="section-sub">Every analysis is persisted &mdash; reports survive restarts.</p>
  <table class="data">
    <tr><th>report</th><th>started (utc)</th><th>target</th><th>status</th><th>open</th></tr>
    {_run_rows(reports)}
  </table>
</div></section>
<script>{_DASHBOARD_SCRIPT}</script>
"""
    return shell("Dashboard — API Test Agent", body)
