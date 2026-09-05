# itu-kontenjan

Two notification bots that run on GitHub Actions and push alerts to Telegram.

| Bot | What it watches | Cadence |
|---|---|---|
| **İTÜ course quota tracker** | Seat availability for a watchlist of CRNs at Istanbul Technical University | every 5 min |
| **GE Aerospace internship tracker** | New internship / co-op postings on GE Aerospace's Workday board | every 30 min |

No server required — GitHub Actions runs both on a schedule and commits the state files back to the repo, so the bots keep working while the laptop is off.

## How it works

Both bots share the same four-part shape:

1. **Fetch** — the İTÜ bot reads `lessons.psv` from [itu-helper/data](https://github.com/itu-helper/data) (refreshed every 5 minutes, no scraping needed); the GE bot POSTs to the public Workday jobs endpoint.
2. **Diff** — the new snapshot is compared against a committed `*_state.json`.
3. **Notify** — only real changes produce a Telegram message. The first run records the baseline silently instead of spamming.
4. **Schedule** — GitHub Actions cron; state is pushed back with `[skip ci]` so a state commit never retriggers the workflow.

The quota bot reports three distinct events, not just "a seat opened":

- free seats went `0` → positive — **a seat opened**
- free seats increased while already positive — **more seats**
- total quota was raised even though free seats stayed at `0` — **quota increased** (the department added capacity; worth knowing even if it filled instantly)

## Files

```
itu_kontenjan_bot.py     quota tracker
ge_intern_bot.py         internship tracker
kontenjan_state.json     last seen quota state (written by Actions)
ge_intern_state.json     last seen posting list (written by Actions)
.github/workflows/       kontenjan.yml (*/5), ge_intern.yml (*/30)
```

## Configuration

Edit `TAKIP_CRN` in `itu_kontenjan_bot.py` to set the CRNs you want to watch. Set `KONTENJAN_ARTISI_DA_BILDIR = False` if you only care about actually free seats.

Telegram credentials come from repository secrets, `ITU_BOT_TOKEN` and `ITU_CHAT_ID`, and are never committed.

## Running locally

```bash
export ITU_BOT_TOKEN=...  ITU_CHAT_ID=...
python itu_kontenjan_bot.py --test     # verify the Telegram connection
python itu_kontenjan_bot.py --status   # print current state, send nothing
python itu_kontenjan_bot.py --once     # one check cycle (what Actions runs)
python itu_kontenjan_bot.py            # continuous loop, 300 s interval
```

The GE bot accepts the same three flags.

## Adapting it to another job board

The four-part shape above is deliberately portable: only step 1 is platform-specific. Identify the applicant tracking system behind a careers page (Greenhouse, Lever, Ashby, Workday), find the request that returns the listings in the browser's network tab, and swap it into the fetch step — the diff, notify and schedule layers stay as they are.
