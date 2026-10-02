"""Every cached `verify` response in a jevcut checkout, as spread.py input (stdlib only).

    python cache_to_spread.py [runs/cache] [--pass verify] > responses.jsonl

jevcut caches each System One response under runs/cache/<hh>/<hash>.json as
{"pass": ..., "response": {"answers": {...}}}, which spread.py reads as it is; this only
filters by pass so one question set is measured at a time.
"""
import argparse
import glob
import json
import sys

ap = argparse.ArgumentParser()
ap.add_argument("cache", nargs="?", default="runs/cache")
ap.add_argument("--pass", dest="pass_name", default="verify")
a = ap.parse_args()
n = 0
for f in glob.glob(f"{a.cache}/*/*.json"):
    d = json.load(open(f))
    if d.get("pass") == a.pass_name:
        print(json.dumps(d["response"]))
        n += 1
print(f"{n} responses", file=sys.stderr)
