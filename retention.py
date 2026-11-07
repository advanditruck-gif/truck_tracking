"""Automatic data clearing (retention rules).

Rule 1 - BILLS (fuel bills: Petrol / Diesel, and Other Expense bills)
    Everything recorded in a month is cleared on the BILL_CLEAR_DAY (default 10th)
    of the NEXT month.  Example: a bill uploaded in November is cleared on 10 December.
    "Cleared" = the bill image is removed from Supabase Storage AND the record is
    deleted from the database.

Rule 2 - OTHER IMAGES (Odometer / Cluster, Generator, Location photos)
    The image is deleted IMAGE_RETENTION_DAYS (default 7) days after upload.
    Example: uploaded 7 Nov -> deleted 14 Nov.
    Only the photo is removed; the text values (km, hours, address ...) stay in the
    database so reports keep working.

Month / day boundaries use RETENTION_TZ (default Asia/Kolkata).
The "month" and the "upload time" of a record are taken from its recorded time
(the `at` column), NOT from the date printed on the bill.

Run it
    python retention.py --dry-run     # show what WOULD be removed
    python retention.py               # really remove
or call  /api/cron/cleanup?key=YOUR_CRON_KEY  from a scheduler (see app.py).
It is safe to run as often as you like (hourly or daily is fine).
"""
import argparse
import json
from datetime import datetime, timedelta, timezone

import config
import db
import supabase_storage

# ---- Which event types belong to which rule (edit here) -------------------
BILL_TYPES = ("fuel", "other_expense")                              # Petrol, Diesel, Other Expense
IMAGE_TYPES = ("start_km", "stop_km", "generator_start", "generator_stop", "location")
# start_km / stop_km  = Odometer (cluster) photos
# generator_start/stop = Generator photos
# location            = Location photos


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(config.RETENTION_TZ)
    except Exception:                                   # tzdata missing (common on Windows)
        return timezone(timedelta(hours=5, minutes=30))  # IST


def _parse(text):
    t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def bill_clear_time(recorded_at):
    """Moment a bill recorded at `recorded_at` must be cleared: day N of the next month, 00:00."""
    local = _parse(recorded_at).astimezone(_tz())
    year, month = (local.year + 1, 1) if local.month == 12 else (local.year, local.month + 1)
    return datetime(year, month, config.BILL_CLEAR_DAY, 0, 0, tzinfo=_tz())


def image_delete_time(recorded_at):
    """Moment an image uploaded at `recorded_at` must be deleted: upload time + N days."""
    return _parse(recorded_at) + timedelta(days=config.IMAGE_RETENTION_DAYS)


def run_cleanup(dry_run=False, now=None):
    now = now or datetime.now(timezone.utc)
    summary = {
        "now": now.isoformat(), "dry_run": dry_run,
        "bills_deleted": [], "images_deleted": [], "errors": [],
    }

    # ---- Rule 1: bills -> delete image + record on the 10th of next month ----
    for ev in db.events_by_types(BILL_TYPES):
        try:
            if now < bill_clear_time(ev["at"]):
                continue
        except (ValueError, TypeError):
            continue                                    # unreadable timestamp: never guess
        path = (ev["d"] or {}).get("image_path")
        try:
            if not dry_run:
                if path:
                    supabase_storage.delete_image(path)  # if this fails, keep the row and retry next run
                db.delete_event(ev["id"])
            summary["bills_deleted"].append({"id": ev["id"], "type": ev["t"], "at": ev["at"]})
        except Exception as error:
            summary["errors"].append({"id": ev["id"], "error": str(error)[:200]})

    # ---- Rule 2: odo / generator / location images -> delete after 7 days ----
    for ev in db.events_by_types(IMAGE_TYPES):
        data = ev["d"] or {}
        path = data.get("image_path")
        if not path:
            continue
        try:
            if now < image_delete_time(ev["at"]):
                continue
        except (ValueError, TypeError):
            continue
        try:
            if not dry_run:
                supabase_storage.delete_image(path)
                data.pop("image_path", None)
                data["image_deleted_at"] = now.isoformat()
                db.update_event_data(ev["id"], data)
            summary["images_deleted"].append({"id": ev["id"], "type": ev["t"], "at": ev["at"]})
        except Exception as error:
            summary["errors"].append({"id": ev["id"], "error": str(error)[:200]})

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply the data-retention rules.")
    parser.add_argument("--dry-run", action="store_true", help="only report, do not delete")
    args = parser.parse_args()
    print(json.dumps(run_cleanup(dry_run=args.dry_run), indent=2))
