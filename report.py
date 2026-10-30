"""Builds the daily run report (start/end odometer, fuel totals, collections,
areas covered) from the events already stored by db.py.

Each "run" is one start_km -> stop_km cycle (run_id is set by the browser
when the driver taps Start). A run can still be open (no stop_km yet).
"""
from collections import defaultdict


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _fuel_label(d):
    return str(d.get("fuel_for") or d.get("product") or "").lower()


def _is_petrol(d):
    return "petrol" in _fuel_label(d)


def _is_diesel(d):
    return "diesel" in _fuel_label(d)


def _place(d):
    """Return the locality resolved for a captured location photo."""
    return str(d.get("location") or "").strip()


def build_reports(events):
    """events: the list returned by db.all_events() -> [{"run","t","at","d"}, ...]
    Returns one summary dict per run, most recently started run first."""
    runs, order = defaultdict(list), []
    for e in events:
        rid = e.get("run")
        if rid not in runs:
            order.append(rid)
        runs[rid].append(e)

    reports = []
    for rid in order:
        evs = runs[rid]
        start = next((e for e in evs if e["t"] == "start_km"), None)
        stop = next((e for e in evs if e["t"] == "stop_km"), None)
        fuels = [e for e in evs if e["t"] == "fuel"]
        visits = [e for e in evs if e["t"] == "visit"]
        locations = [e for e in evs if e["t"] == "location"]

        start_km = _num(start["d"].get("km")) if start else None
        end_km = _num(stop["d"].get("km")) if stop else None

        petrol_amount = sum(_num(e["d"].get("amount")) for e in fuels if _is_petrol(e["d"]))
        diesel_amount = sum(_num(e["d"].get("amount")) for e in fuels if _is_diesel(e["d"]))
        petrol_volume = sum(_num(e["d"].get("volume")) for e in fuels if _is_petrol(e["d"]))
        diesel_volume = sum(_num(e["d"].get("volume")) for e in fuels if _is_diesel(e["d"]))
        collected = sum(_num(e["d"].get("amount_collected")) for e in visits)

        # Areas covered come only from captured location photos, not manually
        # entered business-visit areas.
        areas = []
        for e in locations:
            place = _place(e["d"])
            if place and place.casefold() not in (a.casefold() for a in areas):
                areas.append(place)

        images = [
            {
                "event_id": e["id"],
                "date": (e.get("at") or "")[:10],
                "at": e.get("at"),
                "type": e["t"],
                "fuel_type": _fuel_label(e["d"]) if e["t"] == "fuel" else None,
            }
            for e in evs
            if e.get("id") is not None and e.get("d", {}).get("image_path")
        ]

        reports.append({
            "run": rid,
            "date": (start and start["d"].get("date")) or (start and start["at"][:10]),
            "start_km": start_km,
            "start_time": (start and start["d"].get("time")) or (start and start["at"]),
            "end_km": end_km,
            "end_time": (stop and stop["d"].get("time")) or (stop and stop["at"]),
            "distance_km": (end_km - start_km) if (start_km is not None and end_km is not None) else None,
            "petrol_amount": petrol_amount,
            "diesel_amount": diesel_amount,
            "petrol_volume": petrol_volume,
            "diesel_volume": diesel_volume,
            "fuel_count": len(fuels),
            "collected_amount": collected,
            "balance_amount": collected - (petrol_amount + diesel_amount),
            "areas_covered": areas,
            "visit_count": len(visits),
            "is_open": stop is None,
            "images": images,
        })

    reports.reverse()  # most recently started run first
    return reports