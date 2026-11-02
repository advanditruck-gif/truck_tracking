"""Find and optionally repair stored JPEGs with EXIF rotation metadata."""
import argparse
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

import db
import supabase_storage
from image_utils import normalize_jpeg, rotate_jpeg


def _download_image(path):
    url = supabase_storage.signed_image_url(path, expires_in=300)
    request = Request(url, headers={"User-Agent": "AdVandi-TruckTracker/1.0"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def _backup_path(root, storage_path):
    relative = PurePosixPath(storage_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in ("", ".", "..") or "\\" in part for part in relative.parts)
    ):
        raise ValueError(f"Unsafe storage image path: {storage_path!r}")
    return root.joinpath(*relative.parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Back up and replace images found with non-upright EXIF orientation.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help="New or empty local directory to store original images before replacement.",
    )
    parser.add_argument(
        "--rotate-event",
        type=int,
        help="Manually rotate one image by event ID instead of scanning for EXIF orientation.",
    )
    parser.add_argument(
        "--rotation",
        choices=("clockwise", "counterclockwise", "180"),
        help="Direction to rotate the image selected by --rotate-event.",
    )
    args = parser.parse_args()
    if args.apply and args.rotate_event is not None:
        parser.error("--apply cannot be combined with --rotate-event.")
    if args.apply and not args.backup_dir:
        parser.error("--apply requires --backup-dir.")
    if args.rotate_event is not None:
        if args.apply:
            parser.error("--rotate-event cannot be combined with --apply.")
        if not args.rotation or not args.backup_dir:
            parser.error("--rotate-event requires --rotation and --backup-dir.")
    elif args.rotation:
        parser.error("--rotation can only be used with --rotate-event.")
    elif args.backup_dir and not args.apply:
        parser.error("--backup-dir requires --apply or --rotate-event.")
    if args.apply:
        args.backup_dir.mkdir(parents=True, exist_ok=True)

    if args.rotate_event is not None:
        event = next(
            (item for item in db.all_events() if item.get("id") == args.rotate_event),
            None,
        )
        storage_path = (event.get("d") or {}).get("image_path") if event else None
        if not storage_path:
            parser.error(f"Event {args.rotate_event} does not have a stored image.")
        original = _download_image(storage_path)
        corrected = rotate_jpeg(original, args.rotation)
        backup = _backup_path(args.backup_dir, storage_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        try:
            with backup.open("xb") as backup_file:
                backup_file.write(original)
        except FileExistsError:
            parser.error(f"Backup already exists; refusing to overwrite: {backup}")
        supabase_storage.upload_image(
            storage_path,
            corrected,
            "image/jpeg",
            upsert=True,
            cache_control="no-cache, must-revalidate",
        )
        print(
            f"Rotated event {args.rotate_event} {args.rotation}; "
            f"original backed up at {backup}."
        )
        return

    candidates = []
    scanned_paths = set()
    for event in db.all_events():
        storage_path = (event.get("d") or {}).get("image_path")
        if not storage_path or storage_path in scanned_paths:
            continue
        scanned_paths.add(storage_path)
        image_bytes = _download_image(storage_path)
        _, orientation = normalize_jpeg(image_bytes)
        if orientation in range(2, 9):
            candidates.append((event.get("id"), storage_path, image_bytes))

    print(f"Scanned {len(scanned_paths)} stored image(s).")
    if not candidates:
        print("No images with EXIF orientation requiring correction were found.")
        return

    action = "Will repair" if args.apply else "Would repair"
    print(f"{action} {len(candidates)} image(s):")
    for event_id, storage_path, original in candidates:
        print(f"  event {event_id}: {storage_path}")
        if not args.apply:
            continue

        backup = _backup_path(args.backup_dir, storage_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        with backup.open("xb") as backup_file:
            backup_file.write(original)
        upright, _ = normalize_jpeg(original)
        supabase_storage.upload_image(
            storage_path,
            upright,
            "image/jpeg",
            upsert=True,
        )
    if not args.apply:
        print("Dry run only. No stored images were changed.")
    else:
        print(f"Repaired {len(candidates)} image(s); originals are in {args.backup_dir}.")


if __name__ == "__main__":
    main()
