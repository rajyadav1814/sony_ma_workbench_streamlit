# Sony Music — M&A Catalog Valuation Workbench (Streamlit + PostgreSQL)

The actual application — all 8 screens, dark/light theme, custom SVG charts,
and the Excel export — is a single self-contained file, **`workbench.html`**
(pure HTML/CSS/JS, no frameworks, no Streamlit, no build step). It works on
its own if you just double-click it.

**`app.py`** is a thin Streamlit shell whose only job is to serve that file
full-bleed inside the page via `st.components.v1.html(...)`. It uses the
PostgreSQL database configured by `DATABASE_URL` for catalog and session data.

```
sony_ma_workbench_streamlit/
├── app.py              # Streamlit shell — embeds workbench.html in an iframe
├── workbench.html       # The real app: all 8 screens, self-contained
├── requirements.txt      # pip deps (local run)
├── environment.yml       # conda deps
└── README.md
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The local `.env` file must define `DATABASE_URL`, `APP_SCHEMA`, and the
`extract_s` source schema settings.

## Notes

- All figures are illustrative dummy data, generated for UI review only.
- The embedded iframe is rendered at a fixed height (2400px) with its own
  scrollbar enabled, so nothing is clipped even on the longer screens
  (Metadata Review, New Release Forecasting). Adjust the `height=` argument
  in `app.py` if you want a taller or shorter initial viewport.
- To update the app itself, edit `workbench.html` directly — it's a normal
  static file, no Python changes needed.

---

## Changelog — fixes & feature parity pass

The following changes were made to fix a blocking bug and bring this build
closer to feature parity with the Next.js port of this app, without altering
the working architecture (Streamlit shell + `html/` partials rendered in an
iframe, PostgreSQL-backed session persistence).

### 🔴 Critical fix
- **`catalog_builder.py` — `pull_monthly_detail()` had a truncated SQL
  string** (cut off mid-query), which caused a Python `SyntaxError` on import
  and prevented the app from starting at all. Completed the query (added the
  missing `FROM MONTHLY_MR_SUMMARY` join, `PRODUCT_CATALOG` left join,
  `WHERE`, and `GROUP BY` clauses).

### ✅ Missing features added
1. **Logout button** — added the user's email + a Logout button to the header
   (`html/body_open.html`, `html/workbench_scripts.html: logoutUser()`), wired to a
   `wb_logout` query param handled in `app.py` that clears the Streamlit
   session without marking the in-progress catalogue as completed (so it's
   still resumable next login).
2. **Multi-session resume** — the resume ("Welcome back") screen now lists
   *all* of a user's in-progress catalogues (not just the most recent one),
   each with its own **Continue / Restart / Remove** actions, plus a
   **Start new valuation** action. Added `get_open_sessions()` to
   `session_manager.py` (the existing single-session `get_open_session()` is
   untouched) and rewrote `render_resume_screen()` in `steps/welcome.py` to
   loop over the list.
3. **Cross-device session restore** — step data (search term/mode/resolved
   entities) is now also restored from the PostgreSQL-backed session
   (`window.__STEP_DATA__`, injected by `app.py`) in addition to
   `localStorage`, so resuming on a different browser/device works.
4. **"Select All" checkbox in Step 3** (Metadata to Include) — bulk
   include/exclude for albums, matching the sticky-header table with a
   header checkbox (`html/workbench_scripts.html: toggleSelectAllAlbums()`).
5. **Cancel button on the catalog-building pipeline screen** — lets users
   abort a running or failed pipeline and return to Step 2
   (`html/workbench_scripts.html: cancelPipeline()`).
6. **"Back To Welcome" button** in the step tabbar — lets users jump back to
   the resume/session-picker screen at any point, via a new `wb_action=
   move_resume` query param handled in `app.py`.
7. **Step label text fix** — `config.py`'s `STEP_LABELS` had corrupted
   entries ("Metadata to Big USD", "Revenue A", "Composite score"); restored
   to the correct labels ("Metadata to include", "Revenue & PPD", "Corporate
   export").

All changes are additive/surgical — the interactive logic is consolidated in
`html/workbench_scripts.html`, which is loaded by `app.py`. Every Python file
was verified to compile, and the consolidated script was verified with
`node --check`.
