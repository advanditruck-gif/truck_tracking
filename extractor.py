import base64, json, os, re
from datetime import datetime
import urllib.request, urllib.error
import config
from config import DATE_FMT, ENGINE, MODEL, PROMPTS, SCHEMAS

VERSION = "gemini-first-v2"
_genai_client = None


def _get_api_key():
    return getattr(config, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")


def _clean(d):
    if not isinstance(d, dict):
        return {}

    # Check common aliases for km:
    if d.get("km") in (None, ""):
        for alias in ("odometer", "odo", "km_reading", "distance", "reading", "mileage", "total_km", "total"):
            if d.get(alias) not in (None, ""):
                d["km"] = d[alias]
                break

    if d.get("km") not in (None, ""):
        s = str(d["km"]).split(".")[0]
        digits = re.sub(r"[^\d]", "", s)
        d["km"] = int(digits) if digits else None

    # Check common aliases for date / time:
    if d.get("date") in (None, ""):
        for alias in ("display_date", "reading_date"):
            if d.get(alias) not in (None, ""):
                d["date"] = d[alias]
                break
    if d.get("time") in (None, ""):
        for alias in ("clock", "display_time", "reading_time"):
            if d.get(alias) not in (None, ""):
                d["time"] = d[alias]
                break

    for num_key in ("rate", "volume", "amount"):
        if isinstance(d.get(num_key), str):
            cleaned = re.sub(r"[^\d.]", "", d[num_key])
            try:
                d[num_key] = float(cleaned) if cleaned else None
            except ValueError:
                pass
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
    """Dispatch by ENGINE:
    - auto (default): Gemini first; if it fails or misses fields, EasyOCR fills the gaps.
    - gemini: Gemini only.
    - easyocr: EasyOCR only (offline).
    """
    has_ocr = getattr(config, "HAS_EASYOCR", False)

    if ENGINE == "gemini" or (not has_ocr and ENGINE != "easyocr"):
        return extract_gemini(kind, image_bytes)
    if ENGINE == "easyocr":
        import ocr_extractor
        return ocr_extractor.extract(kind, image_bytes)

    # "auto": Gemini first, then EasyOCR
    print(f"[{kind}] Reading with Gemini first...")
    g = extract_gemini(kind, image_bytes)

    if "_error" in g:
        print("Gemini failed, trying EasyOCR:", g["_error"])
        import ocr_extractor
        o = ocr_extractor.extract(kind, image_bytes)
        if "_error" not in o:
            return o
        return {"_error": "Gemini: " + g["_error"] + " | OCR: " + o["_error"]}

    # Gemini worked, but check for missing fields and let OCR fill them
    expected_keys = list(SCHEMAS.get(kind, {}).keys()) or list(g.keys())
    missing = [k for k in expected_keys if g.get(k) in (None, "")]
    if missing:
        print(f"Gemini missed fields {missing}, trying EasyOCR to fill...")
        import ocr_extractor
        o = ocr_extractor.extract(kind, image_bytes)
        if "_error" not in o:
            for k in missing:
                if o.get(k) not in (None, ""):
                    g[k] = o[k]
        else:
            print("EasyOCR could not fill missing fields:", o["_error"])

    return g


def _parse_model_json(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def _call_gemini_rest(model_name, api_key, prompt, image_bytes):
    """Fallback REST API call using standard library urllib."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64.b64encode(image_bytes).decode("ascii")
                    }
                },
                {"text": prompt}
            ]
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    return res["candidates"][0]["content"]["parts"][0]["text"]


def extract_gemini(kind, image_bytes):
    """Read an image with Gemini vision.
    Supports official google-genai, google-generativeai, and direct REST API.
    On failure returns {"_error": "..."} so the page can show the reason."""
    api_key = _get_api_key()
    if not api_key:
        return {"_error": "GEMINI_API_KEY is not set. Please add it to your .env file."}

    fields_desc = ", ".join(f'"{k}": {SCHEMAS[kind][k]["description"]}' for k in SCHEMAS[kind])
    prompt = (
        f"{PROMPTS[kind]}\n\n"
        f"Return a JSON object with EXACTLY the following keys:\n"
        f"{{{fields_desc}}}\n\n"
        f"Instructions:\n"
        f"- Output ONLY a valid JSON object matching the requested keys.\n"
        f"- Use null only if a value is genuinely not visible or unreadable.\n"
        f"- Do not include markdown code block formatting."
    )
    if kind == "cluster":
        prompt += (
            "\n\nImportant instructions for reading odometer (km):\n"
            "- Locate the vehicle cumulative odometer reading (total kilometers driven).\n"
            "- Look for the main 4-7 digit reading (e.g. 7148, 45210, 154200).\n"
            "- It may be labeled with 'ODO', 'km', 'TOTAL', or appear without an explicit label on the LCD screen or analog counter.\n"
            "- Always extract these digits as a clean integer for 'km'. Do not return null if any odometer digits are visible.\n"
        )

    models_to_try = [MODEL]
    for fallback_model in ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"):
        if fallback_model not in models_to_try:
            models_to_try.append(fallback_model)

    last_error = None
    for model_name in models_to_try:
        try:
            raw_text = None

            # 1. Try modern google-genai SDK
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        prompt,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                raw_text = response.text
            except ImportError:
                pass

            # 2. Try legacy google-generativeai SDK if google-genai is not installed
            if raw_text is None:
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=api_key)
                    g_model = genai.GenerativeModel(model_name)
                    response = g_model.generate_content(
                        [
                            {"mime_type": "image/jpeg", "data": image_bytes},
                            prompt,
                        ],
                        generation_config={"response_mime_type": "application/json"}
                    )
                    raw_text = response.text
                except ImportError:
                    pass

            # 3. If neither SDK installed, use standard library urllib REST API
            if raw_text is None:
                raw_text = _call_gemini_rest(model_name, api_key, prompt, image_bytes)

            data = _clean(_parse_model_json(raw_text))
            print("extract", kind, "using", model_name, "->", data)
            if all(v in (None, "") for v in data.values()):
                return {"_error": "Image received but no values returned: " + json.dumps(data)}
            return data

        except Exception as e:
            last_error = e
            err_msg = str(e)
            print(f"Gemini model {model_name} failed: {err_msg}")
            # model retired (404), quota hit (429) or overloaded (503): try the next model
            if any(c in err_msg for c in ("404", "429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE")) \
                    or "not found" in err_msg.lower():
                continue
            break

    return {"_error": f"{type(last_error).__name__}: {last_error}"[:300]}


# Alias for backward compatibility
extract_claude = extract_gemini