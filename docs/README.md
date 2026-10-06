# docs/

- `assets/dashboard.gif` — recorded from the live dashboard with
  `scripts/record_demo.py` (Playwright + ffmpeg) against a `docker-compose up`
  stack seeded via `python -m src.generator.generate_leads --count 600
  --spread-days 13`, with a handful of leads forced through the dead-letter
  queue first (temporarily setting `CRM_FAILURE_RATE=1.0` on the worker) so
  the DLQ warning banner and "recent errors / dead-letters" panel are visible.
