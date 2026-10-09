# Sony Music — M&A Catalog Valuation Workbench (Streamlit + PostgreSQL)

The application is a Streamlit shell (**`app.py`**) that assembles the `html/` partials
(styles, screens, `workbench_scripts.html`) into one page and serves it full-bleed inside the
page via `st.components.v1.html(...)`. It uses the PostgreSQL database configured by
`DATABASE_URL` for catalog and session data.

```
sony_ma_workbench_streamlit/
├── app.py              # Streamlit shell — builds the page from html/ and embeds it in an iframe
├── html/               # The workbench UI: styles, screens, and workbench_scripts.html
├── steps/welcome.py    # Login and "Welcome back" screens
├── requirements.txt    # pip deps (local run)
├── environment.yml     # conda deps
└── README.md
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The local `.env` file must define `DATABASE_URL`, `APP_SCHEMA`, and the
`extract_s` source schema settings.

## Sign-in

`APP_AUTH_MODE` (in `.env`) chooses how users prove who they are. See `.env.example`.

- **`oidc`** (default): your OpenID Connect provider (Azure AD / Okta / Google) through
  `st.login()`. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill it in.
- **`otp`**: a 6-digit code emailed to the user. Set `APP_AUTH_SECRET` and the `SMTP_*` settings.
  Optionally restrict access with `APP_ALLOWED_EMAILS` and/or `APP_ALLOWED_DOMAINS`; left empty, any email
  address that can receive the code may sign in. Codes
  expire after 10 minutes, allow 5 guesses and are stored hashed in `AUTH_OTP`. After sign-in a signed
  token is kept in a browser cookie for `APP_SESSION_HOURS` (default 720, i.e. 30 days), so the code is only asked for on a new device or after that.
- **`dev`**: the old "type any email" form, for local development only.
  **Never set this in a deployed environment.**

In `oidc` and `otp` the user's email comes from the verified identity, never from the URL or a typed value.

## Notes

- All figures are illustrative dummy data, generated for UI review only.
- The embedded iframe is rendered at a fixed height (900px) with its own
  scrollbar enabled, so nothing is clipped even on the longer screens. Adjust
  the `height=` argument in `app.py` if you want a taller or shorter initial viewport.
- To update the app itself, edit the partials in `html/` (most behaviour lives in
  `html/workbench_scripts.html`).
