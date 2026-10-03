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
    ("match", "Matching release groups in Luminate", 17),
    ("details", "Loading release details", 17),
    ("albums", "Reading catalog albums", 3),
    ("an_ppd", "Loading PPD rates and assumptions", 4),
    ("an_coverage", "Resolving catalog recordings", 10),
    ("an_monthly", "Reading monthly consumption", 10),
    ("an_cube", "Aggregating by territory and release year", 14),
    ("an_albums", "Attributing consumption to albums", 14),
    ("an_tracks", "Analysing new-release tracks", 8),
]


class NullProgress:
    """Drop-in used when nobody is watching (tests, cached paths)."""

    def stage(self, key: str, detail: str = "") -> None: ...
    def advance(self, fraction: float, detail: str = "") -> None: ...
    def note(self, detail: str) -> None: ...
    def finish(self) -> None: ...


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

    def finish(self) -> None:
        self._current = len(self._stages)
        self._fraction = 0.0
        self._detail = "Done"
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
        except Exception:
            pass  # progress display must never break the build

    def html(self, elapsed: float) -> str:
        pct = int(self.percent)
        eta = ""
        if self.percent >= 8:
            eta = f" &nbsp;|&nbsp; Est. remaining: ~{_clock(elapsed * (100 - self.percent) / self.percent)}"
        rows = []
        for i, (_, label, _) in enumerate(self._stages):
            if i < self._current:
                state, icon = "done", "&#10003;"
            elif i == self._current:
                state, icon = "active", '<span class="wb-progress__spin"></span>'
            else:
                state, icon = "todo", "&#9675;"
            detail = ""
            if state == "active" and self._detail:
                detail = f'<span class="wb-progress__detail">{html.escape(self._detail)}</span>'
            rows.append(f'<li class="wb-progress__step wb-progress__step--{state}"><span class="wb-progress__icon">{icon}</span>'
                        f'<span>{html.escape(label)}{detail}</span></li>')
        return f"""
        <div id="wb-navigation-loader" class="wb-build-loader" role="status" aria-live="polite">
          <div class="wb-progress__card">
            <div class="wb-progress__title">Building Catalog</div>
            <div class="wb-progress__sub">Reading your selection from the Luminate tables and preparing the analytics.</div>
            <div class="wb-progress__bar"><div class="wb-progress__fill" style="width:{self.percent:.1f}%"></div></div>
            <div class="wb-progress__pct">{pct}%</div>
            <div class="wb-progress__meta">Elapsed: {_clock(elapsed)}{eta}</div>
            <ul class="wb-progress__steps">{''.join(rows)}</ul>
          </div>
        </div>"""
