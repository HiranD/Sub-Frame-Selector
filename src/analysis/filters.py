"""Pure rejection-filter logic: threshold rules, evaluation and manual overrides.

No Tk imports here -- the filter panel and the app build on these functions.
Manual overrides are keyed by file path (not row index), so they survive
threshold changes and frame deletion.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, NamedTuple, Optional, Set, Tuple


class MetricSpec(NamedTuple):
    """A filterable metric and how to display it."""
    key: str
    label: str
    short: str      # used in rejection reasons
    usual: str      # 'low' or 'high': the side that usually indicates a bad frame
    decimals: int


FILTER_METRICS: List[MetricSpec] = [
    MetricSpec('fwhm', 'FWHM (px)', 'FWHM', 'high', 2),
    MetricSpec('fwhm_arcsec', 'FWHM (″)', 'FWHM″', 'high', 2),
    MetricSpec('eccentricity', 'Eccentricity', 'Eccentricity', 'high', 3),
    MetricSpec('snr', 'SNR', 'SNR', 'low', 1),
    MetricSpec('star_count', 'Stars', 'Stars', 'low', 0),
    MetricSpec('background', 'Background', 'Background', 'high', 1),
]

METRIC_SPECS: Dict[str, MetricSpec] = {spec.key: spec for spec in FILTER_METRICS}


@dataclass(frozen=True)
class Rule:
    """Reject frames whose metric is at or beyond a bound (None = no bound)."""
    metric: str
    low: Optional[float] = None
    high: Optional[float] = None


def parse_bound(text: str) -> Tuple[Optional[float], bool]:
    """
    Parse one bound entry.

    Returns:
        (value, ok). Blank is (None, True); non-numeric or non-finite
        text is (None, False).
    """
    text = text.strip().replace(',', '.')
    if not text:
        return None, True
    try:
        value = float(text)
    except ValueError:
        return None, False
    if not math.isfinite(value):
        return None, False
    return value, True


def parse_rule(metric: str, low_text: str,
               high_text: str) -> Tuple[Optional[Rule], bool, bool]:
    """
    Build a Rule from the min/max entry texts.

    Returns:
        (rule, low_ok, high_ok). An invalid side is dropped; the rule is
        None when no valid side is set or when min >= max (both flagged bad).
    """
    low, low_ok = parse_bound(low_text)
    high, high_ok = parse_bound(high_text)
    if low is not None and high is not None and low >= high:
        return None, False, False
    if low is None and high is None:
        return None, low_ok, high_ok
    return Rule(metric, low, high), low_ok, high_ok


def evaluate(results: List[Optional[dict]],
             rules: List[Rule]) -> Dict[int, List[str]]:
    """
    Apply rules to analysis results.

    Args:
        results: Per-frame result dicts (or None), in file order.
        rules: Rules to apply.

    Returns:
        {index: [reasons]} for failing frames only. Frames without metrics
        or without a value for a rule's metric are never rejected.
    """
    failures: Dict[int, List[str]] = {}
    for i, result in enumerate(results):
        if not result or not result.get('metrics'):
            continue
        metrics = result['metrics']
        for rule in rules:
            value = metrics.get(rule.metric)
            if value is None:
                continue
            spec = METRIC_SPECS[rule.metric]
            fmt = f".{spec.decimals}f"
            if rule.low is not None and value <= rule.low:
                reason = f"{spec.short} {value:{fmt}} below min {rule.low:{fmt}}"
            elif rule.high is not None and value >= rule.high:
                reason = f"{spec.short} {value:{fmt}} above max {rule.high:{fmt}}"
            else:
                continue
            failures.setdefault(i, []).append(reason)
    return failures


def prefill_value(stats: Optional[dict], side: str) -> Optional[float]:
    """
    Suggest a bound at 2 sigma from the median.

    Args:
        stats: Metric stats with 'median' and 'sigma' (or None).
        side: 'high' for median + 2 sigma, 'low' for median - 2 sigma (floored at 0).

    Returns:
        The suggested bound, or None when there are no usable stats.
    """
    if not stats or stats['sigma'] == 0:
        return None
    if side == 'high':
        return stats['median'] + 2 * stats['sigma']
    return max(0.0, stats['median'] - 2 * stats['sigma'])


@dataclass
class Selection:
    """Outcome of combining filter failures with manual overrides."""
    selected: Set[int]
    rejected: int       # frames failing the filters
    kept: int           # failing frames the user manually kept
    notes: Dict[int, List[str]]


def compute_selection(paths: List[str], failures: Dict[int, List[str]],
                      manual_added: Set[str],
                      manual_removed: Set[str]) -> Selection:
    """
    Combine filter failures with path-keyed manual overrides.

    Args:
        paths: File paths in display order.
        failures: Output of evaluate().
        manual_added: Paths the user marked although they pass the filters.
        manual_removed: Paths the user kept although they fail the filters.
    """
    failing = set(failures)
    added = {i for i, p in enumerate(paths) if p in manual_added}
    removed = {i for i, p in enumerate(paths) if p in manual_removed}
    selected = (failing | added) - removed

    notes: Dict[int, List[str]] = {}
    for i in failing:
        notes[i] = ["Rejected: " + reason for reason in failures[i]]
        if i in removed:
            notes[i].append("Kept manually")
    for i in added - failing:
        notes[i] = ["Marked manually"]

    return Selection(selected=selected, rejected=len(failing),
                     kept=len(failing & removed), notes=notes)


def apply_manual_toggle(path: str, selected: bool, failing: bool,
                        manual_added: Set[str], manual_removed: Set[str]) -> None:
    """Record a user checkbox toggle, mutating the two override sets."""
    if selected:
        manual_removed.discard(path)
        manual_added.add(path)
    else:
        manual_added.discard(path)
        if failing:
            manual_removed.add(path)
