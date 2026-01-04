#!/usr/bin/env python3
"""
Test script for the SubFrame Selector analysis engine.

Usage:
    python test_analysis.py <fits_file_or_folder>

Examples:
    python test_analysis.py /path/to/image.fits
    python test_analysis.py /path/to/fits_folder/
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from analysis import SubframeAnalyzer


def print_metrics(result: dict):
    """Pretty print analysis results for a single file."""
    print(f"\n{'='*60}")
    print(f"File: {result['filename']}")
    print(f"{'='*60}")

    if result.get('error'):
        print(f"ERROR: {result['error']}")
        return

    metrics = result['metrics']
    print(f"  Stars detected: {result['star_count_detected']}")
    print(f"  Stars fitted:   {result['star_count_fitted']}")
    print(f"\n  Metrics:")
    print(f"    FWHM:         {metrics['fwhm']:.3f} pixels")
    print(f"    Eccentricity: {metrics['eccentricity']:.3f}")
    print(f"    SNR:          {metrics['snr']:.1f}")
    print(f"    Star Count:   {metrics['star_count']}")
    print(f"    Background:   {metrics['background']:.1f}")


def print_statistics(statistics: dict):
    """Pretty print statistics for all metrics."""
    print(f"\n{'='*60}")
    print("STATISTICS (across all frames)")
    print(f"{'='*60}")

    for metric, stats in statistics.items():
        print(f"\n  {metric.upper()}:")
        print(f"    Median: {stats['median']:.3f}")
        print(f"    Sigma:  {stats['sigma']:.3f}")
        print(f"    Range:  {stats['min']:.3f} - {stats['max']:.3f}")
        print(f"    ±1σ:    {stats['band_1sigma'][0]:.3f} - {stats['band_1sigma'][1]:.3f}")
        print(f"    ±2σ:    {stats['band_2sigma'][0]:.3f} - {stats['band_2sigma'][1]:.3f}")


def progress_callback(current: int, total: int, filename: str):
    """Show progress during analysis."""
    pct = (current / total) * 100
    print(f"  [{current}/{total}] ({pct:.0f}%) Analyzing: {filename}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    path = sys.argv[1]

    # Initialize analyzer
    print("Initializing SubframeAnalyzer...")
    analyzer = SubframeAnalyzer(
        fwhm_estimate=5.0,
        threshold_sigma=5.0,
        max_stars=500
    )

    if os.path.isfile(path):
        # Single file analysis
        print(f"\nAnalyzing single file: {path}")
        result = analyzer.analyze_file(path)
        print_metrics(result)

    elif os.path.isdir(path):
        # Folder analysis
        print(f"\nAnalyzing folder: {path}")
        results = analyzer.analyze_folder(path, progress_callback=progress_callback)

        print(f"\n\nTotal files: {results['total_files']}")

        # Print individual results
        for result in results['results']:
            print_metrics(result)

        # Print overall statistics
        if results['statistics']:
            print_statistics(results['statistics'])

        # Show outliers
        print(f"\n{'='*60}")
        print("POTENTIAL OUTLIERS (>2σ from median)")
        print(f"{'='*60}")

        for metric in ['fwhm', 'eccentricity', 'snr', 'star_count', 'background']:
            outliers = analyzer.get_outliers(results['results'], metric, sigma_threshold=2.0)
            if outliers:
                print(f"\n  {metric.upper()} outliers:")
                for idx in outliers:
                    r = results['results'][idx]
                    val = r['metrics'][metric] if r.get('metrics') else 'N/A'
                    print(f"    - {r['filename']}: {val}")
    else:
        print(f"Error: Path not found: {path}")
        sys.exit(1)

    print("\n\nAnalysis complete!")


if __name__ == "__main__":
    main()
