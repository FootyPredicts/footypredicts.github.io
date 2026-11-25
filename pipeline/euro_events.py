# -*- coding: utf-8 -*-
"""Who scored and who was booked in finished Champions League / Europa League matches (for the "How we did" page).
The domestic leagues already collect this; European matches live in data/history/, so it is saved there:
data/history/events_<league>.json = {fixture id: {"goals": [...], "cards": [...]}}.   python -m pipeline.euro_events"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from .config import DATA_DIR, current_season
from .fetch import FINISHED, _flat_events, api_get

EURO = ["champions-league", "europa-league"]


def run(days=120):
    key = os.environ.get("API_FOOTBALL_KEY", "")
    if not key:
        sys.exit("API_FOOTBALL_KEY is not set")
    hist = os.path.join(DATA_DIR, "history")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    for lg in EURO:
        path = os.path.join(hist, f"events_{lg}.json")
        events = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
        todo = []
        for name in sorted(os.listdir(hist)):
            if name.startswith(lg + "_"):
                for x in json.load(open(os.path.join(hist, name), encoding="utf-8")):
                    if x["status"] in FINISHED and x["date"] >= cutoff and str(x["id"]) not in events:
                        todo.append(x["id"])
        for k in range(0, len(todo), 20):
            data = api_get("fixtures", {"ids": "-".join(map(str, todo[k:k + 20]))}, key)
            for f in data.get("response", []):
                if f.get("events") is not None:
                    events[str(f["fixture"]["id"])] = _flat_events(f)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(events, fh, ensure_ascii=False)
        print(lg, "events saved:", len(events), "new lookups:", len(todo))


if __name__ == "__main__":
    run()
