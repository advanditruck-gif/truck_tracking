import base64, json, os, re
from datetime import datetime
import urllib.request, urllib.error
import config
from config import DATE_FMT, ENGINE, MODEL, PROMPTS, SCHEMAS

VERSION = "gemini-v1"
_genai_client = None


def _get_api_key():
    return getattr(config, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")


def _clean(d):
    if not isinstance(d, dict):
        return {}
    if isinstance(d.get("km"), str):
        digits = re.sub(r"[^\d]", "", d["km"])
        d["km"] = int(digits) if digits else None
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
    - auto (or ocr_first): Runs EasyOCR first, then uses Gemini if OCR fails or misses fields.
    - easyocr: Runs only EasyOCR (offline).
    - gemini: Runs only Gemini vision.
    """
    if ENGINE == "gemini":
        return extract_gemini(kind, image_bytes)
    if ENGINE == "easyocr":
        import ocr_extractor
        return ocr_extractor.extract(kind, image_bytes)

    # Default / "auto" / "ocr_first": EasyOCR first, then Gemini
    import ocr_extractor
    print(f"[{kind}] Reading with EasyOCR first...")
    o = ocr_extractor.extract(kind, image_bytes)

    if "_error" in o:
        print("EasyOCR failed, trying Gemini:", o["_error"])
        g = extract_gemini(kind, image_bytes)
        if "_error" not in g:
            return g
        return {"_error": "OCR: " + o["_error"] + " | Gemini: " + g["_error"]}

    # If EasyOCR succeeded, check for missing fields to fill with Gemini
    expected_keys = list(SCHEMAS.get(kind, {}).keys()) or list(o.keys())
    missing = [k for k in expected_keys if o.get(k) in (None, "")]
    if missing:
        print(f"EasyOCR missed fields {missing}, querying Gemini to fill...")
        g = extract_gemini(kind, image_bytes)
        if "_error" not in g:
            for k in missing:
                if g.get(k) not in (None, ""):
                    o[k] = g[k]
        else:
            print("Gemini could not fill missing fields:", g["_error"])

    return o


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
        f"- Do not include markdown code block formatting if possible."
    )

    models_to_try = [MODEL]
    for fallback_model in ("gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-2.5-flash", "gemini-1.5-flash"):
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
            # If it's a 404 / model not found error, loop to next fallback model
            if "404" in err_msg or "not found" in err_msg.lower():
                continue
            break

    return {"_error": f"{type(last_error).__name__}: {last_error}"[:300]}


# Alias for backward compatibility
extract_claude = extract_gemini