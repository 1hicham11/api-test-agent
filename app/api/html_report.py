"""Render a :class:`Report` as an HTML page using the shared design system."""

from __future__ import annotations

from html import escape

from app.api.design import shell
from app.models.report import Report


def _stat(number: str, label: str) -> str:
    return (
        f'<div><div class="stat-n">{escape(number)}</div>'
        f'<div class="stat-l">{escape(label)}</div></div>'
    )


def _anomaly_rows(report: Report) -> str:
    rows = []
    for anomaly in report.sorted_anomalies():
        rows.append(
            "<tr>"
            f'<td><span class="badge b-{escape(anomaly.severity)}">'
            f"{escape(anomaly.severity)}</span></td>"
            f'<td class="mono">{escape(anomaly.type)}</td>'
            f'<td class="mono">{escape(anomaly.endpoint)}</td>'
            f'<td class="dim">{escape(anomaly.detail)}</td>'
            "</tr>"
        )
    return "".join(rows)


def _result_rows(report: Report) -> str:
    rows = []
    for result in report.results:
        verdict = (
            '<span class="badge b-pass">pass</span>'
            if result.passed
            else '<span class="badge b-fail">fail</span>'
        )
        actual = "&mdash;" if result.actual_status is None else str(result.actual_status)
        rows.append(
            "<tr>"
            f'<td class="mono">{escape(result.endpoint)}</td>'
            f"<td>{escape(result.name)}</td>"
            f'<td class="mono dim">{escape(result.category)}</td>'
            f'<td class="mono">{result.expected_status}</td>'
            f'<td class="mono">{actual}</td>'
            f'<td class="mono dim">{result.latency_ms:.0f} ms</td>'
            f"<td>{verdict}</td>"
            f'<td class="dim" style="font-size:13px">{escape(result.failure_reason or "")}</td>'
            "</tr>"
        )
    return "".join(rows)


def _failed_body(report: Report) -> str:
    return f"""
<header class="wrap" style="padding: 56px 0 32px">
  <p class="kicker">report {escape(report.report_id)}</p>
  <h1 class="display" style="font-size: clamp(28px, 3.6vw, 40px)">Analysis failed</h1>
  <p class="lede">Target: <span class="id">{escape(report.target_url)}</span></p>
</header>
<div class="wrap">
  <table class="data">
    <tr><th style="width:160px">what went wrong</th>
        <td>{escape(report.error_explanation or "unknown error")}</td></tr>
    <tr><th>raw error</th>
        <td class="mono dim" style="font-size:13px">{escape(report.error or "")}</td></tr>
  </table>
  <p style="margin-top: 26px"><a class="btn ghost" href="/dashboard">&larr; Back to dashboard</a></p>
</div>
"""


def _completed_body(report: Report) -> str:
    anomalies = (
        f"""<table class="data">
    <tr><th style="width:110px">severity</th><th style="width:200px">type</th>
        <th style="width:260px">endpoint</th><th>detail</th></tr>
    {_anomaly_rows(report)}</table>"""
        if report.anomalies
        else '<p class="dim">No anomalies detected — the API honors its contract.</p>'
    )
    notes = (
        '<section class="band"><div class="wrap"><h2 class="section">Notes</h2><ul>'
        + "".join(f'<li class="dim" style="font-size:14px">{escape(n)}</li>' for n in report.notes)
        + "</ul></div></section>"
        if report.notes
        else ""
    )
    pytest_note = (
        f'<p class="section-sub" style="margin-top:18px">Re-runnable pytest suite: '
        f'<span class="id">{escape(report.pytest_dir)}</span></p>'
        if report.pytest_dir
        else ""
    )
    return f"""
<header class="wrap" style="padding: 56px 0 36px">
  <p class="kicker">report {escape(report.report_id)} &middot; {escape(report.created_at[:19])} utc</p>
  <h1 class="display" style="font-size: clamp(28px, 3.6vw, 40px)">{escape(report.spec_title or "API analysis")}</h1>
  <p class="lede">Target: <span class="id">{escape(report.target_url)}</span></p>
</header>

<div class="wrap">
  <div class="statgrid">
    {_stat(f"{report.coverage_percent:.0f}%", "endpoint coverage")}
    {_stat(f"{report.tested_endpoints}/{report.total_endpoints}", "endpoints tested")}
    {_stat(f"{report.passed_cases}/{report.total_cases}", "cases passed")}
    {_stat(str(len(report.anomalies)), "anomalies found")}
  </div>
</div>

<section class="band"><div class="wrap">
  <h2 class="section">Anomalies</h2>
  <p class="section-sub">Ranked most severe first.</p>
  {anomalies}
</div></section>

<section class="band"><div class="wrap">
  <h2 class="section">Test results</h2>
  <table class="data">
    <tr><th>endpoint</th><th>case</th><th>category</th><th>want</th>
        <th>got</th><th>latency</th><th>verdict</th><th>reason</th></tr>
    {_result_rows(report)}
  </table>
  {pytest_note}
</div></section>
{notes}
"""


def render_html(report: Report) -> str:
    """Build the full HTML document for a report."""
    title = f"Report {report.report_id} — API Test Agent"
    body = _failed_body(report) if report.status == "failed" else _completed_body(report)
    return shell(title, body)


def render_pending(report_id: str, status: str, detail: str) -> str:
    """Auto-refreshing placeholder shown while an analysis is still running."""
    body = f"""
<header class="wrap" style="padding: 72px 0">
  <p class="kicker">report {escape(report_id)}</p>
  <h1 class="display" style="font-size: clamp(28px, 3.6vw, 40px)">
    Analysis {escape(status)}<span style="color: var(--accent)">&hellip;</span></h1>
  <p class="lede">{escape(detail)}</p>
  <p class="dim mono" style="font-size:13px">this page refreshes automatically every 3 seconds</p>
</header>
"""
    return shell(
        f"Running — {report_id}",
        body,
        head_extra='<meta http-equiv="refresh" content="3">',
    )
