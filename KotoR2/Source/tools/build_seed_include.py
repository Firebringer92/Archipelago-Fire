"""Writes nss/k2ap_seed.nss (the row constants and readers for the seed's 2DA) from client/k2_seed.py. Run it after changing ROWS.
Usage: python tools/build_seed_include.py"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "client"))
import k2_seed  # noqa: E402

if __name__ == "__main__":
    path = os.path.join(ROOT, "nss", "k2ap_seed.nss")
    with open(path, "w", newline="") as f:
        f.write(k2_seed.nss_include())
    print(path)
