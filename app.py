"""Truck Daily Tracker.
Run:  pip install -r requirements.txt
      For local image reading without an API key: py -m pip install -r requirements-ocr.txt
      python app.py   -> open http://127.0.0.1:5000
      Phone (HTTPS):  pip install pyopenssl, set HTTPS=1, then python app.py
"""
import csv, hmac, io, json, os, secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from flask import Flask, abort, jsonify, make_response, redirect, render_template, request, send_from_directory, session, url_for
import config, db
import extractor
import report as reportmod
import supabase_storage
import pwa_assets
from extractor import extract

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
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


@app.get("/sw.js")
def service_worker():
    response = make_response(send_from_directory("static", "sw.js"))
    response.headers["Content-Type"] = "application/javascript"
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.get("/manifest.webmanifest")
def manifest():
    response = make_response(send_from_directory("static", "manifest.webmanifest"))
    response.headers["Content-Type"] = "application/manifest+json"
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@app.get("/favicon.ico")
def favicon():
    pwa_assets.ensure_pwa_icons()
    return send_from_directory(os.path.join("static", "icons"), "favicon.png", mimetype="image/png")


@app.get("/static/icons/<path:filename>")
def static_icons(filename):
    pwa_assets.ensure_pwa_icons()
    return send_from_directory(os.path.join("static", "icons"), filename)


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
    event = db.admin_event(event_id)
    if event and event["d"].get("image_path"):
        try:
            supabase_storage.delete_image(event["d"]["image_path"])
        except Exception as e:
            app.logger.warning("Could not delete image from Supabase Storage: %s", e)
    deleted = db.delete_event(event_id)
    notice = "Record deleted." if deleted else "Record not found."
    return redirect(url_for("admin_page", notice=notice))


@app.get("/admin/image/<int:event_id>")
def admin_event_image(event_id):
    if not _admin_key_is_configured():
        return render_template("admin.html", key_configured=False), 503
    auth_redirect = _require_admin()
    if auth_redirect:
        return auth_redirect
    event = db.admin_event(event_id)
    if not event or not event["d"].get("image_path"):
        abort(404)
    try:
        return redirect(supabase_storage.signed_image_url(event["d"]["image_path"]))
    except Exception as e:
        abort(502, description=f"Could not reach Supabase Storage: {e}")


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


@app.get("/api/report/records")
def api_report_records():
    events = db.all_events()
    records = []
    for event in events:
        data = {
            key: value
            for key, value in event["d"].items()
            if key != "image_path"
        }
        records.append({
            "id": event["id"],
            "run": event["run"],
            "type": event["t"],
            "at": event["at"],
            "data": data,
            "has_image": bool(event["d"].get("image_path")),
        })
    return jsonify({
        "reports": reportmod.build_reports(events),
        "records": records,
    })


@app.get("/report/image/<int:event_id>")
def report_event_image(event_id):
    event = db.admin_event(event_id)
    if not event or not event["d"].get("image_path"):
        abort(404)
    try:
        response = redirect(supabase_storage.signed_image_url(
            event["d"]["image_path"], expires_in=7 * 24 * 60 * 60
        ))
        response.headers["Cache-Control"] = "private, max-age=86400"
        return response
    except Exception as error:
        app.logger.error("Could not create report image URL: %s", error)
        abort(502, description="Could not retrieve this image from Supabase Storage.")


@app.get("/api/ping")
def api_ping():
    """Open /api/ping in the browser to confirm which code is running."""
    return jsonify({"extractor": getattr(extractor, "VERSION", "old"), "engine": config.ENGINE, "model": config.MODEL,
                    "api_key_set": bool(getattr(config, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY")),
                    "database": "supabase" if config.DATABASE_URL else "sqlite",
                    "supabase_image_storage_configured": bool(
                        config.SUPABASE_URL and config.SUPABASE_SERVICE_ROLE_KEY
                    ),
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
    image = request.files.get("image")
    if image:
        try:
            j = json.loads(request.form["event"])
        except (KeyError, json.JSONDecodeError):
            return jsonify({"error": "A valid event payload is required."}), 400
        if not isinstance(j, dict) or not isinstance(j.get("d"), dict):
            return jsonify({"error": "Event data must be a JSON object."}), 400
        if image.mimetype != "image/jpeg":
            return jsonify({"error": "Only JPEG images are accepted."}), 415
        image_bytes = image.read()
        if not image_bytes.startswith(b"\xff\xd8\xff"):
            return jsonify({"error": "The uploaded file is not a valid JPEG image."}), 415
        if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
            return jsonify({"error": "Private Supabase image storage is not configured on the server."}), 503
        image_path = f"events/{uuid4().hex}.jpg"
        try:
            supabase_storage.upload_image(image_path, image_bytes, image.mimetype)
        except Exception as error:
            app.logger.error("Failed to upload image to Supabase: %s", error)
            return jsonify({"error": f"Failed to upload image to Supabase Storage: {error}"}), 502
    else:
        j = request.get_json(force=True)
        if not isinstance(j, dict) or not isinstance(j.get("d"), dict):
            return jsonify({"error": "Event data must be a JSON object."}), 400
    j["d"].pop("image_path", None)
    if image:
        j["d"]["image_path"] = image_path
    if j.get("token") and j.get("run"):   # remember which phone is doing this run (for closed-app alerts)
        try:
            db.link_run_token(j["run"], str(j["token"]))
        except Exception as error:
            app.logger.warning("Could not save the phone token: %s", error)
    try:
        event_id = db.add_event(j.get("run"), j.get("t"), j.get("at"), j.get("d"))
    except db.DuplicateReceiptError:
        if image:
            try:
                supabase_storage.delete_image(image_path)
            except Exception:
                pass
        return jsonify({"error": "duplicate receipt"}), 409
    return jsonify({"ok": True, "id": event_id})


@app.get("/api/events")
def api_list():
    return jsonify(db.all_events())


# ---------- closed-app alerts (Firebase push) ----------
CRON_KEY = os.getenv("CRON_KEY", "")                          # secret used by the scheduler and the test address
LATE_MIN = int(os.getenv("LATE_MINUTES", "30"))               # the photo is late after this many minutes
REPEAT_MIN = int(os.getenv("ALERT_REPEAT_MINUTES", "3"))      # repeat the alert this often while it is late
GIVE_UP_HOURS = int(os.getenv("ALERT_GIVE_UP_HOURS", "6"))    # stop alerting a run that was never stopped
_fcm = None


def _messaging():
    """Start Firebase on first use. The key is env FIREBASE_CREDENTIALS (JSON text) or a Render secret file."""
    global _fcm
    if _fcm is not None:
        return _fcm
    import firebase_admin
    from firebase_admin import credentials, messaging
    raw = os.getenv("FIREBASE_CREDENTIALS", "").strip()
    path = os.getenv("FIREBASE_KEY_FILE", "/etc/secrets/firebase-key.json")
    if raw:
        cred = credentials.Certificate(json.loads(raw))
    elif os.path.exists(path):
        cred = credentials.Certificate(path)
    else:
        raise RuntimeError("Firebase key not found. Add the secret file firebase-key.json on Render.")
    firebase_admin.initialize_app(cred)
    _fcm = messaging
    return _fcm


def send_push(tokens, title, body):
    """Send the alert to these phones. Returns how many Firebase accepted."""
    if not tokens:
        return 0
    m = _messaging()
    message = m.MulticastMessage(
        tokens=tokens,
        notification=m.Notification(title=title, body=body),
        android=m.AndroidConfig(
            priority="high", ttl=600,
            notification=m.AndroidNotification(channel_id="alerts_v1", sound="alert", priority="max"),
        ),
    )
    result = m.send_each_for_multicast(message)
    dead = tuple(c for c in (getattr(m, "UnregisteredError", None), getattr(m, "SenderIdMismatchError", None)) if c)
    gone = [t for t, r in zip(tokens, result.responses) if not r.success and dead and isinstance(r.exception, dead)]
    if gone:
        db.delete_tokens(gone)   # app was uninstalled: forget that phone
    for r in result.responses:
        if not r.success:
            print("push failed:", repr(r.exception))
    return result.success_count


def _when(text):
    t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def check_late():
    """Alert only for runs whose latest location photo is more than LATE_MIN minutes old."""
    now = datetime.now(timezone.utc)
    sent, late_runs = 0, []
    for run_id, last_at in db.active_run_locations():
        try:
            late_by = now - _when(last_at) - timedelta(minutes=LATE_MIN)
        except ValueError:
            continue
        if late_by < timedelta(0) or late_by > timedelta(hours=GIVE_UP_HOURS):
            continue                                    # on time, or the run was abandoned
        previous = db.last_alert(run_id)
        if previous and now - _when(previous) < timedelta(minutes=REPEAT_MIN):
            continue                                    # alerted a moment ago
        token = db.run_token(run_id)
        tokens = [token] if token else db.all_tokens()  # phone unknown: tell everyone rather than miss it
        minutes = int(late_by.total_seconds() // 60)
        n = send_push(tokens, "UPLOAD CURRENT LOCATION IMAGE",
                      "Location photo is " + (str(minutes) + " min late" if minutes else "due now"))
        db.set_last_alert(run_id, now.isoformat())
        sent += n
        late_runs.append({"run": run_id, "late_min": minutes, "sent": n})
    return {"checked_at": now.isoformat(), "alerts_sent": sent, "late_runs": late_runs}


def _cron_allowed():
    return bool(CRON_KEY) and hmac.compare_digest(request.args.get("key", ""), CRON_KEY)


@app.post("/api/push-token")
def api_push_token():
    token = (request.get_json(force=True, silent=True) or {}).get("token", "")
    if not isinstance(token, str) or len(token) < 20:
        return jsonify({"error": "bad token"}), 400
    db.save_token(token)
    return jsonify({"ok": True})


@app.route("/api/cron/check-late", methods=["GET", "POST"])
def api_check_late():
    """A scheduler calls this every minute:  /api/cron/check-late?key=YOUR_CRON_KEY"""
    if not _cron_allowed():
        return jsonify({"error": "forbidden"}), 403
    try:
        return jsonify(check_late())
    except Exception as error:
        app.logger.error("check_late failed: %r", error)
        return jsonify({"error": str(error)[:300]}), 500


@app.route("/api/push-test", methods=["GET", "POST"])
def api_push_test():
    """Open  /api/push-test?key=YOUR_CRON_KEY  to ring every registered phone once."""
    if not _cron_allowed():
        return jsonify({"error": "forbidden"}), 403
    tokens = db.all_tokens()
    try:
        n = send_push(tokens, "TEST ALERT", "If you hear your alert sound, closed-app alerts work.")
    except Exception as error:
        app.logger.error("push test failed: %r", error)
        return jsonify({"error": str(error)[:300], "phones": len(tokens)}), 500
    return jsonify({"phones": len(tokens), "delivered": n})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, ssl_context="adhoc" if config.USE_HTTPS else None)