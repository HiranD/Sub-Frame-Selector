# SubFrame Selector - Implementation Plan

## 1. Project Structure

```
sub-frame-selector/
├── docs/
│   ├── use-case.md              # Use case document
│   └── implementation-plan.md   # This file
├── src/
│   ├── __init__.py
│   ├── main.py                  # Application entry point
│   ├── gui/
│   │   ├── __init__.py
│   │   ├── app.py               # Main application window
│   │   ├── file_panel.py        # File list sidebar
│   │   ├── plot_panel.py        # Matplotlib plot with sigma bands
│   │   └── toolbar.py           # Top toolbar buttons
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── analyzer.py          # Main orchestrator with parallel processing
│   │   ├── fits_reader.py       # FITS file loading
│   │   ├── star_detector.py     # Star detection (DAOStarFinder)
│   │   ├── metrics.py           # FWHM, Eccentricity, SNR, etc.
│   │   └── statistics.py        # Median, sigma bands calculation
│   └── utils/
│       └── __init__.py
├── tests/
│   └── __init__.py
├── requirements.txt
├── run.py                       # Entry point script
└── README.md
```

---

## 2. Dependencies

```txt
# requirements.txt
customtkinter>=5.2.0      # Modern Tkinter GUI
matplotlib>=3.7.0         # Plotting with interactive events
astropy>=5.3.0            # FITS file handling
photutils>=1.9.0          # Star detection, PSF fitting
numpy>=1.24.0             # Numerical operations
scipy>=1.11.0             # Statistical functions
send2trash>=1.8.0         # Cross-platform recycle bin
```

---

## 3. Module Specifications

### 3.1 `src/analysis/fits_reader.py`

**Purpose**: Load FITS files and extract image data

```python
class FITSReader:
    def load_file(self, filepath: str) -> np.ndarray:
        """Load single FITS file, return 2D image array."""

    def load_folder(self, folder_path: str) -> list[dict]:
        """Scan folder for .fits/.fit files."""

    def get_header(self, filepath: str) -> dict:
        """Extract FITS header metadata."""
```

---

### 3.2 `src/analysis/star_detector.py`

**Purpose**: Detect stars in image and fit PSF models

```python
class StarDetector:
    def __init__(self, fwhm_estimate=5.0, threshold_sigma=5.0, max_stars=500):
        """Configure detection parameters."""

    def detect_stars(self, image: np.ndarray) -> list[dict]:
        """Find stars using DAOStarFinder."""

    def fit_psf(self, image: np.ndarray, stars: list[dict]) -> list[dict]:
        """Fit 2D Gaussian to each star."""
```

---

### 3.3 `src/analysis/metrics.py`

**Purpose**: Calculate quality metrics for each frame

```python
class MetricsCalculator:
    def calculate_all(self, image: np.ndarray, psf_results: list[dict]) -> dict:
        """Returns: {fwhm, eccentricity, snr, star_count, background}"""

    def calculate_fwhm(self, psf_results: list[dict]) -> float
    def calculate_eccentricity(self, psf_results: list[dict]) -> float
    def calculate_snr(self, image: np.ndarray, psf_results: list[dict]) -> float
    def calculate_background(self, image: np.ndarray) -> float
```

---

### 3.4 `src/analysis/statistics.py`

**Purpose**: Calculate sigma bands for plotting

```python
class StatisticsCalculator:
    def calculate_bands(self, values: np.ndarray) -> dict:
        """Returns: {median, sigma, band_1sigma, band_2sigma}"""

    def median_absolute_deviation(self, values: np.ndarray) -> float:
        """MAD = median(|xi - median(x)|), sigma = MAD * 1.4826"""
```

---

### 3.5 `src/analysis/analyzer.py`

**Purpose**: Main orchestrator with parallel processing

```python
class SubframeAnalyzer:
    def __init__(self, fwhm_estimate=5.0, threshold_sigma=5.0,
                 max_stars=500, num_workers=None):
        """
        num_workers: Number of CPU cores to use (default: half of available)
        """

    def analyze_file(self, filepath: str) -> dict:
        """Analyze single FITS file."""

    def analyze_folder(self, folder_path: str, progress_callback=None,
                       use_parallel=True) -> dict:
        """
        Analyze all FITS files in folder.
        Uses multiprocessing.Pool for parallel execution.
        Returns: {folder, total_files, results, statistics, workers_used}
        """

    def _analyze_sequential(self, files, total, progress_callback) -> list
    def _analyze_parallel(self, files, total, workers, progress_callback) -> list
```

**Parallel Processing**:
- Uses `multiprocessing.Pool` to process multiple files simultaneously
- Number of workers configurable via slider (1 to max cores)
- Default: half of available CPU cores

---

### 3.6 `src/gui/app.py`

**Purpose**: Main application window

```python
class SubframeSelectorApp(ctk.CTk):
    def __init__(self):
        """Initialize window, layout, and components."""

    def _setup_layout(self):
        """
        Layout:
        +------------------------------------------+
        |              Toolbar                     |
        +-------------+----------------------------+
        |  File Panel |      Plot Panel            |
        |   (30%)     |       (70%)                |
        +-------------+----------------------------+
        |              Status Bar                  |
        +------------------------------------------+
        """

    def on_open_folder(self): """Handle folder selection."""
    def on_analyze(self): """Trigger analysis with progress."""
    def on_delete_selected(self): """Delete selected files."""
    def on_metric_changed(self, metric): """Update plot for new metric."""
    def on_plot_point_click(self, index, is_selected): """Handle plot click."""
```

---

### 3.7 `src/gui/toolbar.py`

**Purpose**: Top toolbar with action buttons and settings

```python
class Toolbar(ctk.CTkFrame):
    def __init__(self, parent, callbacks: dict):
        """
        callbacks = {
            'open_folder': Callable,
            'analyze': Callable,
            'delete_selected': Callable,
            'metric_changed': Callable
        }
        """

    # UI Elements:
    # [Open Folder] [Analyze] [Delete Selected (N)]  Metric:[▼]  Cores:[====] 4/8

    def set_delete_count(self, count: int): """Update delete button."""
    def set_analyzing(self, is_analyzing: bool): """Show/hide progress."""
    def get_selected_metric(self) -> str: """Get current metric."""
    def get_num_cores(self) -> int: """Get selected CPU cores."""
```

---

### 3.8 `src/gui/file_panel.py`

**Purpose**: File list sidebar with checkboxes

```python
class FilePanel(ctk.CTkFrame):
    def load_files(self, file_list: list[dict]): """Populate list."""
    def set_metrics(self, results: list[dict]): """Show metrics."""
    def set_selected(self, indices: set[int]): """Update selection."""
    def remove_files(self, indices: list[int]): """Remove after delete."""
```

---

### 3.9 `src/gui/plot_panel.py`

**Purpose**: Interactive matplotlib plot with sigma bands

```python
class PlotPanel(ctk.CTkFrame):
    def plot_metric(self, values, metric_name, statistics,
                    filenames, selected_indices):
        """
        Draw scatter plot with:
        - Dark gray band: ±1σ
        - Light gray band: ±1σ to ±2σ
        - Dashed lines: ±2σ boundaries
        - Red points: Selected for deletion
        """

    def _on_click(self, event): """Handle click, toggle selection."""
    def _on_hover(self, event): """Show tooltip with filename."""
    def update_selection(self, selected_indices): """Refresh colors."""
```

---

## 4. Implementation Phases

### Phase 1: Core Analysis Engine ✅
**Files**: `fits_reader.py`, `star_detector.py`, `metrics.py`, `statistics.py`, `analyzer.py`

| Step | Task | Status |
|------|------|--------|
| 1.1 | FITS loading with astropy | Done |
| 1.2 | Star detection with DAOStarFinder | Done |
| 1.3 | 2D Gaussian fitting for FWHM | Done |
| 1.4 | Eccentricity calculation | Done |
| 1.5 | SNR estimation | Done |
| 1.6 | Background measurement | Done |
| 1.7 | Sigma band statistics (MAD-based) | Done |
| 1.8 | Parallel processing support | Done |

---

### Phase 2: Basic GUI Shell ✅
**Files**: `app.py`, `toolbar.py`, `file_panel.py`

| Step | Task | Status |
|------|------|--------|
| 2.1 | Main window with CustomTkinter | Done |
| 2.2 | Toolbar with buttons | Done |
| 2.3 | CPU cores slider | Done |
| 2.4 | File panel with scrollable list | Done |
| 2.5 | Folder selection and file loading | Done |

---

### Phase 3: Plot Panel with Sigma Bands ✅
**Files**: `plot_panel.py`

| Step | Task | Status |
|------|------|--------|
| 3.1 | Embed matplotlib in CustomTkinter | Done |
| 3.2 | Scatter plot with sigma bands | Done |
| 3.3 | Click-to-select on points | Done |
| 3.4 | Hover tooltips | Done |
| 3.5 | Metric dropdown selector | Done |
| 3.6 | Selection sync with file panel | Done |

---

### Phase 4: Integration and Polish ✅
**Files**: All

| Step | Task | Status |
|------|------|--------|
| 4.1 | Connect analysis engine to GUI | Done |
| 4.2 | Progress updates during analysis | Done |
| 4.3 | Parallel processing with configurable cores | Done |
| 4.4 | Delete with confirmation (recycle bin) | Done |
| 4.5 | Status bar with statistics | Done |

---

## 5. Key Algorithms

### 5.1 Parallel File Processing

```python
from multiprocessing import Pool, cpu_count

def analyze_folder(files, num_workers):
    with Pool(processes=num_workers) as pool:
        results = pool.imap(analyze_single_file, files)
        for result in results:
            yield result  # Progress updates as files complete
```

### 5.2 Sigma Bands (MAD-based)

```python
def calculate_sigma_bands(values):
    median = np.median(values)
    mad = np.median(np.abs(values - median))
    sigma = mad * 1.4826  # Scale factor for Gaussian

    return {
        'median': median,
        'sigma': sigma,
        'band_1sigma': (median - sigma, median + sigma),
        'band_2sigma': (median - 2*sigma, median + 2*sigma)
    }
```

### 5.3 Eccentricity Calculation

```python
def calculate_eccentricity(fwhm_x, fwhm_y):
    a = max(fwhm_x, fwhm_y)  # semi-major
    b = min(fwhm_x, fwhm_y)  # semi-minor
    return np.sqrt(1 - (b / a) ** 2)
```

---

## 6. UI Layout

```
+-----------------------------------------------------------------------+
|  SubFrame Selector                                              [_][X] |
+-----------------------------------------------------------------------+
| [Open Folder] [Analyze] [Delete Selected (3)]  Metric:[FWHM▼] Cores:[==] 4/8 |
+---------------------+-------------------------------------------------+
|                     |                                                 |
|  folder/            |    +2σ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─     |
|  ----------------   |        ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░       |
|  ☑ frame_001.fits  |   3.5  ▒▒▒▒▒●▒▒●▒▒▒●▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒       |
|  ☑ frame_002.fits  |        ▒▒●▒▒▒▒▒▒▒▒▒▒●▒▒●▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒       |
|  ☐ frame_003.fits X |   3.0  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒       |
|  ☑ frame_004.fits  |        ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░       |
|  ☐ frame_005.fits X |    -2σ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─     |
|  ...                |                    ●                           |
|                     |   2.0                                          |
|  ----------------   |        10   20   30   40   50   60   70        |
|  Total: 94 files    |              Frame Index                       |
|  Selected: 2 X      +-------------------------------------------------+
+---------------------+  Median: 3.12  σ: 0.24  |  Range: 2.45 - 4.89  |
+-----------------------------------------------------------------------+
| Analysis complete. 94 files analyzed using 4 core(s).                 |
+-----------------------------------------------------------------------+
```

---

## 7. Success Criteria

- [x] Load 100+ FITS files from folder
- [x] Calculate 5 metrics (FWHM, Eccentricity, SNR, Star Count, Background)
- [x] Parallel processing with configurable CPU cores
- [x] Display interactive plot with sigma bands (±1σ, ±2σ)
- [x] Click points to select for deletion
- [x] Selection sync between plot and file list
- [x] Delete files to recycle bin
- [x] Works on macOS, Windows, Linux
