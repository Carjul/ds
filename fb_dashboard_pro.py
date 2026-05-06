"""
FB Dashboard Pro - Meta Ads Performance + Campaign Drill-Down
Extended metrics: CPM, CPC, CTR, Checkouts, Cost/Checkout
Auto-report at 7:55 AM EST. Click account name to see campaign breakdown.

Usage:
  pip install flask requests
  python fb_dashboard_pro.py
"""

import json, os, requests, concurrent.futures, threading, time as _time
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from flask import Flask, render_template_string, jsonify, request as flask_request

# ============================================================
# CONFIG
# ============================================================
BM1_TOKEN = os.environ.get("BM1_TOKEN", "YOUR_BM1_TOKEN_HERE")
BM2_TOKEN = os.environ.get("BM2_TOKEN", "YOUR_BM2_TOKEN_HERE")
PORT = int(os.environ.get("PORT", 5001))

API_VERSION = "v21.0"
BASE = f"https://graph.facebook.com/{API_VERSION}/"

ACCOUNTS = [
    {"name":"MARTHA 2","id":"act_528756616577904","bm":"BM1"},
    {"name":"MARTHA 4","id":"act_708152401990591","bm":"BM1"},
    {"name":"GM-177","id":"act_1027335185283047","bm":"BM1"},
    {"name":"RPG 15","id":"act_2121935234933980","bm":"BM1"},
    {"name":"THM-60","id":"act_1247132143392586","bm":"BM1"},
    {"name":"THM-32","id":"act_1985532452249785","bm":"BM1"},
    {"name":"THM-54","id":"act_1594785768155717","bm":"BM1"},
    {"name":"THM-72","id":"act_1540233950717702","bm":"BM1"},
    {"name":"THM-113","id":"act_1074066461137769","bm":"BM1"},
    {"name":"THM-200","id":"act_1059904599553927","bm":"BM1"},
    {"name":"DG-03","id":"act_1306256300004871","bm":"BM2"},
    {"name":"DG-51","id":"act_900364275348331","bm":"BM2"},
    {"name":"MSTC-20","id":"act_1239484177480232","bm":"BM2"},
    {"name":"THM-119","id":"act_1650693448960867","bm":"BM2"},
    {"name":"KM-19","id":"act_2049541032515377","bm":"BM2"},
    {"name":"THM-55","id":"act_1654285161902955","bm":"BM2"},
]

LIVE_MODE = BM1_TOKEN != "YOUR_BM1_TOKEN_HERE"
INSIGHTS_FIELDS = "spend,impressions,cpm,cpc,ctr,unique_link_clicks_ctr,actions,cost_per_action_type,purchase_roas"

def get_token(bm):
    return BM1_TOKEN if bm == "BM1" else BM2_TOKEN

# ============================================================
# CACHED DATA
# ============================================================
CACHED = {
    "today": [
        {"name":"THM-200","bm":"BM1","id":"act_1059904599553927","spend":337.94,"purchases":3,"revenue":253.46,"impressions":3760,"cpm":89.88,"cpc":1.10,"ctr":8.19,"unique_link_ctr":5.42,"checkouts":32,"cost_checkout":10.56},
        {"name":"THM-32","bm":"BM1","id":"act_1985532452249785","spend":1.56,"purchases":0,"revenue":0,"impressions":21,"cpm":74.29,"cpc":0.52,"ctr":14.29,"unique_link_ctr":14.29,"checkouts":0,"cost_checkout":0},
    ],
    "yesterday": [
        {"name":"THM-200","bm":"BM1","id":"act_1059904599553927","spend":402.24,"purchases":2,"revenue":169.94,"impressions":4885,"cpm":82.34,"cpc":1.03,"ctr":8.02,"unique_link_ctr":5.18,"checkouts":16,"cost_checkout":25.14},
        {"name":"THM-32","bm":"BM1","id":"act_1985532452249785","spend":1.71,"purchases":0,"revenue":0,"impressions":24,"cpm":71.25,"cpc":0.57,"ctr":12.50,"unique_link_ctr":12.50,"checkouts":0,"cost_checkout":0},
    ],
    "month": [
        {"name":"THM-200","bm":"BM1","id":"act_1059904599553927","spend":747.30,"purchases":5,"revenue":425.96,"impressions":8760,"cpm":85.31,"cpc":1.06,"ctr":8.08,"unique_link_ctr":5.28,"checkouts":48,"cost_checkout":15.57},
        {"name":"THM-32","bm":"BM1","id":"act_1985532452249785","spend":4.73,"purchases":0,"revenue":0,"impressions":71,"cpm":66.62,"cpc":0.59,"ctr":11.27,"unique_link_ctr":11.27,"checkouts":0,"cost_checkout":0},
    ],
}

CACHED_CAMPAIGNS = {
    "act_1059904599553927": {
        "today": [
            {"id":"120248362905750699","name":"[Zoey Dalton]-[SCRIPT 23 - V1]-#1","spend":80.53,"purchases":1,"revenue":85.36,"impressions":1026,"cpm":78.49,"cpc":1.09,"ctr":7.21,"unique_link_ctr":4.87,"checkouts":8,"cost_checkout":10.07},
            {"id":"120248367316380699","name":"[Zoey Dalton]-[SCRIPT 23 - V4]-#1","spend":74.29,"purchases":1,"revenue":84.69,"impressions":725,"cpm":102.47,"cpc":1.20,"ctr":8.55,"unique_link_ctr":5.66,"checkouts":5,"cost_checkout":14.86},
            {"id":"120248367336190699","name":"[Zoey Dalton]-[SCRIPT 23 - V5]-#1","spend":79.52,"purchases":0,"revenue":0,"impressions":907,"cpm":87.67,"cpc":1.12,"ctr":7.83,"unique_link_ctr":5.18,"checkouts":7,"cost_checkout":11.36},
        ],
    },
    "act_1985532452249785": {
        "today": [
            {"id":"120249848881790273","name":"TEST 1$","spend":1.56,"purchases":0,"revenue":0,"impressions":21,"cpm":74.29,"cpc":0.52,"ctr":14.29,"unique_link_ctr":14.29,"checkouts":0,"cost_checkout":0},
        ],
    },
}

# ============================================================
# META API
# ============================================================
def parse_insights(row, account):
    spend = float(row.get("spend", 0))
    impressions = int(row.get("impressions", 0))
    cpm = float(row.get("cpm", 0))
    cpc = float(row.get("cpc", 0)) if row.get("cpc") else 0
    ctr = float(row.get("ctr", 0))
    unique_link_ctr = float(row.get("unique_link_clicks_ctr", 0)) if row.get("unique_link_clicks_ctr") else 0

    purchases = 0
    checkouts = 0
    for a in row.get("actions", []):
        if a["action_type"] == "offsite_conversion.fb_pixel_purchase":
            purchases = int(a["value"])
        elif a["action_type"] == "offsite_conversion.fb_pixel_initiate_checkout":
            checkouts = int(a["value"])

    cost_checkout = 0
    for c in row.get("cost_per_action_type", []):
        if c["action_type"] in ("initiate_checkout", "omni_initiated_checkout"):
            cost_checkout = float(c["value"]); break

    roas = 0
    for ri in row.get("purchase_roas", []):
        if ri["action_type"] == "omni_purchase":
            roas = float(ri["value"]); break

    return {
        "name": account["name"], "bm": account["bm"], "id": account["id"],
        "spend": spend, "purchases": purchases, "revenue": round(spend * roas, 2),
        "impressions": impressions, "cpm": round(cpm, 2), "cpc": round(cpc, 2),
        "ctr": round(ctr, 2), "unique_link_ctr": round(unique_link_ctr, 2),
        "checkouts": checkouts, "cost_checkout": round(cost_checkout, 2),
    }

def fetch_account(account, date_preset):
    token = get_token(account["bm"])
    url = f"{BASE}{account['id']}/insights"
    params = {"fields": INSIGHTS_FIELDS, "date_preset": date_preset, "access_token": token}
    try:
        r = requests.get(url, params=params, timeout=30)
        data = r.json().get("data", [])
        if not data:
            return {"name":account["name"],"bm":account["bm"],"id":account["id"],"spend":0,"purchases":0,"revenue":0,"impressions":0,"cpm":0,"cpc":0,"ctr":0,"unique_link_ctr":0,"checkouts":0,"cost_checkout":0}
        return parse_insights(data[0], account)
    except Exception:
        return {"name":account["name"],"bm":account["bm"],"id":account["id"],"spend":0,"purchases":0,"revenue":0,"impressions":0,"cpm":0,"cpc":0,"ctr":0,"checkouts":0,"cost_checkout":0}

def has_active_campaigns(account):
    token = get_token(account["bm"])
    url = f"{BASE}{account['id']}/campaigns"
    params = {
        "fields": "id",
        "filtering": json.dumps([{"field":"effective_status","operator":"IN","value":["ACTIVE"]}]),
        "limit": 1,
        "access_token": token,
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        return len(r.json().get("data", [])) > 0
    except Exception:
        return False

def fetch_all_live(date_preset):
    active_accounts = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(has_active_campaigns, a): a for a in ACCOUNTS}
        for f in concurrent.futures.as_completed(futures):
            acct = futures[f]
            if f.result():
                active_accounts.append(acct)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_account, a, date_preset): a for a in active_accounts}
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())
    results.sort(key=lambda x: x["spend"], reverse=True)
    return results

def fetch_campaigns(account_id, bm, date_preset):
    token = get_token(bm)
    url = f"{BASE}{account_id}/campaigns"
    params = {
        "fields": "id,name,status,effective_status",
        "filtering": json.dumps([{"field":"effective_status","operator":"IN","value":["ACTIVE"]}]),
        "limit": 200,
        "access_token": token,
    }
    try:
        r = requests.get(url, params=params, timeout=30)
        campaigns = r.json().get("data", [])
    except Exception:
        return []

    def get_camp_insights(camp):
        url2 = f"{BASE}{camp['id']}/insights"
        p2 = {"fields": INSIGHTS_FIELDS, "date_preset": date_preset, "access_token": token}
        try:
            r2 = requests.get(url2, params=p2, timeout=30)
            data = r2.json().get("data", [])
            if not data:
                return {"id":camp["id"],"name":camp["name"],"spend":0,"purchases":0,"revenue":0,"impressions":0,"cpm":0,"cpc":0,"ctr":0,"unique_link_ctr":0,"checkouts":0,"cost_checkout":0}
            row = data[0]
            acct = {"name":camp["name"],"bm":bm,"id":camp["id"]}
            result = parse_insights(row, acct)
            result["id"] = camp["id"]
            return result
        except Exception:
            return {"id":camp["id"],"name":camp["name"],"spend":0,"purchases":0,"revenue":0,"impressions":0,"cpm":0,"cpc":0,"ctr":0,"checkouts":0,"cost_checkout":0}

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(get_camp_insights, c): c for c in campaigns}
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())
    results.sort(key=lambda x: x["spend"], reverse=True)
    return results

# ============================================================
# AUTO REPORT (7:55 AM EST)
# ============================================================
report_cache: dict[str, Any] = {"data": None, "generated_at": None}

def generate_report():
    if LIVE_MODE:
        data = fetch_all_live("today")
    else:
        data = CACHED.get("today", [])
    report_cache["data"] = data
    report_cache["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"  [AUTO-REPORT] Generated at {report_cache['generated_at']}")

def report_scheduler():
    while True:
        now = datetime.now()
        if now.hour == 7 and now.minute == 55:
            generate_report()
            _time.sleep(61)
        _time.sleep(30)

# ============================================================
# FEEDBACK MANAGEMENT
# ============================================================
FEEDBACK_FILE = "feedback.json"
CREATIVE_LINKS: dict[str, str] = {}

def is_valid_http_url(url):
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False

def load_feedbacks():
    try:
        if os.path.exists(FEEDBACK_FILE):
            with open(FEEDBACK_FILE, "r") as f:
                return json.load(f)
    except:
        pass
    return {"feedbacks": []}

def save_feedbacks(data):
    try:
        with open(FEEDBACK_FILE, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except:
        return False

def get_feedback_id():
    import time as t
    return f"fb_{int(t.time())}_{len(load_feedbacks()['feedbacks'])}"

def get_response_id():
    import time as t
    return f"resp_{int(t.time())}_{len([r for fb in load_feedbacks()['feedbacks'] for r in fb.get('responses', [])])}"

# ============================================================
# FLASK
# ============================================================
app = Flask(__name__)
DATE_MAP = {"today":"today","yesterday":"yesterday","month":"this_month"}

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/data/<period>")
def api_data(period):
    if LIVE_MODE:
        preset = DATE_MAP.get(period, "today")
        rows = fetch_all_live(preset)
    else:
        rows = CACHED.get(period, CACHED["today"])
    rows = [r for r in rows if r.get("spend", 0) > 0]
    return jsonify(rows)

@app.route("/api/campaigns")
def api_campaigns():
    account_id = flask_request.args.get("account_id") or ""
    bm = flask_request.args.get("bm")
    period = flask_request.args.get("period", "today")
    preset = DATE_MAP.get(period, "today")
    if LIVE_MODE:
        camps = fetch_campaigns(account_id, bm, preset)
    else:
        acct_camps = CACHED_CAMPAIGNS.get(account_id, {})
        camps = acct_camps.get(period, acct_camps.get("today", []))
    return jsonify(camps)

@app.route("/api/report")
def api_report():
    if report_cache["data"]:
        return jsonify({"data": report_cache["data"], "generated_at": report_cache["generated_at"]})
    return jsonify({"data": None, "generated_at": None})

@app.route("/api/creative-links", methods=["GET"])
def get_creative_links():
    return jsonify(CREATIVE_LINKS)

@app.route("/api/creative-links", methods=["POST"])
def upsert_creative_link():
    payload = flask_request.json or {}
    name = (payload.get("name") or "").strip()
    url = (payload.get("url") or "").strip()

    if not name:
        return jsonify({"error": "Campaign name is required"}), 400

    if not url:
        if name in CREATIVE_LINKS:
            del CREATIVE_LINKS[name]
        return jsonify({"name": name, "deleted": True}), 200

    if not is_valid_http_url(url):
        return jsonify({"error": "Invalid URL. Use http:// or https://"}), 400

    CREATIVE_LINKS[name] = url
    return jsonify({"name": name, "url": url}), 200

# ============================================================
# FEEDBACK API
# ============================================================
@app.route("/api/feedback", methods=["GET"])
def get_feedbacks():
    data = load_feedbacks()
    return jsonify(data["feedbacks"])

@app.route("/api/feedback", methods=["POST"])
def create_feedback():
    content = flask_request.json.get("content", "").strip()
    if not content:
        return jsonify({"error": "Empty feedback"}), 400
    
    data = load_feedbacks()
    new_fb = {
        "id": get_feedback_id(),
        "content": content,
        "created_at": datetime.now().isoformat(),
        "status": "open",
        "responses": []
    }
    data["feedbacks"].insert(0, new_fb)
    save_feedbacks(data)
    return jsonify(new_fb), 201

@app.route("/api/feedback/<fb_id>", methods=["PATCH"])
def edit_feedback(fb_id):
    content = flask_request.json.get("content", "").strip()
    if not content:
        return jsonify({"error": "Empty feedback"}), 400

    data = load_feedbacks()
    for fb in data["feedbacks"]:
        if fb["id"] == fb_id:
            fb["content"] = content
            fb["updated_at"] = datetime.now().isoformat()
            save_feedbacks(data)
            return jsonify(fb), 200

    return jsonify({"error": "Feedback not found"}), 404

@app.route("/api/feedback/<fb_id>/response", methods=["POST"])
def add_response(fb_id):
    content = flask_request.json.get("content", "").strip()
    if not content:
        return jsonify({"error": "Empty response"}), 400
    
    data = load_feedbacks()
    for fb in data["feedbacks"]:
        if fb["id"] == fb_id:
            new_resp = {
                "id": get_response_id(),
                "content": content,
                "created_at": datetime.now().isoformat()
            }
            fb["responses"].append(new_resp)
            save_feedbacks(data)
            return jsonify(new_resp), 201
    
    return jsonify({"error": "Feedback not found"}), 404

@app.route("/api/feedback/<fb_id>/status", methods=["PATCH"])
def update_status(fb_id):
    status = flask_request.json.get("status", "open")
    data = load_feedbacks()
    for fb in data["feedbacks"]:
        if fb["id"] == fb_id:
            fb["status"] = status
            save_feedbacks(data)
            return jsonify({"status": status}), 200
    
    return jsonify({"error": "Feedback not found"}), 404

@app.route("/api/feedback/<fb_id>/delete", methods=["DELETE"])
def delete_feedback(fb_id):
    data = load_feedbacks()
    data["feedbacks"] = [fb for fb in data["feedbacks"] if fb["id"] != fb_id]
    save_feedbacks(data)
    return jsonify({"deleted": True}), 200


HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Meta Ads Report</title>
<style>
:root{
  --bg:#0b0d11;--bg2:#12151c;--border:#1e2230;--text:#e5e7eb;--text2:#9ca3af;--text3:#6b7280;
  --accent:#3b82f6;--green:#22c55e;--red:#ef4444;--yellow:#f59e0b;
  --card-shadow:0 1px 3px rgba(0,0,0,.3);--row-expand:#0f1117;
}
.light{
  --bg:#f3f4f6;--bg2:#fff;--border:#e5e7eb;--text:#111827;--text2:#4b5563;--text3:#6b7280;
  --card-shadow:0 1px 3px rgba(0,0,0,.08);--row-expand:#f9fafb;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,sans-serif;background:var(--bg);color:var(--text);line-height:1.5;transition:background .3s,color .3s}

.header{background:var(--bg2);border-bottom:1px solid var(--border);padding:16px 32px;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:18px;font-weight:700;display:flex;align-items:center;gap:10px}
.header h1 svg{width:22px;height:22px}
.hdr-r{display:flex;align-items:center;gap:14px}
.status{font-size:12px;color:var(--text3);display:flex;align-items:center;gap:6px}
.status .dot{width:7px;height:7px;border-radius:50%;background:var(--green);display:inline-block}
.status.loading .dot{background:var(--yellow);animation:pulse 1s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

.icon-btn{width:32px;height:32px;border-radius:8px;border:1px solid var(--border);background:var(--bg2);color:var(--text3);cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s}
.icon-btn:hover{border-color:var(--accent);color:var(--accent)}
.icon-btn svg{width:16px;height:16px}
.icon-btn.spinning svg{animation:sp .7s linear infinite}

.theme-t{width:44px;height:24px;background:var(--border);border-radius:12px;cursor:pointer;position:relative;border:none;transition:background .3s}
.theme-t::after{content:'';position:absolute;top:3px;left:3px;width:18px;height:18px;background:var(--accent);border-radius:50%;transition:transform .3s}
.light .theme-t::after{transform:translateX(20px);background:var(--yellow)}

.date-f{display:flex;background:var(--bg2);border:1px solid var(--border);border-radius:8px;overflow:hidden}
.date-b{padding:6px 16px;font-size:13px;font-weight:500;color:var(--text3);background:transparent;border:none;cursor:pointer;transition:all .2s}
.date-b:hover{color:var(--text)}.date-b.active{background:var(--accent);color:#fff}
.date-b:disabled{opacity:.5;cursor:not-allowed}

.ctn{max-width:1400px;margin:0 auto;padding:24px 32px}

.sgrid{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:28px}
.scard{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:18px 20px;box-shadow:var(--card-shadow);transition:border-color .2s}
.scard:hover{border-color:var(--accent)}
.scard .lbl{font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;display:flex;align-items:center;gap:6px}
.scard .lbl svg{width:13px;height:13px;opacity:.7}
.scard .val{font-size:24px;font-weight:700;letter-spacing:-.5px}
.scard .sub{font-size:11px;color:var(--text3);margin-top:2px}
.vg{color:var(--green)}.vr{color:var(--red)}.vy{color:var(--yellow)}

.tw{background:var(--bg2);border:1px solid var(--border);border-radius:12px;overflow:hidden;box-shadow:var(--card-shadow)}
.th-bar{padding:14px 24px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.th-bar h2{font-size:14px;font-weight:600}
.th-bar .cnt{font-size:12px;color:var(--text3);background:var(--bg);padding:2px 10px;border-radius:10px}

.tbl-scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;min-width:1200px}
thead th{text-align:left;padding:10px 12px;font-size:10px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--border);cursor:pointer;user-select:none;white-space:nowrap}
thead th.num{text-align:right}
thead th:hover{color:var(--text)}
thead th .arrow{font-size:9px;margin-left:3px;opacity:.7;color:var(--accent)}
thead th.sorted{color:var(--accent)}
tbody tr{border-bottom:1px solid var(--border);transition:background .15s}
tbody tr:last-child{border-bottom:none}
tbody tr:hover{background:rgba(59,130,246,.04)}
tbody td{padding:10px 12px;font-size:13px;white-space:nowrap}
tbody td.num{text-align:right;font-variant-numeric:tabular-nums}
.an{font-weight:600;display:flex;align-items:center;gap:8px;cursor:pointer}
.an:hover{color:var(--accent)}
.an .chevron{font-size:10px;transition:transform .2s;color:var(--text3)}
.an .chevron.open{transform:rotate(90deg);color:var(--accent)}
.bm{font-size:10px;font-weight:600;padding:2px 6px;border-radius:4px;background:rgba(59,130,246,.15);color:var(--accent)}
.bm.b2{background:rgba(168,139,250,.15);color:#a78bfa}
.zero{color:var(--text3)}

tr.camp-row{background:var(--row-expand);border-left:3px solid var(--accent)}
tr.camp-row td{padding:10px 14px;font-size:12px;color:var(--text);letter-spacing:0.2px}
tr.camp-row td.num{font-size:12px;font-variant-numeric:tabular-nums}
tr.camp-row td:first-child{padding-left:44px}
.camp-name{font-weight:600;max-width:320px;overflow:hidden;text-overflow:ellipsis;font-size:12px;color:var(--accent)}
.camp-name.clickable{cursor:pointer}
.camp-name.clickable:hover{text-decoration:underline}
.camp-loader{text-align:center;padding:12px;color:var(--text3);font-size:12px}

.creative-link{display:inline-block;max-width:240px;overflow:hidden;text-overflow:ellipsis;vertical-align:middle;color:var(--accent);text-decoration:none}
.creative-link:hover{text-decoration:underline}
.creative-action{font-size:11px;padding:3px 8px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text2);cursor:pointer;margin-left:8px}
.creative-action:hover{border-color:var(--accent);color:var(--accent)}

tfoot tr{border-top:2px solid var(--border);font-weight:700;font-size:13px;background:var(--bg)}
tfoot td{padding:12px 12px}
tfoot td.num{text-align:right;font-variant-numeric:tabular-nums}

.footer{text-align:center;padding:20px;font-size:11px;color:var(--text3)}

.loader{display:none;text-align:center;padding:60px;color:var(--text3);font-size:14px}
.loader.show{display:block}
.loader .spin{display:inline-block;width:24px;height:24px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:sp .7s linear infinite;margin-bottom:12px}
@keyframes sp{to{transform:rotate(360deg)}}

.report-badge{display:none;font-size:10px;padding:2px 8px;border-radius:4px;font-weight:600;background:rgba(34,197,94,.15);color:var(--green);cursor:pointer}
.report-badge.show{display:inline-flex;align-items:center;gap:4px}

.feedback-btn{background:var(--accent);color:#fff;border:none;padding:10px 18px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;transition:all .2s;margin:16px 0 16px auto;display:block}
.feedback-btn:hover{opacity:.9;transform:translateY(-2px)}

.modal-backdrop{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.7);z-index:1000;animation:fadeIn .2s}
.modal-backdrop.show{display:flex;align-items:center;justify-content:center}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}

.modal-content{background:var(--bg2);border:1px solid var(--border);border-radius:12px;width:90%;max-width:500px;padding:24px;box-shadow:0 20px 60px rgba(0,0,0,.3);animation:slideUp .3s}
@keyframes slideUp{from{transform:translateY(20px);opacity:0}to{transform:translateY(0);opacity:1}}
.modal-content h3{margin-bottom:16px;font-size:16px;color:var(--text)}
.modal-content textarea{width:100%;min-height:100px;padding:10px;border:1px solid var(--border);border-radius:8px;background:var(--bg);color:var(--text);font-family:inherit;resize:vertical}
.modal-content textarea:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 2px rgba(59,130,246,.1)}
.modal-buttons{display:flex;gap:10px;margin-top:16px;justify-content:flex-end}
.modal-btn{padding:8px 16px;border-radius:8px;border:none;font-weight:600;cursor:pointer;transition:all .2s;font-size:13px}
.modal-btn.submit{background:var(--accent);color:#fff}
.modal-btn.submit:hover{opacity:.9}
.modal-btn.cancel{background:var(--border);color:var(--text3)}
.modal-btn.cancel:hover{color:var(--text);border-color:var(--accent)}

.feedback-canvas{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px;margin:20px auto;box-shadow:var(--card-shadow);max-width:1400px}
.feedback-canvas h3{margin-bottom:16px;font-size:14px;font-weight:600}
.feedback-list{display:flex;flex-direction:column;gap:12px;max-height:400px;overflow-y:auto}
.feedback-item{background:var(--bg);border-left:3px solid var(--accent);border-radius:6px;padding:12px 14px;transition:all .2s}
.feedback-item.resolved{border-left-color:var(--green);opacity:.7}
.feedback-item:hover{border-left-color:var(--yellow)}
.feedback-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;font-size:12px;color:var(--text3)}
.feedback-time{font-size:10px}
.fb-status{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600}
.fb-status.open{background:rgba(59,130,246,.15);color:var(--accent)}
.fb-status.resolved{background:rgba(34,197,94,.15);color:var(--green)}
.feedback-text{font-size:13px;color:var(--text);line-height:1.4;margin-bottom:8px}
.feedback-actions{display:flex;gap:6px;flex-wrap:wrap}
.fb-action{font-size:11px;padding:4px 10px;background:var(--border);border:none;border-radius:4px;color:var(--text3);cursor:pointer;transition:all .2s;display:flex;align-items:center;gap:4px}
.fb-action svg{width:14px;height:14px}
.fb-action:hover{filter:brightness(1.06)}
.reply-btn{background:rgba(59,130,246,.16);color:#93c5fd}
.resolve-btn{background:rgba(34,197,94,.16);color:#86efac}
.delete-btn{background:rgba(239,68,68,.16);color:#fca5a5;display:none}
.edit-btn{background:rgba(245,158,11,.16);color:#fcd34d}
body.show-delete .delete-btn{display:flex}
.feedback-actions .edit-btn{margin-left:auto}
.response-section{margin-top:10px;padding-top:10px;border-top:1px solid var(--border)}
.response-item{background:var(--bg2);padding:10px 12px;border-left:2px solid var(--yellow);border-radius:4px;margin-bottom:6px;font-size:12px}
.response-meta{font-size:10px;color:var(--text3);margin-bottom:4px}
.response-text{color:var(--text2);font-style:italic}
.feedback-text,.response-text,.response-item{overflow-wrap:anywhere;word-break:break-word}
.empty-feedback{text-align:center;padding:30px 20px;color:var(--text3);font-size:13px}

@media(max-width:900px){.sgrid{grid-template-columns:repeat(2,1fr)}.header{padding:12px 16px;flex-wrap:wrap;gap:10px}.ctn{padding:16px}.feedback-item{padding:10px}.feedback-header{flex-wrap:wrap;gap:6px}.feedback-text{font-size:12px;line-height:1.45}.feedback-actions{gap:5px}.fb-action{font-size:10px;padding:4px 8px;max-width:100%}}
</style>
</head>
<body>

<div class="header">
  <h1>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
      <rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
    </svg>
    Meta Ads Report
  </h1>
  <div class="hdr-r">
    <div class="status" id="status">
      <span class="dot"></span>
      <span id="statusText">Auto-report: 7:55 AM</span>
      <span id="lastUpdate" style="margin-left:4px;font-size:11px;color:var(--text3)"></span>
    </div>
    <span class="report-badge" id="reportBadge" title="Auto-report ready">AUTO-REPORT READY</span>
    <button class="icon-btn" id="refreshBtn" onclick="refresh()" title="Refresh now">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
    </button>
    <div class="date-f">
      <button class="date-b active" data-period="today">Today</button>
      <button class="date-b" data-period="yesterday">Yesterday</button>
      <button class="date-b" data-period="month">Month</button>
    </div>
    <button class="theme-t" onclick="document.body.classList.toggle('light')" title="Toggle dark/light"></button>
  </div>
</div>

<div class="ctn">
  <div class="sgrid">
    <div class="scard"><div class="lbl"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 01-8 0"/></svg>Sales</div><div class="val" id="tSales">--</div><div class="sub">purchases (pixel)</div></div>
    <div class="scard"><div class="lbl"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>Revenue</div><div class="val" id="tRev">--</div><div class="sub">from pixel</div></div>
    <div class="scard"><div class="lbl"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>Spend</div><div class="val" id="tSpend">--</div><div class="sub" id="tSpendSub">all accounts</div></div>
    <div class="scard"><div class="lbl"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>ROI</div><div class="val" id="tROI">--</div><div class="sub">(rev - spend) / spend</div></div>
    <div class="scard"><div class="lbl"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>Checkouts</div><div class="val" id="tCO">--</div><div class="sub" id="tCOSub">initiate checkouts</div></div>
  </div>

  <div class="loader" id="loader"><div class="spin"></div><br>Loading data from Meta API...</div>

  <div class="tw" id="tableWrap">
    <div class="th-bar">
      <h2>Account Breakdown <span style="font-weight:400;font-size:12px;color:var(--text3);margin-left:8px">click account to expand campaigns</span></h2>
      <span class="cnt" id="aCnt">--</span>
    </div>
    <div class="tbl-scroll">
    <table>
      <thead>
        <tr>
          <th data-col="name">Account <span class="arrow"></span></th>
          <th class="num" data-col="purchases">Sales <span class="arrow"></span></th>
          <th class="num" data-col="spend">Spend <span class="arrow"></span></th>
          <th class="num" data-col="revenue">Revenue <span class="arrow"></span></th>
          <th class="num" data-col="profit">Profit <span class="arrow"></span></th>
          <th class="num" data-col="cpa">CPA <span class="arrow"></span></th>
          <th class="num" data-col="roi">ROI <span class="arrow"></span></th>
          <th class="num" data-col="cpm">CPM <span class="arrow"></span></th>
          <th class="num" data-col="cpc">CPC <span class="arrow"></span></th>
          <th class="num" data-col="ctr">CTR <span class="arrow"></span></th>
          <th class="num" data-col="unique_link_ctr">U-CTR <span class="arrow"></span></th>
          <th class="num" data-col="checkouts">IC <span class="arrow"></span></th>
          <th class="num" data-col="cost_checkout">$/IC <span class="arrow"></span></th>
          <th>Creative</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
      <tfoot id="tfoot"></tfoot>
    </table>
    </div>
  </div>
</div>

<div class="feedback-canvas">
  <h3>📝 Feedback & Responses</h3>
  <div class="feedback-list" id="feedbackList">
    <div class="empty-feedback">No feedback yet. Be the first to share!</div>
  </div>
  <button class="feedback-btn" onclick="openFeedbackModal()">💬 Send Feedback</button>
</div>

<div class="modal-backdrop" id="feedbackModal">
  <div class="modal-content">
    <h3 id="feedbackModalTitle">Send Feedback</h3>
    <textarea id="feedbackText" placeholder="Share your feedback..."></textarea>
    <div class="modal-buttons">
      <button class="modal-btn cancel" onclick="closeFeedbackModal()">Cancel</button>
      <button class="modal-btn submit" id="feedbackSubmitBtn" onclick="submitFeedback()">Send</button>
    </div>
  </div>
</div>

<div class="modal-backdrop" id="responseModal">
  <div class="modal-content">
    <h3>Add Response</h3>
    <textarea id="responseText" placeholder="Write your response..."></textarea>
    <div class="modal-buttons">
      <button class="modal-btn cancel" onclick="closeResponseModal()">Cancel</button>
      <button class="modal-btn submit" onclick="submitResponse()">Send</button>
    </div>
  </div>
</div>

<div class="modal-backdrop" id="creativeModal">
  <div class="modal-content">
    <h3>Creative URL</h3>
    <div style="font-size:12px;color:var(--text3);margin-bottom:10px">Campaign: <strong id="creativeCampaignName" style="color:var(--text)"></strong></div>
    <textarea id="creativeUrlInput" placeholder="https://example.com/creative" style="min-height:70px"></textarea>
    <div class="modal-buttons">
      <button class="modal-btn cancel" onclick="closeCreativeModal()">Cancel</button>
      <button class="modal-btn submit" onclick="submitCreativeLink()">Save</button>
    </div>
  </div>
</div>

<div class="footer">Data from Meta Marketing API v21.0 &middot; BM1: Martha Lucelly 1 &middot; BM2: JV Liminal</div>

<script>
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const fmt = n => "$"+n.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
const fmtK = n => n>=1000000?(n/1000000).toFixed(1)+"M":n>=1000?(n/1000).toFixed(1)+"K":n.toLocaleString();

let rows=[], sortCol="spend", sortAsc=false, currentPeriod="today", expandedAcct=null, campCache={};
let creativeLinksByName={}, currentCreativeCampaignName=null;

$$(".date-b").forEach(b=>b.addEventListener("click",()=>{
  $$(".date-b").forEach(x=>x.classList.remove("active"));
  b.classList.add("active");
  expandedAcct=null; campCache={};
  doLoad(b.dataset.period);
}));

$$('thead th[data-col]').forEach(th=>th.addEventListener("click",()=>{
  const col=th.dataset.col;
  if(sortCol===col)sortAsc=!sortAsc;else{sortCol=col;sortAsc=col==="name";}
  renderTable();
}));

function renderCards(){
  const ts=rows.reduce((s,r)=>s+r.spend,0);
  const tr=rows.reduce((s,r)=>s+r.revenue,0);
  const tp=rows.reduce((s,r)=>s+r.purchases,0);
  const tc=rows.reduce((s,r)=>s+r.checkouts,0);
  const roi=ts>0?((tr-ts)/ts)*100:0;
  const active=rows.length;

  $("#tSales").textContent=tp.toLocaleString();
  $("#tRev").textContent=fmt(tr);
  $("#tRev").className="val"+(tr>0?" vg":"");
  $("#tSpend").textContent=fmt(ts);
  $("#tSpendSub").textContent=active+" accounts";
  $("#tCO").textContent=tc.toLocaleString();
  const avgCostCO=tc>0?ts/tc:0;
  $("#tCOSub").textContent="avg "+fmt(avgCostCO)+"/checkout";

  const re=$("#tROI");
  re.textContent=(roi>=0?"+":"")+roi.toFixed(1)+"%";
  re.className="val "+(roi>=0?"vg":"vr");
}

function renderTable(){
  const sorted=[...rows].sort((a,b)=>{
    let va=a[sortCol],vb=b[sortCol];
    if(va===null)va=-Infinity;if(vb===null)vb=-Infinity;
    if(typeof va==="string")return sortAsc?va.localeCompare(vb):vb.localeCompare(va);
    return sortAsc?va-vb:vb-va;
  });

  $("#aCnt").textContent=rows.length+" active account"+(rows.length!==1?"s":"");

  $$("thead th[data-col]").forEach(th=>{
    const arrow=th.querySelector(".arrow");
    if(th.dataset.col===sortCol){arrow.textContent=sortAsc?" ▲":" ▼";th.classList.add("sorted");}
    else{arrow.textContent="";th.classList.remove("sorted");}
  });

  let html="";
  sorted.forEach(r=>{
    const isOpen=expandedAcct===r.id;
    html+=`<tr data-acct-id="${r.id}" data-bm="${r.bm}">
      <td><div class="an" onclick="toggleCamps('${r.id}','${r.bm}')"><span class="chevron ${isOpen?'open':''}">&#9654;</span><span class="bm ${r.bm==='BM2'?'b2':''}">${r.bm}</span>${r.name}</div></td>
      <td class="num ${r.purchases===0?'zero':''}">${r.purchases.toLocaleString()}</td>
      <td class="num">${fmt(r.spend)}</td>
      <td class="num ${r.revenue>0?'vg':'zero'}">${fmt(r.revenue)}</td>
      <td class="num ${r.profit>=0?'vg':'vr'}">${fmt(r.profit)}</td>
      <td class="num ${r.cpa!==null?'':'zero'}">${r.cpa!==null?fmt(r.cpa):'—'}</td>
      <td class="num ${r.roi!==null?(r.roi>=0?'vg':'vr'):'zero'}">${r.roi!==null?(r.roi>=0?'+':'')+r.roi.toFixed(1)+'%':'—'}</td>
      <td class="num">${fmt(r.cpm)}</td>
      <td class="num">${fmt(r.cpc)}</td>
      <td class="num">${r.ctr.toFixed(2)}%</td>
      <td class="num">${(r.unique_link_ctr||0).toFixed(2)}%</td>
      <td class="num ${r.checkouts===0?'zero':''}">${r.checkouts}</td>
      <td class="num ${r.cost_checkout>0?'':'zero'}">${r.cost_checkout>0?fmt(r.cost_checkout):'—'}</td>
      <td class="zero">-</td>
    </tr>`;
    if(isOpen){
      const camps=campCache[r.id];
      if(!camps){
        html+=`<tr class="camp-row"><td colspan="14" class="camp-loader"><div class="spin" style="width:16px;height:16px;border-width:2px"></div> Loading campaigns...</td></tr>`;
      } else if(camps.length===0){
        html+=`<tr class="camp-row"><td colspan="14" class="camp-loader">No active campaigns</td></tr>`;
      } else {
        camps.forEach(c=>{
          const encodedCampName=encodeURIComponent(c.name||"");
          const creativeUrl=creativeLinksByName[c.name]||"";
          const creativeCell=creativeUrl
            ? `<a class="creative-link" href="${escapeHtml(creativeUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(creativeUrl)}</a><button class="creative-action creative-edit-btn" data-camp-name="${encodedCampName}">Edit</button>`
            : `<button class="creative-action creative-add-btn" data-camp-name="${encodedCampName}">Add</button>`;
          const cp=c.purchases>0?c.spend/c.purchases:null;
          const cr=c.spend>0?((c.revenue-c.spend)/c.spend)*100:null;
          const pf=c.revenue-c.spend;
          html+=`<tr class="camp-row">
            <td><div class="camp-name clickable camp-name-clickable" data-camp-name="${encodedCampName}">${escapeHtml(c.name||"")}</div></td>
            <td class="num ${c.purchases===0?'zero':''}">${c.purchases||0}</td>
            <td class="num">${fmt(c.spend)}</td>
            <td class="num ${c.revenue>0?'vg':'zero'}">${fmt(c.revenue)}</td>
            <td class="num ${pf>=0?'vg':'vr'}">${fmt(pf)}</td>
            <td class="num ${cp!==null?'':'zero'}">${cp!==null?fmt(cp):'—'}</td>
            <td class="num ${cr!==null?(cr>=0?'vg':'vr'):'zero'}">${cr!==null?(cr>=0?'+':'')+cr.toFixed(1)+'%':'—'}</td>
            <td class="num">${fmt(c.cpm||0)}</td>
            <td class="num">${fmt(c.cpc||0)}</td>
            <td class="num">${(c.ctr||0).toFixed(2)}%</td>
            <td class="num">${(c.unique_link_ctr||0).toFixed(2)}%</td>
            <td class="num ${(c.checkouts||0)===0?'zero':''}">${c.checkouts||0}</td>
            <td class="num ${(c.cost_checkout||0)>0?'':'zero'}">${(c.cost_checkout||0)>0?fmt(c.cost_checkout):'—'}</td>
            <td>${creativeCell}</td>
          </tr>`;
        });
      }
    }
  });
  $("#tbody").innerHTML=html;
  attachCreativeListeners();

  const ts=rows.reduce((s,r)=>s+r.spend,0);
  const tr=rows.reduce((s,r)=>s+r.revenue,0);
  const tp=rows.reduce((s,r)=>s+r.purchases,0);
  const tc=rows.reduce((s,r)=>s+r.checkouts,0);
  const tP=tr-ts;
  const tC=tp>0?ts/tp:null;
  const tR=ts>0?((tr-ts)/ts)*100:0;
  const tImpr=rows.reduce((s,r)=>s+r.impressions,0);
  const tCPM=tImpr>0?(ts/tImpr)*1000:0;
  const tClicks=rows.reduce((s,r)=>s+(r.cpc>0?r.spend/r.cpc:0),0);
  const tCPC=tClicks>0?ts/tClicks:0;
  const tCTR=tImpr>0?(tClicks/tImpr)*100:0;
  const tUCTR=rows.length>0?rows.reduce((s,r)=>s+(r.unique_link_ctr||0),0)/rows.length:0;
  const tCostCO=tc>0?ts/tc:0;

  $("#tfoot").innerHTML=`<tr>
    <td>TOTAL</td>
    <td class="num">${tp.toLocaleString()}</td>
    <td class="num">${fmt(ts)}</td>
    <td class="num ${tr>0?'vg':''}">${fmt(tr)}</td>
    <td class="num ${tP>=0?'vg':'vr'}">${fmt(tP)}</td>
    <td class="num">${tC!==null?fmt(tC):'—'}</td>
    <td class="num ${tR>=0?'vg':'vr'}">${(tR>=0?'+':'')+tR.toFixed(1)}%</td>
    <td class="num">${fmt(tCPM)}</td>
    <td class="num">${fmt(tCPC)}</td>
    <td class="num">${tCTR.toFixed(2)}%</td>
    <td class="num">${tUCTR.toFixed(2)}%</td>
    <td class="num">${tc.toLocaleString()}</td>
    <td class="num">${tCostCO>0?fmt(tCostCO):'—'}</td>
    <td class="zero">-</td>
  </tr>`;
}

function toggleCamps(acctId, bm){
  if(expandedAcct===acctId){expandedAcct=null;renderTable();return;}
  expandedAcct=acctId;
  renderTable();
  if(!campCache[acctId]){
    fetch(`/api/campaigns?account_id=${acctId}&bm=${bm}&period=${currentPeriod}`)
      .then(r=>r.json())
      .then(data=>{campCache[acctId]=data;renderTable();})
      .catch(()=>{campCache[acctId]=[];renderTable();});
  }
}

function loadCreativeLinks(){
  fetch("/api/creative-links")
    .then(r=>r.json())
    .then(data=>{
      creativeLinksByName=data||{};
      if(rows.length)renderTable();
    })
    .catch(()=>{});
}

function attachCreativeListeners(){
  $$(".camp-name-clickable").forEach(el=>el.addEventListener("click",e=>{
    const campName=decodeURIComponent(e.currentTarget.dataset.campName||"");
    openCreativeModal(campName);
  }));
  $$(".creative-add-btn,.creative-edit-btn").forEach(btn=>btn.addEventListener("click",e=>{
    const campName=decodeURIComponent(e.currentTarget.dataset.campName||"");
    openCreativeModal(campName);
  }));
}

function openCreativeModal(campaignName){
  currentCreativeCampaignName=campaignName;
  $("#creativeCampaignName").textContent=campaignName;
  $("#creativeUrlInput").value=creativeLinksByName[campaignName]||"";
  $("#creativeModal").classList.add("show");
}

function closeCreativeModal(){
  $("#creativeModal").classList.remove("show");
  currentCreativeCampaignName=null;
}

function submitCreativeLink(){
  if(!currentCreativeCampaignName)return;
  const url=$("#creativeUrlInput").value.trim();
  fetch("/api/creative-links",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({name:currentCreativeCampaignName,url})
  })
    .then(async r=>{
      const data=await r.json();
      if(!r.ok)throw new Error(data.error||"Could not save URL");
      if(data.deleted)delete creativeLinksByName[currentCreativeCampaignName];
      else creativeLinksByName[currentCreativeCampaignName]=data.url;
      renderTable();
      closeCreativeModal();
    })
    .catch(e=>alert(e.message||"Could not save URL"));
}

// ---- Refresh ----
function refresh(){doLoad(currentPeriod);}

function updateTimestamp(){
  const t=new Date().toLocaleTimeString("en-US",{hour:"2-digit",minute:"2-digit"});
  $("#lastUpdate").textContent="Last: "+t;
  $("#statusText").textContent="Auto-report: 7:55 AM";
}

function checkAutoReport(){
  fetch("/api/report").then(r=>r.json()).then(d=>{
    if(d.generated_at){$("#reportBadge").classList.add("show");$("#reportBadge").textContent="AUTO-REPORT "+d.generated_at.split(" ")[1];}
  }).catch(()=>{});
}

function doLoad(period){
  currentPeriod=period;
  $("#refreshBtn").classList.add("spinning");
  $$(".date-b").forEach(b=>b.disabled=true);
  $("#status").classList.add("loading");
  $("#loader").classList.add("show");
  $("#tableWrap").style.opacity="0.3";

  fetch("/api/data/"+period)
    .then(r=>r.json())
    .then(data=>{
      rows=data.map(r=>({...r,
        profit:r.revenue-r.spend,
        cpa:r.purchases>0?r.spend/r.purchases:null,
        roi:r.spend>0?((r.revenue-r.spend)/r.spend)*100:null,
      }));
      renderCards();renderTable();finish();
    })
    .catch(()=>finish());
}

function finish(){
  $("#status").classList.remove("loading");
  $("#refreshBtn").classList.remove("spinning");
  $("#loader").classList.remove("show");
  $("#tableWrap").style.opacity="1";
  $$(".date-b").forEach(b=>b.disabled=false);
  updateTimestamp();
}

// ---- FEEDBACK SYSTEM ----
let feedbacks=[], currentResponseFbId=null, currentEditingFbId=null, deleteButtonsVisible=false;

function openFeedbackModal(){
  currentEditingFbId=null;
  $("#feedbackModalTitle").textContent="Send Feedback";
  $("#feedbackSubmitBtn").textContent="Send";
  $("#feedbackText").value="";
  $("#feedbackModal").classList.add("show");
}

function openEditFeedbackModal(fbId){
  const target=feedbacks.find(fb=>fb.id===fbId);
  if(!target)return;
  currentEditingFbId=fbId;
  $("#feedbackModalTitle").textContent="Edit Feedback";
  $("#feedbackSubmitBtn").textContent="Save";
  $("#feedbackText").value=target.content||"";
  $("#feedbackModal").classList.add("show");
}

function closeFeedbackModal(){
  $("#feedbackModal").classList.remove("show");
  currentEditingFbId=null;
}

function closeResponseModal(){
  $("#responseModal").classList.remove("show");
  currentResponseFbId=null;
}

function submitFeedback(){
  const text=$("#feedbackText").value.trim();
  if(!text){alert("Please write a feedback message");return;}
  const endpoint=currentEditingFbId?`/api/feedback/${currentEditingFbId}`:"/api/feedback";
  const method=currentEditingFbId?"PATCH":"POST";
  fetch(endpoint,{method,headers:{"Content-Type":"application/json"},body:JSON.stringify({content:text})})
    .then(r=>r.json())
    .then(()=>{loadFeedbacks();closeFeedbackModal();})
    .catch(e=>console.error(e));
}

function loadFeedbacks(){
  fetch("/api/feedback").then(r=>r.json()).then(data=>{feedbacks=data||[];renderFeedbacks();}).catch(()=>{});
}

function renderFeedbacks(){
  const list=$("#feedbackList");
  if(feedbacks.length===0){list.innerHTML='<div class="empty-feedback">No feedback yet. Be the first to share!</div>';return;}
  list.innerHTML=feedbacks.map(fb=>{
    const time=new Date(fb.created_at).toLocaleString();
    const isResolved=fb.status==="resolved";
    let respHtml="";
    if(fb.responses&&fb.responses.length>0){
      respHtml+=`<div class="response-section"><strong style="font-size:11px;color:var(--text3)">Responses:</strong>`;
      fb.responses.forEach(r=>{
        const rtime=new Date(r.created_at).toLocaleString();
        respHtml+=`<div class="response-item"><div class="response-meta">${rtime}</div><div class="response-text">${escapeHtml(r.content)}</div></div>`;
      });
      respHtml+="</div>";
    }
    return `<div class="feedback-item ${isResolved?'resolved':''}">
      <div class="feedback-header">
        <span class="feedback-time">${time}</span>
        <span class="fb-status ${isResolved?'resolved':'open'}">${isResolved?'Resolved':'Open'}</span>
      </div>
      <div class="feedback-text">${escapeHtml(fb.content)}</div>
      <div class="feedback-actions">
        <button class="fb-action reply-btn" data-fb-id="${fb.id}" title="Reply"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 15 16 10 21 5"/><path d="M21 15H9a6 6 0 01-6-6V3"/></svg>Reply</button>
        <button class="fb-action resolve-btn" data-fb-id="${fb.id}" data-status="${isResolved?'open':'resolved'}" title="Toggle Status"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0016.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 002 8.5c0 2.3 1.5 4.05 3 5.5"/></svg>${isResolved?'Reopen':'Resolve'}</button>
        <button class="fb-action edit-btn" data-fb-id="${fb.id}" title="Edit"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 113 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>Edit</button>
        <button class="fb-action delete-btn" data-fb-id="${fb.id}" title="Delete (press D)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>Delete</button>
      </div>
      ${respHtml}
    </div>`;
  }).join("");
  attachFeedbackListeners();
}

function attachFeedbackListeners(){
  $$(".reply-btn").forEach(btn=>{btn.addEventListener("click",e=>{const fbId=e.currentTarget.dataset.fbId;openResponseModal(fbId);});});
  $$(".edit-btn").forEach(btn=>{btn.addEventListener("click",e=>{const fbId=e.currentTarget.dataset.fbId;openEditFeedbackModal(fbId);});});
  $$(".resolve-btn").forEach(btn=>{btn.addEventListener("click",e=>{const fbId=e.currentTarget.dataset.fbId;const status=e.currentTarget.dataset.status;toggleStatus(fbId,status);});});
  $$(".delete-btn").forEach(btn=>{btn.addEventListener("click",e=>{const fbId=e.currentTarget.dataset.fbId;deleteFeedback(fbId);});});
}

function openResponseModal(fbId){
  currentResponseFbId=fbId;
  $("#responseText").value="";
  $("#responseModal").classList.add("show");
}

function submitResponse(){
  if(!currentResponseFbId)return;
  const text=$("#responseText").value.trim();
  if(!text){alert("Please write a response");return;}
  fetch(`/api/feedback/${currentResponseFbId}/response`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({content:text})})
    .then(r=>r.json())
    .then(()=>{loadFeedbacks();closeResponseModal();})
    .catch(e=>console.error(e));
}

function toggleStatus(fbId,newStatus){
  fetch(`/api/feedback/${fbId}/status`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:newStatus})})
    .then(r=>r.json())
    .then(()=>{loadFeedbacks();})
    .catch(e=>console.error(e));
}

function deleteFeedback(fbId){
  if(!confirm("Are you sure you want to delete this feedback?"))return;
  fetch(`/api/feedback/${fbId}/delete`,{method:"DELETE"})
    .then(r=>r.json())
    .then(()=>{loadFeedbacks();})
    .catch(e=>console.error(e));
}

function toggleDeleteButtons(){
  deleteButtonsVisible=!deleteButtonsVisible;
  document.body.classList.toggle("show-delete",deleteButtonsVisible);
}

document.addEventListener("keydown",e=>{
  const tag=(e.target&&e.target.tagName)?e.target.tagName.toLowerCase():"";
  const isEditing=tag==="input"||tag==="textarea"||(e.target&&e.target.isContentEditable);
  if((e.key==="d"||e.key==="D")&&!e.repeat&&!isEditing){
    e.preventDefault();
    toggleDeleteButtons();
  }
});

function escapeHtml(text){
  const map={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'};
  return text.replace(/[&<>"']/g,m=>map[m]);
}

// Cerrar modal al hacer click fuera
$$(".modal-backdrop").forEach(m=>{m.addEventListener("click",e=>{if(e.target===m)m.classList.remove("show");});});

// Cargar feedbacks al iniciar
loadCreativeLinks();
loadFeedbacks();
setInterval(loadFeedbacks,30000);

doLoad("today");
setInterval(checkAutoReport,60000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    t = threading.Thread(target=report_scheduler, daemon=True)
    t.start()
    print(f"\n  Meta Ads Report -> http://localhost:{PORT}")
    print("  Auto-report scheduled at 7:55 AM daily\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)
