"""Main analyzer that combines all analysis components."""

import numpy as np
import os
from pathlib import Path
from typing import Optional, Callable
from multiprocessing import Pool, cpu_count
from .fits_reader import FITSReader
from .star_detector import StarDetector
from .metrics import MetricsCalculator
from .statistics import StatisticsCalculator, calculate_all_metric_stats


def _analyze_single_file(args: tuple) -> dict:
    """
    Analyze a single file (worker function for multiprocessing).

    Args:
        args: Tuple of (filepath, fwhm_estimate, threshold_sigma, max_stars, image_scale)

    Returns:
        Analysis result dict
    """
    filepath, fwhm_estimate, threshold_sigma, max_stars, image_scale = args

    try:
        reader = FITSReader()
        detector = StarDetector(
            fwhm_estimate=fwhm_estimate,
            threshold_sigma=threshold_sigma,
            max_stars=max_stars
        )
        metrics_calc = MetricsCalculator()

        # Load image
        image = reader.load_file(filepath)

        # Detect stars
        stars = detector.detect_stars(image)

        # Fit PSF
        psf_results = detector.fit_psf(image, stars)

        # Calculate metrics (with image_scale for arcsec FWHM)
        metrics = metrics_calc.calculate_all(image, psf_results, image_scale)

        return {
            'filepath': str(filepath),
            'filename': Path(filepath).name,
            'metrics': metrics,
            'star_count_detected': len(stars),
            'star_count_fitted': len(psf_results)
        }
    except Exception as e:
        return {
            'filepath': str(filepath),
            'filename': Path(filepath).name,
            'metrics': None,
            'error': str(e)
        }


class SubframeAnalyzer:
    """
    Main class that orchestrates subframe analysis.

    Combines FITS reading, star detection, PSF fitting, and metrics calculation.
    Supports parallel processing across multiple CPU cores.
    """

    def __init__(
        self,
        fwhm_estimate: float = 5.0,
        threshold_sigma: float = 5.0,
        max_stars: int = 500,
        num_workers: int = None
    ):
        """
        Initialize the analyzer.

        Args:
            fwhm_estimate: Expected FWHM of stars in pixels
            threshold_sigma: Detection threshold in sigma above background
            max_stars: Maximum number of stars to analyze per frame
            num_workers: Number of CPU cores to use (default: half of available)
        """
        self.fwhm_estimate = fwhm_estimate
        self.threshold_sigma = threshold_sigma
        self.max_stars = max_stars

        # Default to max cores - 2
        if num_workers is None:
            num_workers = max(1, cpu_count() - 2)
        self.num_workers = max(1, min(cpu_count(), num_workers))

        self.fits_reader = FITSReader()
        self.star_detector = StarDetector(
            fwhm_estimate=fwhm_estimate,
            threshold_sigma=threshold_sigma,
            max_stars=max_stars
        )
        self.metrics_calc = MetricsCalculator()
        self.stats_calc = StatisticsCalculator()

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
                'star_count_fitted': int
            }
        """
        # Load image
        image = self.fits_reader.load_file(filepath)

        # Get image scale from header if not provided
        if image_scale is None:
            imaging_params = self.fits_reader.get_imaging_params(filepath)
            image_scale = imaging_params.get('image_scale')

        # Detect stars
        stars = self.star_detector.detect_stars(image)

        # Fit PSF to stars
        psf_results = self.star_detector.fit_psf(image, stars)

        # Calculate metrics
        metrics = self.metrics_calc.calculate_all(image, psf_results, image_scale)

        return {
            'filepath': str(filepath),
            'filename': Path(filepath).name,
            'metrics': metrics,
            'star_count_detected': len(stars),
            'star_count_fitted': len(psf_results)
        }

    def analyze_files(
        self,
        files: list[dict],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        use_parallel: bool = True
    ) -> dict:
        """
        Analyze a list of FITS files (can be from multiple folders).

        Args:
            files: List of file dicts with 'path' and 'filename' keys
            progress_callback: Optional callback(current, total, filename)
            use_parallel: Use parallel processing (default True)

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
                'imaging_params': None
            }

        # Get imaging parameters from first file (assume all files have same setup)
        imaging_params = self.fits_reader.get_imaging_params(files[0]['path'])
        image_scale = imaging_params.get('image_scale')

        workers = self.num_workers

        if use_parallel and workers > 1 and total > 1:
            results = self._analyze_parallel(files, total, workers, progress_callback, image_scale)
        else:
            results = self._analyze_sequential(files, total, progress_callback, image_scale)
            workers = 1

        # Calculate statistics across all frames
        valid_metrics = [r['metrics'] for r in results if r.get('metrics')]
        statistics = calculate_all_metric_stats(valid_metrics)

        return {
            'total_files': total,
            'results': results,
            'statistics': statistics,
            'workers_used': workers,
            'imaging_params': imaging_params
        }

    def analyze_folder(
        self,
        folder_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        use_parallel: bool = True
    ) -> dict:
        """
        Analyze all FITS files in a folder.

        Args:
            folder_path: Path to folder containing FITS files
            progress_callback: Optional callback(current, total, filename)
            use_parallel: Use parallel processing (default True)

        Returns:
            Dict with results and statistics (same as analyze_files, plus 'folder' key)
        """
        # Get file list
        files = self.fits_reader.load_folder(folder_path)

        # Use analyze_files for the actual work
        result = self.analyze_files(files, progress_callback, use_parallel)
        result['folder'] = folder_path

        return result

    def _analyze_sequential(
        self,
        files: list[dict],
        total: int,
        progress_callback: Optional[Callable],
        image_scale: Optional[float] = None
    ) -> list[dict]:
        """Analyze files sequentially (single core)."""
        results = []
        for i, file_info in enumerate(files):
            if progress_callback:
                progress_callback(i + 1, total, file_info['filename'])

            try:
                result = self.analyze_file(file_info['path'], image_scale)
                results.append(result)
            except Exception as e:
                results.append({
                    'filepath': file_info['path'],
                    'filename': file_info['filename'],
                    'metrics': None,
                    'error': str(e)
                })
        return results

    def _analyze_parallel(
        self,
        files: list[dict],
        total: int,
        workers: int,
        progress_callback: Optional[Callable],
        image_scale: Optional[float] = None
    ) -> list[dict]:
        """Analyze files in parallel using multiple cores."""
        # Prepare arguments for worker function (including image_scale)
        args_list = [
            (f['path'], self.fwhm_estimate, self.threshold_sigma, self.max_stars, image_scale)
            for f in files
        ]

        results = []
        completed = 0

        # Use multiprocessing pool
        with Pool(processes=workers) as pool:
            # Use imap to get results as they complete
            for result in pool.imap(_analyze_single_file, args_list):
                completed += 1
                results.append(result)

                if progress_callback:
                    progress_callback(completed, total, result['filename'])

        return results

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
            if r.get('metrics') and metric in r['metrics']:
                values.append(r['metrics'][metric])
            else:
                values.append(np.nan)

        values = np.array(values)
        return self.stats_calc.get_outlier_indices(values, sigma_threshold)
