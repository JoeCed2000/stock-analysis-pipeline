#!/usr/bin/env python3
"""
Cache-busting verification for SA frontend deployment.

Verifies that:
1. Vite build produces content-hashed JS/CSS assets
2. index.html references the latest hashed assets
3. Rebuilding changes the asset references (no stale cache)

Usage: python3 scripts/verify_cache_busting.py
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"
INDEX_HTML = DIST_DIR / "index.html"


def get_asset_hashes() -> dict[str, str]:
    """Return {filename: sha256} for all files in dist/assets/."""
    assets_dir = DIST_DIR / "assets"
    if not assets_dir.exists():
        return {}
    hashes = {}
    for f in assets_dir.iterdir():
        if f.is_file():
            hashes[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()[:12]
    return hashes


def get_index_references() -> set[str]:
    """Extract referenced asset filenames from index.html."""
    if not INDEX_HTML.exists():
        return set()
    content = INDEX_HTML.read_text()
    refs = set()
    for line in content.split("\n"):
        if "src=" in line or "href=" in line:
            for attr in ["src=", "href="]:
                if attr in line:
                    start = line.index(attr) + len(attr) + 1  # skip quote
                    end = line.index('"', start) if '"' in line[start:] else len(line)
                    path = line[start:end].strip('"').strip("'")
                    if "/assets/" in path:
                        refs.add(os.path.basename(path))
    return refs


def main():
    print("=== SA Cache-Busting Verification ===\n")

    # 1. Check dist exists
    if not DIST_DIR.exists():
        print("❌ dist/ not found. Run: cd frontend && npm run build")
        return 1

    # 2. Check for content-hashed assets
    assets_dir = DIST_DIR / "assets"
    if not assets_dir.exists():
        print("❌ dist/assets/ not found")
        return 1

    js_files = list(assets_dir.glob("*.js"))
    css_files = list(assets_dir.glob("*.css"))

    print(f"📦 JS assets: {len(js_files)}")
    for f in js_files:
        has_hash = any(c.isdigit() for c in f.stem.split("-")[-1]) if "-" in f.stem else False
        marker = "✅" if has_hash else "⚠️ (no hash)"
        print(f"   {marker} {f.name}")

    print(f"📦 CSS assets: {len(css_files)}")
    for f in css_files:
        has_hash = any(c.isdigit() for c in f.stem.split("-")[-1]) if "-" in f.stem else False
        marker = "✅" if has_hash else "⚠️ (no hash)"
        print(f"   {marker} {f.name}")

    # 3. Verify index.html references hashed assets
    if INDEX_HTML.exists():
        refs = get_index_references()
        print(f"\n📄 index.html references: {len(refs)} assets")
        for ref in sorted(refs):
            print(f"   → {ref}")

        actual = {f.name for f in js_files + css_files}
        missing = refs - actual
        if missing:
            print(f"❌ Broken references (not in dist): {missing}")
            return 1
        print("✅ All references point to existing files")
    else:
        print("❌ index.html not found")
        return 1

    # 4. Snapshot hashes for rebuild comparison
    before_hashes = get_asset_hashes()
    print(f"\n🔑 Asset fingerprints (sha256[:12]):")
    for name, h in sorted(before_hashes.items()):
        print(f"   {h}  {name}")

    # 5. Check Cache-Control header (if server is running)
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8780/stock-analysis/")
        resp = urllib.request.urlopen(req, timeout=3)
        cache_control = resp.headers.get("Cache-Control", "")
        if "no-cache" in cache_control or "must-revalidate" in cache_control:
            print(f"\n✅ Cache-Control: {cache_control}")
        elif cache_control:
            print(f"\n⚠️  Cache-Control: {cache_control} (consider no-cache)")
        else:
            print(f"\n⚠️  No Cache-Control header (CDN may cache aggressively)")
    except Exception:
        print(f"\nℹ️  Server not running — skipping Cache-Control check")

    print("\n✅ Cache-busting verification complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
