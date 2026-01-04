"""Star detection and PSF fitting."""

import numpy as np
from scipy.optimize import curve_fit
from scipy.ndimage import gaussian_filter
from typing import Optional


class StarDetector:
    """Detects stars and measures their properties using PSF fitting."""

    def __init__(
        self,
        fwhm_estimate: float = 5.0,
        threshold_sigma: float = 5.0,
        max_stars: int = 500,
        box_size: int = 15
    ):
        """
        Initialize star detector.

        Args:
            fwhm_estimate: Expected FWHM of stars in pixels
            threshold_sigma: Detection threshold in sigma above background
            max_stars: Maximum number of stars to detect
            box_size: Size of box for PSF fitting (odd number)
        """
        self.fwhm_estimate = fwhm_estimate
        self.threshold_sigma = threshold_sigma
        self.max_stars = max_stars
        self.box_size = box_size if box_size % 2 == 1 else box_size + 1

    def detect_stars(self, image: np.ndarray) -> list[dict]:
        """
        Detect stars in image using DAOStarFinder algorithm.

        Args:
            image: 2D numpy array of image data

        Returns:
            List of dicts with star info:
            [{'x': float, 'y': float, 'flux': float, 'peak': float}, ...]
        """
        try:
            from photutils.detection import DAOStarFinder
            from photutils.background import Background2D, MedianBackground
            return self._detect_with_photutils(image)
        except ImportError:
            # Fallback to simple detection if photutils not available
            return self._detect_simple(image)

    def _detect_with_photutils(self, image: np.ndarray) -> list[dict]:
        """Detect stars using photutils DAOStarFinder."""
        from photutils.detection import DAOStarFinder
        from photutils.background import Background2D, MedianBackground

        # Estimate background
        try:
            bkg = Background2D(
                image,
                box_size=(50, 50),
                filter_size=(3, 3),
                bkg_estimator=MedianBackground()
            )
            image_sub = image - bkg.background
            bkg_rms = bkg.background_rms_median
        except Exception:
            # Fallback for small images or edge cases
            bkg_value = np.median(image)
            image_sub = image - bkg_value
            bkg_rms = np.std(image[image < np.percentile(image, 90)])

        # Detect stars
        threshold = self.threshold_sigma * bkg_rms
        daofind = DAOStarFinder(fwhm=self.fwhm_estimate, threshold=threshold)
        sources = daofind(image_sub)

        if sources is None:
            return []

        # Sort by flux and limit number
        sources.sort('flux', reverse=True)
        if len(sources) > self.max_stars:
            sources = sources[:self.max_stars]

        # Convert to list of dicts
        stars = []
        for row in sources:
            stars.append({
                'x': float(row['xcentroid']),
                'y': float(row['ycentroid']),
                'flux': float(row['flux']),
                'peak': float(row['peak'])
            })

        return stars

    def _detect_simple(self, image: np.ndarray) -> list[dict]:
        """Simple peak detection fallback when photutils not available."""
        from scipy.ndimage import maximum_filter, label

        # Estimate background
        bkg = np.median(image)
        std = np.std(image[image < np.percentile(image, 90)])

        # Smooth image slightly
        smoothed = gaussian_filter(image - bkg, sigma=self.fwhm_estimate / 2.355)

        # Find local maxima
        threshold = self.threshold_sigma * std
        data_max = maximum_filter(smoothed, size=int(self.fwhm_estimate * 2))
        peaks = (smoothed == data_max) & (smoothed > threshold)

        # Label connected regions
        labeled, num_features = label(peaks)

        stars = []
        for i in range(1, min(num_features + 1, self.max_stars + 1)):
            region = (labeled == i)
            coords = np.where(region)
            if len(coords[0]) > 0:
                y_center = np.mean(coords[0])
                x_center = np.mean(coords[1])
                peak_val = image[int(y_center), int(x_center)]
                stars.append({
                    'x': float(x_center),
                    'y': float(y_center),
                    'flux': float(np.sum(image[region] - bkg)),
                    'peak': float(peak_val)
                })

        # Sort by flux
        stars.sort(key=lambda s: s['flux'], reverse=True)
        return stars[:self.max_stars]

    def fit_psf(self, image: np.ndarray, stars: list[dict]) -> list[dict]:
        """
        Fit 2D Gaussian PSF to each detected star.

        Args:
            image: 2D image array
            stars: List of star positions from detect_stars()

        Returns:
            List of dicts with PSF parameters:
            [{'fwhm_x': float, 'fwhm_y': float, 'amplitude': float,
              'x': float, 'y': float, 'fit_success': bool}, ...]
        """
        results = []
        half_box = self.box_size // 2

        for star in stars:
            x, y = int(round(star['x'])), int(round(star['y']))

            # Check bounds
            if (x - half_box < 0 or x + half_box >= image.shape[1] or
                y - half_box < 0 or y + half_box >= image.shape[0]):
                continue

            # Extract cutout
            cutout = image[y - half_box:y + half_box + 1,
                          x - half_box:x + half_box + 1].copy()

            # Fit 2D Gaussian
            fit_result = self._fit_gaussian_2d(cutout)

            if fit_result is not None:
                results.append({
                    'x': star['x'],
                    'y': star['y'],
                    'fwhm_x': fit_result['fwhm_x'],
                    'fwhm_y': fit_result['fwhm_y'],
                    'amplitude': fit_result['amplitude'],
                    'fit_success': True
                })
            else:
                # Use estimate if fit fails
                results.append({
                    'x': star['x'],
                    'y': star['y'],
                    'fwhm_x': self.fwhm_estimate,
                    'fwhm_y': self.fwhm_estimate,
                    'amplitude': star['peak'],
                    'fit_success': False
                })

        return results

    def _fit_gaussian_2d(self, cutout: np.ndarray) -> Optional[dict]:
        """
        Fit a 2D Gaussian to a star cutout.

        Args:
            cutout: Small 2D array centered on star

        Returns:
            Dict with 'fwhm_x', 'fwhm_y', 'amplitude' or None if fit fails
        """
        size = cutout.shape[0]
        center = size // 2

        # Create coordinate grids
        y, x = np.mgrid[0:size, 0:size]

        # Initial parameter guesses
        offset = np.percentile(cutout, 10)
        amplitude = cutout[center, center] - offset
        sigma_guess = self.fwhm_estimate / 2.355

        try:
            # Flatten for curve_fit
            xdata = np.vstack([x.ravel(), y.ravel()])
            ydata = cutout.ravel()

            # Initial parameters: amplitude, x0, y0, sigma_x, sigma_y, offset
            p0 = [amplitude, center, center, sigma_guess, sigma_guess, offset]

            # Bounds
            bounds = (
                [0, 0, 0, 0.5, 0.5, -np.inf],  # Lower bounds
                [np.inf, size, size, size/2, size/2, np.inf]  # Upper bounds
            )

            popt, _ = curve_fit(
                self._gaussian_2d,
                xdata,
                ydata,
                p0=p0,
                bounds=bounds,
                maxfev=1000
            )

            amplitude, x0, y0, sigma_x, sigma_y, offset = popt

            # Convert sigma to FWHM
            fwhm_x = 2.355 * sigma_x
            fwhm_y = 2.355 * sigma_y

            # Sanity check
            if fwhm_x < 0.5 or fwhm_y < 0.5 or fwhm_x > size or fwhm_y > size:
                return None

            return {
                'fwhm_x': fwhm_x,
                'fwhm_y': fwhm_y,
                'amplitude': amplitude
            }

        except Exception:
            return None

    @staticmethod
    def _gaussian_2d(xy, amplitude, x0, y0, sigma_x, sigma_y, offset):
        """2D Gaussian function for curve fitting."""
        x, y = xy
        return offset + amplitude * np.exp(
            -((x - x0)**2 / (2 * sigma_x**2) + (y - y0)**2 / (2 * sigma_y**2))
        )
