# Viewer README

## Scope
This folder contains the AI Scientist v3 web viewer backend (`app.py`), trajectory parser (`parse_trajectory.py`), and HTML templates (`templates/`).

## Run
```bash
python3 viewer/app.py --jobs-dir ./jobs --port 8501
```

## Requirements Ledger
- Use Harbor agentic trajectory data as primary source.
- Track newer jobs/ideas reliably in the dashboard and job detail pages.
- Prevent API key leakage in any rendered HTML/API payload.
- Keep PDF artifacts from auto-downloading; prefer inline preview and explicit open link.
- Show submissions in a dedicated area with per-version dossier.
- Render review/rebuttal with proper Markdown.
- Show the original matched idea input for each job in readable format.
- Improve viewer responsiveness for large job directories.
- Add job-level duration to the main job list when timing data is available.

## Change Log
### 2026-02-25
- Switched event parsing flow to prefer Harbor trajectory with fallback/backfill.
- Added secret masking across viewer APIs and UI-facing payloads.
- Added submissions dossier UX with version navigation and Markdown rendering.
- Added inline PDF preview flow with fallback link behavior.
- Added idea input matching/rendering per job.
- Improved dashboard and detail performance with server-side caching and lighter polling.
- Added `/api/jobs/{job_id}/meta` for lightweight detail-page metadata fetches.
- Added concise glossary text (`Job`, `Trajectory`, `Submission`) in the UI.
- Set `Submissions` as default tab and auto-preview selected submission PDF.
- Added dashboard `Duration` column based on job `started_at`/`finished_at` metadata.
- Expanded redaction unit coverage in `tests/test_viewer_secret_redaction.py`.

## Notes
- Duration is best-effort and depends on timestamp presence in `result.json`.
- Running jobs use elapsed time from `started_at` if available.
