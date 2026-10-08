"""Real-time progress for the catalog build (tables -> albums -> analytics).

The build runs inside one blocking Streamlit script run, and Streamlit streams element updates to
the browser while it runs. ``BuildProgress`` is told what the database work is actually doing
(``stage`` / ``advance`` / ``note``) and re-renders a progress card into a placeholder each time.
The percentage is the weighted share of completed work, never a timer.
"""

from __future__ import annotations

import html
import time

# (key, label, weight). Weights are rough relative costs and only shape the bar; they sum to 100.
STAGES = [
    ("prepare", "Preparing catalog tables", 3),
    ("match", "Matching release groups in Luminate", 14),
    ("details", "Loading release details", 14),
    ("albums", "Reading catalog albums", 3),
    ("an_ppd", "Loading PPD rates and assumptions", 3),
    # The heavy step: it joins the catalog's recordings to the monthly consumption table once.
    ("an_coverage", "Collecting the catalog's recordings and consumption", 30),
    ("an_monthly", "Reading monthly consumption", 5),
    ("an_cube", "Aggregating by territory and release year", 8),
    ("an_albums", "Attributing consumption to albums", 12),
    ("an_tracks", "Analysing new-release tracks", 8),
]
SPIN_SECONDS = 0.8          # keep in sync with .wb-progress__spin in app.py


class NullProgress:
    """Drop-in used when nobody is watching (tests, cached paths)."""

    def stage(self, key: str, detail: str = "") -> None: ...
    def advance(self, fraction: float, detail: str = "") -> None: ...
    def note(self, detail: str) -> None: ...
    def finish(self, failed: bool = False) -> None: ...


NULL_PROGRESS = NullProgress()


def _clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class BuildProgress:
    def __init__(self, slot, stages=STAGES, min_interval: float = 0.12):
        self._slot = slot
        self._stages = list(stages)
        self._index = {key: i for i, (key, _, _) in enumerate(self._stages)}
        self._total = float(sum(weight for _, _, weight in self._stages)) or 1.0
        self._min_interval = min_interval
        self._started = time.monotonic()
        self._current = -1          # index of the stage in progress, -1 before the first
        self._fraction = 0.0
        self._detail = ""
        self._last_render = 0.0
        self.percent = 0.0
        self._drawn = 0.0           # percent shown by the previous render: the bar animates from here
        self._failed = False

    # ── called by the database code ──────────────────────────────────────────
    def stage(self, key: str, detail: str = "") -> None:
        """A stage starts; every earlier stage is complete."""
        if key not in self._index:
            return
        self._current = max(self._current, self._index[key])
        self._fraction = 0.0
        self._detail = detail
        self._render(force=True)

    def advance(self, fraction: float, detail: str = "") -> None:
        """Progress within the current stage (0..1), e.g. batch 3 of 8."""
        self._fraction = min(1.0, max(0.0, fraction))
        if detail:
            self._detail = detail
        self._render()

    def note(self, detail: str) -> None:
        self._detail = detail
        self._render(force=True)

    def finish(self, failed: bool = False) -> None:
        """The build is over. ``failed`` keeps the bar where it stopped instead of claiming 100%."""
        self._failed = failed
        if not failed:
            self._current = len(self._stages)
            self._fraction = 0.0
        self._detail = "Stopped. The details are shown next." if failed else "Done"
        self._render(force=True)

    # ── rendering ────────────────────────────────────────────────────────────
    def _percent(self) -> float:
        done = sum(weight for _, _, weight in self._stages[: max(self._current, 0)])
        if 0 <= self._current < len(self._stages):
            done += self._stages[self._current][2] * self._fraction
        return min(100.0, done / self._total * 100.0)

    def _render(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_render < self._min_interval:
            return
        self._last_render = now
        self.percent = max(self.percent, self._percent())   # never move backwards
        try:
            self._slot.markdown(self.html(now - self._started), unsafe_allow_html=True)
            self._drawn = self.percent
        except Exception:
            pass  # progress display must never break the build

    def html(self, elapsed: float) -> str:
        pct = int(self.percent)
        eta = ""
        if self.percent >= 8 and not self._failed:
            eta = f" &nbsp;|&nbsp; Est. remaining: ~{_clock(elapsed * (100 - self.percent) / self.percent)}"
        # Every update replaces the card's DOM, so CSS state would restart. Hand the new element where
        # the old one left off: the bar animates from the previous percent, the spinner keeps its phase.
        spin_phase = f"-{elapsed % SPIN_SECONDS:.2f}s"
        rows = []
        for i, (_, label, _) in enumerate(self._stages):
            if i < self._current:
                state, icon = "done", "&#10003;"
            elif i == self._current:
                state = "failed" if self._failed else "active"
                icon = "&#9888;" if self._failed else f'<span class="wb-progress__spin" style="animation-delay:{spin_phase}"></span>'
            else:
                state, icon = "todo", "&#9675;"
            detail = ""
            if state in ("active", "failed") and self._detail:
                detail = f'<span class="wb-progress__detail">{html.escape(self._detail)}</span>'
            rows.append(f'<li class="wb-progress__step wb-progress__step--{state}"><span class="wb-progress__icon">{icon}</span>'
                        f'<span>{html.escape(label)}{detail}</span></li>')
        title = "Build stopped" if self._failed else "Building Catalog"
        done_cls = " wb-build-loader--done" if self._current >= len(self._stages) or self._failed else ""
        return f"""
        <div id="wb-navigation-loader" class="wb-build-loader{done_cls}">
          <div class="wb-progress__card">
            <div class="wb-progress__title" role="status">{title}</div>
            <div class="wb-progress__sub">Reading your selection from the Luminate tables and preparing the analytics.</div>
            <div class="wb-progress__bar" role="progressbar" aria-label="Catalog build progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{pct}">
              <div class="wb-progress__fill{' wb-progress__fill--failed' if self._failed else ''}" style="width:{self.percent:.1f}%;--from:{self._drawn:.1f}%"></div>
            </div>
            <div class="wb-progress__pct">{pct}%</div>
            <div class="wb-progress__meta">Elapsed: {_clock(elapsed)}{eta}</div>
            <ul class="wb-progress__steps">{''.join(rows)}</ul>
          </div>
        </div>"""
