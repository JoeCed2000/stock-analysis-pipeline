#!/usr/bin/env python3
"""Extract key lines from the fill_dossiers batch log."""
import sys

keywords = [
    "Processing", "10-K PDF generated", "Upload failed", "Uploaded",
    "YF cached", "Finnhub", "ERROR", "No 10-K",
    "No analysis found", "Status:", "Starting dossier",
    "Found", "Cannot check"
]

for line in sys.stdin:
    if any(kw in line for kw in keywords):
        print(line.rstrip())
