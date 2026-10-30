"""Private Supabase Storage operations used only by the Flask server."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import config


class StorageNotConfiguredError(RuntimeError):
    pass


def _settings():
    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
        raise StorageNotConfiguredError(
            "Image storage is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )
    return config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY


def _request(method, endpoint, body=None, content_type=None, cache_control=None):
    base_url, key = _settings()
    headers = {
        "apikey": key,
        "Authorization": "Bearer " + key,
    }
    data = body
    if content_type:
        headers["Content-Type"] = content_type
    if cache_control:
        headers["Cache-Control"] = cache_control
    elif body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = Request(base_url + endpoint, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=20) as response:
            response_body = response.read()
            return json.loads(response_body.decode("utf-8")) if response_body else {}
    except HTTPError as error:
        error_body = error.read(2048).decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase Storage returned HTTP {error.code}: {error_body}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise RuntimeError("Could not reach Supabase Storage.") from error


def upload_image(path, image_bytes, content_type):
    bucket = quote(config.SUPABASE_STORAGE_BUCKET, safe="")
    object_path = quote(path, safe="/")
    _request(
        "POST",
        f"/storage/v1/object/{bucket}/{object_path}",
        image_bytes,
        content_type=content_type,
        cache_control="max-age=86400",
    )


def delete_image(path):
    bucket = quote(config.SUPABASE_STORAGE_BUCKET, safe="")
    _request(
        "DELETE",
        f"/storage/v1/object/{bucket}",
        {"prefixes": [path]},
    )


def signed_image_url(path, expires_in=300):
    bucket = quote(config.SUPABASE_STORAGE_BUCKET, safe="")
    object_path = quote(path, safe="/")
    result = _request(
        "POST",
        f"/storage/v1/object/sign/{bucket}/{object_path}",
        {"expiresIn": expires_in},
    )
    signed_path = result.get("signedURL")
    if not signed_path:
        raise RuntimeError("Supabase Storage did not return a signed image URL.")
    if signed_path.startswith("http://") or signed_path.startswith("https://"):
        return signed_path
    base_url = config.SUPABASE_URL.rstrip("/")
    if signed_path.startswith("/storage/v1/"):
        return base_url + signed_path
    if signed_path.startswith("/object/"):
        return base_url + "/storage/v1" + signed_path
    if signed_path.startswith("object/"):
        return base_url + "/storage/v1/" + signed_path
    raise RuntimeError("Supabase Storage returned an invalid signed image path.")
