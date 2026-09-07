"""Per-frame analysis sidecars.

Each analyzed FITS file gets a JSON sidecar written next to it:

    M31_L_120s_0001.fits  ->  M31_L_120s_0001.fits.sfs.json

The sidecar holds the frame's quality metrics, its (sanitized) FITS header and
the full per-star PSF table. Two reasons this exists:

1. Re-analysing an unchanged frame becomes free -- the validity check never
   even opens the FITS file on the fast path.
2. The per-star table is otherwise discarded inside the worker process, so the
   data needed for tilt maps, field-curvature analysis or re-aggregation is
   lost the moment analysis finishes.

The suffix is appended to the *full* filename rather than the stem so that
``x.fits`` and ``x.fit`` in the same folder don't collide, and so sidecars
never match a ``*.fits`` glob.
"""

import hashlib
import json
import numbers
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SIDECAR_SUFFIX = ".sfs.json"
SIDECAR_VERSION = 1

# Bump when star_detector.py or metrics.py change in a way that alters the
# numbers they produce. Every existing sidecar is then treated as stale.
ALGO_VERSION = "1.0"

# Single source of truth for the detection parameters. Both the analyzer and
# the GUI's open-time cache lookup read from here -- if they ever disagreed,
# every sidecar would silently be considered invalid.
DEFAULT_PARAMS = {
    "fwhm_estimate": 5.0,
    "threshold_sigma": 5.0,
    "max_stars": 500,
    "box_size": 15,
}

# Header cards that are repeated, unbounded, or carry no analysis value.
_SKIP_HEADER_KEYS = {"COMMENT", "HISTORY", "", "END"}

# Decimal places per star column. Star tables dominate sidecar size, and full
# float64 repr roughly triples it for precision nobody uses.
_STAR_ROUNDING = {"x": 2, "y": 2, "fwhm_x": 3, "fwhm_y": 3, "amplitude": 1}

_METRIC_ROUNDING = 4


def sidecar_path(fits_path) -> Path:
    """Return the sidecar path for a FITS file."""
    return Path(str(fits_path) + SIDECAR_SUFFIX)


def _json_safe(value):
    """Coerce a FITS header value into something json can serialize."""
    if value is None or isinstance(value, (bool, str)):
        return value

    # Test against the numeric ABCs rather than the concrete types: numpy
    # scalars register here, but only np.float64 subclasses Python's float.
    # Integral must be checked first -- int() accepts a float and would
    # silently truncate it.
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        value = float(value)
        # NaN/inf have no JSON literal.
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value

    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", "replace")
        except Exception:
            return None

    # astropy Undefined, complex, anything else.
    try:
        return str(value)
    except Exception:
        return None


def sanitize_header(header) -> dict:
    """Convert a FITS header to a flat, JSON-safe dict.

    Drops COMMENT/HISTORY (repeated cards that would collapse anyway) and
    keeps the first occurrence of any duplicated key.
    """
    out = {}
    try:
        items = header.items()
    except AttributeError:
        items = dict(header).items()

    for key, value in items:
        if not key or key.upper() in _SKIP_HEADER_KEYS:
            continue
        if key in out:
            continue
        out[key] = _json_safe(value)
    return out


def header_hash(header) -> Optional[str]:
    """SHA1 of the raw header, used as a content fingerprint for the frame.

    Cheap: the header is already in hand wherever this is called, and reading
    one from disk touches only the first few KB of the file.
    """
    try:
        raw = header.tostring()
    except AttributeError:
        try:
            raw = json.dumps(sanitize_header(header), sort_keys=True)
        except Exception:
            return None
    except Exception:
        return None

    if isinstance(raw, str):
        raw = raw.encode("utf-8", "replace")
    return hashlib.sha1(raw).hexdigest()


def _params_key(params: dict) -> tuple:
    """Canonical, comparable form of a detection-parameter set."""
    key = []
    for name in sorted(DEFAULT_PARAMS):
        value = params.get(name, DEFAULT_PARAMS[name])
        try:
            value = round(float(value), 6)
        except (TypeError, ValueError):
            value = None
        key.append((name, value))
    return tuple(key)


def _round(value, places):
    """Round to a plain Python float, or None if not numeric."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    return round(value, places)


def _star_table(psf_results: list) -> dict:
    """Per-star records -> parallel arrays.

    Parallel arrays are roughly a third the size of an array-of-objects and
    load straight into ``np.array()`` / ``pd.DataFrame(doc["stars"])``.
    """
    table = {name: [] for name in ("x", "y", "fwhm_x", "fwhm_y", "amplitude", "ok")}
    for star in psf_results or []:
        for name, places in _STAR_ROUNDING.items():
            table[name].append(_round(star.get(name), places))
        table["ok"].append(1 if star.get("fit_success", True) else 0)
    return table


def build(
    fits_path,
    header,
    params: dict,
    image_scale: Optional[float],
    metrics: Optional[dict],
    counts: Optional[dict] = None,
    psf_results: Optional[list] = None,
    error: Optional[str] = None,
) -> dict:
    """Assemble a sidecar document for one analyzed frame."""
    fits_path = Path(fits_path)

    try:
        stat = fits_path.stat()
        size, mtime = stat.st_size, stat.st_mtime
    except OSError:
        size, mtime = None, None

    clean_header = sanitize_header(header) if header is not None else {}

    rounded_metrics = None
    if metrics:
        rounded_metrics = {}
        for name, value in metrics.items():
            if name == "star_count":
                rounded_metrics[name] = int(value) if value is not None else None
            else:
                rounded_metrics[name] = _round(value, _METRIC_ROUNDING)

    doc = {
        "sfs_version": SIDECAR_VERSION,
        "algo_version": ALGO_VERSION,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "filename": fits_path.name,
            "size": size,
            "mtime": mtime,
            "header_sha1": header_hash(header) if header is not None else None,
            "naxis1": clean_header.get("NAXIS1"),
            "naxis2": clean_header.get("NAXIS2"),
        },
        "header": clean_header,
        "params": {name: params.get(name, DEFAULT_PARAMS[name]) for name in DEFAULT_PARAMS},
        "image_scale": _round(image_scale, 6),
        "metrics": rounded_metrics,
        "counts": counts or {},
        "stars": _star_table(psf_results),
    }

    if error:
        doc["error"] = str(error)

    return doc


def write(fits_path, doc: dict) -> bool:
    """Write a sidecar atomically. Returns success; never raises.

    Astro data routinely lives on read-only, full or flaky external drives.
    A failed cache write must never take an analysis run down with it.
    """
    target = sidecar_path(fits_path)
    tmp = target.with_name(target.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, separators=(",", ":"))
        os.replace(tmp, target)
        return True
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def read(fits_path) -> Optional[dict]:
    """Read a sidecar. Returns None if absent, unreadable or corrupt."""
    try:
        with open(sidecar_path(fits_path), "r", encoding="utf-8") as handle:
            doc = json.load(handle)
    except Exception:
        return None
    return doc if isinstance(doc, dict) else None


def is_valid(doc: Optional[dict], fits_path, params: dict) -> bool:
    """Is this sidecar still an accurate description of the frame on disk?

    Checks run cheapest-first; the common case never opens the FITS file.
    """
    if not doc:
        return False

    if doc.get("sfs_version") != SIDECAR_VERSION:
        return False
    if doc.get("algo_version") != ALGO_VERSION:
        return False
    if _params_key(doc.get("params") or {}) != _params_key(params):
        return False

    source = doc.get("source") or {}
    try:
        stat = Path(fits_path).stat()
    except OSError:
        return False

    if source.get("size") != stat.st_size:
        return False

    recorded_mtime = source.get("mtime")
    if recorded_mtime is not None and abs(recorded_mtime - stat.st_mtime) < 1e-6:
        return True

    # Size matches but mtime moved. That is usually an rsync or a restore from
    # backup rewriting the timestamp on identical bytes, so fall back to the
    # header fingerprint before paying for a full re-analysis.
    #
    # The fingerprint covers the header, not the pixels, so a frame whose data
    # changed while its header and size stayed byte-identical would slip
    # through. Capture software writes a unique DATE-OBS per exposure, so in
    # practice this only matters for a deliberate in-place pixel rewrite that
    # preserves the header exactly -- and mtime is the guard for that anyway.
    recorded_hash = source.get("header_sha1")
    if not recorded_hash:
        return False

    try:
        # Must pick the same HDU the sidecar was written from, or the
        # fingerprints would never match on multi-extension files.
        from .fits_reader import FITSReader

        header = FITSReader().read_image_header(fits_path)
    except Exception:
        return False

    return header is not None and header_hash(header) == recorded_hash


def load_valid(fits_path, params: dict) -> Optional[dict]:
    """Return the sidecar for a frame if it is present and still valid."""
    doc = read(fits_path)
    return doc if is_valid(doc, fits_path, params) else None


def to_result(doc: dict, fits_path) -> dict:
    """Convert a sidecar into the per-frame result dict the analyzer returns."""
    counts = doc.get("counts") or {}
    result = {
        "filepath": str(fits_path),
        "filename": Path(fits_path).name,
        "metrics": doc.get("metrics"),
        "star_count_detected": counts.get("detected"),
        "star_count_fitted": counts.get("fitted"),
        "image_scale": doc.get("image_scale"),
        "cached": True,
    }
    if doc.get("error"):
        result["error"] = doc["error"]
    return result


def trash(fits_path) -> None:
    """Send a frame's sidecar to the recycle bin, if it has one."""
    target = sidecar_path(fits_path)
    if not target.exists():
        return
    try:
        from send2trash import send2trash

        send2trash(str(target))
    except Exception:
        pass
