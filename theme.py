"""Light / dark mode for the "Welcome back" screen (the login screen is always light).

The choice lives in the browser (``localStorage["wb_theme"]``, the same key the workbench uses) and is
applied as ``data-wb-theme`` on the page's <html>. The screens' CSS reads the ``--wb-*`` variables below,
so flipping the attribute restyles them instantly without a Streamlit rerun (which would drop a half
typed email). The toggle is a small embedded component because Streamlit strips inline click handlers
from markdown.
"""

import streamlit.components.v1 as components

# Palette. Dark values match the workbench's dark theme (html/styles.html).
LIGHT_CSS = """
    html {
        --wb-scheme: light;
        --wb-bg: #F1EFE7;
        --wb-surface: #FFFFFF;
        --wb-text: #141210;
        --wb-text-dim: #5A564C;
        --wb-text-mute: #6B7280;
        --wb-text-faint: #8F8A7E;
        --wb-line: #141210;
        --wb-line-soft: #C9C5BB;
        --wb-card-border: rgb(20 19 19 / 20%);
        --wb-input-bg: #FFFFFF;
        --wb-input-border: #9CA3AF;
        --wb-title: #C51616;
        --wb-heading-green: #1B5A02;
        --wb-pill-future-bg: #EEF1F6;
        --wb-pill-future-fg: #9CA3AF;
        --wb-alert-bg: #FFF1F2;
        --wb-alert-border: #FDA4AF;
        --wb-alert-text: #9F1239;
        --wb-shadow: rgba(0, 0, 0, 0.08);
    }
"""

DARK_CSS = """
    html[data-wb-theme="dark"] {
        --wb-scheme: dark;
        --wb-bg: #0A0A0A;
        --wb-surface: #141414;
        --wb-text: #F1EFEA;
        --wb-text-dim: #A8A49C;
        --wb-text-mute: #A8A49C;
        --wb-text-faint: #8A867E;
        --wb-line: rgba(255, 255, 255, 0.28);
        --wb-line-soft: rgba(255, 255, 255, 0.2);
        --wb-card-border: rgba(255, 255, 255, 0.16);
        --wb-input-bg: #1A1A1A;
        --wb-input-border: rgba(255, 255, 255, 0.28);
        --wb-title: #FF5A4F;
        --wb-heading-green: #4ADE80;
        --wb-pill-future-bg: #1F1F1F;
        --wb-pill-future-fg: #6F6B64;
        --wb-alert-bg: rgba(225, 38, 28, 0.14);
        --wb-alert-border: rgba(253, 164, 175, 0.45);
        --wb-alert-text: #FDA4AF;
        --wb-shadow: rgba(0, 0, 0, 0.5);
    }
"""

THEME_CSS = LIGHT_CSS + DARK_CSS

_TOGGLE_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  html, body { margin: 0; background: transparent; overflow: hidden; }
  button { display: flex; align-items: center; gap: 10px; background: none; border: 0; cursor: pointer;
           padding: 8px 4px; font: 600 10.5px ui-monospace, "JetBrains Mono", Menlo, monospace;
           letter-spacing: .08em; color: #5A564C; }
  html[data-theme="dark"] button { color: #A8A49C; }
  .track { position: relative; width: 44px; height: 24px; border-radius: 20px; background: #DAD7CC;
           border: 1px solid rgba(20, 18, 14, .2); transition: .25s; }
  html[data-theme="dark"] .track { background: #262626; border-color: rgba(255, 255, 255, .16); }
  .thumb { position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%;
           background: #E1261C; transition: .25s cubic-bezier(.4, 0, .2, 1); box-shadow: 0 2px 6px rgba(0, 0, 0, .3); }
  html[data-theme="light"] .thumb { transform: translateX(20px); }
</style></head><body>
<button id="t" aria-label="Toggle dark / light mode"><span id="label">DARK</span><span class="track"><span class="thumb"></span></span></button>
<script>
  (function () {
    var KEY = "wb_theme", label = document.getElementById("label");
    function read() { try { return localStorage.getItem(KEY) === "dark" ? "dark" : "light"; } catch (e) { return "light"; } }
    function apply(t) {
      document.documentElement.setAttribute("data-theme", t);
      label.textContent = t === "dark" ? "LIGHT" : "DARK";   // the mode you switch TO
      try { window.parent.document.documentElement.setAttribute("data-wb-theme", t); } catch (e) {}
    }
    document.getElementById("t").onclick = function () {
      var next = read() === "dark" ? "light" : "dark";
      try { localStorage.setItem(KEY, next); } catch (e) {}
      apply(next);
    };
    apply(read());
  })();
</script></body></html>"""


def render_theme_toggle() -> None:
    """Embed the DARK/LIGHT switch. Also applies the saved theme to the page when it loads."""
    components.html(_TOGGLE_HTML, height=44)
