"""Secure Dashboard module for Pesa AI Logger.

Provides public functions consumed by webhook.py:

    build_dashboard_response(api_key, session, error) -> tuple
    build_auth_response(request, api_key, session)    -> tuple
    build_logout_response(session)                    -> tuple

Architecture
------------
* Login gate  — API key entered once, stored in Flask session
* Single page — 6 tabs, all data fetched live via JS fetch()
* Zero reload — tab switching is instant, no server round-trips
* JSON APIs   — completely untouched, Android app unaffected

Tabs
----
1. Overview      — live stats, heartbeat pulse, recent transactions + type chart
2. Transactions  — filterable full ledger table with summary stats
3. Analytics     — AI insights, anomaly detection, monthly + weekly bar charts
4. Health        — system status, heartbeat history, full endpoint reference
5. Ledger        — tamper-evident chain verify + events table
6. SMS Tester    — paste any M-Pesa SMS and see it parsed live
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def build_auth_response(request, api_key: str, session: dict) -> tuple:
    """Handle POST /auth — validate API key and set session."""
    body     = request.get_json(silent=True) or {}
    provided = (body.get("key") or "").strip()

    if not api_key:
        session["authenticated"] = True
        return {"status": "ok", "message": "Open access granted"}, 200

    import hmac
    if provided and hmac.compare_digest(provided, api_key):
        session["authenticated"] = True
        return {"status": "ok", "message": "Authenticated"}, 200

    return {"status": "error", "message": "Invalid API key"}, 401


def build_logout_response(session: dict) -> tuple:
    """Handle GET /logout — clear session."""
    session.clear()
    return {"status": "ok", "message": "Logged out"}, 200


def is_authenticated(api_key: str, session: dict) -> bool:
    """Return True when the current session is allowed through."""
    if not api_key:
        return True  # No key configured = open access
    return bool(session.get("authenticated"))


# ---------------------------------------------------------------------------
# Login page
# ---------------------------------------------------------------------------

def build_login_page(error: bool = False) -> tuple:
    """Return the HTML login gate page."""
    error_html = """
      <div class="error-msg" id="errorMsg">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2.5">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        Invalid API key — please try again
      </div>""" if error else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Pesa AI Logger — Sign In</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --green:#00ff9d; --green-d:#00c97a; --bg:#050a0e;
      --border:rgba(0,255,157,0.15); --text:#e2f0eb; --muted:#4a6b5a;
    }}
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{
      font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);
      min-height:100vh;display:flex;align-items:center;justify-content:center;
      overflow:hidden;
    }}
    body::before{{
      content:'';position:fixed;inset:0;
      background-image:
        linear-gradient(rgba(0,255,157,0.025) 1px,transparent 1px),
        linear-gradient(90deg,rgba(0,255,157,0.025) 1px,transparent 1px);
      background-size:40px 40px;
      animation:gridMove 25s linear infinite;
    }}
    @keyframes gridMove{{0%{{transform:translateY(0)}}100%{{transform:translateY(40px)}}}}
    body::after{{
      content:'';position:fixed;
      width:700px;height:700px;
      background:radial-gradient(circle,rgba(0,255,157,0.05) 0%,transparent 70%);
      top:50%;left:50%;transform:translate(-50%,-50%);pointer-events:none;
    }}
    .wrap{{position:relative;z-index:10;width:100%;max-width:400px;padding:20px}}
    .logo{{text-align:center;margin-bottom:36px}}
    .logo-icon{{
      width:52px;height:52px;
      background:linear-gradient(135deg,var(--green),#00b8ff);
      border-radius:14px;display:inline-flex;align-items:center;
      justify-content:center;font-size:26px;margin-bottom:14px;
      box-shadow:0 0 40px rgba(0,255,157,0.25);
    }}
    .logo h1{{font-family:'Space Mono',monospace;font-size:18px;font-weight:700;letter-spacing:0.06em}}
    .logo p{{font-size:12px;color:var(--muted);margin-top:3px}}
    .card{{
      background:rgba(255,255,255,0.025);border:1px solid var(--border);
      border-radius:20px;padding:32px;backdrop-filter:blur(20px);
      box-shadow:0 0 0 1px rgba(0,255,157,0.04),0 32px 64px rgba(0,0,0,0.5);
    }}
    .card h2{{font-size:17px;font-weight:600;margin-bottom:5px}}
    .card p{{font-size:13px;color:var(--muted);margin-bottom:26px;line-height:1.5}}
    .field{{margin-bottom:18px}}
    .field label{{
      display:block;font-size:10px;font-weight:700;text-transform:uppercase;
      letter-spacing:0.1em;color:var(--muted);margin-bottom:7px;
      font-family:'Space Mono',monospace;
    }}
    .field input{{
      width:100%;background:rgba(0,0,0,0.35);border:1px solid rgba(255,255,255,0.07);
      border-radius:10px;padding:12px 15px;color:var(--text);font-size:13px;
      font-family:'Space Mono',monospace;letter-spacing:0.04em;outline:none;
      transition:border-color .2s,box-shadow .2s;
    }}
    .field input:focus{{border-color:var(--green);box-shadow:0 0 0 3px rgba(0,255,157,0.09)}}
    .btn{{
      width:100%;padding:13px;
      background:linear-gradient(135deg,var(--green),#00c5ff);
      border:none;border-radius:10px;color:#050a0e;font-size:13px;
      font-weight:700;font-family:'Space Mono',monospace;cursor:pointer;
      transition:opacity .2s,transform .1s;letter-spacing:0.04em;
    }}
    .btn:hover{{opacity:.9}} .btn:active{{transform:scale(.99)}}
    .btn:disabled{{opacity:.5;cursor:not-allowed}}
    .error-msg{{
      display:flex;align-items:center;gap:8px;
      background:rgba(255,77,109,0.09);border:1px solid rgba(255,77,109,0.22);
      color:#ff4d6d;font-size:12px;padding:10px 13px;border-radius:8px;
      margin-bottom:18px;
    }}
    .footer-note{{text-align:center;margin-top:14px;font-size:11px;color:var(--muted);font-family:'Space Mono',monospace}}
    .footer-note span{{color:var(--green)}}
    .spinner{{
      display:inline-block;width:14px;height:14px;
      border:2px solid rgba(5,10,14,.3);border-top-color:#050a0e;
      border-radius:50%;animation:spin .6s linear infinite;
      vertical-align:middle;margin-right:6px;
    }}
    @keyframes spin{{to{{transform:rotate(360deg)}}}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="logo">
      <div class="logo-icon">💳</div>
      <h1>PESA AI LOGGER</h1>
      <p>M-Pesa Transaction Intelligence</p>
    </div>
    <div class="card">
      <h2>Sign in to Dashboard</h2>
      <p>Enter your API key to access live monitoring and analytics.</p>
      {error_html}
      <div class="field">
        <label>API Key</label>
        <input type="password" id="apiKey" placeholder="Enter your API key…" autocomplete="current-password"/>
      </div>
      <button class="btn" id="loginBtn" onclick="doLogin()">ENTER DASHBOARD</button>
      <div class="footer-note">Secured with <span>HMAC</span> authentication</div>
    </div>
  </div>
  <script>
    document.getElementById('apiKey').addEventListener('keydown', e => {{ if(e.key==='Enter') doLogin(); }});
    async function doLogin() {{
      const key = document.getElementById('apiKey').value.trim();
      const btn = document.getElementById('loginBtn');
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span>VERIFYING…';
      try {{
        const res = await fetch('/auth', {{
          method:'POST', headers:{{'Content-Type':'application/json'}},
          body: JSON.stringify({{key}})
        }});
        window.location.href = res.ok ? '/dashboard' : '/dashboard?error=1';
      }} catch(e) {{
        btn.disabled=false; btn.innerHTML='ENTER DASHBOARD';
      }}
    }}
  </script>
</body>
</html>"""
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


# ---------------------------------------------------------------------------
# Main dashboard — single page, 6 tabs, all data via JS fetch()
# ---------------------------------------------------------------------------

def build_dashboard_page(api_key_configured: bool = False) -> tuple:
    """Return the full SPA dashboard HTML."""

    # JS fetch headers — include API key header if auth is enabled
    fetch_headers = "{'X-API-Key': sessionStorage.getItem('_pk') || ''}" if api_key_configured else "{}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Pesa AI Logger — Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
  <style>
    /* ── Tokens ── */
    :root {{
      --green:#00ff9d; --green-d:#00c97a; --blue:#00b8ff;
      --red:#ff4d6d;   --yellow:#ffd166;  --purple:#c084fc;
      --bg:#050a0e;    --bg2:#0b1318;     --bg3:#111d24;
      --surface:rgba(255,255,255,0.03);
      --border:rgba(0,255,157,0.1);   --border2:rgba(255,255,255,0.06);
      --text:#e2f0eb;  --muted:#4a6b5a;   --muted2:#1a2e24;
      --mono:'Space Mono',monospace;  --sans:'DM Sans',sans-serif;
      --r:12px; --sidebar:210px;
    }}
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:var(--sans);background:var(--bg);color:var(--text);height:100vh;display:flex;overflow:hidden}}
    ::-webkit-scrollbar{{width:3px;height:3px}}
    ::-webkit-scrollbar-track{{background:transparent}}
    ::-webkit-scrollbar-thumb{{background:var(--muted2);border-radius:2px}}

    /* ── Sidebar ── */
    .sidebar{{
      width:var(--sidebar);min-width:var(--sidebar);background:var(--bg2);
      border-right:1px solid var(--border2);display:flex;flex-direction:column;z-index:100;
    }}
    .sb-logo{{padding:22px 18px 18px;border-bottom:1px solid var(--border2)}}
    .sb-logo .icon{{
      width:34px;height:34px;background:linear-gradient(135deg,var(--green),var(--blue));
      border-radius:9px;display:inline-flex;align-items:center;justify-content:center;
      font-size:17px;margin-bottom:9px;box-shadow:0 0 18px rgba(0,255,157,0.18);
    }}
    .sb-logo h1{{font-family:var(--mono);font-size:11px;font-weight:700;letter-spacing:.07em;line-height:1.4}}
    .sb-logo p{{font-size:10px;color:var(--muted);margin-top:2px}}
    .nav{{flex:1;padding:10px 6px;overflow-y:auto}}
    .nav-sec{{font-size:9px;font-family:var(--mono);letter-spacing:.12em;color:var(--muted);padding:10px 10px 5px;text-transform:uppercase}}
    .nav-item{{
      display:flex;align-items:center;gap:9px;padding:8px 10px;border-radius:7px;
      cursor:pointer;font-size:12px;font-weight:500;color:var(--muted);
      transition:all .15s;border:1px solid transparent;margin-bottom:1px;text-decoration:none;
    }}
    .nav-item:hover{{background:var(--surface);color:var(--text)}}
    .nav-item.active{{background:rgba(0,255,157,0.07);border-color:var(--border);color:var(--green)}}
    .nav-item .ic{{font-size:14px;width:18px;text-align:center}}
    .nav-item .tag{{
      margin-left:auto;background:rgba(0,255,157,0.12);color:var(--green);
      font-size:9px;font-family:var(--mono);padding:1px 5px;border-radius:9999px;
    }}
    .sb-foot{{padding:14px;border-top:1px solid var(--border2)}}
    .logout{{
      display:flex;align-items:center;gap:7px;width:100%;padding:7px 10px;
      background:transparent;border:1px solid rgba(255,77,109,.18);border-radius:7px;
      color:var(--red);font-size:11px;font-family:var(--mono);cursor:pointer;transition:all .15s;
    }}
    .logout:hover{{background:rgba(255,77,109,.07);border-color:rgba(255,77,109,.35)}}

    /* ── Main ── */
    .main{{flex:1;display:flex;flex-direction:column;overflow:hidden}}
    .topbar{{
      height:52px;min-height:52px;background:var(--bg2);border-bottom:1px solid var(--border2);
      display:flex;align-items:center;justify-content:space-between;padding:0 24px;
    }}
    .topbar-title{{font-size:14px;font-weight:600}}
    .tb-right{{display:flex;align-items:center;gap:14px}}
    .pulse{{width:7px;height:7px;background:var(--green);border-radius:50%;box-shadow:0 0 7px var(--green);animation:pulse 2s infinite}}
    @keyframes pulse{{0%,100%{{opacity:1;box-shadow:0 0 7px var(--green)}}50%{{opacity:.4;box-shadow:0 0 3px var(--green)}}}}
    .tb-status{{font-size:11px;font-family:var(--mono);color:var(--green)}}
    .btn-refresh{{
      background:var(--surface);border:1px solid var(--border2);color:var(--muted);
      padding:5px 10px;border-radius:6px;font-size:11px;cursor:pointer;
      font-family:var(--mono);transition:all .15s;
    }}
    .btn-refresh:hover{{color:var(--text);border-color:var(--border)}}
    .content{{flex:1;overflow-y:auto;padding:24px}}

    /* ── Tabs ── */
    .tab{{display:none}} .tab.active{{display:block}}

    /* ── Stat grid ── */
    .stat-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:20px}}
    .sc{{
      background:var(--bg3);border:1px solid var(--border2);border-radius:var(--r);
      padding:18px;position:relative;overflow:hidden;transition:border-color .2s;
    }}
    .sc:hover{{border-color:var(--border)}}
    .sc::after{{
      content:'';position:absolute;top:0;right:0;width:50px;height:50px;
      background:radial-gradient(circle,rgba(0,255,157,0.05) 0%,transparent 70%);
    }}
    .sc .lbl{{font-size:9px;font-family:var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:.09em}}
    .sc .val{{font-size:26px;font-weight:700;color:var(--green);margin:7px 0 3px;font-family:var(--mono);line-height:1}}
    .sc .sub{{font-size:10px;color:var(--muted)}}
    .val.red{{color:var(--red)}} .val.blue{{color:var(--blue)}} .val.white{{color:var(--text)}}

    /* ── Two-col ── */
    .two-col{{display:grid;grid-template-columns:1fr 340px;gap:18px}}
    @media(max-width:1080px){{.two-col{{grid-template-columns:1fr}}}}

    /* ── Panel ── */
    .panel{{background:var(--bg3);border:1px solid var(--border2);border-radius:var(--r);overflow:hidden}}
    .ph{{
      padding:14px 18px;border-bottom:1px solid var(--border2);
      display:flex;align-items:center;justify-content:space-between;
    }}
    .pt{{font-size:11px;font-family:var(--mono);font-weight:700;color:var(--text);text-transform:uppercase;letter-spacing:.06em}}
    .pb{{padding:18px}}
    .pa{{font-size:10px;color:var(--muted);cursor:pointer;font-family:var(--mono);background:none;border:none;transition:color .15s}}
    .pa:hover{{color:var(--green)}}

    /* ── Table ── */
    .tw{{overflow-x:auto}}
    table{{width:100%;border-collapse:collapse}}
    th{{
      padding:9px 12px;text-align:left;font-size:9px;font-family:var(--mono);
      color:var(--muted);text-transform:uppercase;letter-spacing:.09em;
      border-bottom:1px solid var(--border2);white-space:nowrap;
    }}
    td{{padding:10px 12px;font-size:11px;border-bottom:1px solid rgba(255,255,255,.025);white-space:nowrap}}
    tr:last-child td{{border-bottom:none}}
    tr:hover td{{background:rgba(0,255,157,.015)}}

    /* ── Chips ── */
    .chip{{display:inline-block;padding:2px 7px;border-radius:9999px;font-size:9px;font-family:var(--mono);font-weight:700;letter-spacing:.02em}}
    .cg{{background:rgba(0,255,157,.1);color:var(--green)}}
    .cb{{background:rgba(0,184,255,.1);color:var(--blue)}}
    .cr{{background:rgba(255,77,109,.1);color:var(--red)}}
    .cy{{background:rgba(255,209,102,.1);color:var(--yellow)}}
    .cp{{background:rgba(192,132,252,.1);color:var(--purple)}}
    .cx{{background:rgba(255,255,255,.05);color:var(--muted)}}

    .amt{{color:var(--green);font-family:var(--mono);font-weight:700}}
    .mn{{font-family:var(--mono);font-size:10px}}
    .mu{{color:var(--muted)}}

    .empty{{text-align:center;padding:40px 16px;color:var(--muted);font-size:12px}}
    .empty .ei{{font-size:28px;display:block;margin-bottom:10px}}

    /* ── Filters ── */
    .frow{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px;align-items:center}}
    .frow select,.frow input{{
      background:var(--bg);border:1px solid var(--border2);color:var(--text);
      padding:7px 11px;border-radius:7px;font-size:11px;font-family:var(--sans);
      outline:none;transition:border-color .15s;
    }}
    .frow select:focus,.frow input:focus{{border-color:var(--green)}}
    .frow select{{cursor:pointer}} .frow select option{{background:var(--bg2)}}
    .btn-s{{padding:7px 13px;border-radius:7px;font-size:11px;font-family:var(--mono);font-weight:700;cursor:pointer;border:none;transition:all .15s}}
    .bp{{background:var(--green);color:var(--bg)}} .bp:hover{{background:var(--green-d)}}
    .bg{{background:transparent;border:1px solid var(--border2);color:var(--muted)}} .bg:hover{{color:var(--text);border-color:var(--border)}}

    /* ── Insight ── */
    .ins{{display:flex;gap:10px;padding:12px 0;border-bottom:1px solid var(--border2)}}
    .ins:last-child{{border-bottom:none}}
    .ins-dot{{width:5px;min-width:5px;height:5px;background:var(--green);border-radius:50%;margin-top:7px;box-shadow:0 0 5px var(--green)}}
    .ins-txt{{font-size:12px;line-height:1.65;color:var(--text)}}

    /* ── Anomaly ── */
    .anom{{background:rgba(255,77,109,.04);border:1px solid rgba(255,77,109,.13);border-radius:9px;padding:13px;margin-bottom:9px}}
    .anom-type{{font-size:10px;font-family:var(--mono);color:var(--red);text-transform:uppercase;letter-spacing:.06em}}
    .anom-desc{{font-size:12px;color:var(--text);margin-top:3px}}
    .anom-meta{{font-size:10px;color:var(--muted);margin-top:5px;font-family:var(--mono)}}

    /* ── Health ── */
    .hstat{{display:flex;align-items:center;gap:14px;padding:18px;background:var(--bg);border-radius:9px;border:1px solid var(--border2);margin-bottom:14px}}
    .hstat .hico{{font-size:28px}}
    .hstat .hlbl{{font-size:18px;font-weight:700;font-family:var(--mono)}}
    .hstat .hsub{{font-size:11px;color:var(--muted);margin-top:3px}}

    /* ── Ledger ── */
    .lv{{display:flex;align-items:center;gap:11px;padding:16px;border-radius:9px;margin-bottom:14px;font-family:var(--mono);font-size:12px}}
    .lv.ok{{background:rgba(0,255,157,.05);border:1px solid rgba(0,255,157,.18);color:var(--green)}}
    .lv.err{{background:rgba(255,77,109,.05);border:1px solid rgba(255,77,109,.18);color:var(--red)}}

    /* ── SMS tester ── */
    .sms-in{{
      width:100%;background:var(--bg);border:1px solid var(--border2);border-radius:9px;
      padding:14px;color:var(--text);font-size:12px;font-family:var(--mono);
      resize:vertical;min-height:110px;outline:none;transition:border-color .15s;line-height:1.65;
    }}
    .sms-in:focus{{border-color:var(--green);box-shadow:0 0 0 3px rgba(0,255,157,.07)}}
    .res{{
      background:var(--bg);border:1px solid var(--border2);border-radius:9px;
      padding:14px;font-family:var(--mono);font-size:11px;line-height:1.7;
      min-height:130px;overflow-x:auto;white-space:pre-wrap;word-break:break-all;
    }}
    .res.ok{{color:var(--green)}} .res.err{{color:var(--red)}} .res.idle{{color:var(--muted)}}

    /* ── Chart ── */
    .cw{{position:relative;height:200px}}

    /* ── Skeleton ── */
    .sk{{
      background:linear-gradient(90deg,var(--bg3) 25%,rgba(255,255,255,.03) 50%,var(--bg3) 75%);
      background-size:200% 100%;animation:shim 1.5s infinite;border-radius:4px;height:12px;margin-bottom:7px;
    }}
    @keyframes shim{{0%{{background-position:-200% 0}}100%{{background-position:200% 0}}}}

    /* ── Toast ── */
    .toast{{
      position:fixed;bottom:20px;right:20px;background:var(--bg3);border:1px solid var(--border);
      border-radius:9px;padding:10px 16px;font-size:12px;font-family:var(--mono);color:var(--green);
      z-index:9999;transform:translateY(60px);opacity:0;transition:all .3s cubic-bezier(.34,1.56,.64,1);pointer-events:none;
    }}
    .toast.show{{transform:translateY(0);opacity:1}}

    /* ── Loading ── */
    .ld{{display:inline-flex;align-items:center;gap:7px;color:var(--muted);font-size:11px;font-family:var(--mono)}}
    .ld::before{{content:'';width:12px;height:12px;border:2px solid var(--muted2);border-top-color:var(--green);border-radius:50%;animation:spin .6s linear infinite}}
    @keyframes spin{{to{{transform:rotate(360deg)}}}}
  </style>
</head>
<body>

<!-- ── Sidebar ── -->
<aside class="sidebar">
  <div class="sb-logo">
    <div class="icon">💳</div>
    <h1>PESA AI<br>LOGGER</h1>
    <p>M-Pesa Intelligence</p>
  </div>
  <nav class="nav">
    <div class="nav-sec">Monitor</div>
    <a class="nav-item active" onclick="showTab('overview',this)"><span class="ic">⚡</span>Overview</a>
    <a class="nav-item" onclick="showTab('health',this)"><span class="ic">❤️</span>Health</a>
    <div class="nav-sec">Data</div>
    <a class="nav-item" onclick="showTab('transactions',this)"><span class="ic">📋</span>Transactions</a>
    <a class="nav-item" onclick="showTab('analytics',this)"><span class="ic">📊</span>Analytics</a>
    <div class="nav-sec">Security</div>
    <a class="nav-item" onclick="showTab('ledger',this)"><span class="ic">🔐</span>Ledger</a>
    <div class="nav-sec">Tools</div>
    <a class="nav-item" onclick="showTab('sms',this)"><span class="ic">🧪</span>SMS Tester</a>
    <a class="nav-item" href="/export/csv" target="_blank"><span class="ic">⬇️</span>Export CSV<span class="tag">CSV</span></a>
  </nav>
  <div class="sb-foot">
    <button class="logout" onclick="doLogout()"><span>⏻</span> Sign Out</button>
  </div>
</aside>

<!-- ── Main ── -->
<div class="main">
  <div class="topbar">
    <span class="topbar-title" id="pageTitle">Overview</span>
    <div class="tb-right">
      <span class="pulse"></span>
      <span class="tb-status" id="tbStatus">LIVE</span>
      <button class="btn-refresh" onclick="refreshTab()">↻ Refresh</button>
    </div>
  </div>

  <div class="content">

    <!-- ━━━ OVERVIEW ━━━ -->
    <div class="tab active" id="tab-overview">
      <div class="stat-grid" id="ovStats">
        <div class="sc"><div class="sk" style="width:50%"></div><div class="sk" style="width:35%;height:24px"></div></div>
        <div class="sc"><div class="sk" style="width:50%"></div><div class="sk" style="width:35%;height:24px"></div></div>
        <div class="sc"><div class="sk" style="width:50%"></div><div class="sk" style="width:35%;height:24px"></div></div>
        <div class="sc"><div class="sk" style="width:50%"></div><div class="sk" style="width:35%;height:24px"></div></div>
      </div>
      <div class="two-col">
        <div class="panel">
          <div class="ph"><span class="pt">Recent Transactions</span>
            <button class="pa" onclick="showTab('transactions',document.querySelectorAll('.nav-item')[2])">View all →</button>
          </div>
          <div class="tw">
            <table>
              <thead><tr><th>ID</th><th>Type</th><th>Amount</th><th>Category</th><th>Time (UTC)</th></tr></thead>
              <tbody id="ovTxBody"><tr><td colspan="5"><div class="ld" style="padding:18px">Loading…</div></td></tr></tbody>
            </table>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:14px">
          <div class="panel">
            <div class="ph"><span class="pt">By Type</span></div>
            <div class="pb"><div class="cw"><canvas id="typeChart"></canvas></div></div>
          </div>
          <div class="panel">
            <div class="ph"><span class="pt">Heartbeat</span></div>
            <div class="pb" id="ovHb"><div class="ld">Checking…</div></div>
          </div>
        </div>
      </div>
    </div>

    <!-- ━━━ TRANSACTIONS ━━━ -->
    <div class="tab" id="tab-transactions">
      <div class="stat-grid" id="txStats">
        <div class="sc"><div class="sk" style="width:50%"></div><div class="sk" style="width:35%;height:24px"></div></div>
        <div class="sc"><div class="sk" style="width:50%"></div><div class="sk" style="width:35%;height:24px"></div></div>
        <div class="sc"><div class="sk" style="width:50%"></div><div class="sk" style="width:35%;height:24px"></div></div>
      </div>
      <div class="panel">
        <div class="ph"><span class="pt">Transaction Ledger</span><a href="/export/csv" class="btn-s bg" style="text-decoration:none">⬇ CSV</a></div>
        <div class="pb">
          <div class="frow">
            <select id="txType" onchange="loadTx()">
              <option value="">All Types</option>
              <option value="send_money">Send Money</option>
              <option value="receive_money">Receive</option>
              <option value="pay_bill">Pay Bill</option>
              <option value="buy_goods">Buy Goods</option>
              <option value="withdraw">Withdraw</option>
              <option value="airtime">Airtime</option>
              <option value="deposit">Deposit</option>
            </select>
            <input type="text" id="txCat" placeholder="Category…" style="width:130px" oninput="debounceFn(loadTx,400)()"/>
            <input type="number" id="txLim" value="100" min="10" max="1000" style="width:75px" oninput="debounceFn(loadTx,400)()"/>
            <button class="btn-s bp" onclick="loadTx()">Filter</button>
            <button class="btn-s bg" onclick="clearTxF()">Clear</button>
          </div>
          <div class="tw">
            <table>
              <thead><tr><th>ID</th><th>Type</th><th>Amount</th><th>Balance</th><th>Category</th><th>Source</th><th>Time (UTC)</th></tr></thead>
              <tbody id="txBody"><tr><td colspan="7"><div class="ld" style="padding:18px">Loading…</div></td></tr></tbody>
            </table>
          </div>
          <div id="txMeta" style="font-size:10px;color:var(--muted);font-family:var(--mono);margin-top:10px;padding-top:10px;border-top:1px solid var(--border2)"></div>
        </div>
      </div>
    </div>

    <!-- ━━━ ANALYTICS ━━━ -->
    <div class="tab" id="tab-analytics">
      <div class="two-col">
        <div style="display:flex;flex-direction:column;gap:16px">
          <div class="panel">
            <div class="ph">
              <span class="pt">AI Insights</span>
              <select id="insDays" onchange="loadInsights()" style="background:var(--bg);border:1px solid var(--border2);color:var(--muted);padding:4px 7px;border-radius:5px;font-size:10px">
                <option value="7">7 days</option>
                <option value="30" selected>30 days</option>
                <option value="90">90 days</option>
              </select>
            </div>
            <div class="pb" id="insBody"><div class="ld">Generating…</div></div>
          </div>
          <div class="panel">
            <div class="ph"><span class="pt">Anomalies</span><span id="anomCount" style="font-size:10px;font-family:var(--mono);color:var(--muted)">—</span></div>
            <div class="pb" id="anomBody"><div class="ld">Scanning…</div></div>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:16px">
          <div class="panel">
            <div class="ph"><span class="pt">Monthly</span></div>
            <div class="pb"><div class="cw"><canvas id="monthChart"></canvas></div></div>
          </div>
          <div class="panel">
            <div class="ph"><span class="pt">Weekly</span></div>
            <div class="pb"><div class="cw"><canvas id="weekChart"></canvas></div></div>
          </div>
        </div>
      </div>
    </div>

    <!-- ━━━ HEALTH ━━━ -->
    <div class="tab" id="tab-health">
      <div id="hStatus" style="margin-bottom:16px"><div class="ld">Checking…</div></div>
      <div class="two-col">
        <div class="panel">
          <div class="ph"><span class="pt">Heartbeat History</span><button class="pa" onclick="loadHbHistory()">↻</button></div>
          <div class="tw">
            <table>
              <thead><tr><th>Status</th><th>Last SMS</th><th>Alert</th><th>Checked At</th></tr></thead>
              <tbody id="hbHist"><tr><td colspan="4"><div class="ld" style="padding:18px">Loading…</div></td></tr></tbody>
            </table>
          </div>
        </div>
        <div class="panel">
          <div class="ph"><span class="pt">API Reference</span></div>
          <div class="pb" id="epList"></div>
        </div>
      </div>
    </div>

    <!-- ━━━ LEDGER ━━━ -->
    <div class="tab" id="tab-ledger">
      <div id="ledgerV" style="margin-bottom:16px"><div class="ld">Verifying chain…</div></div>
      <div class="panel">
        <div class="ph"><span class="pt">Ledger Events</span><button class="pa" onclick="loadLedger()">↻ Refresh</button></div>
        <div class="tw">
          <table>
            <thead><tr><th>Seq</th><th>Table</th><th>Entity ID</th><th>Event Hash</th><th>Prev Hash</th><th>Created At</th></tr></thead>
            <tbody id="ledgerBody"><tr><td colspan="6"><div class="ld" style="padding:18px">Loading…</div></td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ━━━ SMS TESTER ━━━ -->
    <div class="tab" id="tab-sms">
      <div class="two-col">
        <div style="display:flex;flex-direction:column;gap:14px">
          <div class="panel">
            <div class="ph"><span class="pt">Paste M-Pesa SMS</span></div>
            <div class="pb">
              <textarea class="sms-in" id="smsIn" placeholder="Paste any M-Pesa SMS here…&#10;&#10;Example:&#10;BC47YUI Confirmed. Ksh1,000.00 sent to JOHN DOE&#10;0712345678 on 1/3/26 at 10:30 AM. New M-PESA&#10;balance is Ksh5,000.00. Transaction cost, Ksh14.00."></textarea>
              <div style="display:flex;gap:8px;margin-top:10px">
                <button class="btn-s bp" onclick="testSMS()">⚡ Parse &amp; Submit</button>
                <button class="btn-s bg" onclick="clearSMS()">Clear</button>
                <button class="btn-s bg" onclick="loadSample(0)">Sample</button>
              </div>
            </div>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:14px">
          <div class="panel">
            <div class="ph">
              <span class="pt">Parse Result</span>
              <span id="smsStatus" style="font-size:9px;font-family:var(--mono);color:var(--muted)">IDLE</span>
            </div>
            <div class="pb">
              <div class="res idle" id="smsRes">// Result will appear here…

Submit an SMS to see the parsed
transaction data from the API.</div>
            </div>
          </div>
          <div class="panel">
            <div class="ph"><span class="pt">Sample Templates</span></div>
            <div class="pb" id="sampleList" style="display:flex;flex-direction:column;gap:7px"></div>
          </div>
        </div>
      </div>
    </div>

  </div><!-- /content -->
</div><!-- /main -->

<div class="toast" id="toast"></div>

<script>
// ── Constants ──
const HEADERS = {fetch_headers};
const SAMPLES = [
  {{label:'Send Money',    sms:'BC47YUI Confirmed. Ksh1,000.00 sent to JOHN DOE 0712345678 on 1/3/26 at 10:30 AM. New M-PESA balance is Ksh5,000.00. Transaction cost, Ksh14.00.'}},
  {{label:'Receive Money', sms:'AA11BBB Confirmed you have received Ksh500.00 from JANE SMITH 0723456789 on 1/3/26 at 2:15 PM. New M-PESA balance is Ksh5,500.00.'}},
  {{label:'Pay Bill',      sms:'QR55TYU Confirmed. Ksh2,500.00 paid to KENYA POWER 123456 account on 1/3/26 at 8:00 AM. New M-PESA balance is Ksh3,000.00. Transaction cost Ksh30.00.'}},
  {{label:'Buy Goods',     sms:'ZX99KLM Confirmed. Ksh350.00 paid to NAIVAS SUPERMARKET 654321 on 1/3/26 at 3:45 PM. New M-PESA balance is Ksh4,650.00.'}},
];

// ── State ──
let curTab = 'overview';
let charts = {{}};
let dbt     = {{}};

// ── Helpers ──
function toast(msg, col='var(--green)') {{
  const t = document.getElementById('toast');
  t.textContent = msg; t.style.color = col;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2600);
}}

function debounceFn(fn, ms) {{
  return (...a) => {{ clearTimeout(dbt[fn]); dbt[fn] = setTimeout(() => fn(...a), ms); }};
}}

function fmt(n) {{
  if (n === null || n === undefined || n === '') return '—';
  return parseFloat(n).toLocaleString('en-KE', {{minimumFractionDigits:2,maximumFractionDigits:2}});
}}

function esc(v) {{
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}}

function shortText(v, n) {{
  return esc(String(v ?? '—').substring(0, n));
}}

function chip(type) {{
  const m = {{
    send_money:['cb','Send'],receive_money:['cg','Receive'],
    pay_bill:['cp','Pay Bill'],buy_goods:['cy','Goods'],
    withdraw:['cr','Withdraw'],airtime:['cx','Airtime'],
    deposit:['cg','Deposit'],reversal:['cr','Reversal'],
  }};
  const [c,l] = m[type]||['cx',type||'—'];
  return `<span class="chip ${{c}}">${{esc(l)}}</span>`;
}}

async function api(url) {{
  try {{
    const r = await fetch(url, {{headers: HEADERS}});
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }} catch(e) {{ console.error(url, e); return null; }}
}}

// ── Tab switching ──
function showTab(name, el) {{
  document.querySelectorAll('.tab').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  if (el) el.classList.add('active');
  curTab = name;
  const titles = {{overview:'Overview',transactions:'Transactions',analytics:'Analytics',health:'Health',ledger:'Ledger',sms:'SMS Tester'}};
  document.getElementById('pageTitle').textContent = titles[name]||name;
  loadTabData(name);
}}

function refreshTab() {{ loadTabData(curTab); toast('↻ Refreshed'); }}

function loadTabData(n) {{
  if (n==='overview')     loadOverview();
  if (n==='transactions') loadTx();
  if (n==='analytics')    loadAnalytics();
  if (n==='health')       loadHealth();
  if (n==='ledger')       loadLedger();
  if (n==='sms')          buildSamples();
}}

// ── Charts ──
function mkChart(id, type, labels, datasets, opts={{}}) {{
  const ctx = document.getElementById(id);
  if (!ctx) return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(ctx, {{
    type,
    data: {{labels, datasets}},
    options: {{
      responsive:true, maintainAspectRatio:false,
      plugins:{{ legend:{{ labels:{{ color:'#4a6b5a', font:{{size:9}}, padding:7, boxWidth:9 }} }} }},
      ...opts
    }}
  }});
}}

// ━━━ OVERVIEW ━━━
async function loadOverview() {{
  const [txs, hb] = await Promise.all([api('/transactions?limit=500'), api('/monitor/heartbeat?record=0')]);
  if (txs) {{
    const total  = txs.length;
    const inc    = txs.filter(t=>['receive_money','deposit'].includes(t.transaction_type)).reduce((s,t)=>s+parseFloat(t.amount||0),0);
    const spt    = txs.filter(t=>['send_money','pay_bill','buy_goods','withdraw','airtime'].includes(t.transaction_type)).reduce((s,t)=>s+parseFloat(t.amount||0),0);
    const net    = inc - spt;
    document.getElementById('ovStats').innerHTML = `
      <div class="sc"><div class="lbl">Transactions</div><div class="val">${{total}}</div><div class="sub">All time</div></div>
      <div class="sc"><div class="lbl">Received</div><div class="val" style="font-size:17px">Ksh ${{fmt(inc)}}</div><div class="sub">Deposits + Inflows</div></div>
      <div class="sc"><div class="lbl">Spent</div><div class="val red" style="font-size:17px">Ksh ${{fmt(spt)}}</div><div class="sub">Outflows</div></div>
      <div class="sc"><div class="lbl">Net Flow</div><div class="val ${{net>=0?'':'red'}}" style="font-size:17px">Ksh ${{fmt(net)}}</div><div class="sub">Balance change</div></div>`;

    document.getElementById('ovTxBody').innerHTML = txs.slice(0,8).map(t=>`<tr>
      <td class="mn mu">${{shortText(t.id,8)}}…</td>
      <td>${{chip(t.transaction_type)}}</td>
      <td class="amt">Ksh ${{fmt(t.amount)}}</td>
      <td class="mu" style="font-size:10px">${{esc(t.category||'—')}}</td>
      <td class="mn mu">${{shortText(t.event_time_utc,19)}}</td>
    </tr>`).join('') || `<tr><td colspan="5" class="empty"><span class="ei">📭</span>No transactions yet</td></tr>`;

    const tc = {{}};
    txs.forEach(t=>{{ tc[t.transaction_type||'unknown']=(tc[t.transaction_type||'unknown']||0)+1; }});
    mkChart('typeChart','doughnut',Object.keys(tc),[{{data:Object.values(tc),backgroundColor:['#00ff9d','#00b8ff','#ffd166','#ff4d6d','#c084fc','#fb923c','#2dd4bf','#e879f9'],borderColor:'#111d24',borderWidth:2}}]);
  }}
  if (hb) {{
    const ok = hb.status==='ok';
    document.getElementById('ovHb').innerHTML = `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <span style="font-size:20px">${{ok?'✅':'⚠️'}}</span>
        <div>
          <div style="font-family:var(--mono);font-size:13px;color:${{ok?'var(--green)':'var(--red)'}}">${{ok?'HEALTHY':'ALERT'}}</div>
          <div style="font-size:10px;color:var(--muted);margin-top:2px">${{esc(hb.status)}}</div>
        </div>
      </div>
      <div style="font-size:10px;color:var(--muted);font-family:var(--mono)">Last SMS: ${{esc(hb.last_sms_utc||'No data')}}</div>`;
    document.getElementById('tbStatus').textContent = ok?'LIVE':'ALERT';
    document.getElementById('tbStatus').style.color = ok?'var(--green)':'var(--red)';
  }}
}}

// ━━━ TRANSACTIONS ━━━
async function loadTx() {{
  const type = document.getElementById('txType').value;
  const cat  = document.getElementById('txCat').value;
  const lim  = document.getElementById('txLim').value||100;
  let url = `/transactions?limit=${{lim}}`;
  if (type) url+=`&type=${{encodeURIComponent(type)}}`;
  if (cat)  url+=`&category=${{encodeURIComponent(cat)}}`;
  const data = await api(url);
  if (!data) return;
  const inc = data.filter(t=>['receive_money','deposit'].includes(t.transaction_type)).reduce((s,t)=>s+parseFloat(t.amount||0),0);
  const spt = data.filter(t=>['send_money','pay_bill','buy_goods','withdraw','airtime'].includes(t.transaction_type)).reduce((s,t)=>s+parseFloat(t.amount||0),0);
  document.getElementById('txStats').innerHTML = `
    <div class="sc"><div class="lbl">Showing</div><div class="val">${{data.length}}</div><div class="sub">transactions</div></div>
    <div class="sc"><div class="lbl">Received</div><div class="val" style="font-size:16px">Ksh ${{fmt(inc)}}</div><div class="sub">This view</div></div>
    <div class="sc"><div class="lbl">Spent</div><div class="val red" style="font-size:16px">Ksh ${{fmt(spt)}}</div><div class="sub">This view</div></div>`;
  document.getElementById('txBody').innerHTML = data.length
    ? data.map(t=>`<tr>
        <td class="mn mu">${{shortText(t.id,8)}}…</td>
        <td>${{chip(t.transaction_type)}}</td>
        <td class="amt">Ksh ${{fmt(t.amount)}}</td>
        <td class="mn mu">${{t.balance_after?'Ksh '+fmt(t.balance_after):'—'}}</td>
        <td class="mu" style="font-size:10px">${{esc(t.category||'—')}}</td>
        <td class="mu" style="font-size:10px">${{shortText(t.source,18)}}</td>
        <td class="mn mu">${{shortText(t.event_time_utc,19)}}</td>
      </tr>`).join('')
    : `<tr><td colspan="7" class="empty"><span class="ei">🔍</span>No results for these filters</td></tr>`;
  document.getElementById('txMeta').textContent=`${{data.length}} records · limit: ${{lim}}`;
}}

function clearTxF() {{
  document.getElementById('txType').value='';
  document.getElementById('txCat').value='';
  document.getElementById('txLim').value=100;
  loadTx();
}}

// ━━━ ANALYTICS ━━━
async function loadAnalytics() {{ await Promise.all([loadInsights(),loadAnomalies(),loadBarCharts()]); }}

async function loadInsights() {{
  const days = document.getElementById('insDays').value;
  const d = await api(`/analytics/insights?days=${{days}}`);
  const b = document.getElementById('insBody');
  if (!d||!d.insights) {{ b.innerHTML='<div class="empty"><span class="ei">💡</span>No insights yet</div>'; return; }}
  const items = Array.isArray(d.insights)?d.insights:[d.insights];
  b.innerHTML = items.map(i=>`<div class="ins"><div class="ins-dot"></div><div class="ins-txt">${{esc(i)}}</div></div>`).join('');
}}

async function loadAnomalies() {{
  const d = await api('/analytics/anomalies?days=90');
  document.getElementById('anomCount').textContent = d?`${{d.length}} found`:'';
  const b = document.getElementById('anomBody');
  if (!d||!d.length) {{ b.innerHTML='<div class="empty"><span class="ei">✅</span>No anomalies detected</div>'; return; }}
  b.innerHTML = d.map(a=>`<div class="anom">
    <div class="anom-type">${{esc(a.anomaly_type||a.type||'anomaly')}}</div>
    <div class="anom-desc">${{esc(a.description||a.reason||JSON.stringify(a))}}</div>
    <div class="anom-meta">${{shortText(a.event_time_utc||a.timestamp||'',19)}}</div>
  </div>`).join('');
}}

async function loadBarCharts() {{
  const [mo,wk] = await Promise.all([api('/analytics/summary/monthly?months=6'),api('/analytics/summary/weekly?weeks=8')]);
  const barOpts = {{ scales:{{ x:{{ticks:{{color:'#4a6b5a',font:{{size:9}}}},grid:{{color:'rgba(255,255,255,.025)'}}}}, y:{{ticks:{{color:'#4a6b5a',font:{{size:9}}}},grid:{{color:'rgba(255,255,255,.025)'}}}} }} }};
  if (mo&&Array.isArray(mo)) {{
    mkChart('monthChart','bar',mo.map(d=>d.month||d.period||''),[
      {{label:'Received',data:mo.map(d=>parseFloat(d.total_received||d.income||0)),backgroundColor:'rgba(0,255,157,.5)',borderColor:'var(--green)',borderWidth:1}},
      {{label:'Spent',   data:mo.map(d=>parseFloat(d.total_spent||d.expenses||0)),backgroundColor:'rgba(255,77,109,.5)',borderColor:'var(--red)',   borderWidth:1}},
    ],barOpts);
  }}
  if (wk&&Array.isArray(wk)) {{
    mkChart('weekChart','bar',wk.map(d=>d.week||d.period||''),[
      {{label:'Received',data:wk.map(d=>parseFloat(d.total_received||d.income||0)),backgroundColor:'rgba(0,255,157,.5)',borderColor:'var(--green)',borderWidth:1}},
      {{label:'Spent',   data:wk.map(d=>parseFloat(d.total_spent||d.expenses||0)),backgroundColor:'rgba(255,77,109,.5)',borderColor:'var(--red)',   borderWidth:1}},
    ],barOpts);
  }}
}}

// ━━━ HEALTH ━━━
async function loadHealth() {{
  const [hb,hi] = await Promise.all([api('/monitor/heartbeat?record=0'),api('/health/details')]);
  if (hb) {{
    const ok=hb.status==='ok';
    document.getElementById('hStatus').innerHTML=`
      <div class="hstat">
        <span class="hico">${{ok?'✅':'⚠️'}}</span>
        <div>
          <div class="hlbl" style="color:${{ok?'var(--green)':'var(--red)'}}">${{ok?'SYSTEM HEALTHY':'SYSTEM ALERT'}}</div>
          <div class="hsub">Heartbeat: ${{esc(hb.status)}} · Last SMS: ${{esc(hb.last_sms_utc||'No data')}} · Alert: ${{hb.alert?'Yes':'No'}}</div>
        </div>
      </div>
      ${{hi?`<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px">
        <div class="sc"><div class="lbl">Database</div><div class="val white" style="font-size:12px;margin-top:7px">${{esc(hi.db||'—')}}</div></div>
        <div class="sc"><div class="lbl">API Auth</div><div class="val ${{hi.api_key_required?'':'blue'}}" style="font-size:16px;margin-top:7px">${{hi.api_key_required?'🔐 On':'🔓 Open'}}</div></div>
        <div class="sc"><div class="lbl">Status</div><div class="val" style="font-size:16px;margin-top:7px">${{esc(hi.status||'—')}}</div></div>
      </div>`:''}}`;
  }}
  await loadHbHistory();
  await loadRoutesInventory();
}}

async function loadRoutesInventory() {{
  const routes = await api('/routes');
  const panel = document.getElementById('epList');
  if (!routes || !routes.length) {{
    panel.innerHTML = '<div class="empty"><span class="ei">🧭</span>No route data</div>';
    return;
  }}
  const ordered = routes
    .slice()
    .sort((a, b) => String(a.path || '').localeCompare(String(b.path || '')));
  panel.innerHTML = ordered.map(r => {{
    const methods = Array.isArray(r.methods) ? r.methods : ['GET'];
    const methodBadges = methods.map(m =>
      `<span class="chip ${{m==='POST'?'cg':'cb'}}" style="min-width:32px;text-align:center">${{esc(m)}}</span>`
    ).join('');
    const authBadge = r.requires_auth
      ? '<span class="chip cr" style="min-width:56px;text-align:center">AUTH</span>'
      : '<span class="chip cg" style="min-width:56px;text-align:center">OPEN</span>';
    return `
      <div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border2);font-size:11px">
        <span style="display:flex;gap:4px">${{methodBadges}}</span>
        <span class="mn" style="color:var(--text);flex:1">${{esc(r.path||'')}}</span>
        ${{authBadge}}
        <span class="mu" style="font-size:9px">${{esc(r.description||'')}}</span>
      </div>`;
  }}).join('');
}}

async function loadHbHistory() {{
  const d=await api('/monitor/heartbeat/history?limit=20');
  const b=document.getElementById('hbHist');
  if(!d||!d.length){{b.innerHTML=`<tr><td colspan="4" class="empty">No history yet</td></tr>`;return;}}
  b.innerHTML=d.map(h=>`<tr>
    <td><span class="chip ${{h.status==='ok'?'cg':'cr'}}">${{esc(h.status||'—')}}</span></td>
    <td class="mn mu">${{shortText(h.last_sms_utc,19)}}</td>
    <td class="mn" style="color:${{h.alert?'var(--red)':'var(--muted)'}}">${{h.alert?'YES':'—'}}</td>
    <td class="mn mu">${{shortText(h.checked_at||h.created_at,19)}}</td>
  </tr>`).join('');
}}

// ━━━ LEDGER ━━━
async function loadLedger() {{
  const [v,e]=await Promise.all([api('/ledger/verify'),api('/ledger/events?limit=50')]);
  if(v){{
    const ok=v.valid;
    document.getElementById('ledgerV').innerHTML=`
      <div class="lv ${{ok?'ok':'err'}}">
        <span style="font-size:18px">${{ok?'🔐':'⚠️'}}</span>
        <div><div style="font-weight:700">${{ok?'CHAIN INTACT':'CHAIN ISSUE'}}</div>
        <div style="font-size:10px;margin-top:2px;opacity:.8">Events: ${{v.event_count||0}} · Valid: ${{v.valid?'Yes':'No'}} · ${{esc(v.message||'')}}</div></div>
      </div>`;
  }}
  const b=document.getElementById('ledgerBody');
  if(!e||!e.length){{b.innerHTML=`<tr><td colspan="6" class="empty"><span class="ei">🔐</span>No ledger events yet</td></tr>`;return;}}
  b.innerHTML=e.map(ev=>`<tr>
    <td class="mn mu">${{esc(ev.seq||ev.id||'—')}}</td>
    <td><span class="chip cb">${{esc(ev.entity_table||'—')}}</span></td>
    <td class="mn mu">${{shortText(ev.entity_id,12)}}…</td>
    <td class="mn mu" style="font-size:9px">${{shortText(ev.event_hash,16)}}…</td>
    <td class="mn mu" style="font-size:9px">${{shortText(ev.prev_hash,16)}}…</td>
    <td class="mn mu">${{shortText(ev.created_at,19)}}</td>
  </tr>`).join('');
}}

// ━━━ SMS TESTER ━━━
function buildSamples() {{
  document.getElementById('sampleList').innerHTML=SAMPLES.map((s,i)=>
    `<button class="btn-s bg" style="text-align:left;width:100%" onclick="loadSample(${{i}})">${{esc(s.label)}}</button>`
  ).join('');
}}

function loadSample(i){{ document.getElementById('smsIn').value=SAMPLES[i].sms; }}

function clearSMS() {{
  document.getElementById('smsIn').value='';
  document.getElementById('smsRes').textContent='// Result will appear here…';
  document.getElementById('smsRes').className='res idle';
  document.getElementById('smsStatus').textContent='IDLE';
}}

async function testSMS() {{
  const sms=document.getElementById('smsIn').value.trim();
  if(!sms){{ toast('Paste an SMS first','var(--yellow)'); return; }}
  const se=document.getElementById('smsStatus');
  const re=document.getElementById('smsRes');
  se.textContent='PARSING…'; se.style.color='var(--yellow)';
  re.className='res idle'; re.textContent='// Submitting to /sms…';
  try {{
    const r=await fetch('/sms',{{
      method:'POST',
      headers:{{'Content-Type':'application/json',...HEADERS}},
      body:JSON.stringify({{sms}})
    }});
    const d=await r.json();
    re.textContent=JSON.stringify(d,null,2);
    if(r.status===201){{ re.className='res ok'; se.textContent='✅ SAVED'; se.style.color='var(--green)'; toast('✅ Transaction saved!'); }}
    else if(r.status===200){{ re.className='res ok'; se.textContent='⚠️ DUPLICATE'; se.style.color='var(--yellow)'; toast('Already in ledger','var(--yellow)'); }}
    else{{ re.className='res err'; se.textContent='❌ FAILED'; se.style.color='var(--red)'; }}
  }} catch(e) {{
    re.textContent=`// Error: ${{e.message}}`; re.className='res err';
    se.textContent='❌ ERROR'; se.style.color='var(--red)';
  }}
}}

// ── Logout ──
async function doLogout() {{
  await fetch('/logout');
  window.location.href='/dashboard';
}}

// ── Auto-refresh overview every 60s ──
setInterval(()=>{{ if(curTab==='overview') loadOverview(); }}, 60000);

// ── Init ──
loadOverview();
buildSamples();
</script>
</body>
</html>"""
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_dashboard_response(api_key: str, session: dict, error: bool = False) -> tuple:
    """Gate check — return login page or main dashboard based on session."""
    if not is_authenticated(api_key, session):
        return build_login_page(error=error)
    return build_dashboard_page(api_key_configured=bool(api_key))
