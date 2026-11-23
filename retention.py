"""Automatic data clearing (retention rules).

Rule 1 - FUEL BILLS (Petrol / Diesel)
    Everything recorded in a month is cleared after BILL_CLEAR_DAY (default 10th)
    of the NEXT month. Example: a November bill is cleared on 11 December.
    "Cleared" = the bill IMAGE is removed from Supabase Storage.
    The database record (receipt no, amount, litres, reason ...) is KEPT.

Rule 2 - LOCATION, ODOMETER, AND GENERATOR PHOTOS
    The image is deleted IMAGE_RETENTION_DAYS (default 7) days after capture.
    Only the photo is removed; the event data stays in the database.

NO database record is ever deleted by this module - only images.

Month / day boundaries use RETENTION_TZ (default Asia/Kolkata).
The "month" and capture time are taken from the event timestamp (`at` column),
not from the date printed on a bill.

Run it
    python retention.py --dry-run     # show what WOULD be removed
    python retention.py               # really remove
The app also runs this cleanup automatically every day at 2:00 a.m. in
RETENTION_TZ. The protected /api/cron/cleanup endpoint remains available for
manual or external runs.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone

import config
import db
import supabase_storage

# ---- Which event types belong to which rule (edit here) -------------------
BILL_TYPES = ("fuel",)
IMAGE_TYPES = ("location", "start_km", "stop_km", "generator_start", "generator_stop")


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
    """Moment a bill must be cleared: midnight after BILL_CLEAR_DAY next month."""
    local = _parse(recorded_at).astimezone(_tz())
    year, month = (local.year + 1, 1) if local.month == 12 else (local.year, local.month + 1)
    return datetime(year, month, config.BILL_CLEAR_DAY, tzinfo=_tz()) + timedelta(days=1)


def image_delete_time(recorded_at):
    """Moment an image uploaded at `recorded_at` must be deleted: upload time + N days."""
    return _parse(recorded_at) + timedelta(days=config.IMAGE_RETENTION_DAYS)


def _remove_image(ev, data, now):
    """Delete the image file, then keep the record: only image_path is removed from its data."""
    supabase_storage.delete_image(data["image_path"])   # if this fails, nothing changes; retried next run
    data.pop("image_path", None)
    data["image_deleted_at"] = now.isoformat()
    db.update_event_data(ev["id"], data)


def run_cleanup(dry_run=False, now=None):
    now = now or datetime.now(timezone.utc)
    summary = {
        "now": now.isoformat(), "dry_run": dry_run,
        "bill_images_deleted": [], "other_images_deleted": [], "errors": [],
    }

    # ---- Rule 1: bills -> delete only the IMAGE after the 10th of next month ----
    for ev in db.events_by_types(BILL_TYPES):
        data = ev["d"] or {}
        path = data.get("image_path")
        if not path:
            continue                                    # image already cleared
        try:
            if now < bill_clear_time(ev["at"]):
                continue
        except (ValueError, TypeError):
            continue                                    # unreadable timestamp: never guess
        try:
            if not dry_run:
                _remove_image(ev, data, now)
            summary["bill_images_deleted"].append({"id": ev["id"], "type": ev["t"], "at": ev["at"]})
        except Exception as error:
            summary["errors"].append({"id": ev["id"], "error": str(error)[:200]})

    # ---- Rule 2: location / odometer / generator photos -> delete after 7 days ----
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
                _remove_image(ev, data, now)
            summary["other_images_deleted"].append({"id": ev["id"], "type": ev["t"], "at": ev["at"]})
        except Exception as error:
            summary["errors"].append({"id": ev["id"], "error": str(error)[:200]})

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply the data-retention rules.")
    parser.add_argument("--dry-run", action="store_true", help="only report, do not delete")
    args = parser.parse_args()
    print(json.dumps(run_cleanup(dry_run=args.dry_run), indent=2))