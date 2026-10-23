"""Formatting helpers for the dashboard templates."""

from django import template

register = template.Library()

DASH = "—"


@register.filter
def duration(seconds: float | None) -> str:
    """78 -> "1m 18s"; None -> "—"."""
    if seconds is None:
        return DASH
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


@register.filter
def pct(value: float | None) -> str:
    """0.4237 -> "42%"; None -> "—"."""
    return DASH if value is None else f"{value * 100:.0f}%"


@register.filter
def num(value: float | None, digits: int = 1) -> str:
    """2.333 -> "2.3"; None -> "—"."""
    return DASH if value is None else f"{value:.{int(digits)}f}"


@register.filter
def bar_pct(value: int, peak: int) -> int:
    """Bar height as a percent of the tallest bar (at least 2% for non-zero values)."""
    if not peak or not value:
        return 0
    return max(2, round(value * 100 / peak))


@register.simple_tag
def sparkline(series, width: int = 240, height: int = 40) -> str:
    """An inline SVG polyline points string for [(label, value), ...]."""
    values = [v for _, v in series]
    if not values:
        return ""
    peak = max(values) or 1
    step = width / max(1, len(values) - 1)
    return " ".join(
        f"{i * step:.1f},{height - 2 - (v / peak) * (height - 4):.1f}" for i, v in enumerate(values)
    )
