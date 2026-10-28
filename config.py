import os

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
DB_PATH = os.getenv("DB_PATH", "tracker.db")
PORT = int(os.getenv("PORT", "5000"))
# Reading engine: "easyocr" runs locally without a Claude API key; "auto" uses Claude first.
ENGINE = os.getenv("EXTRACT_ENGINE", "easyocr").lower()
# How dates/times are shown in the form (strftime). 12-hour time like "8:00 PM".
DATE_FMT = os.getenv("DATE_FMT", "%d-%b-%Y")      # 20-Sep-2026  (use "%d-%b-%y" for 20-Sep-26)
USE_HTTPS = bool(os.getenv("HTTPS"))  # phone camera needs HTTPS

S, N = ["string", "null"], ["number", "null"]


def f(t, d):
    return {"type": t, "description": d}


# Fields Claude must fill for each image type (null only if truly unreadable).
SCHEMAS = {
    "cluster": {
        "km": f(N, "Odometer reading beside the ODO label, digits only, no units."),
        "date": f(S, "Date shown at top of the display as YYYY-MM-DD (e.g. 20-SEP-26 -> 2026-09-20)."),
        "time": f(S, "Read the clock printed at the top-right of the display. For example, 8:00 PM must be returned as 20:00. Do not return null when the clock is legible."),
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
    "cluster": "This is a photo of a vehicle instrument cluster display. Read the odometer (the number beside ODO, "
               "usually bottom of the screen) and the date and time shown at the top. The clock is at the top-right; "
               "read it carefully, including AM/PM, and convert it to 24-hour HH:MM (8:00 PM is 20:00). "
               "Ignore people, hands and reflections.",
    "geo": "Read only details that are actually visible in this image or its text overlay. Extract any visible date, "
           "time, address, and printed coordinates. Do not guess a street, town, district, or state from the scene; "
           "return null for details not visible.",
    "fuel": "This is a fuel pump bill; the layout varies by pump. Read the values from the printed text.",
}