"""Sushiro queue tracker.

Every run: snapshot every store's wait status in 5 markets (storelist).
Every 3rd run (~15 min): also record the ticket numbers being called at each
store (groupqueues) - the daily rise in called numbers ~ groups seated.
"""
import csv, json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

MARKETS = {  # host, lat, lon, UTC offset (hours)
    "HK": ("sushipass.sushiro.com.hk", 22.3, 114.17, 8),
    "TH": ("sushipass.sushiro.co.th", 13.7, 100.5, 7),
    "SG": ("sushipass.sushiro.com.sg", 1.3, 103.8, 8),
    "ID": ("sushipass.sushiro.co.id", -6.2, 106.8, 7),
    "MY": ("sushipass.sushiro.com.my", 3.15, 101.7, 8),
    "TW": ("sushipass.sushiro.com.tw", 25.04, 121.5, 8),
}
SNAP_FIELDS = ["ts_utc", "ts_local", "market", "store_id", "name", "name_en",
               "area", "region", "store_status", "wait_min", "waiting_groups",
               "groups_table", "groups_counter", "net_ticket_status",
               "reservation_status", "commencement_date", "lat", "lon"]
CALL_FIELDS = ["ts_utc", "ts_local", "market", "store_id", "calling_mixed",
               "calling_table", "calling_counter", "calling_reservation",
               "max_called_number"]
HEADERS = {"User-Agent": "Mozilla/5.0 (research tracker)"}


def get_json(url, tries=2):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3)


def append(path, fields, rows):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            if f.readline().strip() != ",".join(fields):
                path = path.replace(".csv", "_v2.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerows(rows)


def nums(xs):
    out = []
    for x in xs or []:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            pass
    return out


def main(with_calls):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    day = (now + timedelta(hours=8)).strftime("%Y-%m-%d")  # file per HK day
    snaps, calls, log = [], [], []
    for mkt, (host, lat, lon, off) in MARKETS.items():
        local = (now + timedelta(hours=off)).strftime("%Y-%m-%d %H:%M")
        try:
            stores = get_json(f"https://{host}/api/2.0/info/storelist?latitude={lat}"
                              f"&longitude={lon}&numresults=200&region={mkt}")
        except Exception as e:
            log.append(f"{mkt}: FAILED {e}")
            continue
        for s in stores:
            snaps.append({
                "ts_utc": ts, "ts_local": local, "market": mkt,
                "store_id": s.get("id"), "name": s.get("name"),
                "name_en": s.get("nameEn"), "area": s.get("area"),
                "region": s.get("region"), "store_status": s.get("storeStatus"),
                "wait_min": s.get("wait"), "waiting_groups": s.get("waitingGroup"),
                "groups_table": s.get("waitingGroupTable"),
                "groups_counter": s.get("waitingGroupCounter"),
                "net_ticket_status": s.get("netTicketStatus"),
                "reservation_status": s.get("reservationStatus"),
                "commencement_date": s.get("commencementDate"),
                "lat": s.get("latitude"), "lon": s.get("longitude"),
            })
        n_calls = 0
        if with_calls:
            for s in stores:
                if s.get("storeStatus") != "OPEN":
                    continue
                try:
                    q = get_json(f"https://{host}/api/2.0/remote/groupqueues"
                                 f"?region={mkt}&storeid={s.get('id')}", tries=1)
                except Exception:
                    continue
                allnums = nums(q.get("mixedQueue")) + nums(q.get("boothQueue")) + \
                    nums(q.get("counterQueue"))
                calls.append({
                    "ts_utc": ts, "ts_local": local, "market": mkt,
                    "store_id": s.get("id"),
                    "calling_mixed": " ".join(q.get("mixedQueue") or []),
                    "calling_table": " ".join(q.get("boothQueue") or []),
                    "calling_counter": " ".join(q.get("counterQueue") or []),
                    "calling_reservation": " ".join(q.get("reservationQueue") or []),
                    "max_called_number": max(allnums) if allnums else "",
                })
                n_calls += 1
                time.sleep(0.4)
        log.append(f"{mkt}: {len(stores)} stores" + (f", {n_calls} call boards" if with_calls else ""))
        time.sleep(1)
    os.makedirs("data", exist_ok=True)
    append(f"data/snapshots_{day}.csv", SNAP_FIELDS, snaps)
    if calls:
        append(f"data/calls_{day}.csv", CALL_FIELDS, calls)
    print(ts, "|", "; ".join(log))


if __name__ == "__main__":
    main(with_calls="--calls" in sys.argv)
