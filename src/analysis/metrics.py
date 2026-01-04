"""Quality metrics calculation for subframes."""

import numpy as np
from typing import Optional
from scipy import stats


class MetricsCalculator:
    """Calculates frame quality metrics from detected stars."""

    def calculate_all(
        self,
        image: np.ndarray,
        psf_results: list[dict],
        image_scale: Optional[float] = None
    ) -> dict:
        """
        Calculate all metrics for a single frame.

        Args:
            image: 2D image array
            psf_results: List of PSF fit results from StarDetector.fit_psf()
            image_scale: Image scale in arcsec/pixel (optional, from FITS header)

        Returns:
            Dict with all metrics:
            {
                'fwhm': float (pixels),
                'fwhm_arcsec': float or None (arcseconds, if image_scale provided),
                'eccentricity': float,
                'snr': float,
                'star_count': int,
                'background': float
            }
        """
        fwhm_pixels = self.calculate_fwhm(psf_results)
        fwhm_arcsec = fwhm_pixels * image_scale if image_scale else None

        return {
            'fwhm': fwhm_pixels,
            'fwhm_arcsec': fwhm_arcsec,
            'eccentricity': self.calculate_eccentricity(psf_results),
            'snr': self.calculate_snr(image, psf_results),
            'star_count': self.calculate_star_count(psf_results),
            'background': self.calculate_background(image)
        }

    def calculate_fwhm(self, psf_results: list[dict]) -> float:
        """
        Calculate median FWHM from all detected stars.

        Uses the geometric mean of FWHM_x and FWHM_y for each star,
        then takes the median across all stars.

        Args:
            psf_results: List of PSF fit results

        Returns:
            Median FWHM in pixels, or 0.0 if no valid stars
        """
        if not psf_results:
            return 0.0

        fwhm_values = []
        for star in psf_results:
            if star.get('fit_success', True):
                # Geometric mean of x and y FWHM
                fwhm = np.sqrt(star['fwhm_x'] * star['fwhm_y'])
                fwhm_values.append(fwhm)

        if not fwhm_values:
            return 0.0

        return float(np.median(fwhm_values))

    def calculate_eccentricity(self, psf_results: list[dict]) -> float:
        """
        Calculate median eccentricity from all detected stars.

        Eccentricity = sqrt(1 - (b/a)^2) where a is major axis, b is minor axis.
        For stars: a = max(fwhm_x, fwhm_y), b = min(fwhm_x, fwhm_y)

        Args:
            psf_results: List of PSF fit results

        Returns:
            Median eccentricity (0=round, 1=line), or 0.0 if no valid stars
        """
        if not psf_results:
            return 0.0

        ecc_values = []
        for star in psf_results:
            if star.get('fit_success', True):
                fwhm_x = star['fwhm_x']
                fwhm_y = star['fwhm_y']

                # Major and minor axis
                a = max(fwhm_x, fwhm_y)
                b = min(fwhm_x, fwhm_y)

                # Avoid division by zero
                if a > 0:
                    ratio = b / a
                    # Clamp to valid range for sqrt
                    ratio_sq = min(ratio ** 2, 1.0)
                    eccentricity = np.sqrt(1 - ratio_sq)
                    ecc_values.append(eccentricity)

        if not ecc_values:
            return 0.0

        return float(np.median(ecc_values))

    def calculate_snr(
        self,
        image: np.ndarray,
        psf_results: list[dict]
    ) -> float:
        """
        Calculate Signal-to-Noise Ratio.

        SNR = mean(star_amplitude) / background_noise

        Args:
            image: 2D image array
            psf_results: List of PSF fit results

        Returns:
            SNR value, or 0.0 if cannot be calculated
        """
        if not psf_results:
            return 0.0

        # Get star amplitudes (signal)
        amplitudes = []
        for star in psf_results:
            if star.get('fit_success', True) and star.get('amplitude', 0) > 0:
                amplitudes.append(star['amplitude'])

        if not amplitudes:
            return 0.0

        mean_signal = np.mean(amplitudes)

        # Estimate background noise using sigma-clipped std
        background_noise = self._estimate_noise(image)

        if background_noise <= 0:
            return 0.0

        return float(mean_signal / background_noise)

    def calculate_star_count(self, psf_results: list[dict]) -> int:
        """
        Count number of successfully detected stars.

        Args:
            psf_results: List of PSF fit results

        Returns:
            Number of stars with successful PSF fits
        """
        if not psf_results:
            return 0

        count = sum(1 for star in psf_results if star.get('fit_success', True))
        return count

    def calculate_background(self, image: np.ndarray) -> float:
        """
        Calculate median background level.

        Uses sigma clipping to exclude stars and get true background.

        Args:
            image: 2D image array

        Returns:
            Median background value
        """
        # Sigma-clipped median for robust background estimate
        clipped = self._sigma_clip(image.ravel(), sigma=3.0)
        return float(np.median(clipped))

    def _estimate_noise(self, image: np.ndarray) -> float:
        """
        Estimate background noise using sigma-clipped standard deviation.

        Args:
            image: 2D image array

        Returns:
            Estimated noise (standard deviation)
        """
        # Use lower percentile region to avoid stars
        flat = image.ravel()
        clipped = self._sigma_clip(flat, sigma=3.0)

        if len(clipped) == 0:
            return 1.0

        return float(np.std(clipped))

    def _sigma_clip(
        self,
        data: np.ndarray,
        sigma: float = 3.0,
        max_iters: int = 5
    ) -> np.ndarray:
        """
        Iterative sigma clipping.

        Args:
            data: 1D array of values
            sigma: Number of standard deviations for clipping
            max_iters: Maximum number of iterations

        Returns:
            Clipped array with outliers removed
        """
        clipped = data.copy()

        for _ in range(max_iters):
            median = np.median(clipped)
            std = np.std(clipped)

            if std == 0:
                break

            mask = np.abs(clipped - median) < sigma * std
            new_clipped = clipped[mask]

            if len(new_clipped) == len(clipped):
                break

            clipped = new_clipped

        return clipped
