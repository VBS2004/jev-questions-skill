# Worked adapters: jevcut

These turn the artifacts of a real System One project, [jevcut](https://github.com/VBS2004/jevcut),
into the plain-JSONL inputs the scripts in `../../scripts/` read. They are here as templates:
the scripts never need to know a project's internals, only these row formats.

Run them from a jevcut checkout (they use its modules and its response cache, so a re-run
costs no requests):

```bash
uv run python SKILL_DIR/examples/jevcut/cache_to_spread.py  > verify.jsonl
python SKILL_DIR/scripts/spread.py verify.jsonl

uv run python SKILL_DIR/examples/jevcut/promotion_scores.py --out /tmp/promo
python SKILL_DIR/scripts/threshold.py /tmp/promo.context.jsonl \
    --positive "promotion, whole;promotion, middle;shipped ad" --hard "promotion, middle" \
    --negative content

uv run python SKILL_DIR/examples/jevcut/openings_coverage.py > cov.jsonl
python SKILL_DIR/scripts/coverage.py cov.jsonl --tol 1.0
```
