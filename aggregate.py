"""Build dashboard/analysis summaries from data/*.csv.

v2 — informed by the China queue-history file:
- Keep zero and closed readings explicit. Per-store averages run over OPEN
  readings but INCLUDE zero-queue readings, so we don't repeat the China file's
  missing-zero bias (dropping zeros made its average wait look like it fell).
- Tag each reading weekday/weekend from the local date.
- Classify every store two ways, using the app's own commencement_date:
    * tier:  prime vs next-wave  (HK, SG, Bangkok = prime; ID, MY, Thai
      provinces = next-wave — matching the pitch's market framework)
    * age:   new (opened <=365 days ago) vs mature
- Flag implausible ticket outliers instead of letting them distort averages.

Outputs (data/ -> dash/):
  market_ts.csv      per-market time series (+ day_type)
  stores_latest.csv  every store at the latest snapshot (+ tier, age_class)
  hourly.csv         avg groups/store by market and local hour
  served.csv         highest ticket called per store per day (+ outlier flag)
  store_class.csv    one row per store: tier, age, period averages      [NEW]
  class_summary.csv  prime/next-wave and new/mature roll-ups            [NEW]
"""
import csv, glob, os, collections
from datetime import date, datetime, timezone

TODAY = datetime.now(timezone.utc).date()
PRIME_MARKETS = {"HK", "SG"}
NEXTWAVE_MARKETS = {"ID", "MY"}
BANGKOK = "กรุงเทพมหานคร"  # Bangkok Metropolis
TICKET_OUTLIER = 4000  # a daily max ticket above this is flagged, not averaged


def read(pattern):
    rows = []
    for f in sorted(glob.glob(pattern)):
        rows += list(csv.DictReader(open(f, encoding="utf-8")))
    return rows


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def ensure_local(r):
    if r.get("ts_local"):
        return r["ts_local"]
    off = {"TH": 7, "ID": 7}.get(r["market"], 8)
    h = int(r["ts_utc"][11:13]) + off
    return f"{r['ts_utc'][:10]} {h % 24:02d}:{r['ts_utc'][14:16]}"


def day_type(local_date):
    try:
        return "weekend" if date.fromisoformat(local_date).weekday() >= 5 else "weekday"
    except Exception:
        return "unknown"


def tier(market, area):
    if market in PRIME_MARKETS:
        return "prime"
    if market in NEXTWAVE_MARKETS:
        return "next-wave"
    if market == "TH":
        return "prime" if (area or "").strip() == BANGKOK else "next-wave"
    return "unknown"


def age_class(opened):
    if not opened:
        return "unknown"
    try:
        d = date.fromisoformat(opened)
    except Exception:
        return "unknown"
    days = (TODAY - d).days
    if days < 0:
        return "unknown"
    return "new" if days <= 365 else "mature"


def days_open(opened):
    try:
        return (TODAY - date.fromisoformat(opened)).days
    except Exception:
        return ""


def write(name, rows, fields):
    os.makedirs("dash", exist_ok=True)
    with open(f"dash/{name}", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    snaps = read("data/snapshots_*.csv")
    calls = read("data/calls_*.csv")
    for r in snaps:
        r["ts_local"] = ensure_local(r)

    # 1. market time series (+ day_type) --------------------------------------
    g = collections.defaultdict(list)
    for r in snaps:
        g[(r["ts_utc"], r["market"])].append(r)
    ts_rows = []
    for (ts, m), rs in sorted(g.items()):
        op = [r for r in rs if r["store_status"] == "OPEN"]
        if not op:
            continue
        groups = sum(num(r["waiting_groups"]) or 0 for r in op)   # zeros included
        waits = [num(r["wait_min"]) or 0 for r in op]
        q = sum(1 for r in op if (num(r["waiting_groups"]) or 0) > 0)
        ts_rows.append({
            "ts_utc": ts, "market": m, "day_type": day_type(op[0]["ts_local"][:10]),
            "open_stores": len(op), "waiting_groups": int(groups),
            "groups_per_store": round(groups / len(op), 2),
            "avg_wait_min": round(sum(waits) / len(waits), 1),
            "stores_queuing": q, "pct_queuing": round(100 * q / len(op), 1)})

    # 2. served: highest ticket per store per local day (+ outlier flag) -------
    names = {(r["market"], r["store_id"]):
             ((r.get("name_en") or "").strip() or r["name"]) for r in snaps}
    smax = {}
    for r in calls:
        v = num(r.get("max_called_number"))
        if v is None:
            continue
        k = (r["ts_local"][:10], r["market"], r["store_id"])
        smax[k] = max(smax.get(k, 0), v)
    served = []
    for (d, m, sid), v in sorted(smax.items()):
        served.append({"date_local": d, "day_type": day_type(d), "market": m,
                       "store_key": f"{m}-{sid}", "store": names.get((m, sid), sid),
                       "max_ticket_called": int(v),
                       "outlier": "yes" if v > TICKET_OUTLIER else ""})

    # 3. per-store aggregation over OPEN readings (zeros included) -------------
    store = {}
    for r in snaps:
        key = f"{r['market']}-{r['store_id']}"
        s = store.setdefault(key, {
            "market": r["market"], "name": (r.get("name_en") or "").strip() or r["name"],
            "area": r.get("area", ""), "opened": r.get("commencement_date") or "",
            "open_readings": 0, "sum_groups": 0.0,
            "latest_ts": "", "latest_groups": 0, "latest_wait": 0, "latest_status": ""})
        if (r.get("name_en") or "").strip():
            s["name"] = r["name_en"].strip()
        if r["store_status"] == "OPEN":
            s["open_readings"] += 1
            s["sum_groups"] += num(r["waiting_groups"]) or 0
        if r["ts_utc"] > s["latest_ts"]:
            s["latest_ts"] = r["ts_utc"]
            s["latest_groups"] = int(num(r["waiting_groups"]) or 0)
            s["latest_wait"] = int(num(r["wait_min"]) or 0)
            s["latest_status"] = r["store_status"]
    # per-store average daily ticket (non-outlier)
    sd = collections.defaultdict(list)
    for (d, m, sid), v in smax.items():
        if v <= TICKET_OUTLIER:
            sd[f"{m}-{sid}"].append(v)
    for key, s in store.items():
        s["avg_groups"] = (s["sum_groups"] / s["open_readings"]) if s["open_readings"] else None
        s["tier"] = tier(s["market"], s["area"])
        s["age_class"] = age_class(s["opened"])
        tix = sd.get(key, [])
        s["avg_ticket"] = (sum(tix) / len(tix)) if tix else None

    store_rows = []
    for key, s in sorted(store.items(), key=lambda kv: -(kv[1]["avg_groups"] or 0)):
        store_rows.append({
            "store_key": key, "market": s["market"], "store": s["name"],
            "area": s["area"], "tier": s["tier"], "age_class": s["age_class"],
            "opened": s["opened"], "days_open": days_open(s["opened"]),
            "avg_groups_per_store": round(s["avg_groups"], 2) if s["avg_groups"] is not None else "",
            "latest_groups": s["latest_groups"], "latest_wait": s["latest_wait"],
            "avg_daily_tickets": round(s["avg_ticket"], 0) if s["avg_ticket"] is not None else ""})

    # 4. classification roll-ups ----------------------------------------------
    def roll(dim, keyfn):
        agg = collections.defaultdict(lambda: {"stores": 0, "sg": 0.0, "ng": 0, "st": 0.0, "nt": 0})
        for s in store.values():
            a = agg[keyfn(s)]
            a["stores"] += 1
            if s["avg_groups"] is not None:
                a["sg"] += s["avg_groups"]; a["ng"] += 1
            if s["avg_ticket"] is not None:
                a["st"] += s["avg_ticket"]; a["nt"] += 1
        out = []
        for cls, a in agg.items():
            out.append({"dimension": dim, "class": cls, "stores": a["stores"],
                        "avg_groups_per_store": round(a["sg"] / a["ng"], 2) if a["ng"] else "",
                        "avg_daily_tickets": round(a["st"] / a["nt"], 0) if a["nt"] else ""})
        return out
    summary = (roll("tier", lambda s: s["tier"])
               + roll("age", lambda s: s["age_class"])
               + roll("tier_x_age", lambda s: f"{s['tier']} / {s['age_class']}"))

    # 5. latest-snapshot store table (+ tier, age_class) ----------------------
    last = max(r["ts_utc"] for r in snaps)
    latest = []
    for r in snaps:
        if r["ts_utc"] != last:
            continue
        latest.append({
            "store_key": f"{r['market']}-{r['store_id']}", "market": r["market"],
            "store": (r.get("name_en") or "").strip() or r["name"], "area": r.get("area", ""),
            "tier": tier(r["market"], r.get("area", "")), "age_class": age_class(r.get("commencement_date") or ""),
            "status": r["store_status"], "wait_min": int(num(r["wait_min"]) or 0),
            "waiting_groups": int(num(r["waiting_groups"]) or 0),
            "opened": r.get("commencement_date") or "", "as_of_local": r["ts_local"]})
    latest.sort(key=lambda x: (-x["waiting_groups"], -x["wait_min"]))

    # 6. hourly profile -------------------------------------------------------
    h = collections.defaultdict(list)
    for r in snaps:
        if r["store_status"] != "OPEN":
            continue
        h[(r["market"], int(r["ts_local"][11:13]))].append(num(r["waiting_groups"]) or 0)
    hourly = [{"market": m, "hour": hr, "groups_per_store": round(sum(v) / len(v), 2), "samples": len(v)}
              for (m, hr), v in sorted(h.items())]

    write("market_ts.csv", ts_rows, list(ts_rows[0]))
    write("stores_latest.csv", latest, list(latest[0]))
    write("hourly.csv", hourly, list(hourly[0]))
    write("served.csv", served, ["date_local", "day_type", "market", "store_key", "store", "max_ticket_called", "outlier"])
    write("store_class.csv", store_rows, list(store_rows[0]))
    write("class_summary.csv", summary, ["dimension", "class", "stores", "avg_groups_per_store", "avg_daily_tickets"])

    print(f"{len(snaps)} snapshot rows, {len(store)} stores")
    print("class_summary:")
    for row in summary:
        print(" ", row["dimension"], "|", row["class"], "| stores", row["stores"],
              "| groups/store", row["avg_groups_per_store"], "| daily tickets", row["avg_daily_tickets"])


if __name__ == "__main__":
    main()
