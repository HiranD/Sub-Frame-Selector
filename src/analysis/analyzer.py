"""Main analyzer that combines all analysis components."""

import numpy as np
import os
from pathlib import Path
from typing import Optional, Callable
from multiprocessing import Pool, cpu_count
from . import sidecar
from .fits_reader import FITSReader
from .star_detector import StarDetector
from .metrics import MetricsCalculator
from .statistics import StatisticsCalculator, calculate_all_metric_stats


def _analyze_one(
    filepath: str,
    params: dict,
    image_scale: Optional[float] = None,
    write_sidecar: bool = True
) -> dict:
    """
    Run the full analysis pipeline on one file and cache the result.

    Shared by the multiprocessing worker and the in-process analyze_file(),
    so sidecar writing can't drift between the two paths.

    Args:
        filepath: Path to FITS file
        params: Detection parameters (see sidecar.DEFAULT_PARAMS)
        image_scale: Image scale in arcsec/pixel; derived from this frame's
            own header when None
        write_sidecar: Persist the result next to the frame

    Returns:
        Analysis result dict
    """
    reader = FITSReader()
    detector = StarDetector(
        fwhm_estimate=params['fwhm_estimate'],
        threshold_sigma=params['threshold_sigma'],
        max_stars=params['max_stars'],
        box_size=params['box_size']
    )
    metrics_calc = MetricsCalculator()

    # One open for both pixels and header; the header is needed for the image
    # scale and for the sidecar.
    image, header = reader.load_with_header(filepath)

    # Each frame gets its own scale, so mixing folders from different scopes
    # or cameras no longer applies the first frame's scale to everything.
    if image_scale is None:
        image_scale = reader.imaging_params_from_header(header).get('image_scale')

    stars = detector.detect_stars(image)
    psf_results = detector.fit_psf(image, stars)
    metrics = metrics_calc.calculate_all(image, psf_results, image_scale)

    counts = {
        'detected': len(stars),
        'fitted': len(psf_results),
        'fit_success': sum(1 for s in psf_results if s.get('fit_success', True))
    }

    doc = sidecar.build(filepath, header, params, image_scale, metrics, counts, psf_results)

    if write_sidecar:
        sidecar.write(filepath, doc)

    # Return the values as the sidecar stores them (rounded), so a frame reads
    # back identically whether it was just computed or loaded from cache.
    return {
        'filepath': str(filepath),
        'filename': Path(filepath).name,
        'metrics': doc['metrics'],
        'star_count_detected': counts['detected'],
        'star_count_fitted': counts['fitted'],
        'image_scale': doc['image_scale'],
        'cached': False
    }


def summarize_imaging_params(results: list[dict]) -> Optional[dict]:
    """
    Reduce the per-frame image scales to a single summary for the UI.

    Scale is measured per frame, so a set spanning two telescopes has no one
    answer. Report a scale only when the frames agree; otherwise leave
    'image_scale' None and flag the set as mixed.

    Args:
        results: Per-frame analysis results

    Returns:
        Dict with 'image_scale', 'image_scale_min', 'image_scale_max' and
        'mixed', or None if no frame reported a scale
    """
    scales = [r['image_scale'] for r in results if r and r.get('image_scale')]
    if not scales:
        return None

    mixed = (max(scales) - min(scales)) > 1e-6
    return {
        'image_scale': None if mixed else scales[0],
        'image_scale_min': min(scales),
        'image_scale_max': max(scales),
        'mixed': mixed
    }


def _analyze_single_file(args: dict) -> dict:
    """
    Analyze a single file (worker function for multiprocessing).

    Must stay at module level to remain picklable for the Pool.

    Args:
        args: Dict with 'filepath' and 'params' keys

    Returns:
        Analysis result dict
    """
    filepath = args['filepath']

    try:
        return _analyze_one(filepath, args['params'])
    except Exception as e:
        # Cache the failure too, so a corrupt frame isn't retried on every
        # run. Force re-analyze is the escape hatch if the cause was transient.
        sidecar.write(filepath, sidecar.build(
            filepath, None, args['params'], None, None, error=str(e)
        ))
        return {
            'filepath': str(filepath),
            'filename': Path(filepath).name,
            'metrics': None,
            'error': str(e),
            'cached': False
        }


class SubframeAnalyzer:
    """
    Main class that orchestrates subframe analysis.

    Combines FITS reading, star detection, PSF fitting, and metrics calculation.
    Supports parallel processing across multiple CPU cores.
    """

    def __init__(
        self,
        fwhm_estimate: float = sidecar.DEFAULT_PARAMS['fwhm_estimate'],
        threshold_sigma: float = sidecar.DEFAULT_PARAMS['threshold_sigma'],
        max_stars: int = sidecar.DEFAULT_PARAMS['max_stars'],
        num_workers: int = None,
        box_size: int = sidecar.DEFAULT_PARAMS['box_size']
    ):
        """
        Initialize the analyzer.

        Detection defaults come from sidecar.DEFAULT_PARAMS so that the GUI's
        cache lookup and the analysis itself can never disagree about which
        parameters a sidecar was produced with.

        Args:
            fwhm_estimate: Expected FWHM of stars in pixels
            threshold_sigma: Detection threshold in sigma above background
            max_stars: Maximum number of stars to analyze per frame
            num_workers: Number of CPU cores to use (default: all but two)
            box_size: Size of the cutout used for PSF fitting, in pixels
        """
        self.fwhm_estimate = fwhm_estimate
        self.threshold_sigma = threshold_sigma
        self.max_stars = max_stars
        self.box_size = box_size

        # Default to max cores - 2
        if num_workers is None:
            num_workers = max(1, cpu_count() - 2)
        self.num_workers = max(1, min(cpu_count(), num_workers))

        self.fits_reader = FITSReader()
        self.star_detector = StarDetector(
            fwhm_estimate=fwhm_estimate,
            threshold_sigma=threshold_sigma,
            max_stars=max_stars,
            box_size=box_size
        )
        self.metrics_calc = MetricsCalculator()
        self.stats_calc = StatisticsCalculator()

    @property
    def params(self) -> dict:
        """Detection parameters, in the form sidecars record and compare."""
        return {
            'fwhm_estimate': self.fwhm_estimate,
            'threshold_sigma': self.threshold_sigma,
            'max_stars': self.max_stars,
            'box_size': self.box_size
        }

    @staticmethod
    def get_cpu_count() -> int:
        """Get total number of CPU cores available."""
        return cpu_count()

    def analyze_file(self, filepath: str, image_scale: Optional[float] = None) -> dict:
        """
        Analyze a single FITS file.

        Args:
            filepath: Path to FITS file
            image_scale: Image scale in arcsec/pixel (optional)

        Returns:
            Dict with metrics and file info:
            {
                'filepath': str,
                'filename': str,
                'metrics': {
                    'fwhm': float,
                    'fwhm_arcsec': float or None,
                    'eccentricity': float,
                    'snr': float,
                    'star_count': int,
                    'background': float
                },
                'star_count_detected': int,
                'star_count_fitted': int,
                'image_scale': float or None,
                'cached': bool
            }
        """
        return _analyze_one(filepath, self.params, image_scale)

    def analyze_files(
        self,
        files: list[dict],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        use_parallel: bool = True,
        force: bool = False
    ) -> dict:
        """
        Analyze a list of FITS files (can be from multiple folders).

        Frames with a valid sidecar are loaded from it instead of being
        re-analyzed, so re-running an unchanged dataset costs almost nothing.

        Args:
            files: List of file dicts with 'path' and 'filename' keys
            progress_callback: Optional callback(current, total, filename)
            use_parallel: Use parallel processing (default True)
            force: Ignore existing sidecars and re-analyze everything

        Returns:
            Dict with results and statistics:
            {
                'total_files': int,
                'results': [
                    {'filepath': ..., 'filename': ..., 'metrics': {...}},
                    ...
                ],
                'statistics': {
                    'fwhm': {'median': ..., 'sigma': ..., 'band_1sigma': ..., ...},
                    'eccentricity': {...},
                    ...
                },
                'workers_used': int,
                'imaging_params': dict or None
            }
        """
        total = len(files)

        if total == 0:
            return {
                'total_files': 0,
                'results': [],
                'statistics': {},
                'workers_used': 0,
                'cached_count': 0,
                'imaging_params': None
            }

        params = self.params

        # Partition into cache hits and work to do. Results are addressed by
        # index throughout, so the list stays aligned with `files` regardless
        # of which frames were cached or what order the pool returns.
        results = [None] * total
        pending = []
        for i, file_info in enumerate(files):
            doc = None if force else sidecar.load_valid(file_info['path'], params)
            if doc is not None:
                results[i] = sidecar.to_result(doc, file_info['path'])
            else:
                pending.append(i)

        cached = total - len(pending)

        # Report the whole cached batch in one call rather than one per frame,
        # which would flood the GUI's event queue with instant updates.
        if progress_callback and cached:
            progress_callback(cached, total, f"{cached} cached")

        workers = self.num_workers

        if use_parallel and workers > 1 and len(pending) > 1:
            self._analyze_parallel(
                files, pending, results, total, cached, workers, progress_callback
            )
        else:
            self._analyze_sequential(files, pending, results, total, cached, progress_callback)
            workers = 1

        # Calculate statistics across all frames
        valid_metrics = [r['metrics'] for r in results if r and r.get('metrics')]
        statistics = calculate_all_metric_stats(valid_metrics)

        return {
            'total_files': total,
            'results': results,
            'statistics': statistics,
            'workers_used': workers,
            'cached_count': cached,
            'imaging_params': summarize_imaging_params(results)
        }

    def analyze_folder(
        self,
        folder_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        use_parallel: bool = True,
        force: bool = False
    ) -> dict:
        """
        Analyze all FITS files in a folder.

        Args:
            folder_path: Path to folder containing FITS files
            progress_callback: Optional callback(current, total, filename)
            use_parallel: Use parallel processing (default True)
            force: Ignore existing sidecars and re-analyze everything

        Returns:
            Dict with results and statistics (same as analyze_files, plus 'folder' key)
        """
        # Get file list
        files = self.fits_reader.load_folder(folder_path)

        # Use analyze_files for the actual work
        result = self.analyze_files(files, progress_callback, use_parallel, force)
        result['folder'] = folder_path

        return result

    def _analyze_sequential(
        self,
        files: list[dict],
        pending: list[int],
        results: list,
        total: int,
        cached: int,
        progress_callback: Optional[Callable]
    ) -> None:
        """Analyze the pending files sequentially, filling `results` in place."""
        completed = cached
        params = self.params

        for idx in pending:
            file_info = files[idx]
            completed += 1

            if progress_callback:
                progress_callback(completed, total, file_info['filename'])

            # Same worker entry point as the parallel path, so error handling
            # and sidecar writing behave identically on one core.
            results[idx] = _analyze_single_file({
                'filepath': file_info['path'],
                'params': params
            })

    def _analyze_parallel(
        self,
        files: list[dict],
        pending: list[int],
        results: list,
        total: int,
        cached: int,
        workers: int,
        progress_callback: Optional[Callable]
    ) -> None:
        """Analyze the pending files across multiple cores, filling `results` in place."""
        params = self.params
        args_list = [
            {'filepath': files[idx]['path'], 'params': params}
            for idx in pending
        ]

        completed = cached

        with Pool(processes=workers) as pool:
            # imap preserves submission order, so zipping it back against
            # `pending` puts every result at its original index.
            for idx, result in zip(pending, pool.imap(_analyze_single_file, args_list)):
                results[idx] = result
                completed += 1

                if progress_callback:
                    progress_callback(completed, total, result['filename'])

    def get_outliers(
        self,
        results: list[dict],
        metric: str,
        sigma_threshold: float = 2.0
    ) -> list[int]:
        """
        Get indices of frames that are outliers for a specific metric.

        Args:
            results: List of analysis results from analyze_folder()
            metric: Metric name ('fwhm', 'eccentricity', 'snr', etc.)
            sigma_threshold: Number of sigmas for outlier detection

        Returns:
            List of indices of outlier frames
        """
        values = []
        for r in results:
            if r and r.get('metrics') and metric in r['metrics']:
                values.append(r['metrics'][metric])
            else:
                values.append(np.nan)

        values = np.array(values)
        return self.stats_calc.get_outlier_indices(values, sigma_threshold)
