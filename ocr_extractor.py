"""Offline reading with EasyOCR + regex rules (no API key needed).
Install:  py -m pip install -r requirements-ocr.txt      (downloads ~1-2 GB incl. PyTorch; models download on first run)
Returns the same fields as the Claude reader: cluster {km,date,time}, geo {...}, fuel {...}.
"""
import re

_reader = None

MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
DATE_PATTERNS = [  # your patterns, applied after _norm() turns '20- SEP -26' into '20 SEP 26'
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",
    r"\b\d{1,2}\s*" + MON + r"\.?,?\s*\d{2,4}\b",
    r"\b" + MON + r"\.?\s*\d{1,2},?\s*\d{2,4}\b",
]


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["en"], gpu=False)
    return _reader


# ---------- helpers (pure functions, easy to test) ----------
def _norm(t):
    t = re.sub(r"\b5EP\b", "SEP", t)
    t = re.sub(r"\b0CT\b", "OCT", t)
    t = re.sub(r"\bN0V\b", "NOV", t)
    # '20- SEP -26' / '26-Oct-2026' -> '20 SEP 26' / '26 Oct 2026'
    return re.sub(r"(\d{1,2})\s*[-/.]\s*([A-Za-z]{3,9})\s*[-/.,]?\s*(\d{2,4})", r"\1 \2 \3", t)


_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
_DIG = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "Z": "2", "z": "2", "S": "5", "B": "8"})


def _fuzzy_date(text):
    """Tolerates OCR typos: '2O- 5EP -Z6', '20 - SEF - 26', '20-SEP-26'."""
    import difflib
    from datetime import date
    for m in re.finditer(r"([0-9OolI|Zz]{1,2})\s*[-\u2013\u2014_./,]*\s*([A-Za-z0-9]{3})\s*[-\u2013\u2014_./,]*\s*([0-9OolI|ZzSB]{2,4})", text):
        day, yr = m.group(1).translate(_DIG), m.group(3).translate(_DIG)
        tok = m.group(2).upper().replace("5", "S").replace("0", "O").replace("1", "I")
        mon = difflib.get_close_matches(tok, _MONTHS, n=1, cutoff=0.6)
        if not mon or not day.isdigit() or not yr.isdigit():
            continue
        y = int(yr) + (2000 if len(yr) == 2 else 0)
        try:
            return date(y, _MONTHS.index(mon[0]) + 1, int(day)).isoformat() if 2000 <= y <= 2100 else None
        except ValueError:
            continue
    return None


def find_date(text):
    from dateutil import parser
    text = _norm(text)
    for p in DATE_PATTERNS:
        for m in re.finditer(p, text, flags=re.I):
            try:
                d = parser.parse(m.group(0), dayfirst=True).date()  # dayfirst: Indian format
            except (ValueError, OverflowError):
                continue
            if 2000 <= d.year <= 2100:
                return d.isoformat()
    return _fuzzy_date(text)


def find_time(text):
    m = re.search(r"\b(\d{1,2})\s*[:.;]\s*(\d{2})(?:\s*[:.;]\s*\d{2})?\s*([ap])\.?\s*m\b", text, re.I)
    if m:
        h, mi, ap = int(m.group(1)), m.group(2), m.group(3).lower()
        if 1 <= h <= 12:
            h = h % 12 + (12 if ap == "p" else 0)
            return f"{h:02d}:{mi}"
    m = re.search(r"\b([01]?\d|2[0-3])\s*[:;]\s*([0-5]\d)\b", text)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def _num(s):
    try:
        return float(str(s).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _lines(res):
    """Group OCR boxes into text lines (top to bottom, left to right)."""
    items = []
    for box, text, *_ in res:
        ys, xs = [p[1] for p in box], [p[0] for p in box]
        items.append((sum(ys) / len(ys), min(xs), max(ys) - min(ys), text))
    if not items:
        return []
    items.sort()
    med = sorted(i[2] for i in items)[len(items) // 2] or 10
    groups, cur = [], [items[0]]
    for it in items[1:]:
        if abs(it[0] - cur[-1][0]) <= 0.6 * med:
            cur.append(it)
        else:
            groups.append(cur)
            cur = [it]
    groups.append(cur)
    return [" ".join(t[3] for t in sorted(g, key=lambda t: t[1])) for g in groups]


_FIX = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8"})


def find_km(*result_sets):
    b = _km_best(*result_sets)
    return b[1] if b else None


def _km_best(*result_sets):
    """Odometer = the biggest 3-7 digit number on the display (largest text height). Returns (box, value)."""
    best = None
    for res in result_sets:
        for box, text, *_ in res or []:
            s = re.sub(r"[\s,]", "", text)
            s = re.sub(r"(?i)km$", "", s)
            if not re.fullmatch(r"[0-9OolI|SB]{3,7}", s) or sum(c.isdigit() for c in s) < 2:
                continue
            s = s.translate(_FIX)
            h = max(p[1] for p in box) - min(p[1] for p in box)
            key = (h, len(s))
            if best is None or key > best[0]:
                best = (key, int(s), box)
    return (best[2], best[1]) if best else None


# ---------- per-kind parsers ----------
def parse_cluster(res, digits_res=None):
    text = " ".join(_lines(res))
    return {"km": find_km(res, digits_res), "date": find_date(text), "time": find_time(text)}


def parse_geo(res, digits_res=None):
    lines = _lines(res)
    text = " ".join(lines)
    di = next((i for i, l in enumerate(lines) if find_date(l)), None)
    addr = []
    if di is not None:
        for l in lines[di + 1:]:
            if re.match(r"\s*(altitude|speed|index|lat|long)", l, re.I):
                break
            if re.search(r"[°º]", l) or re.match(r"\s*\d{1,3}\s*(NE|NW|SE|SW|N|S|E|W)\b", l) or len(l.strip()) < 3:
                continue
            addr.append(l.strip())
    if len(addr) > 4:
        addr = [", ".join(addr[:-3])] + addr[-3:]
    addr = [None] * (4 - len(addr)) + addr
    g = re.search(r"-?\d{1,3}\.\d{3,}\s*[,;]\s*-?\d{1,3}\.\d{3,}", text)
    return {"date": find_date(text), "time": find_time(text), "road": addr[0], "location": addr[1],
            "district": addr[2], "state": addr[3], "gps": g.group(0).replace(" ", "") if g else None}


def parse_fuel(res, digits_res=None):
    lines = _lines(res)
    text = "\n".join(lines)
    normalized = [re.sub(r"\s+", " ", line).strip() for line in lines]

    def labeled_value(labels):
        label = re.compile(labels, re.I)
        for i, line in enumerate(normalized):
            match = label.search(line)
            if not match:
                continue
            value_text = line[match.end():]
            number = re.search(r"(?:rs\.?|₹)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", value_text, re.I)
            if not number and i + 1 < len(normalized) and not re.search(
                    r"\b(?:date|time|rate|sale|volume|qty|fuel|bill|receipt|vehicle)\b", normalized[i + 1], re.I):
                number = re.search(r"(?:rs\.?|₹)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", normalized[i + 1], re.I)
            if number:
                return _num(number.group(1).replace(",", ""))
        return None

    receipt = None
    for labels in (
        r"\bbill\s*(?:no|number|#)\b",
        r"\b(?:receipt|voucher|invoice)\s*(?:no|number|#)\b",
        r"\b(?:txn|transaction)\s*(?:id|no|number|#)\b",
    ):
        for line in normalized:
            match = re.search(labels + r"\s*[:#\-]?\s*([A-Z0-9][A-Z0-9/\-]{2,})", line, re.I)
            if match and any(char.isdigit() for char in match.group(1)):
                receipt = match.group(1).rstrip("-/")
                break
        if receipt:
            break
    if not receipt:
        match = re.search(r"\b(?:bill|receipt|voucher|invoice)\s*(?:no|number|#)?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9/\-]{2,})",
                          text, re.I)
        if match and any(char.isdigit() for char in match.group(1)):
            receipt = match.group(1).rstrip("-/")

    rate = labeled_value(r"\brate\b")
    volume = labeled_value(r"\b(?:volume|qty|quantity|litres?|ltrs?)\b")
    amount = labeled_value(r"\b(?:sale|amount|amt|total|value)\b")
    if amount is None and rate and volume:
        amount = round(rate * volume, 2)
    prod = re.search(r"diesel|petrol|gasoline|hsd|xtra\s*premium|power\s*\d*", text, re.I)
    veh = re.search(r"\b([A-Z]{2})\s?(\d{1,2})\s?([A-Z]{1,3})\s?(\d{3,4})\b", text.upper())
    return {"date": find_date(text), "time": find_time(re.sub(r"\d+\.\d+", "", text)), "receipt_no": receipt,
            "product": prod.group(0).title() if prod else None, "rate": rate, "volume": volume,
            "amount": amount, "vehicle_no": "".join(veh.groups()) if veh else None}


PARSERS = {"cluster": parse_cluster, "geo": parse_geo, "fuel": parse_fuel}


def warmup():
    try:
        _get_reader()
        print("OCR reader ready")
    except Exception as e:
        print("OCR warmup failed:", repr(e))


def _load(image_bytes, maxside=1000):
    import io
    import numpy as np
    from PIL import Image
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    k = maxside / max(im.size)
    if k < 1:
        im = im.resize((int(im.width * k), int(im.height * k)))
    return np.array(im)


def _date_strip(arr, box):
    """The date/time line sits ~8x the odometer digit height above the odometer: crop it and enlarge 3x."""
    import numpy as np
    from PIL import Image
    xs, ys = [p[0] for p in box], [p[1] for p in box]
    h = max(ys) - min(ys)
    cx, top = (min(xs) + max(xs)) / 2, min(ys)
    x0, x1 = max(0, int(cx - 5 * h)), min(arr.shape[1], int(cx + 5 * h))
    y0, y1 = max(0, int(top - 11 * h)), max(1, int(top - 5 * h))
    if x1 - x0 < 10 or y1 - y0 < 5:
        return None
    im = Image.fromarray(arr[y0:y1, x0:x1])
    return np.array(im.resize((im.width * 3, im.height * 3)))


def extract(kind, image_bytes):
    try:
        r = _get_reader()
    except ImportError:
        return {"_error": "EasyOCR not installed. Run: py -m pip install -r requirements-ocr.txt"}
    try:
        arr = _load(image_bytes)                 # smaller image = much faster on CPU
        res = r.readtext(arr, detail=1)
        print("ocr lines:", _lines(res))
        digits = None
        if kind == "cluster" and find_km(res) is None:   # digits-only pass only when needed
            digits = r.readtext(arr, detail=1, allowlist="0123456789")
        out = PARSERS[kind](res, digits)
        if kind == "cluster" and (not out["date"] or not out["time"]):
            kb = _km_best(res, digits)
            strip = _date_strip(arr, kb[0]) if kb else None
            if strip is not None:
                sres = r.readtext(strip, detail=1, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-:/. ")
                st = " ".join(_lines(sres))
                print("ocr date strip:", st)
                out["date"] = out["date"] or find_date(st)
                out["time"] = out["time"] or find_time(st)
        print("ocr", kind, "->", out)
        if all(v in (None, "") for v in out.values()):
            return {"_error": "OCR found no values. Text seen: " + " | ".join(_lines(res))[:200]}
        return out
    except Exception as e:
        print("ocr failed:", repr(e))
        return {"_error": f"OCR {type(e).__name__}: {e}"[:300]}