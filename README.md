# jev-questions

How to write questions for Jev / [TypeSafe](https://docs.typesafe.ai/models.md) System One
(Noul, Choice and Score), and how to debug the ones that don't work, as a skill for AI coding
agents. 1 skill, 9 rules, and 5 scripts that check them.

> **Quick start:** `npx skills add VBS2004/jev-questions-skill`, then ask your agent to write
> or debug a System One question. Works with 60+ agents. Other ways to install are
> [below](#install).

## Why

Most advice on prompting a model is a hunch. These rules each come with a number, measured
while building [jevcut](https://github.com/VBS2004/jevcut), an auto-clipper on Jev, and
several were learned by getting them wrong first:

- A question that listed surface forms ("opens on 'and so', 'but then'") fired on nearly every
  excerpt, and listing the forms that were *fine* was the same mistake inverted.
- A question that asked "is this worth having?" of an already-filtered set answered 0.64-0.91
  on all 45 items. It never said no.
- A Choice lost to a tuned constant offset (8.7s vs 5.5s median error); another caught that a
  clip opened by answering a question it did not contain, which no rule can compute.
- The ad check caught 94% of whole sponsor reads and 50% of the same reads' middles. Setting
  the bar from the hard cases, not the easy ones, moved it to 82%.

The rules are about System One in general, not clipping. They apply to any judge, gate, filter,
classifier or extractor built on it.

## What's included

### The skill: [`skills/jev-questions`](skills/jev-questions/SKILL.md)

1. Criteria describe situations, never words
2. Check that your question can discriminate (the spread test)
3. Pick the primitive for the shape of the judgment
4. State: put the model exactly where the judge sits
5. Many questions, one state, one request
6. Do not ask for a number you are about to compute
7. Separate judgment from policy
8. Know where the model actually beats code
9. Failure patterns that look like model errors
10. The scripts below

### Scripts

Standard library only, no API calls, Python 3.10+. Inputs are plain JSONL, so any project can
feed them; the formats are in each script's `--help`.

| script | rule | what it answers |
| --- | --- | --- |
| [`lint_questions.py`](skills/jev-questions/scripts/lint_questions.py) `PATH…` | 1, 3, 4, 6 | Finds questions in Python (SDK calls, raw dicts, helper functions), JS/TS and JSON, and flags word lists, a Choice with no escape, a state anchor made authoritative, negative phrasing over a positive `true`. A heuristic: it says where to look |
| [`spread.py`](skills/jev-questions/scripts/spread.py) `RESPONSES.jsonl` | 2 | Does this question discriminate or is it a constant? Median, range, spread, fire rate; AUC when you have labels. Calls rare-event questions out instead of mislabelling them constant |
| [`coverage.py`](skills/jev-questions/scripts/coverage.py) `CASES.jsonl` | 9 | Was the right option ever offered? Splits misses into "never on the list" (fix the candidate generator) and "offered, not picked" (fix the question) |
| [`chance.py`](skills/jev-questions/scripts/chance.py) `picks`, `spans` | 2 | What random picks would have scored at the same density, how many times better you are, and an exact p-value |
| [`threshold.py`](skills/jev-questions/scripts/threshold.py) `SCORES.jsonl` | 7 | Where genuine content peaks and where the hard cases sit, recall and false fires at every bar, and a suggestion |

[`examples/gate.py`](skills/jev-questions/examples/gate.py) is a runnable ticket-triage gate with
the judgment / verdict split, an escape option, and a policy ordered by repairability
(`python examples/gate.py --dry "my card was charged twice"` needs no key).
[`examples/jevcut/`](skills/jev-questions/examples/jevcut/) shows how to turn a real project's
artifacts into the script inputs.

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

Each script was run on real System One output, and where the project had already measured the
same thing by hand, the numbers were compared.

| script | data | result | the project's own figure |
| --- | --- | --- | --- |
| `spread.py` | 20,037 cached `verify` responses (jevcut) | `worth_clipping`: 100% fire rate on 45 items, so it gates nothing | RESEARCH.md: the general "is it worth it" question went flat on a filtered population |
| `coverage.py` | the opening Choice on 203 found clips; the 48 that start 10s+ off | **30 of 48 never had the right start on offer** | RESEARCH.md: "in 30 of the 48 far-off cases the right start is never a candidate" |
| `threshold.py` | 652 labeled ad-check texts | genuine content peaks at 0.41; whole reads caught 94%; read middles 82% at 0.5 and 95% at 0.35 | RESEARCH.md: 94% / 82%, bar moved 0.5 → 0.35 |
| `spread.py` with labels | 57 labeled messages (learngate) | `gate` AUC **0.92** | learngate's notes: "0.92 on your 60 labels" |
| `chance.py spans` | 50 random cases | identical to jevcut's `evaluate.chance_recall` to 12 digits | |
| `lint_questions.py` | 12 repos on one machine, 101 questions | 2 warnings (a connectivity probe, a historical experiment), 9 notes | |

Two bugs in the tools themselves were found this way and fixed: the linter missed questions
built through helper functions and structured `instructions`, and `spread.py` called a
rare-event question "constant".

## Install

The skill is a folder with a `SKILL.md` (`name` and `description` frontmatter), the format
Claude Code, Codex, Antigravity, Hermes and the rest read. Pick whichever install suits you.

### Option 1: `npx skills` (recommended)

```bash
npx skills add VBS2004/jev-questions-skill          # this project; add -g for all projects
npx skills add VBS2004/jev-questions-skill -g -a claude-code -a codex
```

[`skills`](https://github.com/vercel-labs/skills) detects the agents you have and installs
into each one's folder. `npx skills update` refreshes, `npx skills remove` removes.

### Option 2: Claude Code plugin

```text
/plugin marketplace add VBS2004/jev-questions-skill
/plugin install jev-questions@jev-questions
```

### Option 3: the bundled installer (Python only, no Node)

```bash
curl -fsSL https://raw.githubusercontent.com/VBS2004/jev-questions-skill/main/install.py | python3 -
```

It lists the 69 agents it knows, ticks the ones it finds on your machine, lets you toggle the
rest with a numbered checklist, then asks whether to install globally or into the current
project. Or from a clone:

```bash
git clone https://github.com/VBS2004/jev-questions-skill && cd jev-questions-skill
python3 install.py                    # the checklist
python3 install.py --list             # every agent and the folders it reads
python3 install.py --yes              # every agent it detects, no questions
python3 install.py --agents claude,codex,hermes
python3 install.py --project          # into this project, copied so it can be committed
python3 install.py --uninstall
```

Global installs symlink to one copy (your clone, or `~/.local/share/jev-questions-skill`), so
`git pull` or `install.py --update` updates every agent at once. `--copy` copies instead and
`--dry-run` shows what would happen. It never overwrites a folder that is not its own unless
you pass `--force`, which moves the old one aside to `.bak`. Tools that share a folder
(`~/.agents/skills` serves Cline, Pi, Warp, Zed and others) are installed once.

Where each agent reads skills comes from the table
[`skills` publishes](https://github.com/vercel-labs/skills#supported-agents) (checked
2026-10-02); the `AGENT_TABLE` at the top of [`install.py`](install.py) is that table, so a
correction there is a one-line change.

### Option 4: by hand

Copy [`skills/jev-questions`](skills/jev-questions) into your agent's skills folder
(`~/.claude/skills/`, `~/.codex/skills/`, `~/.agents/skills/`, `.agents/skills/` in a project,
and so on). Or just read [SKILL.md](skills/jev-questions/SKILL.md); it is plain Markdown.

## Tests

```bash
python -m pytest
```

## License

[MIT](LICENSE).
