import os

# Auto-load .env if available
env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_file):
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
    except ImportError:
        with open(env_file, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _k, _v = _k.strip(), _v.strip().strip("'\"")
                    if _k and _k not in os.environ:
                        os.environ[_k] = _v

import importlib.util
HAS_EASYOCR = importlib.util.find_spec("easyocr") is not None  # really check that it is installed

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ADMIN_KEY = os.getenv("ADMIN_KEY", "")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DB_PATH = os.getenv("DB_PATH", "tracker.db")
DATABASE_URL = os.getenv("DATABASE_URL", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SECRET_KEY", "")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "truck-tracker-images")
PORT = int(os.getenv("PORT", "5000"))
# Reading engine: "auto" (runs EasyOCR first if available, then Gemini) | "gemini" | "easyocr"
_default_engine = "auto" if HAS_EASYOCR else "gemini"
ENGINE = os.getenv("EXTRACT_ENGINE", _default_engine).lower()
# How dates/times are shown in the form (strftime). 12-hour time like "8:00 PM".
DATE_FMT = os.getenv("DATE_FMT", "%d-%b-%Y")      # 20-Sep-2026  (use "%d-%b-%y" for 20-Sep-26)
USE_HTTPS = bool(os.getenv("HTTPS"))  # phone camera needs HTTPS

S, N = ["string", "null"], ["number", "null"]


def f(t, d):
    return {"type": t, "description": d}


# Fields Gemini must fill for each image type (null only if truly unreadable).
SCHEMAS = {
    "cluster": {
        "km": f(N, "Vehicle total odometer / mileage reading (digits only, e.g. 7148 or 123456). Look for numbers labeled with 'ODO', 'km', 'TOTAL', or the primary 4-7 digit counter on the digital or analog dashboard. Do not return null if any odometer reading is legible."),
        "date": f(S, "Date shown on the display as YYYY-MM-DD (e.g. 20-SEP-26 -> 2026-09-20)."),
        "time": f(S, "Clock time shown on the display (e.g. 8:00 PM -> 20:00, 24-hour HH:MM). Do not return null when the clock is legible."),
    },
    "geo": {
        "date": f(S, "Date in the overlay as YYYY-MM-DD."),
        "time": f(S, "Time in the overlay, 24-hour HH:MM."),
        "road": f(S, "Road or street line of the address overlay."),
        "location": f(S, "Locality / town line of the address overlay."),
        "district": f(S, "District."),
        "state": f(S, "State."),
        "gps": f(S, "Latitude,longitude if printed in the overlay, else null."),
    },
    "fuel": {
        "date": f(S, "Bill date as YYYY-MM-DD."),
        "time": f(S, "Bill time, 24-hour HH:MM."),
        "receipt_no": f(S, "Receipt / voucher / invoice / bill number: the unique id printed on the bill."),
        "product": f(S, "Fuel product, e.g. Diesel or Petrol."),
        "rate": f(N, "Price per litre."),
        "volume": f(N, "Litres dispensed."),
        "amount": f(N, "Total amount paid."),
        "vehicle_no": f(S, "Vehicle number if printed."),
    },
}

PROMPTS = {
    "cluster": "This is a photo of a vehicle instrument cluster / dashboard display. "
               "Read the odometer reading carefully (the cumulative total kilometers driven by the vehicle, "
               "typically a 4 to 7 digit number like 7148, 45210, 154200, often displayed near 'ODO', 'km', 'TOTAL', "
               "or on the main digital LCD / analog mileage counter). "
               "Also read the date and clock time shown on the display (convert clock to 24-hour HH:MM). "
               "Ignore steering wheel, people, hands, and reflections.",
    "geo": "Read only details that are actually visible in this image or its text overlay. Extract any visible date, "
           "time, address, and printed coordinates. Do not guess a street, town, district, or state from the scene; "
           "return null for details not visible.",
    "fuel": "This is a fuel pump bill; the layout varies by pump. Read the values from the printed text.",
}