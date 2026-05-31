"""
YonaCan - Interactive log graph (zoom, pan, home) with decimated drawing.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional, Tuple

import tkinter as tk
from tkinter import ttk

from config import COLORS


def format_time_axis(ts: float) -> str:
    """Format Unix timestamp for axis label."""
    try:
        return datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return f"{ts:.1f}"


def format_time_range(t0: float, t1: float) -> str:
    try:
        a = datetime.fromtimestamp(t0).strftime("%Y-%m-%d %H:%M:%S")
        b = datetime.fromtimestamp(t1).strftime("%H:%M:%S")
        return f"{a} — {b}"
    except (OSError, OverflowError, ValueError):
        return f"{t0:.2f} — {t1:.2f}"


def decimate_points(
    points: List[Tuple[float, float]], max_points: int
) -> List[Tuple[float, float]]:
    """Reduce points for drawing while keeping shape (min/max buckets)."""
    n = len(points)
    if n <= max_points or max_points < 4:
        return points
    bucket = max(1, n // max_points)
    out: List[Tuple[float, float]] = [points[0]]
    i = 0
    while i < n:
        chunk = points[i : i + bucket]
        if not chunk:
            break
        if len(chunk) == 1:
            out.append(chunk[0])
        else:
            t_lo, v_lo = chunk[0]
            t_hi, v_hi = chunk[0]
            v_min = v_max = chunk[0][1]
            for t, v in chunk:
                if t < t_lo:
                    t_lo, v_lo = t, v
                if t > t_hi:
                    t_hi, v_hi = t, v
                v_min = min(v_min, v)
                v_max = max(v_max, v)
            if v_min != v_max:
                out.append((t_lo, v_min))
                out.append((t_hi, v_max))
            else:
                out.append((t_hi, v_hi))
        i += bucket
    if points[-1] != out[-1]:
        out.append(points[-1])
    return out


@dataclass
class TimeSeries:
    """One plotted line: (unix_time, value) pairs."""
    label: str
    color: str
    points: List[Tuple[float, float]] = field(default_factory=list)
    visible: bool = True
    y_auto: bool = True
    y_min: float = 0.0
    y_max: float = 255.0


class LogGraphView:
    """Canvas-backed time-series plot with pan/zoom and decimation."""

    MARGIN_LEFT = 58
    MARGIN_RIGHT = 12
    MARGIN_TOP = 14
    MARGIN_BOTTOM = 28

    def __init__(
        self,
        canvas: tk.Canvas,
        on_view_change: Optional[Callable[[str], None]] = None,
        max_draw_points: int = 2500,
        y_fixed_0_255: bool = False,
        hover_enabled: bool = True,
        value_as_int: bool = False,
    ):
        self.canvas = canvas
        self.on_view_change = on_view_change
        self.max_draw_points = max_draw_points
        self.y_fixed_0_255 = y_fixed_0_255
        self.hover_enabled = hover_enabled
        self.value_as_int = value_as_int
        self.plot_mode: str = "line"  # "line" or "scatter"
        self.series: List[TimeSeries] = []
        self.view_t0: Optional[float] = None
        self.view_t1: Optional[float] = None
        self.view_y0: Optional[float] = None
        self.view_y1: Optional[float] = None
        self._data_t0: Optional[float] = None
        self._data_t1: Optional[float] = None
        self._pan_anchor: Optional[Tuple[int, int, float, float]] = None
        self._draw_cache: List[Tuple[TimeSeries, List[Tuple[float, float]]]] = []
        self._hover_ids: List[int] = []
        self._bind_events()

    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self._on_pan_start)
        self.canvas.bind("<B1-Motion>", self._on_pan_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_pan_end)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Configure>", self._on_resize)
        if self.hover_enabled:
            self.canvas.bind("<Motion>", self._on_motion)
            self.canvas.bind("<Leave>", self._on_leave)

    def clear_series(self):
        self.series.clear()

    def set_series(self, series: List[TimeSeries]):
        self.series = series
        self.home()

    def copy_state_from(self, other: "LogGraphView"):
        """Clone series and viewport from another view."""
        self.series = [
            TimeSeries(
                label=s.label,
                color=s.color,
                points=list(s.points),
                visible=s.visible,
                y_auto=s.y_auto,
                y_min=s.y_min,
                y_max=s.y_max,
            )
            for s in other.series
        ]
        self.view_t0 = other.view_t0
        self.view_t1 = other.view_t1
        self.view_y0 = other.view_y0
        self.view_y1 = other.view_y1
        self.plot_mode = other.plot_mode
        self._data_t0 = other._data_t0
        self._data_t1 = other._data_t1
        self.redraw()

    def set_plot_mode(self, mode: str):
        if mode not in ("line", "scatter"):
            mode = "line"
        self.plot_mode = mode
        self.redraw()

    def _compute_data_bounds(self):
        t_vals: List[float] = []
        for s in self.series:
            if not s.visible or len(s.points) < 1:
                continue
            t_vals.extend(t for t, _ in s.points)
        if not t_vals:
            self._data_t0 = self._data_t1 = None
            return
        self._data_t0 = min(t_vals)
        self._data_t1 = max(t_vals)
        if self._data_t1 <= self._data_t0:
            self._data_t1 = self._data_t0 + 1.0

    def home(self):
        self._compute_data_bounds()
        if self._data_t0 is None:
            self.view_t0 = self.view_t1 = None
            self.redraw()
            return
        self.view_t0 = self._data_t0
        self.view_t1 = self._data_t1
        self._auto_y()
        self.redraw()

    def set_y_fixed_0_255(self, enabled: bool):
        """Fix Y axis to integer 0–255 (byte view); off = auto Y from data."""
        self.y_fixed_0_255 = enabled
        for s in self.series:
            s.y_auto = not enabled
            if enabled:
                s.y_min, s.y_max = 0.0, 255.0
        if enabled:
            self.view_y0, self.view_y1 = 0.0, 255.0
        else:
            self._auto_y()
        self.redraw()

    def _auto_y(self):
        if self.y_fixed_0_255:
            self.view_y0, self.view_y1 = 0.0, 255.0
            return
        y_vals: List[float] = []
        for s in self.series:
            if not s.visible:
                continue
            if s.y_auto:
                y_vals.extend(v for _, v in s.points)
            else:
                y_vals.extend([s.y_min, s.y_max])
        if y_vals:
            pad = (max(y_vals) - min(y_vals)) * 0.08 or 1.0
            self.view_y0 = min(y_vals) - pad
            self.view_y1 = max(y_vals) + pad
            if self.view_y1 <= self.view_y0:
                self.view_y1 = self.view_y0 + 1.0
        else:
            self.view_y0, self.view_y1 = 0.0, 255.0

    def zoom_time(self, factor: float, center_t: Optional[float] = None):
        if self.view_t0 is None or self.view_t1 is None:
            return
        span = self.view_t1 - self.view_t0
        if span <= 0:
            return
        ct = center_t if center_t is not None else (self.view_t0 + self.view_t1) / 2
        new_span = span / factor
        new_span = max(new_span, span * 0.02, 0.001)
        self.view_t0 = ct - new_span / 2
        self.view_t1 = ct + new_span / 2
        self._clamp_time_view()
        self.redraw()

    def _clamp_time_view(self):
        if self._data_t0 is None:
            return
        span = self.view_t1 - self.view_t0
        if self.view_t0 < self._data_t0:
            self.view_t0 = self._data_t0
            self.view_t1 = self.view_t0 + span
        if self.view_t1 > self._data_t1:
            self.view_t1 = self._data_t1
            self.view_t0 = self.view_t1 - span

    def _notify(self):
        if self.on_view_change and self.view_t0 is not None and self.view_t1 is not None:
            self.on_view_change(format_time_range(self.view_t0, self.view_t1))

    def _format_value(self, v: float) -> str:
        if self.value_as_int:
            return str(int(round(v)))
        return f"{v:.4g}"

    def _plot_rect(self) -> Tuple[int, int, int, int]:
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        ml = self.MARGIN_LEFT
        mr = self.MARGIN_RIGHT
        mt = self.MARGIN_TOP
        mb = self.MARGIN_BOTTOM
        return ml, mt, max(1, w - ml - mr), max(1, h - mt - mb)

    def _xy_to_tv(self, x: float, y: float) -> Tuple[Optional[float], Optional[float]]:
        if self.view_t0 is None or self.view_t1 is None:
            return None, None
        ml, mt, gw, gh = self._plot_rect()
        y0 = self.view_y0 if self.view_y0 is not None else 0.0
        y1 = self.view_y1 if self.view_y1 is not None else 255.0
        if y1 <= y0:
            y1 = y0 + 1.0
        t0, t1 = self.view_t0, self.view_t1
        if t1 <= t0:
            t1 = t0 + 0.001
        frac_x = max(0.0, min(1.0, (x - ml) / gw))
        frac_y = max(0.0, min(1.0, (y - mt) / gh))
        t = t0 + frac_x * (t1 - t0)
        v = y1 - frac_y * (y1 - y0)
        return t, v

    def _tv_to_xy(self, t: float, v: float) -> Tuple[float, float]:
        ml, mt, gw, gh = self._plot_rect()
        y0 = self.view_y0 if self.view_y0 is not None else 0.0
        y1 = self.view_y1 if self.view_y1 is not None else 255.0
        t0, t1 = self.view_t0 or t, self.view_t1 or t + 1
        if t1 <= t0:
            t1 = t0 + 0.001
        if y1 <= y0:
            y1 = y0 + 1.0
        x = ml + ((t - t0) / (t1 - t0)) * gw
        y = mt + gh - ((v - y0) / (y1 - y0)) * gh
        return x, y

    def redraw(self):
        c = self.canvas
        c.delete("all")
        self._hover_ids.clear()
        self._draw_cache.clear()
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 40 or h < 40:
            return
        ml, mt, gw, gh = self._plot_rect()
        if gw <= 0 or gh <= 0:
            return

        if self.view_t0 is None or self.view_t1 is None:
            c.create_text(
                w // 2, h // 2,
                text="Select a PGN to load data",
                fill=COLORS["fg_secondary"],
                font=("Segoe UI", 10),
            )
            return

        t0, t1 = self.view_t0, self.view_t1
        if t1 <= t0:
            t1 = t0 + 0.001
        if self.y_fixed_0_255:
            y0, y1 = 0.0, 255.0
        else:
            y0 = self.view_y0 if self.view_y0 is not None else 0.0
            y1 = self.view_y1 if self.view_y1 is not None else 255.0
        if y1 <= y0:
            y1 = y0 + 1.0

        self._draw_grid(c, ml, mt, gw, gh, y0, y1)
        c.create_text(
            ml + gw // 2, h - 6,
            text=format_time_range(t0, t1),
            fill=COLORS["fg_secondary"],
            font=("Consolas", 8),
        )
        ylab = "Byte value" if self.y_fixed_0_255 else "Value"
        c.create_text(
            ml - 4, mt + gh // 2,
            text=ylab,
            fill=COLORS["fg_secondary"],
            font=("Consolas", 8),
            angle=90,
        )

        scatter = self.plot_mode == "scatter"
        min_pts = 1 if scatter else 2
        for s in self.series:
            if not s.visible or len(s.points) < min_pts:
                continue
            visible_pts = [(t, v) for t, v in s.points if t0 <= t <= t1]
            if len(visible_pts) < min_pts:
                continue
            draw_pts = decimate_points(visible_pts, self.max_draw_points)
            self._draw_cache.append((s, draw_pts))
            if scatter:
                r = 2.5
                for t, v in draw_pts:
                    x, py = self._tv_to_xy(t, v)
                    c.create_oval(
                        x - r, py - r, x + r, py + r,
                        fill=s.color, outline=s.color,
                    )
            else:
                coords: List[float] = []
                for t, v in draw_pts:
                    x, py = self._tv_to_xy(t, v)
                    coords.extend([x, py])
                if len(coords) >= 4:
                    c.create_line(coords, fill=s.color, width=2, smooth=False)

        c.create_rectangle(ml, mt, ml + gw, mt + gh, outline=COLORS["fg_secondary"])
        self._notify()

    def _draw_grid(self, c, ml, mt, gw, gh, y0, y1):
        if self.y_fixed_0_255:
            ticks = [0, 64, 128, 192, 255]
            for yv in ticks:
                if y1 <= y0:
                    break
                ly = mt + gh - ((yv - y0) / (y1 - y0)) * gh
                c.create_line(ml, ly, ml + gw, ly, fill=COLORS["bg_light"], dash=(2, 4))
                c.create_text(
                    ml - 5, ly, text=str(yv),
                    fill=COLORS["fg_secondary"], font=("Consolas", 8), anchor=tk.E,
                )
        else:
            for i in range(5):
                ly = mt + (i / 4) * gh
                c.create_line(ml, ly, ml + gw, ly, fill=COLORS["bg_light"], dash=(2, 4))
                yv = y1 - (i / 4) * (y1 - y0)
                label = (
                    str(int(round(yv))) if self.value_as_int
                    else self._format_value(yv)
                )
                c.create_text(
                    ml - 5, ly, text=label,
                    fill=COLORS["fg_secondary"], font=("Consolas", 8), anchor=tk.E,
                )
        for i in range(6):
            lx = ml + (i / 5) * gw
            c.create_line(lx, mt, lx, mt + gh, fill=COLORS["bg_light"], dash=(2, 4))
            t = self.view_t0 + (i / 5) * (self.view_t1 - self.view_t0)
            c.create_text(
                lx, mt + gh + 10, text=format_time_axis(t),
                fill=COLORS["fg_secondary"], font=("Consolas", 7), anchor=tk.N,
            )

    def _time_at_pixel(self, x: int) -> Optional[float]:
        t, _ = self._xy_to_tv(float(x), self.MARGIN_TOP + 1)
        return t

    def _find_nearest_point(
        self, x: int, y: int, max_px: float = 18.0
    ) -> Optional[Tuple[TimeSeries, float, float, float, float]]:
        """Return series, t, v, px, py for nearest drawn point."""
        best = None
        best_d2 = max_px * max_px
        for s, pts in self._draw_cache:
            for t, v in pts:
                px, py = self._tv_to_xy(t, v)
                d2 = (px - x) ** 2 + (py - y) ** 2
                if d2 < best_d2:
                    best_d2 = d2
                    best = (s, t, v, px, py)
        return best

    def _clear_hover(self):
        c = self.canvas
        for iid in self._hover_ids:
            try:
                c.delete(iid)
            except tk.TclError:
                pass
        self._hover_ids.clear()

    def _on_motion(self, event):
        if self._pan_anchor is not None or self.view_t0 is None:
            return
        ml, mt, gw, gh = self._plot_rect()
        if not (ml <= event.x <= ml + gw and mt <= event.y <= mt + gh):
            self._clear_hover()
            return
        hit = self._find_nearest_point(event.x, event.y)
        self._clear_hover()
        if hit is None:
            return
        s, t, v, px, py = hit
        c = self.canvas
        r = 4
        self._hover_ids.append(
            c.create_oval(px - r, py - r, px + r, py + r,
                          outline=s.color, width=2, fill=""))
        tip = f"{s.label}: {self._format_value(v)}  @  {format_time_axis(t)}"
        try:
            t_full = datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
            tip = f"{s.label}: {self._format_value(v)}  @  {t_full}"
        except (OSError, OverflowError, ValueError):
            pass
        tx = min(event.x + 12, c.winfo_width() - 8)
        ty = max(event.y - 24, mt + 4)
        self._hover_ids.append(
            c.create_rectangle(tx - 2, ty - 2, tx + 180, ty + 14,
                               fill=COLORS["bg_light"], outline=s.color))
        self._hover_ids.append(
            c.create_text(tx, ty, text=tip, anchor=tk.NW,
                          fill=COLORS["fg_primary"], font=("Consolas", 9)))

    def _on_leave(self, event):
        self._clear_hover()

    def _on_wheel(self, event):
        if self.view_t0 is None:
            return
        factor = 1.2 if event.delta > 0 else 1 / 1.2
        self.zoom_time(factor, self._time_at_pixel(event.x))

    def _on_pan_start(self, event):
        if self.view_t0 is None:
            return
        self._pan_anchor = (event.x, event.y, self.view_t0, self.view_t1)

    def _on_pan_move(self, event):
        if self._pan_anchor is None:
            return
        self._clear_hover()
        _, _, t0, t1 = self._pan_anchor
        ml, _, gw, _ = self._plot_rect()
        if gw <= 0:
            return
        dx = event.x - self._pan_anchor[0]
        span = t1 - t0
        dt = -dx / gw * span
        self.view_t0 = t0 + dt
        self.view_t1 = t1 + dt
        self._clamp_time_view()
        self.redraw()

    def _on_pan_end(self, event):
        self._pan_anchor = None

    def _on_resize(self, event):
        if event.widget == self.canvas:
            self.redraw()


def attach_graph_toolbar(
    parent: tk.Widget,
    graph: LogGraphView,
    on_popout: Optional[Callable[[], None]] = None,
    max_points_var: Optional[tk.StringVar] = None,
    on_y_0_255: Optional[Callable[[], None]] = None,
    on_plot_mode_toggle: Optional[Callable[[], None]] = None,
    plot_mode_label: Optional[tk.StringVar] = None,
) -> tk.Frame:
    """Build Home / Zoom / Pop-out toolbar; return the bar frame."""
    bar = ttk.Frame(parent, style="Medium.TFrame")
    bar.pack(fill=tk.X, pady=(0, 4))

    ttk.Button(bar, text="Home", width=6,
               command=graph.home).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Button(bar, text="Zoom +", width=7,
               command=lambda: graph.zoom_time(1.4)).pack(side=tk.LEFT, padx=2)
    ttk.Button(bar, text="Zoom −", width=7,
               command=lambda: graph.zoom_time(1 / 1.4)).pack(side=tk.LEFT, padx=2)
    if on_popout is not None:
        ttk.Button(bar, text="Pop out", width=8,
                   command=on_popout).pack(side=tk.LEFT, padx=(8, 4))

    if on_y_0_255 is not None:
        ttk.Button(bar, text="Y 0–255", width=8,
                   command=on_y_0_255).pack(side=tk.LEFT, padx=2)

    if on_plot_mode_toggle is not None:
        lbl = plot_mode_label
        if lbl is None:
            lbl = tk.StringVar(value="Line")
        ttk.Button(
            bar, textvariable=lbl, width=9,
            command=on_plot_mode_toggle,
        ).pack(side=tk.LEFT, padx=2)

    if max_points_var is not None:
        ttk.Label(bar, text="Max pts:", style="Medium.TLabel").pack(side=tk.LEFT, padx=(8, 2))
        combo = ttk.Combobox(
            bar, textvariable=max_points_var, width=6, state="readonly",
            values=["1000", "2500", "5000", "10000"],
        )
        combo.pack(side=tk.LEFT, padx=2)
        combo.bind("<<ComboboxSelected>>", lambda e: _on_max_points(graph, max_points_var))

    graph._range_label = ttk.Label(bar, text="", style="Status.TLabel")
    graph._range_label.pack(side=tk.RIGHT, padx=4)

    def status_cb(msg: str):
        if hasattr(graph, "_range_label"):
            graph._range_label.configure(text=msg)

    graph.on_view_change = status_cb
    return bar


def _on_max_points(graph: LogGraphView, var: tk.StringVar):
    try:
        graph.max_draw_points = int(var.get())
    except ValueError:
        graph.max_draw_points = 2500
    graph.redraw()
