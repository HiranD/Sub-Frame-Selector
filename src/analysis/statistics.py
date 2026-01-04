"""Statistical calculations for outlier detection and sigma bands."""

import numpy as np
from typing import Optional


class StatisticsCalculator:
    """Calculates statistical bounds for outlier detection using MAD."""

    # Scale factor to convert MAD to standard deviation estimate
    # For normal distribution: sigma = MAD * 1.4826
    MAD_SCALE_FACTOR = 1.4826

    def calculate_bands(self, values: np.ndarray) -> dict:
        """
        Calculate median and sigma bands for a set of values.

        Uses Median Absolute Deviation (MAD) for robust sigma estimation.
        MAD is more resistant to outliers than standard deviation.

        Args:
            values: 1D numpy array of metric values

        Returns:
            Dict with:
            {
                'median': float,
                'sigma': float,
                'mad': float,
                'band_1sigma': (low, high),
                'band_2sigma': (low, high),
                'min': float,
                'max': float
            }
        """
        if len(values) == 0:
            return self._empty_result()

        values = np.asarray(values, dtype=np.float64)

        # Remove NaN/Inf values
        valid_mask = np.isfinite(values)
        if not np.any(valid_mask):
            return self._empty_result()

        values = values[valid_mask]

        # Calculate statistics
        median = float(np.median(values))
        mad = self.median_absolute_deviation(values)
        sigma = mad * self.MAD_SCALE_FACTOR

        # Handle edge case where all values are identical
        if sigma == 0:
            sigma = 0.001  # Small non-zero value

        return {
            'median': median,
            'sigma': sigma,
            'mad': mad,
            'band_1sigma': (median - sigma, median + sigma),
            'band_2sigma': (median - 2 * sigma, median + 2 * sigma),
            'min': float(np.min(values)),
            'max': float(np.max(values))
        }

    def median_absolute_deviation(self, values: np.ndarray) -> float:
        """
        Calculate Median Absolute Deviation.

        MAD = median(|xi - median(x)|)

        Args:
            values: 1D numpy array

        Returns:
            MAD value
        """
        if len(values) == 0:
            return 0.0

        median = np.median(values)
        mad = np.median(np.abs(values - median))
        return float(mad)

    def is_outlier(
        self,
        value: float,
        stats: dict,
        sigma_threshold: float = 2.0
    ) -> bool:
        """
        Check if a value is an outlier based on sigma threshold.

        Args:
            value: Value to check
            stats: Statistics dict from calculate_bands()
            sigma_threshold: Number of sigmas for outlier threshold

        Returns:
            True if value is outside the sigma threshold
        """
        if stats['sigma'] == 0:
            return False

        deviation = abs(value - stats['median'])
        return deviation > sigma_threshold * stats['sigma']

    def get_outlier_indices(
        self,
        values: np.ndarray,
        sigma_threshold: float = 2.0
    ) -> list[int]:
        """
        Get indices of outlier values.

        Args:
            values: 1D numpy array
            sigma_threshold: Number of sigmas for outlier threshold

        Returns:
            List of indices where values are outliers
        """
        stats = self.calculate_bands(values)
        outliers = []

        for i, val in enumerate(values):
            if np.isfinite(val) and self.is_outlier(val, stats, sigma_threshold):
                outliers.append(i)

        return outliers

    def get_sigma_deviation(self, value: float, stats: dict) -> float:
        """
        Calculate how many sigmas a value deviates from median.

        Args:
            value: Value to check
            stats: Statistics dict from calculate_bands()

        Returns:
            Number of sigmas (can be negative for below median)
        """
        if stats['sigma'] == 0:
            return 0.0

        return (value - stats['median']) / stats['sigma']

    def _empty_result(self) -> dict:
        """Return empty statistics result."""
        return {
            'median': 0.0,
            'sigma': 0.0,
            'mad': 0.0,
            'band_1sigma': (0.0, 0.0),
            'band_2sigma': (0.0, 0.0),
            'min': 0.0,
            'max': 0.0
        }


def calculate_all_metric_stats(metrics_list: list[dict]) -> dict:
    """
    Calculate statistics for all metrics across multiple frames.

    Args:
        metrics_list: List of metric dicts from MetricsCalculator.calculate_all()
                     [{'fwhm': ..., 'eccentricity': ..., ...}, ...]

    Returns:
        Dict mapping metric name to its statistics:
        {
            'fwhm': {'median': ..., 'sigma': ..., 'band_1sigma': ..., ...},
            'fwhm_arcsec': {...} (if available),
            'eccentricity': {...},
            ...
        }
    """
    if not metrics_list:
        return {}

    calc = StatisticsCalculator()
    metric_names = ['fwhm', 'eccentricity', 'snr', 'star_count', 'background']
    result = {}

    for metric in metric_names:
        values = np.array([m.get(metric, 0) for m in metrics_list])
        result[metric] = calc.calculate_bands(values)

    # Add fwhm_arcsec statistics if available
    fwhm_arcsec_values = [m.get('fwhm_arcsec') for m in metrics_list]
    if any(v is not None for v in fwhm_arcsec_values):
        # Replace None with NaN for numpy
        values = np.array([v if v is not None else np.nan for v in fwhm_arcsec_values])
        result['fwhm_arcsec'] = calc.calculate_bands(values)

    return result
