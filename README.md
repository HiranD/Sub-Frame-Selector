# SubFrame Selector

A Python GUI tool for astrophotographers to analyze and select subframes based on quality metrics.

## Features

- **Load FITS files** from a folder
- **Analyze subframes** for quality metrics:
  - FWHM (star sharpness)
  - Eccentricity (star roundness)
  - SNR (signal-to-noise ratio)
  - Star Count
  - Background (brightness level)
- **Interactive plot** with sigma bands for outlier detection
- **Click-to-select** bad frames on the plot
- **Delete to Recycle Bin** (recoverable)

## Screenshot

```
+------------------------------------------------------------------+
|  SubFrame Selector                                               |
+------------------------------------------------------------------+
|  [Open Folder]  [Analyze]  [Delete Selected]   Metric: [FWHM ▼]  |
+--------------------+---------------------------------------------+
|                    |                                             |
|  File List         |    +2σ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─              |
|  ☑ frame_001.fits |        ░░░░░░░░░░░░░░░░░░░░░░░              |
|  ☑ frame_002.fits |   3.5  ▒▒▒●▒▒●▒▒▒●▒▒▒▒▒▒▒▒▒▒               |
|  ☐ frame_003.fits |        ▒▒●▒▒▒▒▒▒▒▒●▒▒●▒▒▒▒▒▒               |
|  ☐ frame_004.fits |   3.0  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒               |
|  ☑ frame_005.fits |        ░░░░░░░░░░░░░░░░░░░░░░░              |
|                    |    -2σ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─              |
|  Selected: 2       |              Frame Index                    |
+--------------------+---------------------------------------------+
```

## Installation

```bash
# Clone or download the project
cd sub-frame-selector

# Install dependencies
pip install -r requirements.txt
```

## Requirements

- Python 3.10+
- customtkinter
- matplotlib
- astropy
- photutils
- numpy
- scipy
- send2trash

## Usage

```bash
python run.py
```

1. **Open Folder** - Select a folder containing FITS files
2. **Analyze** - Calculate quality metrics for all frames
3. **Select Metric** - Choose which metric to display (FWHM, Eccentricity, etc.)
4. **Click Points** - Click on outlier points in the plot to mark for deletion
5. **Delete Selected** - Move bad frames to Recycle Bin

## How It Works

### Sigma Bands
The plot shows statistical boundaries:
- **Dark gray band**: ±1σ from median (good frames)
- **Light gray band**: ±1σ to ±2σ (marginal)
- **Outside bands**: Outliers (bad frames)

### Metrics Explained

| Metric | Good | Bad | Indicates |
|--------|------|-----|-----------|
| FWHM | Low | High | Focus/seeing quality |
| Eccentricity | Low (<0.5) | High (>0.6) | Tracking errors |
| SNR | High | Low | Image noise |
| Star Count | Consistent | Low | Clouds/obstructions |
| Background | Low/stable | High | Moonlight/twilight |

## Project Structure

```
sub-frame-selector/
├── src/
│   ├── analysis/       # FITS reading, star detection, metrics
│   │   ├── fits_reader.py
│   │   ├── star_detector.py
│   │   ├── metrics.py
│   │   ├── statistics.py
│   │   └── analyzer.py
│   └── gui/            # CustomTkinter UI
│       ├── app.py
│       ├── toolbar.py
│       ├── file_panel.py
│       └── plot_panel.py
├── docs/
│   ├── use-case.md
│   └── implementation-plan.md
├── requirements.txt
├── run.py
└── README.md
```

## License

MIT
