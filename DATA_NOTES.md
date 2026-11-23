# Data notes & known limitations

Honest record of how this data is collected and where it can mislead — the same
discipline the China queue-history file used. Read this before quoting a number.

## Source
Sushiro's own SushiPass queue servers, the same data its apps show, for 5 markets:
Hong Kong, Thailand, Singapore, Indonesia, Malaysia. One request per market every
10 minutes (store list), one per store every 30 minutes (ticket call boards).
China, Japan, Taiwan and Korea run on different systems and are not included here.

## Metrics
- **waiting_groups** — parties in the walk-in queue. Primary demand signal.
- **max_ticket_called** — highest queue ticket a store has called that local day.
  Tickets reset each morning, so this approximates groups seated from the queue.
  This is a proxy, not a customer count: group size is unknown.
- **wait_min** — Sushiro's own estimate. Use with care (see below).

## Known limitations
- **Wait minutes are capped at 180** and are Sushiro's own estimate. Lead with
  ticket counts and waiting groups, not wait minutes.
- **Keep the zeros.** Averages run over OPEN readings and include zero-queue
  readings on purpose. Dropping zeros biases averages upward — the China file's
  pre-8-Jul gap did exactly this and faked a demand decline.
- **Short window.** Collection began 23 Nov 2026. There is no year-ago baseline,
  so this shows level and mix, not growth. New-vs-mature is a cross-section, not
  a ramp over time.
- **Scheduler gaps.** GitHub's timer can run late or skip; the always-on loop
  mitigates this but some 10-minute intervals may be uneven.
- **Ticket outliers.** Daily max tickets above 4000 are flagged and excluded from
  averages (China had a store hitting ~7400 from an odd number range).

## Store classification
- **tier** — prime (HK, SG, Bangkok) vs next-wave (ID, MY, Thai provinces),
  matching the pitch's market framework.
- **age_class** — new (opened within 365 days) vs mature, from the app's
  `commencement_date`. Unlike the China scrape, this feed gives real opening
  dates, so "new store" is a fact here, not an inference from first appearance.
