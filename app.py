"""Truck Daily Tracker.
Run:  pip install -r requirements.txt
      For local image reading without an API key: py -m pip install -r requirements-ocr.txt
      python app.py   -> open http://127.0.0.1:5000
      Phone (HTTPS):  pip install pyopenssl, set HTTPS=1, then python app.py
"""
import json, os, sqlite3
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from flask import Flask, jsonify, render_template, request
import config, db
from extractor import extract

app = Flask(__name__)

if config.ENGINE in ("easyocr", "auto", "ocr_first"):  # load the OCR models in the background so the first photo is not slow
    import threading, ocr_extractor
    threading.Thread(target=ocr_extractor.warmup, daemon=True).start()


@app.get("/")
def index():
    return render_template("index.html")


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
        "location": address.get("neighbourhood") or address.get("suburb") or address.get("village")
                    or address.get("town") or address.get("city") or address.get("municipality"),
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