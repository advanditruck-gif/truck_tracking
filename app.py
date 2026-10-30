"""Truck Daily Tracker.
Run:  pip install -r requirements.txt
      For local image reading without an API key: py -m pip install -r requirements-ocr.txt
      python app.py   -> open http://127.0.0.1:5000
      Phone (HTTPS):  pip install pyopenssl, set HTTPS=1, then python app.py
"""
import csv, hmac, io, json, os, secrets, sqlite3
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
import config, db
import extractor
import report as reportmod
from extractor import extract

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or config.ADMIN_KEY or os.urandom(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.getenv("RENDER") or config.USE_HTTPS),
)


def _admin_key_is_configured():
    return len(config.ADMIN_KEY.encode("utf-8")) >= 32


def _admin_csrf_token():
    token = session.get("admin_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["admin_csrf_token"] = token
    return token


def _valid_admin_csrf():
    token = session.get("admin_csrf_token", "")
    submitted = request.form.get("csrf_token", "")
    return bool(token and submitted and hmac.compare_digest(token, submitted))


def _require_admin():
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_page"))
    return None

# Gemini is tried first in "auto" mode, so only pre-load the OCR models when EasyOCR is the main engine.
if config.ENGINE == "easyocr" and getattr(config, "HAS_EASYOCR", False):
    import threading, ocr_extractor
    threading.Thread(target=ocr_extractor.warmup, daemon=True).start()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/report")
def report_page():
    return render_template("report.html")


@app.get("/admin")
def admin_page():
    if not _admin_key_is_configured():
        return render_template("admin.html", key_configured=False), 503
    return render_template(
        "admin.html",
        key_configured=True,
        authenticated=bool(session.get("admin_authenticated")),
        csrf_token=_admin_csrf_token(),
        events=db.admin_events() if session.get("admin_authenticated") else [],
        notice=request.args.get("notice", ""),
        error="",
    )


@app.post("/admin/login")
def admin_login():
    if not _admin_key_is_configured():
        return render_template("admin.html", key_configured=False), 503
    if not _valid_admin_csrf():
        abort(400, "Invalid form token.")
    submitted_key = request.form.get("admin_key", "")
    if not hmac.compare_digest(config.ADMIN_KEY, submitted_key):
        return render_template(
            "admin.html",
            key_configured=True,
            authenticated=False,
            csrf_token=_admin_csrf_token(),
            events=[],
            notice="",
            error="Invalid admin key.",
        ), 401
    session.clear()
    session["admin_authenticated"] = True
    _admin_csrf_token()
    return redirect(url_for("admin_page"))


@app.post("/admin/logout")
def admin_logout():
    if not _admin_key_is_configured():
        return render_template("admin.html", key_configured=False), 503
    if not session.get("admin_authenticated") or not _valid_admin_csrf():
        abort(400, "Invalid form token.")
    session.clear()
    return redirect(url_for("admin_page"))


@app.post("/admin/delete/<int:event_id>")
def admin_delete_event(event_id):
    if not _admin_key_is_configured():
        return render_template("admin.html", key_configured=False), 503
    auth_redirect = _require_admin()
    if auth_redirect:
        return auth_redirect
    if not _valid_admin_csrf():
        abort(400, "Invalid form token.")
    deleted = db.delete_event(event_id)
    notice = "Record deleted." if deleted else "Record not found."
    return redirect(url_for("admin_page", notice=notice))


@app.get("/admin/export")
def admin_export():
    if not _admin_key_is_configured():
        return render_template("admin.html", key_configured=False), 503
    auth_redirect = _require_admin()
    if auth_redirect:
        return auth_redirect

    def safe_cell(value):
        text = str(value)
        if text.startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + text
        return text

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["ID", "Run", "Type", "Recorded at", "Data"])
    for event in db.admin_events():
        writer.writerow([
            safe_cell(event["id"]),
            safe_cell(event["run"]),
            safe_cell(event["t"]),
            safe_cell(event["at"]),
            safe_cell(json.dumps(event["d"], ensure_ascii=False)),
        ])
    response = app.response_class(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = 'attachment; filename="truck-tracker-records.csv"'
    return response


@app.get("/api/report")
def api_report():
    return jsonify(reportmod.build_reports(db.all_events()))


@app.get("/api/ping")
def api_ping():
    """Open /api/ping in the browser to confirm which code is running."""
    return jsonify({"extractor": getattr(extractor, "VERSION", "old"), "engine": config.ENGINE, "model": config.MODEL,
                    "api_key_set": bool(getattr(config, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY")),
                    "folder": os.path.dirname(os.path.abspath(__file__))})


@app.get("/api/reverse-geocode")
def api_reverse_geocode():
    try:
        lat, lon = float(request.args.get("lat", "")), float(request.args.get("lon", ""))
    except ValueError:
        return jsonify({"error": "Valid latitude and longitude are required."}), 400
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({"error": "Latitude or longitude is out of range."}), 400

    url = "https://nominatim.openstreetmap.org/reverse?" + urlencode({
        "format": "jsonv2", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1,
    })
    req = Request(url, headers={
        "User-Agent": "TruckDailyTracker/1.0 (reverse geocoding)",
        "Accept": "application/json",
        "Accept-Language": request.accept_languages.best or "en",
    })
    try:
        with urlopen(req, timeout=8) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as e:
        print("reverse geocoding failed:", repr(e))
        return jsonify({"error": "Address lookup failed. Check the server's internet connection and try again."}), 502

    if result.get("error"):
        return jsonify({"error": "No address could be found for these coordinates."}), 404
    address = result.get("address", {})
    state = address.get("state")
    district = address.get("state_district") or address.get("district")
    is_kerala = bool(state and state.strip().casefold() == "kerala")
    if is_kerala and district and district.strip().casefold() == "ernad":
        district = "Malappuram"
    if not district and not is_kerala:
        district = address.get("city_district") or address.get("county")
    return jsonify({
        "road": address.get("road") or address.get("pedestrian") or address.get("footway") or address.get("residential"),
        "location": address.get("suburb") or address.get("village") or address.get("town")
                    or address.get("city") or address.get("hamlet") or address.get("neighbourhood")
                    or address.get("municipality"),
        "district": district,
        "state": state,
    })


@app.post("/api/extract")
def api_extract():
    kind, img = request.form.get("kind", ""), request.files.get("image")
    if kind not in config.PROMPTS or not img:
        return jsonify({}), 400
    return jsonify(extract(kind, img.read()))


@app.post("/api/events")
def api_add():
    j = request.get_json(force=True)
    try:
        db.add_event(j.get("run"), j.get("t"), j.get("at"), j.get("d"))
    except sqlite3.IntegrityError:
        return jsonify({"error": "duplicate receipt"}), 409
    return jsonify({"ok": True})


@app.get("/api/events")
def api_list():
    return jsonify(db.all_events())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, ssl_context="adhoc" if config.USE_HTTPS else None)