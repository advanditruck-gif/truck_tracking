import base64, json, re
import anthropic
from datetime import datetime
from config import DATE_FMT, ENGINE, MODEL, PROMPTS, SCHEMAS
import ocr_extractor

VERSION = "tool-v7"
_client = None


def _get():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # needs ANTHROPIC_API_KEY
    return _client


def _clean(d):
    if isinstance(d.get("km"), str):
        digits = re.sub(r"[^\d]", "", d["km"])
        d["km"] = int(digits) if digits else None
    return d


def _format(d):
    """Internal ISO date / 24h time -> display format (20-Sep-2026, 8:00 PM)."""
    if "_error" in d:
        return d
    if d.get("date"):
        value = str(d["date"]).strip()
        for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%b-%y", "%d %b %Y"):
            try:
                d["date"] = datetime.strptime(value, fmt).strftime(DATE_FMT)
                break
            except ValueError:
                continue
    if d.get("time"):
        value = str(d["time"]).strip().upper()
        for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
            try:
                d["time"] = datetime.strptime(value, fmt).strftime("%I:%M %p").lstrip("0")
                break
            except ValueError:
                continue
    return d


def extract(kind, image_bytes):
    return _format(_extract(kind, image_bytes))


def _extract(kind, image_bytes):
    """Dispatch by ENGINE: claude | easyocr | auto (Claude, then EasyOCR as fallback)."""
    if ENGINE == "easyocr":
        return ocr_extractor.extract(kind, image_bytes)
    r = extract_claude(kind, image_bytes)
    if ENGINE == "auto" and "_error" in r:
        print("Claude failed, trying EasyOCR:", r["_error"])
        o = ocr_extractor.extract(kind, image_bytes)
        if "_error" not in o:
            return o
        return {"_error": "Claude: " + r["_error"] + " | OCR: " + o["_error"]}
    if ENGINE == "auto":
        missing = [key for key, value in r.items() if value in (None, "")]
        if missing:
            o = ocr_extractor.extract(kind, image_bytes)
            if "_error" not in o:
                for key in missing:
                    if o.get(key) not in (None, ""):
                        r[key] = o[key]
            else:
                print("EasyOCR could not fill missing fields:", o["_error"])
    return r


def extract_claude(kind, image_bytes):
    """Read an image with Claude vision using a forced tool call (fixed field names).
    On failure returns {"_error": "..."} so the page can show the reason."""
    try:
        tool = {"name": "record_reading", "description": "Record the values read from the image.",
                "input_schema": {"type": "object", "properties": SCHEMAS[kind],
                                 "required": list(SCHEMAS[kind])}}
        msg = _get().messages.create(
            model=MODEL, max_tokens=600,
            tools=[tool], tool_choice={"type": "tool", "name": "record_reading"},
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.b64encode(image_bytes).decode()}},
                {"type": "text", "text": PROMPTS[kind] + " Call record_reading. Use null only if a value is genuinely unreadable."}]}])
        for b in msg.content:
            if b.type == "tool_use":
                data = _clean(dict(b.input))
                print("extract", kind, "->", data)
                if all(v in (None, "") for v in data.values()):
                    return {"_error": "Image received but no values returned: " + json.dumps(data)}
                return data
        return {"_error": "No result from model: " + str([getattr(b, "text", b.type) for b in msg.content])[:200]}
    except Exception as e:
        print("extract failed:", repr(e))
        return {"_error": f"{type(e).__name__}: {e}"[:300]}