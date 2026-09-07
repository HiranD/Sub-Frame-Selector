#!/usr/bin/env python3
"""
Tests for the analysis sidecar cache.

Self-contained -- builds its own synthetic FITS files, so it needs no sample
data. The repo has no test framework, so this follows the same runnable-script
style as test_analysis.py.

Usage:
    python tests/test_sidecar.py
"""

import os
import shutil
import sys
import tempfile

import numpy as np

# Add src to path for imports (this file lives in tests/, so src/ is one up)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from astropy.io import fits

from analysis import sidecar


# --------------------------------------------------------------------------
# Tiny test harness
# --------------------------------------------------------------------------

_PASSED = []
_FAILED = []


def check(name: str, condition: bool, detail: str = ""):
    """Record a single assertion without aborting the rest of the run."""
    if condition:
        _PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        _FAILED.append(name)
        print(f"  FAIL  {name}  {detail}")


def make_fits(path: str, seed: int = 0, extra_header: dict = None):
    """Write a small synthetic FITS frame.

    DATE-OBS varies with the seed, matching real capture software, which
    stamps a unique timestamp on every exposure. The header fingerprint
    relies on that to tell two same-size frames apart.
    """
    rng = np.random.default_rng(seed)
    data = rng.normal(800, 5, size=(64, 64)).astype(np.float32)

    hdu = fits.PrimaryHDU(data)
    hdu.header['DATE-OBS'] = f'2026-07-12T09:43:{seed % 60:02d}'
    hdu.header['EXPTIME'] = 180.0
    hdu.header['FILTER'] = 'L'
    hdu.header['XPIXSZ'] = 2.9
    hdu.header['FOCALLEN'] = 360.0
    hdu.header['XBINNING'] = 1
    hdu.header['INSTRUME'] = 'Test Camera'
    for key, value in (extra_header or {}).items():
        hdu.header[key] = value
    hdu.header['COMMENT'] = 'first comment'
    hdu.header['COMMENT'] = 'second comment'
    hdu.header['HISTORY'] = 'some history'

    hdu.writeto(path, overwrite=True)
    return hdu.header


def sample_psf(n: int = 3):
    """A few PSF-fit records in the shape star_detector.fit_psf() returns."""
    return [
        {'x': 10.123456, 'y': 20.987654, 'fwhm_x': 3.4567891,
         'fwhm_y': 3.9876543, 'amplitude': 1820.55555, 'fit_success': True}
        for _ in range(n - 1)
    ] + [
        {'x': 1.0, 'y': 2.0, 'fwhm_x': 5.0, 'fwhm_y': 5.0,
         'amplitude': 10.0, 'fit_success': False}
    ]


SAMPLE_METRICS = {
    'fwhm': 3.2109876,
    'fwhm_arcsec': 4.6123456,
    'eccentricity': 0.3812345,
    'snr': 42.7654321,
    'star_count': 431,
    'background': 812.5432,
}

SAMPLE_COUNTS = {'detected': 500, 'fitted': 3, 'fit_success': 2}


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_round_trip(tmp):
    print("\nRound trip")
    path = os.path.join(tmp, 'frame.fits')
    header = make_fits(path)

    doc = sidecar.build(path, header, sidecar.DEFAULT_PARAMS, 1.661579,
                        SAMPLE_METRICS, SAMPLE_COUNTS, sample_psf())

    check("write succeeds", sidecar.write(path, doc) is True)
    check("sidecar named <name>.fits.sfs.json",
          os.path.basename(str(sidecar.sidecar_path(path))) == 'frame.fits.sfs.json')
    check("sidecar does not match a *.fits glob",
          not str(sidecar.sidecar_path(path)).endswith('.fits'))

    back = sidecar.read(path)
    check("read returns a dict", isinstance(back, dict))
    check("survives round trip", back == doc)
    check("valid immediately after write",
          sidecar.load_valid(path, sidecar.DEFAULT_PARAMS) is not None)

    result = sidecar.to_result(back, path)
    check("to_result marks cached", result['cached'] is True)
    check("to_result carries metrics", result['metrics'] == doc['metrics'])
    check("to_result carries counts",
          result['star_count_detected'] == 500 and result['star_count_fitted'] == 3)
    check("to_result carries filename", result['filename'] == 'frame.fits')


def test_star_table(tmp):
    print("\nStar table")
    path = os.path.join(tmp, 'stars.fits')
    header = make_fits(path)
    doc = sidecar.build(path, header, sidecar.DEFAULT_PARAMS, 1.5,
                        SAMPLE_METRICS, SAMPLE_COUNTS, sample_psf(3))

    stars = doc['stars']
    check("parallel arrays, not array-of-objects", isinstance(stars, dict))
    check("all columns same length",
          len({len(v) for v in stars.values()}) == 1)
    check("one row per fitted star", len(stars['x']) == 3)
    check("x rounded to 2dp", stars['x'][0] == 10.12, f"got {stars['x'][0]}")
    check("fwhm rounded to 3dp", stars['fwhm_x'][0] == 3.457, f"got {stars['fwhm_x'][0]}")
    check("amplitude rounded to 1dp", stars['amplitude'][0] == 1820.6,
          f"got {stars['amplitude'][0]}")
    check("fit_success stored as 0/1", stars['ok'] == [1, 1, 0], f"got {stars['ok']}")
    check("star_count metric stays an int", isinstance(doc['metrics']['star_count'], int))
    check("loads into numpy cleanly", np.array(stars['fwhm_x']).dtype.kind == 'f')


def test_header_sanitizing(tmp):
    print("\nHeader sanitizing")
    path = os.path.join(tmp, 'hdr.fits')
    header = make_fits(path, extra_header={'OBJECT': 'M31', 'GAIN': 100})
    clean = sidecar.sanitize_header(header)

    check("COMMENT dropped", 'COMMENT' not in clean)
    check("HISTORY dropped", 'HISTORY' not in clean)
    check("real cards kept", clean.get('OBJECT') == 'M31' and clean.get('EXPTIME') == 180.0)
    check("binning kept for later use", clean.get('XBINNING') == 1)

    import json
    try:
        json.dumps(clean)
        check("whole header is JSON serializable", True)
    except (TypeError, ValueError) as e:
        check("whole header is JSON serializable", False, str(e))

    check("NaN coerced away", sidecar._json_safe(float('nan')) is None)
    check("inf coerced away", sidecar._json_safe(float('inf')) is None)
    check("numpy float coerced", sidecar._json_safe(np.float32(1.5)) == 1.5)


def test_invalidation(tmp):
    print("\nInvalidation")
    path = os.path.join(tmp, 'inv.fits')
    header = make_fits(path, seed=1)
    doc = sidecar.build(path, header, sidecar.DEFAULT_PARAMS, 1.5,
                        SAMPLE_METRICS, SAMPLE_COUNTS, sample_psf())
    sidecar.write(path, doc)
    P = sidecar.DEFAULT_PARAMS

    check("baseline is valid", sidecar.load_valid(path, P) is not None)

    for name, override in (('fwhm_estimate', 4.0), ('threshold_sigma', 3.0),
                           ('max_stars', 300), ('box_size', 21)):
        check(f"invalidated by changed {name}",
              sidecar.load_valid(path, {**P, name: override}) is None)

    original = sidecar.ALGO_VERSION
    sidecar.ALGO_VERSION = '999.0'
    check("invalidated by ALGO_VERSION bump", sidecar.load_valid(path, P) is None)
    sidecar.ALGO_VERSION = original

    bad_version = dict(doc, sfs_version=doc['sfs_version'] + 1)
    check("invalidated by sfs_version bump", not sidecar.is_valid(bad_version, path, P))

    # mtime rewritten over identical bytes -- the header fingerprint should
    # rescue this rather than forcing a needless re-analysis.
    st = os.stat(path)
    os.utime(path, (st.st_atime, st.st_mtime + 5000))
    check("survives mtime-only change via header_sha1",
          sidecar.load_valid(path, P) is not None)
    os.utime(path, (st.st_atime, st.st_mtime))

    # Different content, same size -- only the fingerprint catches this.
    other = os.path.join(tmp, 'other.fits')
    make_fits(other, seed=99)
    check("test precondition: same file size",
          os.path.getsize(other) == os.path.getsize(path))
    shutil.copy(other, path)
    check("invalidated by different content at same size",
          sidecar.load_valid(path, P) is None)


def test_fingerprint_limitation(tmp):
    """Records a known, accepted limitation rather than hiding it.

    The fingerprint hashes the header, not the pixels. A frame whose data
    changed while its header and size stayed byte-identical is indistinguishable
    to it. Real capture software stamps a unique DATE-OBS per exposure, so this
    needs a deliberate in-place pixel rewrite that preserves the header exactly
    -- and the mtime check is the guard for that case.
    """
    print("\nFingerprint limitation (documented, not a regression)")
    path = os.path.join(tmp, 'twin_a.fits')
    twin = os.path.join(tmp, 'twin_b.fits')
    header = make_fits(path, seed=7)
    make_fits(twin, seed=8, extra_header={'DATE-OBS': header['DATE-OBS']})

    P = sidecar.DEFAULT_PARAMS
    sidecar.write(path, sidecar.build(path, header, P, 1.5, SAMPLE_METRICS,
                                      SAMPLE_COUNTS, sample_psf()))

    st = os.stat(path)
    shutil.copy(twin, path)          # different pixels, identical header
    os.utime(path, (st.st_atime, st.st_mtime))   # and mtime restored

    check("identical header + size + mtime reads as unchanged (known limit)",
          sidecar.load_valid(path, P) is not None)


def test_failure_modes(tmp):
    print("\nFailure modes")
    path = os.path.join(tmp, 'fail.fits')
    header = make_fits(path, seed=2)
    P = sidecar.DEFAULT_PARAMS

    check("missing sidecar reads as None", sidecar.read(path) is None)
    check("missing sidecar is not valid", sidecar.load_valid(path, P) is None)

    sidecar.write(path, sidecar.build(path, header, P, 1.5, SAMPLE_METRICS,
                                      SAMPLE_COUNTS, sample_psf()))

    sp = sidecar.sidecar_path(path)
    backup = sp.read_bytes()

    sp.write_text('{ this is not json')
    check("corrupt JSON reads as None", sidecar.read(path) is None)
    check("corrupt JSON is not valid", sidecar.load_valid(path, P) is None)

    sp.write_text('[1, 2, 3]')
    check("non-dict JSON reads as None", sidecar.read(path) is None)

    sp.write_bytes(backup)
    check("restored sidecar valid again", sidecar.load_valid(path, P) is not None)

    check("missing FITS file is not valid",
          sidecar.load_valid(os.path.join(tmp, 'nope.fits'), P) is None)

    # A frame that failed analysis still gets cached, so it isn't retried on
    # every run. It must be readable and carry the error.
    bad = os.path.join(tmp, 'broken.fits')
    with open(bad, 'w') as fh:
        fh.write('not a fits file')
    err_doc = sidecar.build(bad, None, P, None, None, error='Empty or corrupt FITS file')
    check("failure doc writes", sidecar.write(bad, err_doc) is True)
    check("failure doc is valid (won't be retried)",
          sidecar.load_valid(bad, P) is not None)
    err_result = sidecar.to_result(sidecar.read(bad), bad)
    check("failure result has no metrics", err_result['metrics'] is None)
    check("failure result carries the error",
          err_result.get('error') == 'Empty or corrupt FITS file')


def test_readonly_dir(tmp):
    print("\nRead-only media")
    ro = os.path.join(tmp, 'readonly')
    os.makedirs(ro, exist_ok=True)
    path = os.path.join(ro, 'frame.fits')
    header = make_fits(path, seed=3)
    doc = sidecar.build(path, header, sidecar.DEFAULT_PARAMS, 1.5,
                        SAMPLE_METRICS, SAMPLE_COUNTS, sample_psf())

    os.chmod(ro, 0o500)
    try:
        wrote = sidecar.write(path, doc)
        check("write returns False instead of raising", wrote is False)
        check("no .tmp file left behind",
              not any(f.endswith('.tmp') for f in os.listdir(ro)))
    finally:
        os.chmod(ro, 0o700)


def main():
    tmp = tempfile.mkdtemp(prefix='sfs-sidecar-test-')
    print(f"Sidecar tests (scratch: {tmp})")
    try:
        test_round_trip(tmp)
        test_star_table(tmp)
        test_header_sanitizing(tmp)
        test_invalidation(tmp)
        test_fingerprint_limitation(tmp)
        test_failure_modes(tmp)
        test_readonly_dir(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{len(_PASSED)} passed, {len(_FAILED)} failed")
    if _FAILED:
        for name in _FAILED:
            print(f"  FAILED: {name}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
