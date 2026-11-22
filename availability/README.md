# Availability

Part-sourcing state for the Smash BOM (kept out of `dist/`, which gets wiped).

- `decisions.csv` — one row per problem line: original, replacement, status (APPLIED / ACCEPTED / KEEP / OPEN), date, library status, note.
- `bom_accepted.csv` — the chosen parts with stock, lead time, price and origin at Mouser / Farnell / Digi-Key.
- `bom_alternates.csv` — second sources. Sourcing only: alternates get no footprints.
- `rounds/` — each round's upload list (`problem_parts_roundN_upload.csv`) and merged comparison.
- `responses/rN/` — the raw supplier answers per round (`mouser.xlsx`, `farnell.xls`, `digikey.xlsx`).
- `full_bom/` — the earlier full dev-board / tower BOM uploads and Mouser answers.
- `tools/` — `compare4.py` (merge one round), `boms.py` (rebuild the two BOM lists from all responses; edit its ACC/ALT tables when a decision changes), `octo.py` + `exists.py` (Octopart lookups through the Zyte proxy; key from the repo's `.env`, never printed).

Rules: tower parts must be orderable (stocked, ideally at 2 of Mouser/Farnell/Digi-Key; lead time < 20 weeks if not stocked); dev-board-only parts may be thinly stocked; no Chinese origin (Malaysia OK); MEMS-only clocks; MCU/MPU alternates keep secure boot + crypto.

Rebuild the lists: `python3 availability/tools/boms.py`
Merge a round: `python3 availability/tools/compare4.py availability/responses/rN availability/rounds/problem_parts_roundN_upload.csv`
