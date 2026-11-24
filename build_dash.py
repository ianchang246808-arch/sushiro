"""Build the three files the dashboard artifact reads, from data/*.csv.

Run from the repo root:  python3 build_dash.py
Writes dash/upload/market_ts.csv, served.csv and ov_stores.csv.

- market_ts.csv : straight from aggregate.py.
- served.csv    : aggregate.py's served.csv minus each market's in-progress
                  local day (a partial day would understate tickets).
- ov_stores.csv : aggregate.py's store_class.csv joined to dash/ov_meta.csv
                  (English area name, province/district for the maps, local
                  name, coordinates). Stores missing from ov_meta.csv get
                  their raw area, no admin1, and coordinates from the latest
                  snapshot, so new stores still appear.
"""
import csv, glob, os, subprocess
from datetime import datetime, timedelta, timezone

UTC_OFFSET = {"HK": 8, "SG": 8, "MY": 8, "TW": 8, "TH": 7, "ID": 7}
OUT = "dash/upload"


def rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write(path, data, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(data)


def main():
    subprocess.run(["python3", "aggregate.py"], check=True)
    os.makedirs(OUT, exist_ok=True)
    now = datetime.now(timezone.utc)

    # 1. market time series, unchanged
    ts = rows("dash/market_ts.csv")
    write(f"{OUT}/market_ts.csv", ts, list(ts[0].keys()))

    # 2. served: completed local days only
    served = rows("dash/served.csv")
    keep = []
    for r in served:
        today_local = (now + timedelta(hours=UTC_OFFSET.get(r["market"], 8))).date().isoformat()
        if r["date_local"] < today_local:
            keep.append(r)
    write(f"{OUT}/served.csv", keep, list(served[0].keys()))

    # 3. store list with map fields
    meta = {r["store_key"]: r for r in rows("dash/ov_meta.csv")}
    latest = {}
    for f in sorted(glob.glob("data/snapshots_*.csv"))[-2:]:
        for r in rows(f):
            latest[f'{r["market"]}-{r["store_id"]}'] = r
    out = []
    for r in rows("dash/store_class.csv"):
        k = r["store_key"]
        m = meta.get(k, {})
        snap = latest.get(k, {})
        out.append({
            "store_key": k,
            "market": r["market"],
            "store": m.get("store") or r["store"],
            "name_local": m.get("name_local") or snap.get("name", r["store"]),
            "area": m.get("area") or r["area"],
            "tier": r["tier"],
            "age_class": r["age_class"],
            "opened": r["opened"],
            "lat": m.get("lat") or snap.get("lat", ""),
            "lon": m.get("lon") or snap.get("lon", ""),
            "avg_groups_per_store": r["avg_groups_per_store"],
            "avg_daily_tickets": r["avg_daily_tickets"],
            "admin1": m.get("admin1", ""),
        })
    fields = ["store_key", "market", "store", "name_local", "area", "tier", "age_class",
              "opened", "lat", "lon", "avg_groups_per_store", "avg_daily_tickets", "admin1"]
    write(f"{OUT}/ov_stores.csv", out, fields)
    missing = [k for k in (r["store_key"] for r in out) if k not in meta]
    print(f"market_ts {len(ts)} rows; served {len(keep)} rows (of {len(served)}); "
          f"stores {len(out)} ({len(missing)} without map metadata: {missing})")


if __name__ == "__main__":
    main()
