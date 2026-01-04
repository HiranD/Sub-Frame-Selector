# SubFrame Selector - Use Case Document

## 1. Overview

**Application Name**: SubFrame Selector

**Purpose**: A Python GUI tool for astrophotographers to analyze, visualize, and reject bad subframes from imaging sessions based on quality metrics.

**Problem Solved**: During astrophotography sessions, some captured frames are degraded by:
- Tracking errors (high eccentricity - elongated stars)
- Poor seeing/focus (high FWHM - bloated stars)
- Clouds passing (low star count, low SNR)
- Moonlight/twilight contamination (high background brightness)

Manually reviewing hundreds of frames is tedious. This tool automates quality measurement and provides visual selection for rejection.

---

## 2. User Personas

**Primary User**: Amateur/professional astrophotographer who:
- Captures 50-500+ subframes per imaging session
- Uses FITS format from dedicated astronomy cameras
- Wants to quickly identify and remove bad frames before stacking
- Has basic understanding of image quality metrics

---

## 3. Core Use Cases

### UC-1: Load Subframes

**Actor**: User
**Precondition**: User has a folder of FITS files from an imaging session

**Flow**:
1. User clicks "Open Folder" button
2. System opens folder selection dialog
3. User selects folder containing FITS files
4. System scans folder and lists all .fits/.fit files
5. System displays file count and list in sidebar

**Postcondition**: Files loaded and ready for analysis

---

### UC-2: Analyze Subframes

**Actor**: User
**Precondition**: FITS files are loaded

**Flow**:
1. User clicks "Analyze" button
2. System shows progress bar
3. For each FITS file, system calculates:
   - **Star Detection**: Find stars using DAOStarFinder or similar
   - **Star Count**: Total number of detected stars
   - **FWHM**: Mean Full Width at Half Maximum of stars
   - **Eccentricity**: Mean star elongation (a-b)/a
   - **SNR**: Signal-to-Noise Ratio estimation
   - **Background**: Median background level (brightness)
4. System stores metrics for each frame
5. System displays initial plot with default metric (FWHM)

**Postcondition**: All frames analyzed, metrics stored, plot displayed

---

### UC-3: Visualize Metrics

**Actor**: User
**Precondition**: Analysis complete

**Flow**:
1. User sees scatter plot: Frame Index (X) vs Metric Value (Y)
2. Plot displays:
   - All data points as dots
   - Median line (horizontal)
   - **Dark gray band**: ±1σ from median
   - **Light gray band**: ±1σ to ±2σ from median
   - **Dashed lines**: ±2σ boundaries
3. User selects different metric from dropdown (FWHM, Eccentricity, SNR, Stars, Brightness)
4. Plot updates to show selected metric with recalculated bands

**Postcondition**: User can visually identify outliers

---

### UC-4: Select Bad Frames

**Actor**: User
**Precondition**: Plot is displayed

**Flow**:
1. User identifies outlier points (outside gray bands)
2. User clicks on a data point in the plot
3. System highlights the point (changes color to red)
4. System marks corresponding file in file list with X
5. System updates "Selected for deletion: N frames" counter
6. User can click again to deselect
7. User can switch metrics and select more points

**Postcondition**: Bad frames marked for deletion

---

### UC-5: Delete Selected Frames

**Actor**: User
**Precondition**: One or more frames selected

**Flow**:
1. User clicks "Delete Selected" button
2. System shows confirmation dialog: "Move N files to Recycle Bin?"
3. User confirms
4. System moves each selected file to system recycle bin
5. System removes files from list and plot
6. System recalculates sigma bands for remaining frames
7. System updates plot

**Postcondition**: Bad frames moved to recycle bin, plot updated

---

## 4. UI Wireframe

```
+-------------------------------------------------------------------+
|  SubFrame Selector                                          [_][X] |
+-------------------------------------------------------------------+
|  [Open Folder]  [Analyze]  [Delete Selected (3)]   Metric: [FWHM] |
+------------------------+------------------------------------------+
|                        |  Metric: [FWHM           v]              |
|  Folder: /path/to/fits |                                          |
|  -------------------   |    +2s - - - - - - - - - - - - - - - -   |
|  [x] frame_001.fits    |        ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   |
|  [x] frame_002.fits    |   3.5  ▒▒▒▒▒●▒▒●▒▒▒●▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒   |
|  [ ] frame_003.fits X  |        ▒▒●▒▒▒▒▒▒▒▒▒▒●▒▒●▒▒▒▒▒▒▒▒▒▒▒▒   |
|  [x] frame_004.fits    |   3.0  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒   |
|  [ ] frame_005.fits X  |        ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   |
|  [x] frame_006.fits    |    -2s - - - - - - - - - - - - - - - -   |
|  [ ] frame_007.fits X  |                    ●                     | <- outlier
|  [x] frame_008.fits    |   2.0                                    |
|  ...                   |        10   20   30   40   50   60       |
|                        |              Frame Index                 |
|  -------------------   +------------------------------------------+
|  Total: 94 frames      |  Stats: Median=3.12  Sigma=0.24         |
|  Selected: 3 X         |  Range: 2.45 - 4.89                      |
+------------------------+------------------------------------------+
```

**Legend:**
- `▒▒▒` Dark gray band: ±1σ from median (good zone)
- `░░░` Light gray band: ±1σ to ±2σ (marginal zone)
- `- -` Dashed lines: ±2σ boundaries
- `●` Data points (frames)
- `X` Marked for deletion

---

## 5. Metric Definitions

| Metric | Description | Good Value | Bad Value |
|--------|-------------|------------|-----------|
| **FWHM** | Star width in pixels at half brightness | Low (tight stars) | High (bloated) |
| **Eccentricity** | Star elongation: (a-b)/a where a=major, b=minor axis | Low (<0.5, round) | High (>0.6, trails) |
| **SNR** | Signal-to-Noise Ratio of stars | High | Low (noisy) |
| **Stars** | Number of detected stars | High (consistent) | Low (clouds) |
| **Background** | Median background brightness | Low/consistent | High (moonlight) |

---

## 6. Statistical Bands Calculation

For each metric:

1. Calculate **median** of all values
2. Calculate **σ (sigma)** using Median Absolute Deviation:
   ```
   σ = MAD × 1.4826
   where MAD = median(|xi - median(x)|)
   ```
3. Draw bands:
   - **±1σ band** (dark gray): `median - σ` to `median + σ`
   - **±2σ band** (light gray): `median - 2σ` to `median + 2σ`
   - Points outside ±2σ are strong rejection candidates

**Why MAD instead of standard deviation?**
- More robust to outliers
- Single bad frame won't skew the statistics
- Better represents "normal" frame quality

---

## 7. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| **Performance** | Analyze 100 frames in <60 seconds |
| **File Safety** | Delete sends to recycle bin (recoverable) |
| **Simplicity** | Minimal UI, single-window application |
| **Platform** | Windows, macOS, Linux (Python cross-platform) |
| **Memory** | Handle 500+ frames without excessive RAM usage |

---

## 8. Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| GUI Framework | CustomTkinter | Modern, simple interface |
| Plotting | Matplotlib | Interactive plots with click events |
| FITS Handling | Astropy | Read astronomical FITS files |
| Star Detection | Photutils | DAOStarFinder, PSF fitting |
| File Deletion | Send2Trash | Cross-platform recycle bin |

---

## 9. Future Enhancements (Out of Scope)

- Automatic rejection based on sigma thresholds
- Batch processing multiple folders
- Integration with stacking software
- Dark/flat frame analysis
- FITS header metadata display
