# jev-questions

A [Claude Code](https://claude.com/claude-code) skill for designing typed questions for
Jev / [TypeSafe](https://docs.typesafe.ai/models.md) System One: Noul, Choice and Score,
plus scripts that check its rules mechanically.

It is a field guide to writing questions that mean something, and to debugging the ones
that don't: a question that fires on everything, one that fires on nothing, a Choice that
picks something implausible. Every rule comes with a number that was measured while
building [jevcut](https://github.com/VBS2004/jevcut), an auto-clipper built on Jev, and
several were learned by getting them wrong first.

The rules are about System One in general, not clipping. They apply to any judge, gate,
filter, classifier or extractor built on it.

## Install

```bash
git clone https://github.com/VBS2004/jev-questions-skill ~/.claude/skills/jev-questions
```

Claude Code loads it when you build or debug a System One question. You can also just read
[SKILL.md](SKILL.md); it is plain Markdown.

## The rules ([SKILL.md](SKILL.md))

1. Criteria describe situations, never words
2. Check that your question can discriminate (the spread test)
3. Pick the primitive for the shape of the judgment
4. State: put the model exactly where the judge sits
5. Many questions, one state, one request
6. Do not ask for a number you are about to compute
7. Separate judgment from policy
8. Know where the model actually beats code
9. Failure patterns that look like model errors

## Scripts

Standard library only, no API calls, Python 3.10+. Inputs are plain JSONL, so any project
can feed them; the formats are in each script's `--help`.

| script | rule | what it answers |
| --- | --- | --- |
| [`lint_questions.py`](scripts/lint_questions.py) `PATH…` | 1, 3, 4, 6 | Finds questions in Python (SDK calls, raw dicts, helper functions), JS/TS and JSON, and flags word lists, a Choice with no escape, a state anchor made authoritative, negative phrasing over a positive `true`. A heuristic: it says where to look |
| [`spread.py`](scripts/spread.py) `RESPONSES.jsonl` | 2 | Does this question discriminate or is it a constant? Median, range, spread, fire rate; AUC when you have labels. Calls rare-event questions out instead of mislabelling them constant |
| [`coverage.py`](scripts/coverage.py) `CASES.jsonl` | 9 | Was the right option ever offered? Splits misses into "never on the list" (fix the candidate generator) and "offered, not picked" (fix the question) |
| [`chance.py`](scripts/chance.py) `picks`, `spans` | 2 | What random picks would have scored at the same density, how many times better you are, and an exact p-value |
| [`threshold.py`](scripts/threshold.py) `SCORES.jsonl` | 7 | Where genuine content peaks and where the hard cases sit, recall and false fires at every bar, and a suggestion |

[`examples/gate.py`](examples/gate.py) is a runnable ticket-triage gate with the judgment /
verdict split, an escape option, and a policy ordered by repairability
(`python examples/gate.py --dry "my card was charged twice"` needs no key).
[`examples/jevcut/`](examples/jevcut/) shows how to turn a real project's artifacts into the
script inputs.

```text
$ python scripts/lint_questions.py my_project/
17 questions (9 noul, 6 choice, 2 score), 3 findings
  warn no-escape   eval/pick_vs_snap.py:137 start_cut §3
       no none-of-these option among: before_this_region

$ python scripts/spread.py responses.jsonl
question               type        n  median       range  spread  verdict
worth_clipping         noul       45    0.87  0.64-0.91     0.07  nearly constant
needs_the_room         noul    20037    0.09  0.03-0.90     0.08  rare event?
ends_mid_thought       noul    20037    0.64  0.07-0.97     0.22  discriminates
- worth_clipping: fires on 100% at 0.5: it gates nothing
```

### Checked against real data

Each script was run on real System One output, and where the project had already measured
the same thing by hand, the numbers were compared.

| script | data | result | the project's own figure |
| --- | --- | --- | --- |
| `spread.py` | 20,037 cached `verify` responses (jevcut) | `worth_clipping`: 100% fire rate on 45 items, so it gates nothing | RESEARCH.md: the general "is it worth it" question went flat on a filtered population |
| `coverage.py` | the opening Choice on 203 found clips; the 48 that start 10s+ off | **30 of 48 never had the right start on offer** | RESEARCH.md: "in 30 of the 48 far-off cases the right start is never a candidate" |
| `threshold.py` | 652 labeled ad-check texts | genuine content peaks at 0.41; whole reads caught 94%; read middles 82% at 0.5 and 95% at 0.35 | RESEARCH.md: 94% / 82%, bar moved 0.5 → 0.35 |
| `spread.py` with labels | 57 labeled messages (learngate) | `gate` AUC **0.92** | learngate's notes: "0.92 on your 60 labels" |
| `chance.py spans` | 50 random cases | identical to jevcut's `evaluate.chance_recall` to 12 digits | |
| `lint_questions.py` | 12 repos on one machine, 101 questions | 2 warnings (a connectivity probe, a historical experiment), 9 notes | |

Two bugs in the tools themselves were found this way and fixed: the linter missed
questions built through helper functions and structured `instructions`, and `spread.py`
called a rare-event question "constant".

## Tests

```bash
python -m pytest
```

## License

[MIT](LICENSE).
