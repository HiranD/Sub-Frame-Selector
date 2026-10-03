"""FITS file reading and preprocessing."""

import os
from pathlib import Path
from typing import Optional
import numpy as np
from astropy.io import fits


class FITSReader:
    """Handles FITS file loading and basic preprocessing."""

    SUPPORTED_EXTENSIONS = {'.fits', '.fit', '.fts'}

    def load_file(self, filepath: str) -> np.ndarray:
        """
        Load a single FITS file and return the image data.

        Args:
            filepath: Path to the FITS file

        Returns:
            2D numpy array of image data (float32)

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If no image data found in FITS file
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"FITS file not found: {filepath}")

        with fits.open(filepath) as hdul:
            # Find the first HDU with image data
            for hdu in hdul:
                if hdu.data is not None and len(hdu.data.shape) >= 2:
                    # Handle 3D data (e.g., RGB) by taking first channel
                    if len(hdu.data.shape) == 3:
                        data = hdu.data[0]
                    else:
                        data = hdu.data

                    return data.astype(np.float32)

        raise ValueError(f"No image data found in FITS file: {filepath}")

    def load_with_header(self, filepath: str) -> tuple[np.ndarray, fits.Header]:
        """
        Load image data and its own header in a single open.

        Used by the analysis worker, which needs both the pixels and the
        header (for image scale and the sidecar) and should not pay for two
        opens of a 50 MB frame.

        The header returned belongs to the same HDU the data came from, so it
        always describes the pixels being analyzed.

        Args:
            filepath: Path to the FITS file

        Returns:
            Tuple of (2D float32 array, FITS header)

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If no image data found in FITS file
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"FITS file not found: {filepath}")

        with fits.open(filepath) as hdul:
            for hdu in hdul:
                if hdu.data is not None and len(hdu.data.shape) >= 2:
                    if len(hdu.data.shape) == 3:
                        data = hdu.data[0]
                    else:
                        data = hdu.data

                    return data.astype(np.float32), hdu.header.copy()

        raise ValueError(f"No image data found in FITS file: {filepath}")

    def read_image_header(self, filepath: str) -> Optional[fits.Header]:
        """
        Read the header of the image-bearing HDU without loading pixel data.

        Selects the HDU by its NAXIS card rather than by touching `.data`,
        which would defeat astropy's lazy loading. This must pick the same HDU
        as load_with_header so header fingerprints stay comparable.

        Returns:
            The header, or None if no image HDU is present
        """
        with fits.open(filepath) as hdul:
            for hdu in hdul:
                if hdu.header.get('NAXIS', 0) >= 2:
                    return hdu.header.copy()
        return None

    def load_folder(self, folder_path: str) -> list[dict]:
        """
        Scan folder for FITS files and return file info.

        Args:
            folder_path: Path to folder containing FITS files

        Returns:
            List of dicts: [{'path': str, 'filename': str}, ...]
            Sorted by filename
        """
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        if not folder.is_dir():
            raise ValueError(f"Path is not a directory: {folder_path}")

        files = []
        for filepath in folder.iterdir():
            if filepath.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                files.append({
                    'path': str(filepath),
                    'filename': filepath.name,
                    'folder': str(folder),
                    'folder_name': folder.name
                })

        # Sort by filename
        files.sort(key=lambda x: x['filename'])
        return files

    def get_header(self, filepath: str) -> dict:
        """
        Extract FITS header metadata.

        Args:
            filepath: Path to the FITS file

        Returns:
            Dictionary of header key-value pairs
        """
        filepath = Path(filepath)
        with fits.open(filepath) as hdul:
            # Get header from primary HDU or first HDU with data
            for hdu in hdul:
                if hdu.header:
                    return dict(hdu.header)
        return {}

    def get_image_info(self, filepath: str) -> dict:
        """
        Get basic image information without loading full data.

        Args:
            filepath: Path to the FITS file

        Returns:
            Dict with 'width', 'height', 'dtype', 'header_count'
        """
        filepath = Path(filepath)
        with fits.open(filepath) as hdul:
            for hdu in hdul:
                if hdu.data is not None and len(hdu.data.shape) >= 2:
                    shape = hdu.data.shape
                    if len(shape) == 3:
                        height, width = shape[1], shape[2]
                    else:
                        height, width = shape[0], shape[1]

                    return {
                        'width': width,
                        'height': height,
                        'dtype': str(hdu.data.dtype),
                        'header_count': len(hdu.header)
                    }

        return {'width': 0, 'height': 0, 'dtype': 'unknown', 'header_count': 0}

    def get_imaging_params(self, filepath: str) -> dict:
        """
        Extract imaging parameters for image scale calculation.

        Args:
            filepath: Path to the FITS file

        Returns:
            Dict with 'pixel_size_um', 'focal_length_mm', 'aperture_mm',
            'binning', 'image_scale'. Values are None if not found in header.
            image_scale is in arcsec/pixel if calculable.
        """
        return self.imaging_params_from_header(self.get_header(filepath))

    def imaging_params_from_header(self, header) -> dict:
        """
        Extract imaging parameters from an already-read header.

        Split out from get_imaging_params so the analysis worker, which has
        the header in hand already, doesn't reopen the file just to compute
        the image scale.

        Args:
            header: FITS header (or plain dict of header cards)

        Returns:
            Same dict as get_imaging_params
        """
        # Common header keywords for pixel size (in microns).
        # PIXSCALE is deliberately absent: by convention it holds arcsec/pixel,
        # not microns, so treating it as a pixel size yields a wildly wrong scale.
        pixel_size_keys = ['XPIXSZ', 'PIXSIZE', 'PIXSIZE1', 'XPIXELSZ']
        pixel_size = None
        for key in pixel_size_keys:
            if key in header and header[key]:
                try:
                    pixel_size = float(header[key])
                    break
                except (ValueError, TypeError):
                    continue

        # Common header keywords for focal length (in mm)
        focal_length_keys = ['FOCALLEN', 'FOCAL', 'FOCALLENGTH', 'FL']
        focal_length = None
        for key in focal_length_keys:
            if key in header and header[key]:
                try:
                    focal_length = float(header[key])
                    break
                except (ValueError, TypeError):
                    continue

        # Common header keywords for aperture diameter (in mm)
        aperture_keys = ['APTDIA', 'DIAMETER', 'APERTURE', 'APTDIAMM']
        aperture = None
        for key in aperture_keys:
            if key in header and header[key]:
                try:
                    aperture = float(header[key])
                    break
                except (ValueError, TypeError):
                    continue

        # Binning. Assumes XPIXSZ is the unbinned sensor pixel size, which is
        # the ASCOM/ZWO convention; a few writers instead pre-multiply it, in
        # which case binned frames would be double-counted here.
        binning_keys = ['XBINNING', 'BINNING', 'XBIN']
        binning = 1
        for key in binning_keys:
            if key in header and header[key]:
                try:
                    value = int(float(header[key]))
                    if value >= 1:
                        binning = value
                        break
                except (ValueError, TypeError):
                    continue

        # Calculate image scale if we have pixel size and focal length
        # Formula: scale (arcsec/pixel) = (pixel_size_um * binning / focal_length_mm) * 206.265
        image_scale = None
        if pixel_size and focal_length and focal_length > 0:
            image_scale = (pixel_size * binning / focal_length) * 206.265

        return {
            'pixel_size_um': pixel_size,
            'focal_length_mm': focal_length,
            'aperture_mm': aperture,
            'binning': binning,
            'image_scale': image_scale  # arcsec/pixel
        }
