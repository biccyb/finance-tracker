#!/usr/bin/env python3
"""
Run: python3 build-logos.py
Paste printed output into <script id="logos"> in index.html.
"""
import base64, pathlib, sys

LOGOS_DIR = pathlib.Path(__file__).parent / "Assets" / "Logos"
FILES = {
    "KBANK":   "KBANK-wisdom-CC.png",
    "UOB":     "UOB Premier CC.png",
    "KTC":     "KTC X CC.png",
    "YOUTUBE": "YouTube_Logo_2017.svg.png",
    "ICLOUD":  "ICloud_logo.svg.png",
}

print("const LOGOS = {")
for key, filename in FILES.items():
    path = LOGOS_DIR / filename
    if not path.exists():
        print(f"  // WARNING: {filename} not found", file=sys.stderr)
        print(f"  {key}: '',")
        continue
    b64 = base64.b64encode(path.read_bytes()).decode()
    print(f"  {key}: 'data:image/png;base64,{b64}',")
print("};")
