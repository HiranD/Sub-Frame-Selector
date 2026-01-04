# SubFrame Selector - Standalone App Packaging Plan

## Goal

Package SubFrame Selector as a standalone application for **macOS** and **Windows** that users can download, extract, and run without installing Python or any dependencies.

## Distribution Format

- **Folder-based distribution**: Zip file containing app folder with executable + dependencies
- **Automated builds**: GitHub Actions workflow triggered on release creation

---

## Implementation Plan

### Phase 1: PyInstaller Configuration

**Create `subframe-selector.spec`** - PyInstaller spec file for customized builds

```
Files to create:
├── subframe-selector.spec    # PyInstaller build configuration
├── assets/
│   ├── icon.icns            # macOS app icon
│   └── icon.ico             # Windows app icon
```

**Key PyInstaller settings:**
- `onedir` mode (folder-based, not single file)
- `--windowed` (no console window)
- `--collect-all matplotlib` (include fonts/data)
- `--collect-all astropy` (include IERS data)
- `--collect-all photutils`
- Hidden imports for multiprocessing on Windows

---

### Phase 2: Multiprocessing Fix for Windows

**Problem**: PyInstaller + multiprocessing on Windows requires `freeze_support()`

**Modify `run.py`:**
```python
from multiprocessing import freeze_support

if __name__ == "__main__":
    freeze_support()  # Required for Windows frozen executables
    run_app()
```

---

### Phase 3: GitHub Actions Workflow

**Create `.github/workflows/build-release.yml`**

Triggered on: `release` event (when you create a GitHub release)

**Jobs:**
1. **build-macos**: Build on `macos-latest` (universal binary for Intel + Apple Silicon)
2. **build-windows**: Build on `windows-latest`

**Workflow steps:**
1. Checkout code
2. Set up Python 3.11
3. Install dependencies from requirements.txt
4. Install PyInstaller
5. Run PyInstaller with spec file
6. Create zip archive of dist folder
7. Upload as release asset

**Output artifacts:**
- `SubFrameSelector-macOS.zip`
- `SubFrameSelector-Windows.zip`

---

### Phase 4: App Icons (Optional)

Create app icons for professional appearance:
- `assets/icon.icns` - macOS (1024x1024 base)
- `assets/icon.ico` - Windows (256x256 multi-resolution)

---

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `run.py` | Modify | Add `freeze_support()` for Windows |
| `subframe-selector.spec` | Create | PyInstaller build configuration |
| `.github/workflows/build-release.yml` | Create | Automated CI/CD builds |
| `assets/icon.icns` | Create | macOS app icon |
| `assets/icon.ico` | Create | Windows app icon |

---

## Build Commands (for reference)

**Local macOS build:**
```bash
pyinstaller subframe-selector.spec
cd dist && zip -r SubFrameSelector-macOS.zip "SubFrame Selector"
```

**Local Windows build:**
```bash
pyinstaller subframe-selector.spec
cd dist && powershell Compress-Archive "SubFrame Selector" SubFrameSelector-Windows.zip
```

---

## Expected Output

After creating a GitHub release:
1. GitHub Actions automatically builds for both platforms
2. Two zip files attached to the release:
   - `SubFrameSelector-macOS.zip` (~150-200MB)
   - `SubFrameSelector-Windows.zip` (~150-200MB)

Users download, extract, and run the app directly.

---

## Estimated Bundle Size

| Component | Size |
|-----------|------|
| numpy | ~30MB |
| scipy | ~40MB |
| matplotlib | ~30MB |
| astropy | ~50MB |
| photutils | ~10MB |
| customtkinter | ~5MB |
| Python runtime | ~30MB |
| **Total (compressed)** | **~150-200MB** |

---

## Dependency Analysis

All dependencies have pre-built binary wheels for Mac and Windows:

| Dependency | Type | Packaging Notes |
|------------|------|-----------------|
| customtkinter | Pure Python | Cross-platform compatible |
| matplotlib | Compiled | Has binary wheels, needs TkAgg backend |
| astropy | Compiled | Has binary wheels, includes FITS I/O |
| photutils | Compiled | Depends on astropy, numpy, scipy |
| numpy | Compiled | Binary wheels for all platforms |
| scipy | Compiled | Binary wheels for all platforms |
| send2trash | Pure Python | Cross-platform (Trash/Recycle Bin) |

No blocking issues - all dependencies are production-ready with binary wheels available.
