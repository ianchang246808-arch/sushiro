"""Build dashboard files from data/*.csv -> dash/*.csv"""
import csv, glob, os, collections

def read(pattern):
    rows = []
    for f in sorted(glob.glob(pattern)):
        rows += list(csv.DictReader(open(f, encoding="utf-8")))
    return rows

def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None

snaps = read("data/snapshots_*.csv")
calls = read("data/calls_*.csv")
os.makedirs("dash", exist_ok=True)
for r in snaps:  # older rows lack ts_local
    if not r.get("ts_local"):
        off = {"TH": 7, "ID": 7}.get(r["market"], 8)
        h = int(r["ts_utc"][11:13]) + off
        d = r["ts_utc"][:10]
        r["ts_local"] = f"{d} {h%24:02d}:{r['ts_utc'][14:16]}" if h < 24 else f"{d} {h-24:02d}:{r['ts_utc'][14:16]}"

# 1. market time series
g = collections.defaultdict(list)
for r in snaps: g[(r["ts_utc"], r["market"])].append(r)
ts_rows = []
for (ts, m), rs in sorted(g.items()):
    op = [r for r in rs if r["store_status"] == "OPEN"]
    if not op: continue
    groups = sum(num(r["waiting_groups"]) or 0 for r in op)
    waits = [num(r["wait_min"]) or 0 for r in op]
    q = sum(1 for r in op if (num(r["waiting_groups"]) or 0) > 0)
    ts_rows.append({"ts_utc": ts, "market": m, "open_stores": len(op),
        "waiting_groups": int(groups), "groups_per_store": round(groups/len(op), 2),
        "avg_wait_min": round(sum(waits)/len(waits), 1), "stores_queuing": q,
        "pct_queuing": round(100*q/len(op), 1)})

# 2. latest store snapshot
last = max(r["ts_utc"] for r in snaps)
latest = []
for r in snaps:
    if r["ts_utc"] != last: continue
    latest.append({"store_key": f'{r["market"]}-{r["store_id"]}', "market": r["market"],
        "store": (r["name_en"] or "").strip() or r["name"], "area": r["area"],
        "status": r["store_status"], "wait_min": int(num(r["wait_min"]) or 0),
        "waiting_groups": int(num(r["waiting_groups"]) or 0),
        "opened": r["commencement_date"] or "", "as_of_local": r["ts_local"]})
latest.sort(key=lambda x: (-x["waiting_groups"], -x["wait_min"]))

# 3. hourly profile (local hour)
h = collections.defaultdict(list)
for r in snaps:
    if r["store_status"] != "OPEN": continue
    h[(r["market"], int(r["ts_local"][11:13]))].append(num(r["waiting_groups"]) or 0)
hourly = [{"market": m, "hour": hr, "groups_per_store": round(sum(v)/len(v), 2), "samples": len(v)}
          for (m, hr), v in sorted(h.items())]

# 4. groups served proxy: max called ticket per store per local day
names = {(r["market"], r["store_id"]): ((r["name_en"] or "").strip() or r["name"]) for r in snaps}
s = {}
for r in calls:
    v = num(r.get("max_called_number"))
    if v is None: continue
    k = (r["ts_local"][:10], r["market"], r["store_id"])
    s[k] = max(s.get(k, 0), v)
served = [{"date_local": d, "market": m, "store_key": f"{m}-{sid}", "store": names.get((m, sid), sid),
           "max_ticket_called": int(v)} for (d, m, sid), v in sorted(s.items())]

def write(name, rows, fields):
    with open(f"dash/{name}", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
write("market_ts.csv", ts_rows, list(ts_rows[0]))
write("stores_latest.csv", latest, list(latest[0]))
write("hourly.csv", hourly, list(hourly[0]))
write("served.csv", served, ["date_local","market","store_key","store","max_ticket_called"])
print(len(snaps), "snapshot rows;", len(ts_rows), "ts;", len(latest), "stores;", len(hourly), "hourly;", len(served), "served")
