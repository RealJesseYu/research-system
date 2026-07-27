"""liveview/web.py — the same picture, in a browser, on localhost.

A stdlib http.server (no dependency to install, nothing to build) that serves one
self-contained page plus a small read-only JSON API the page polls. It binds
127.0.0.1 only: this is a window onto a machine's own runs, not a service.

READ-ONLY, ENFORCED. There is no route that writes anything, and every id that
arrives from a URL is checked against the id pattern before it is used to build a
path, so no request can read outside studies/ and runs/.

    GET /                          the page
    GET /api/snapshot[?study=ID]   the whole picture (what the page polls)
    GET /api/studies               every study on disk, newest first
    GET /api/log?run=ID[&n=200]    a run's log tail
    GET /api/decision?study=ID&n=N one director turn in full, including the brief
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from liveview.reader import (
    RUNS_ROOT,
    STUDIES_ROOT,
    _ID_RE,
    full_snapshot,
    list_studies,
    read_decisions,
    tail_lines,
)

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>live view — research system</title>
<style>
  :root {
    --bg:#0e1116; --panel:#161b22; --panel2:#1c232c; --line:#2a323d;
    --fg:#e6edf3; --muted:#8b98a5; --dim:#6b7785;
    --green:#3fb950; --yellow:#d29922; --red:#f85149; --blue:#58a6ff; --cyan:#39c5cf;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg:#f6f8fa; --panel:#fff; --panel2:#f0f3f6; --line:#d8dee4;
            --fg:#1f2328; --muted:#57606a; --dim:#8c959f;
            --green:#1a7f37; --yellow:#9a6700; --red:#cf222e; --blue:#0969da; --cyan:#1b7c83; }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  code, pre, .mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
  header { position:sticky; top:0; z-index:5; background:var(--panel);
           border-bottom:1px solid var(--line); padding:12px 20px; }
  .pill { display:inline-block; padding:3px 10px; border-radius:999px; font-weight:700;
          font-size:12px; letter-spacing:.04em; }
  .running{background:color-mix(in srgb,var(--green) 18%,transparent);color:var(--green)}
  .finished{background:color-mix(in srgb,var(--cyan) 18%,transparent);color:var(--cyan)}
  .ended-badly,.vanished{background:color-mix(in srgb,var(--red) 18%,transparent);color:var(--red)}
  .unknown{background:color-mix(in srgb,var(--yellow) 18%,transparent);color:var(--yellow)}
  h1 { font-size:16px; margin:6px 0 2px; font-weight:650; }
  .sub { color:var(--muted); font-size:13px; }
  .wrap { max-width:1400px; margin:0 auto; padding:18px 20px 60px;
          display:grid; grid-template-columns:minmax(0,1.6fr) minmax(0,1fr); gap:18px; }
  @media (max-width:1000px){ .wrap{grid-template-columns:1fr} }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:10px;
          padding:14px 16px; margin-bottom:18px; }
  .card h2 { font-size:12px; letter-spacing:.08em; text-transform:uppercase;
             color:var(--muted); margin:0 0 10px; font-weight:650; }
  .now { font-size:18px; font-weight:650; }
  .meta { color:var(--muted); font-size:12.5px; margin-top:4px; }
  pre.log { background:var(--panel2); border:1px solid var(--line); border-radius:8px;
            padding:10px; max-height:240px; overflow:auto; font-size:12px;
            color:var(--muted); white-space:pre-wrap; word-break:break-word; margin:10px 0 0;}
  .label { color:var(--cyan); font-size:11px; letter-spacing:.08em; font-weight:700;
           text-transform:uppercase; margin-top:12px; }
  .prose { margin-top:4px; }
  .arc { list-style:none; padding:0; margin:0; }
  .arc li { border-left:2px solid var(--line); padding:6px 0 6px 12px; margin-left:4px; }
  .arc li.kids > ul { margin-top:8px; }
  .row { display:flex; gap:8px; align-items:baseline; flex-wrap:wrap; cursor:pointer; }
  .seq { color:var(--dim); min-width:22px; }
  .type { font-weight:650; }
  .ok{color:var(--green)} .warn{color:var(--yellow)} .bad{color:var(--red)}
  .blue{color:var(--blue)} .muted{color:var(--muted)} .dim{color:var(--dim)}
  .finding { color:var(--muted); font-size:12.5px; margin-top:2px; }
  .claims { margin:8px 0 2px; border-top:1px solid var(--line); padding-top:8px; }
  .claim { display:flex; gap:8px; font-size:12.5px; padding:2px 0; }
  .claim .v { flex:0 0 14px; }
  .stat { display:flex; justify-content:space-between; align-items:baseline;
          padding:6px 0; border-bottom:1px dashed var(--line); }
  .stat:last-child{border-bottom:none}
  .stat b { font-size:16px; font-weight:650; }
  .bar { height:6px; background:var(--panel2); border-radius:3px; overflow:hidden; margin-top:8px;}
  .bar > i { display:block; height:100%; background:var(--green); }
  .ev { border-left:3px solid var(--line); padding:8px 0 8px 10px; margin-bottom:10px; }
  .ev.fatal{border-color:var(--red)} .ev.recorded{border-color:var(--yellow)}
  .ev.watch{border-color:var(--blue)}
  .tag { font-size:10.5px; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
         padding:1px 6px; border-radius:4px; background:var(--panel2); }
  .ev.fatal .tag{color:var(--red)} .ev.recorded .tag{color:var(--yellow)}
  .ev.watch .tag{color:var(--blue)}
  .ev .why { color:var(--dim); font-size:12.5px; margin-top:3px; }
  .ev .det { color:var(--muted); font-size:12px; margin-top:3px;
             font-family:ui-monospace,monospace; white-space:pre-wrap; word-break:break-word;
             display:-webkit-box; -webkit-line-clamp:5; -webkit-box-orient:vertical;
             overflow:hidden; }
  .legend { color:var(--dim); font-size:12.5px; border-top:1px solid var(--line);
            margin-top:10px; padding-top:10px; }
  select, button { background:var(--panel2); color:var(--fg); border:1px solid var(--line);
                   border-radius:6px; padding:4px 8px; font-size:12.5px; }
  .right { float:right; color:var(--dim); font-size:12px; }
</style></head><body>
<header>
  <div class="right"><span id="tick">…</span> ·
    <select id="picker" onchange="pick()"></select></div>
  <span id="pill" class="pill unknown">…</span>
  <span id="detail" class="sub"></span>
  <h1 id="goal">loading…</h1>
  <div class="sub" id="ident"></div>
</header>
<div class="wrap">
  <div>
    <div class="card"><h2>Now</h2><div id="now"></div></div>
    <div class="card"><h2>Director's latest turn</h2><div id="turn"></div></div>
    <div class="card"><h2>The arc so far</h2><ul class="arc" id="arc"></ul></div>
  </div>
  <div>
    <div class="card"><h2>Where it stands</h2><div id="stats"></div></div>
    <div class="card"><h2>Failures</h2><div id="events"></div>
      <div class="legend">A <b>recorded</b> failure is data: it is written to the arc,
      the director reads it on its next turn, and the study continues — a traceback
      printed by a child process is one of these. Only <b>fatal</b> means the
      investigation itself ended.</div>
    </div>
  </div>
</div>
<script>
const E = s => String(s === null || s === undefined ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
const open = new Set(JSON.parse(sessionStorage.getItem("open") || "[]"));
let study = new URLSearchParams(location.search).get("study") || "";
let timer = null, secs = 0;

function age(s){ if(s===null||s===undefined) return "?"; s=Math.max(0,Math.round(s));
  if(s<60) return s+"s"; if(s<3600) return Math.floor(s/60)+"m";
  return Math.floor(s/3600)+"h"+String(Math.floor(s%3600/60)).padStart(2,"0")+"m"; }
function toks(n){ n=n||0; return n>=1e6 ? (n/1e6).toFixed(1)+"M"
  : n>=1e3 ? Math.round(n/1e3)+"k" : ""+n; }
function toggle(k){ open.has(k) ? open.delete(k) : open.add(k);
  sessionStorage.setItem("open", JSON.stringify([...open])); draw(window._snap); }
function pick(){ study = document.getElementById("picker").value;
  history.replaceState({}, "", "?study="+encodeURIComponent(study)); load(); }

function arcHtml(node){
  const kids = {}; (node.children||[]).forEach(c => kids[c.study_id] = c);
  let h = "";
  for (const a of node.arc || []) {
    const key = node.study_id + "#" + a.seq, isOpen = open.has(key);
    const good = a.results_total && a.results_verified === a.results_total;
    const counts = a.results_total
      ? `<span class="${good?'ok':'warn'}">${a.results_verified}/${a.results_total} verified</span>`
      : (a.child_termination ? `<span class="dim">${E(a.child_termination)}</span>` : "");
    h += `<li class="kids"><div class="row" onclick="toggle('${key}')">
      <span class="${a.succeeded?'ok':'warn'}">${a.succeeded?"✓":"✗"}</span>
      <span class="seq">${a.seq}.</span>
      <span class="type">${E(a.move_type)}</span>
      <span class="muted">${E(a.outcome_plain||a.outcome||"")}</span> ${counts}</div>`;
    if (a.finding) h += `<div class="finding">${E(a.finding)}</div>`;
    if (isOpen && (a.results||[]).length) {
      h += `<div class="claims">` + a.results.map(r =>
        `<div class="claim"><span class="v ${r.verified?'ok':'bad'}">${r.verified?"✓":"✗"}</span>
         <span><b>${E(r.value)}</b> — ${E(r.label)}
         <span class="dim">(${E(r.reason)})</span></span></div>`).join("") + `</div>`;
    }
    if (isOpen && (a.artifacts||[]).length)
      h += `<div class="finding">files: ${a.artifacts.map(E).join(", ")}</div>`;
    const child = kids[a.child_study_id];
    if (child) h += `<ul class="arc">${arcHtml(child)}</ul>`;
    h += `</li>`;
  }
  const f = node.in_flight || {};
  if (node.state === "running" && f.action && f.action !== "deciding") {
    h += `<li><div class="row"><span class="blue">▸</span>
      <span class="seq">${(node.arc||[]).length + 1}.</span>
      <span class="type blue">${E(f.action)} — running now</span></div>`;
    const child = (node.children||[]).find(c => c.study_id === f.child_study_id);
    if (child) h += `<ul class="arc">${arcHtml(child)}</ul>`;
    h += `</li>`;
  }
  return h || `<li class="dim">no moves recorded yet</li>`;
}

function draw(s){
  window._snap = s;
  if (!s || !s.root) { document.getElementById("goal").textContent = s && s.error || "no study"; return; }
  const h = s.health || {}, t = s.totals || {}, root = s.root, act = s.active || root;
  const pill = document.getElementById("pill");
  pill.className = "pill " + (h.state || "unknown");
  pill.textContent = (h.headline || "").split(" — ")[0];
  document.getElementById("detail").textContent = h.headline || "";
  document.getElementById("goal").textContent = root.goal || "";
  const b = root.budget || {};
  document.getElementById("ident").textContent =
    [root.study_id, (root.mode||"?") + " mode",
     b.remaining !== undefined ? `budget ${b.remaining} of ${b.total_at_node} moves left` : null,
     t.studies > 1 ? `${t.studies} studies incl. sub-investigations` : null,
     h.detail].filter(Boolean).join("  ·  ");

  const f = act.in_flight || {}, run = f.run || {};
  let now = `<div class="now">${E(act.phase)}</div>`;
  if (act.study_id !== root.study_id)
    now += `<div class="meta">in sub-investigation ${E(act.study_id)}</div>`;
  if (run.run_id) {
    now += `<div class="meta">run ${E(run.run_id)}${run.elapsed?" · running "+age(run.elapsed):""}
      · last wrote ${age(run.last_write_age)} ago
      · workspace ${run.workspace_files} file(s) · log ${run.log_bytes}B</div>`;
    now += `<pre class="log">${(run.log_tail||[]).map(E).join("\n")}</pre>`;
  } else if (f.action === "deciding") {
    now += `<div class="meta">the director is thinking — no move is running right now</div>`;
  }
  if (act.state === "running" && act.quiet_seconds !== null && act.quiet_seconds !== undefined)
    now += `<div class="meta">nothing on disk has changed for ${age(act.quiet_seconds)}</div>`;
  document.getElementById("now").innerHTML = now;

  const ds = (act.decisions || []).filter(x => !x.incomplete), d = ds[ds.length - 1] || {};
  const tm = d.timing || {};
  document.getElementById("turn").innerHTML = !ds.length ? `<span class="dim">no decision yet</span>` :
    `<div class="meta">decision ${d.seq} · ${E(tm.model||"")} ${tm.duration_seconds?("· "+tm.duration_seconds.toFixed(1)+"s"):""}</div>
     ${d.reading ? `<div class="label">What it read</div><div class="prose">${E(d.reading)}</div>` : ""}
     <div class="label">What it chose</div>
     <div class="prose"><b>${E(d.action)}</b>${d.instrument?" on "+E(d.instrument):""}${d.campaign?" [campaign]":""}</div>
     ${d.reasoning ? `<div class="label">Why</div><div class="prose">${E(d.reasoning)}</div>` : ""}
     ${d.stop_reason ? `<div class="label">Stop reason</div><div class="prose">${E(d.stop_reason)}</div>` : ""}
     ${d.detail ? `<div class="label">The brief it sent</div><pre class="log">${E(d.detail)}</pre>` : ""}`;

  document.getElementById("arc").innerHTML = arcHtml(root);

  const pct = t.claims ? Math.round(100 * t.verified / t.claims) : 0;
  document.getElementById("stats").innerHTML =
    `<div class="stat"><span>Claims that reproduced</span>
       <b class="${t.claims && t.verified===t.claims ? 'ok' : (t.verified?'warn':'bad')}">${t.verified}/${t.claims}</b></div>
     <div class="bar"><i style="width:${pct}%"></i></div>
     <div class="stat"><span>Moves run</span><b>${t.moves}</b></div>
     <div class="stat"><span>Studies (incl. children)</span><b>${t.studies}</b></div>
     <div class="stat"><span>Spend in runs, whole tree</span><b>${t.calls} calls · ${toks(t.tokens)} tok</b></div>
     ${root.spend_reported ? `<div class="stat"><span>This study's report (its runs + its director)</span>
        <b>${root.spend_reported.calls} calls · ${toks(root.spend_reported.tokens)} tok</b></div>` : ""}
     ${root.report ? `<div class="stat"><span>Termination</span>
        <b class="${h.state==='ended-badly'?'bad':''}">${E((root.termination||{}).reason)}</b></div>` : ""}`;

  const c = h.counts || {};
  document.getElementById("events").innerHTML =
    `<div class="meta" style="margin-bottom:8px">
       <span class="${c.fatal?'bad':'dim'}">${c.fatal||0} fatal</span> ·
       <span class="${c.recorded?'warn':'dim'}">${c.recorded||0} recorded</span> ·
       <span class="${c.watch?'blue':'dim'}">${c.watch||0} to watch</span></div>` +
    ((s.events||[]).map(e => `<div class="ev ${e.severity}">
       <span class="tag">${E(e.severity)}</span> ${E(e.title)}
       ${e.study_id && e.study_id !== root.study_id ? `<span class="dim"> (${E(e.study_id)})</span>` : ""}
       ${e.detail ? `<div class="det">${E(e.detail)}</div>` : ""}
       <div class="why">→ ${E(e.means)}</div></div>`).join("")
     || `<div class="dim">nothing has failed</div>`);
}

async function load(){
  try {
    const r = await fetch("/api/snapshot" + (study ? "?study="+encodeURIComponent(study) : ""));
    const s = await r.json();
    if (!study && s.study_id) study = s.study_id;
    draw(s); secs = 0;
    const ss = await (await fetch("/api/studies")).json();
    const p = document.getElementById("picker");
    if (p.options.length !== ss.length || p.value !== study) {
      p.innerHTML = ss.map(x => `<option value="${E(x.study_id)}" ${x.study_id===study?"selected":""}>
        ${x.finished ? "○" : "●"} ${E(x.study_id)}</option>`).join("");
    }
  } catch (e) {
    document.getElementById("tick").textContent = "reader unreachable — retrying";
  }
}
setInterval(() => { document.getElementById("tick").textContent = "updated " + age(secs++) + " ago"; }, 1000);
setInterval(load, 4000);
load();
</script></body></html>
"""


def _handler_class(studies_root: Path, runs_root: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "liveview"

        def log_message(self, *args):  # silence: the terminal is the run's, not ours
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:  # the page navigated away mid-write
                pass

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj, default=str).encode(), "application/json")

        def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's name
            url = urlparse(self.path)
            q = parse_qs(url.query)
            one = lambda k: (q.get(k) or [None])[0]  # noqa: E731

            def ident(value):
                return value if value and _ID_RE.match(value) and ".." not in value else None

            if url.path in ("/", "/index.html"):
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif url.path == "/api/snapshot":
                self._json(
                    full_snapshot(
                        ident(one("study")), studies_root=studies_root, runs_root=runs_root
                    )
                )
            elif url.path == "/api/studies":
                self._json(list_studies(studies_root))
            elif url.path == "/api/log":
                rid = ident(one("run"))
                if not rid:
                    return self._json({"error": "bad run id"}, 400)
                n = min(int(one("n") or 200), 2000)
                self._json({"run_id": rid,
                            "lines": tail_lines(runs_root / rid / "log.txt", limit=n)})
            elif url.path == "/api/decision":
                sid, n = ident(one("study")), one("n")
                if not sid:
                    return self._json({"error": "bad study id"}, 400)
                decisions = read_decisions(studies_root / sid, full=True)
                if n:
                    decisions = [d for d in decisions if str(d.get("seq")) == str(n)]
                self._json(decisions)
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def serve(
    *,
    port: int = 8765,
    host: str = "127.0.0.1",
    studies_root: Path = STUDIES_ROOT,
    runs_root: Path = RUNS_ROOT,
    open_browser: bool = True,
    serve_forever: bool = True,
) -> ThreadingHTTPServer:
    """Start the local view. Returns the server (already serving in a background
    thread when `serve_forever` is False, so a test can hit it and shut it down)."""
    httpd = ThreadingHTTPServer((host, port), _handler_class(Path(studies_root), Path(runs_root)))
    url = f"http://{host}:{httpd.server_address[1]}/"
    print(f"live view on {url}  (read-only; Ctrl-C to stop)")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    if not serve_forever:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return httpd
