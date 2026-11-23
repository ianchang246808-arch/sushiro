"""Sushiro queue tracker: snapshot every store's wait status in 5 markets."""
import csv, json, os, time, urllib.request
from datetime import datetime, timezone

MARKETS = {
    "HK": ("sushipass.sushiro.com.hk", 22.3, 114.17),
    "TH": ("sushipass.sushiro.co.th", 13.7, 100.5),
    "SG": ("sushipass.sushiro.com.sg", 1.3, 103.8),
    "ID": ("sushipass.sushiro.co.id", -6.2, 106.8),
    "MY": ("sushipass.sushiro.com.my", 3.15, 101.7),
}
FIELDS = ["ts_utc", "market", "store_id", "name", "name_en", "area", "region",
          "store_status", "wait_min", "waiting_groups", "groups_table",
          "groups_counter", "net_ticket_status", "reservation_status",
          "commencement_date", "lat", "lon"]
HEADERS = {"User-Agent": "Mozilla/5.0 (research tracker; 1 request per market per 15 min)"}

def fetch(host, lat, lon, region):
    url = (f"https://{host}/api/2.0/info/storelist?latitude={lat}"
           f"&longitude={lon}&numresults=200&region={region}")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = os.path.join("data", f"snapshots_{ts[:10]}.csv")
    new = not os.path.exists(path)
    rows, log = [], []
    for mkt, (host, lat, lon) in MARKETS.items():
        try:
            stores = fetch(host, lat, lon, mkt)
            for s in stores:
                rows.append({
                    "ts_utc": ts, "market": mkt, "store_id": s.get("id"),
                    "name": s.get("name"), "name_en": s.get("nameEn"),
                    "area": s.get("area"), "region": s.get("region"),
                    "store_status": s.get("storeStatus"), "wait_min": s.get("wait"),
                    "waiting_groups": s.get("waitingGroup"),
                    "groups_table": s.get("waitingGroupTable"),
                    "groups_counter": s.get("waitingGroupCounter"),
                    "net_ticket_status": s.get("netTicketStatus"),
                    "reservation_status": s.get("reservationStatus"),
                    "commencement_date": s.get("commencementDate"),
                    "lat": s.get("latitude"), "lon": s.get("longitude"),
                })
            log.append(f"{mkt}: {len(stores)} stores")
        except Exception as e:
            log.append(f"{mkt}: FAILED {e}")
        time.sleep(2)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerows(rows)
    print(ts, "|", "; ".join(log))

if __name__ == "__main__":
    main()
