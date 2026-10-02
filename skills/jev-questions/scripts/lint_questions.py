#!/usr/bin/env python3
"""Lint System One questions for the mistakes SKILL.md names. No API calls, stdlib only.

    python scripts/lint_questions.py PATH [PATH ...] [--json] [--include-tests]
                                     [--fail-on warn|info]

Finds questions in Python (SDK calls such as `Noul(...)`, wrapped ones such as
`self._Noul(...)`, helper functions that build one, and raw
`{"type": "noul", "instructions": ..., "criteria": ...}` dicts), in JavaScript/TypeScript
object literals, and in JSON files, then checks each one against rules
that can be decided from the text alone.

This is a heuristic. A finding is a place to look, not a verdict: the spread test
(spread.py) is what says whether a question actually discriminates. Rule ids point at
the SKILL.md section that explains them.

    word-list          §1  criteria enumerate quoted surface forms
    surface-form       §1  criteria are about how text begins/what words it contains
    false-is-negation  §1  the "false" side is just "not <the true side>"
    criteria-overlap   §1  true and false describe nearly the same thing
    score-levels       §1  too few levels, or levels that are numbers, not situations
    no-escape          §3  a Choice with no none-of-these option
    state-anchor       §4  the instruction makes one piece of state authoritative
    arithmetic         §4  the question asks the model to count, compare or order
    polarity           §1  a negatively-phrased instruction over a positive `true` criterion
    verdict-question   §6  a general "is this good / worth it" verdict
    thin-instructions  --  the instruction is too short to say what is being asked
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "site-packages", "__pycache__", "dist",
    "build", ".tox", ".mypy_cache", ".ruff_cache", ".hermes", "typesafe_sdk",
}
TEST_DIRS = {"tests", "test", "__tests__", "spec"}
KINDS = ("noul", "choice", "score")
MAX_BYTES = 1_000_000

ESCAPE_KEY = re.compile(
    r"^(none|no_?one|nothing|neither|other|unknown|n_?a|abstain|skip|unsure|not_?sure|"
    r"unclear|no_?match|no_?anchor|noop|none_of.*|.*none_of_these.*)$",
    re.IGNORECASE,
)
ESCAPE_TEXT = re.compile(
    r"none_of|none of (these|the above)|if (no|none|nothing)\b|choose `?\w+`? if no", re.I
)
QUOTED_LIST = re.compile(
    r"""(["'“‘`])[^"'”’`\n]{1,40}\1\s*(?:,|/|\bor\b|\band\b)\s*["'“‘`]"""
)
SURFACE = re.compile(
    r"\b(starts?|begins?|opens?|ends?) (with|on) (the )?(word|words|phrase|phrases|"
    r"letter|letters|keyword|keywords)\b|\bcontains? the (word|words|phrase|keyword)s?\b|"
    r"\bkeywords?\b|\bmentions? (the )?(word|words)\b",
    re.I,
)
VERDICT = re.compile(
    r"\bis (this|it|the (clip|text|answer|message|post))\b[^.?]{0,25}\b(good|great|"
    r"worth (it|having|keeping|watching|clipping|reading)|interesting|engaging|"
    r"high[- ]quality|valuable|useful)\b|\bhow good\b|\bis this worth\b",
    re.I,
)
ACTION = re.compile(
    r"\b(which|what)( of (these|the))? (moves?|actions?|keys?|buttons?|jumps?|operations?|"
    r"steps?|hotkeys?|commands?|tools?|landing spots?|option should)\b|\bnext (move|action|step)\b|\bshould .* (press|"
    r"click|move|jump)\b|\bbest (next )?(move|action|outcome|landing)\b", re.I)
ARITHMETIC = re.compile(
    r"\bhow many\b|\bcount (the|how)\b|\bwhich (comes|is) (first|earlier|later)\b|"
    r"\b(earlier|later|older|newer) than\b|\bsort\b|\bin order of\b|\badd up\b",
    re.I,
)
STATE_ANCHOR = re.compile(
    r"\b(around|at|on|near|from) (the )?(line|sentence|row|item|message|mark|segment|"
    r"chunk) `[^`]+`|\b(cut|centred|centered|anchored) (around|on) `[^`]+`",
    re.I,
)
NEGATION_START = re.compile(
    r"^(not\b|does not\b|doesn'?t\b|is not\b|isn'?t\b|no\b|never\b|without\b)", re.I
)
NEGATION = re.compile(
    r"\b(without|unless|never|cannot|can't|can not|doesn'?t|does not|isn'?t|is not|aren'?t|"
    r"are not|no longer|lacks?|missing|absent|fails? to)\b", re.I)
STOP = set(
    "a an the of to and or in on is it that this for with as at be by from are was were "
    "has have had not no its their they them there which who what when where".split()
)


@dataclass
class Question:
    kind: str
    file: str
    line: int
    name: str | None = None
    instructions: str | None = None
    true: str | None = None
    false: str | None = None
    options: dict[str, str | None] | None = None  # Choice, when statically known
    options_dynamic: bool = False
    levels: list[str] | None = None  # Score
    dynamic_instructions: bool = False


@dataclass
class Finding:
    rule: str
    severity: str  # "warn" | "info"
    file: str
    line: int
    name: str | None
    message: str
    section: str = ""


# ---- Python extraction ---------------------------------------------------------------


class _Fold:
    """Fold a node to a string when that can be done without running the program."""

    def __init__(self, consts: dict[str, ast.AST]):
        self.consts = consts

    def text(self, node: ast.AST | None, depth: int = 0) -> str | None:
        if node is None or depth > 6:
            return None
        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, str) else None
        if isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant):
                    parts.append(str(v.value))
                else:
                    parts.append("{}")
            return "".join(parts)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            a, b = self.text(node.left, depth + 1), self.text(node.right, depth + 1)
            return a + b if a is not None and b is not None else None
        if isinstance(node, ast.Name) and node.id in self.consts:
            return self.text(self.consts[node.id], depth + 1)
        return None

    def instructions(self, node: ast.AST | None) -> str | None:
        """Instructions may be prose or an object of prose parts (goal, trade_off, ...)."""
        if isinstance(node, ast.Dict):
            parts = [self.text(v) for v in node.values]
            parts = [t for t in parts if t]
            return "\n".join(parts) if parts else None
        return self.text(node)

    def strings(self, node: ast.AST | None, depth: int = 0) -> list[str] | None:
        if isinstance(node, ast.Name) and node.id in self.consts and depth < 4:
            return self.strings(self.consts[node.id], depth + 1)
        if isinstance(node, (ast.List, ast.Tuple)):
            out = [self.text(e) for e in node.elts]
            return None if any(t is None for t in out) else out  # type: ignore[return-value]
        return None

    def mapping(self, node: ast.AST | None, depth: int = 0):
        """(options dict | None, dynamic?) for a dict-ish criteria value."""
        if isinstance(node, ast.Name) and node.id in self.consts and depth < 4:
            return self.mapping(self.consts[node.id], depth + 1)
        if isinstance(node, ast.Dict):
            out: dict[str, str | None] = {}
            dynamic = False
            for k, v in zip(node.keys, node.values):
                if k is None:  # {**other}
                    sub, dyn = self.mapping(v, depth + 1)
                    dynamic = dynamic or dyn or sub is None
                    out.update(sub or {})
                    continue
                key = self.text(k)
                if key is None:
                    dynamic = True
                    continue
                out[key] = self.text(v) if not (
                    isinstance(v, ast.Constant) and v.value is None
                ) else None
            return out, dynamic
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name == "dict" and node.args:
                sub, dyn = self.mapping(node.args[0], depth + 1)
                return sub or {}, dyn or sub is None
            if name == "fromkeys":
                if node.args and isinstance(node.args[0], (ast.List, ast.Tuple)):
                    keys = [self.text(e) for e in node.args[0].elts]
                    return {k: None for k in keys if k}, any(k is None for k in keys)
                return {}, True
        if isinstance(node, (ast.DictComp, ast.ListComp)):
            return {}, True
        return None, True


def _kw(call: ast.Call, name: str) -> ast.AST | None:
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


def _callee(call: ast.Call) -> str:
    f = call.func
    n = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
    return n.lstrip("_")


def _helpers(tree: ast.AST) -> tuple[dict[str, dict], set[int]]:
    """Functions that build a question dict from their own parameters.

    Returns {function name: {"kind", "ins", "true", "false" -> parameter name}} and the ids
    of the dicts inside them: those are templates, not questions; the call sites are."""
    helpers: dict[str, dict] = {}
    templates: set[int] = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = {a.arg for a in fn.args.args}
        for d in ast.walk(fn):
            if not isinstance(d, ast.Dict):
                continue
            keys = {k.value: v for k, v in zip(d.keys, d.values)
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            ins = keys.get("instructions")
            if not (isinstance(ins, ast.Name) and ins.id in params and "type" in keys):
                continue
            kind = keys["type"].value if isinstance(keys["type"], ast.Constant) else None
            spec = {"kind": kind, "ins": ins.id}
            crit = keys.get("criteria")
            if isinstance(crit, ast.Dict):
                for k, v in zip(crit.keys, crit.values):
                    if (isinstance(k, ast.Constant) and k.value in ("true", "false")
                            and isinstance(v, ast.Name) and v.id in params):
                        spec[k.value] = v.id
            helpers[fn.name] = {**spec, "params": [a.arg for a in fn.args.args]}
            templates.add(id(d))
    return helpers, templates


def _py_questions(path: Path, rel: str) -> list[Question]:
    try:
        with warnings.catch_warnings():  # other people's invalid escapes are not our news
            warnings.simplefilter("ignore")
            tree = ast.parse(path.read_text(errors="replace"))
    except (SyntaxError, ValueError):
        return []
    consts: dict[str, ast.AST] = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            consts[n.targets[0].id] = n.value
    fold = _Fold(consts)
    found: list[Question] = []
    names: dict[int, str] = {}
    for n in ast.walk(tree):  # `"key": Noul(...)` — remember the key for messages
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    names[id(v)] = k.value
    helpers, templates = _helpers(tree)
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and (f := (n.func.attr if isinstance(n.func, ast.Attribute)
                                              else getattr(n.func, "id", ""))) in helpers:
            h = helpers[f]
            bound = dict(zip(h["params"], n.args))
            bound.update({k.arg: k.value for k in n.keywords if k.arg})
            q = Question(kind=h["kind"] or "noul", file=rel, line=n.lineno)
            q.instructions = fold.instructions(bound.get(h["ins"]))
            q.dynamic_instructions = q.instructions is None
            q.true = fold.text(bound.get(h.get("true", "")))
            q.false = fold.text(bound.get(h.get("false", "")))
            q.name = names.get(id(n))
            found.append(q)
        elif isinstance(n, ast.Call) and _callee(n).lower() in KINDS and _callee(n) in (
            "Noul", "Choice", "Score"
        ):
            q = _from_call(n, fold, rel)
            q.name = names.get(id(n))
            found.append(q)
        elif isinstance(n, ast.Dict) and id(n) not in templates:
            q = _from_dict(n, fold, rel)
            if q:
                q.name = names.get(id(n))
                found.append(q)
    return found


def _from_call(call: ast.Call, fold: _Fold, rel: str) -> Question:
    kind = _callee(call).lower()
    q = Question(kind=kind, file=rel, line=call.lineno)
    ins = _kw(call, "instructions") or (call.args[0] if call.args else None)
    q.instructions = fold.instructions(ins)
    q.dynamic_instructions = ins is not None and q.instructions is None
    crit = _kw(call, "criteria")
    if kind == "noul":
        if isinstance(crit, ast.Call) and _callee(crit) == "NoulCriteria":
            q.true = fold.text(_kw(crit, "true"))
            q.false = fold.text(_kw(crit, "false"))
        elif isinstance(crit, ast.Dict):
            m, _ = fold.mapping(crit)
            q.true, q.false = (m or {}).get("true"), (m or {}).get("false")
    elif kind == "choice":
        q.options, q.options_dynamic = fold.mapping(crit)
    else:
        q.levels = fold.strings(crit)
    return q


def _from_dict(d: ast.Dict, fold: _Fold, rel: str) -> Question | None:
    keys = {fold.text(k): v for k, v in zip(d.keys, d.values) if k is not None}
    typed = (fold.text(keys.get("type")) or "").lower() in KINDS
    if "instructions" not in keys or ("criteria" not in keys and not typed):
        return None
    crit = keys.get("criteria")
    kind = (fold.text(keys.get("type")) or "").lower()
    if kind not in KINDS:
        m, _ = fold.mapping(crit)
        if fold.strings(crit) is not None:
            kind = "score"
        elif m is not None and set(m) == {"true", "false"}:
            kind = "noul"
        else:
            kind = "choice"
    q = Question(kind=kind, file=rel, line=d.lineno)
    q.instructions = fold.instructions(keys["instructions"])
    q.dynamic_instructions = q.instructions is None
    if kind == "noul":
        m, _ = fold.mapping(crit)
        q.true, q.false = (m or {}).get("true"), (m or {}).get("false")
    elif kind == "choice":
        q.options, q.options_dynamic = fold.mapping(crit)
    else:
        q.levels = fold.strings(crit)
    return q


# ---- JavaScript / TypeScript extraction ----------------------------------------------

_STR = re.compile(r"""'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`""", re.S)


def _js_unescape(s: str) -> str:
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def _js_string_expr(src: str, i: int) -> tuple[str | None, int]:
    """Read `'a' + "b"` starting at i. Returns (text | None, end index)."""
    parts: list[str] = []
    while True:
        while i < len(src) and src[i] in " \t\r\n(":
            i += 1
        m = _STR.match(src, i)
        if not m:
            return (None if not parts else "".join(parts)), i
        parts.append(_js_unescape(next(g for g in m.groups() if g is not None)))
        i = m.end()
        j = i
        while j < len(src) and src[j] in " \t\r\n":
            j += 1
        if j < len(src) and src[j] == "+":
            i = j + 1
            continue
        return "".join(parts), i


def _balanced(src: str, i: int) -> int:
    """Index just past the bracket group opening at src[i]."""
    pairs = {"{": "}", "[": "]", "(": ")"}
    stack = [pairs[src[i]]]
    j = i + 1
    while j < len(src) and stack:
        c = src[j]
        if c in "'\"`":
            m = _STR.match(src, j)
            j = m.end() if m else j + 1
            continue
        if c in pairs:
            stack.append(pairs[c])
        elif c == stack[-1]:
            stack.pop()
        j += 1
    return j


_JS_KEY = re.compile(r"""\s*(?:([A-Za-z_$][\w$]*)|'([^']*)'|"([^"]*)")\s*:""")


def _js_object(src: str) -> list[tuple[str, str | None]]:
    """Top-level `key: 'string' | other` pairs of an object literal body."""
    out: list[tuple[str, str | None]] = []
    i = 1
    while i < len(src) - 1:
        m = _JS_KEY.match(src, i)
        if not m:
            i += 1
            continue
        key = next(g for g in m.groups() if g is not None)
        text, end = _js_string_expr(src, m.end())
        if text is None:
            k = m.end()
            while k < len(src) and src[k] in " \t\r\n":
                k += 1
            if src.startswith("null", k):
                out.append((key, None))
                i = k + 4
                continue
            out.append((key, None))
            if k < len(src) and src[k] in "{[(":
                i = _balanced(src, k)
            else:
                i = k + 1
                while i < len(src) and src[i] not in ",\n}":
                    i += 1
            continue
        out.append((key, text))
        i = end
    return out


def _js_questions(path: Path, rel: str) -> list[Question]:
    src = path.read_text(errors="replace")
    out: list[Question] = []
    starts = [m for m in re.finditer(r"\binstructions\s*:", src)]
    for i, m in enumerate(starts):
        text, end = _js_string_expr(src, m.end())
        stop = starts[i + 1].start() if i + 1 < len(starts) else len(src)
        window = src[end : min(stop, end + 6000)]
        around = src[max(0, m.start() - 160) : end + 160]
        t = re.search(r"\btype\s*:\s*['\"](\w+)['\"]", around)
        kind = {"boolean": "noul", "noul": "noul", "choice": "choice", "score": "score",
                "scale": "score"}.get((t.group(1) if t else "").lower())
        line = src.count("\n", 0, m.start()) + 1
        q = Question(kind=kind or "choice", file=rel, line=line, instructions=text)
        q.dynamic_instructions = text is None
        c = re.search(r"\bcriteria\s*:\s*", window)
        if not c:
            if kind:  # a typed question with no criteria (a plain Noul) is still a question
                out.append(q)
            continue
        k = c.end()
        if k < len(window) and window[k] in "{[":
            body = window[k : _balanced(window, k)]
            if body[0] == "[":
                q.kind = "score"
                q.levels = [
                    _js_unescape(next(g for g in mm.groups() if g is not None))
                    for mm in _STR.finditer(body)
                ]
            else:
                pairs = dict(_js_object(body))
                if set(pairs) == {"true", "false"}:
                    q.kind, q.true, q.false = "noul", pairs["true"], pairs["false"]
                else:
                    q.kind, q.options = "choice", pairs
        else:
            q.kind, q.options, q.options_dynamic = "choice", None, True
        out.append(q)
    return out


# ---- JSON extraction -----------------------------------------------------------------


def _json_questions(path: Path, rel: str) -> list[Question]:
    try:
        data = json.loads(path.read_text(errors="replace"))
    except ValueError:
        return []
    out: list[Question] = []

    def text(v) -> str | None:
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            parts = [x for x in v.values() if isinstance(x, str)]
            return "\n".join(parts) if parts else None
        return None

    def walk(node, name=None):
        if isinstance(node, dict):
            typed = str(node.get("type", "")).lower() in KINDS
            if "instructions" in node and ("criteria" in node or typed):
                crit = node.get("criteria")
                kind = str(node.get("type", "")).lower()
                if kind not in KINDS:
                    kind = ("score" if isinstance(crit, list) else
                            "noul" if isinstance(crit, dict) and set(crit) == {"true", "false"}
                            else "choice")
                q = Question(kind=kind, file=rel, line=1, name=name)
                q.instructions = text(node["instructions"])
                q.dynamic_instructions = q.instructions is None
                if kind == "noul" and isinstance(crit, dict):
                    q.true, q.false = text(crit.get("true")), text(crit.get("false"))
                elif kind == "choice" and isinstance(crit, dict):
                    q.options = {k: (v if isinstance(v, str) else None) for k, v in crit.items()}
                elif kind == "score" and isinstance(crit, list):
                    q.levels = [x for x in crit if isinstance(x, str)]
                out.append(q)
                return
            for k, v in node.items():
                walk(v, k if isinstance(k, str) else name)
        elif isinstance(node, list):
            for v in node:
                walk(v, name)

    walk(data)
    return out


# ---- rules ---------------------------------------------------------------------------


def _stem(instructions: str) -> str:
    """The clause that sets a question's polarity: the first sentence, cut at the first
    subordinate clause. A negation inside "a question that is not in the clip" does not."""
    first = re.split(r"(?<=[?.!])\s", instructions.strip(), maxsplit=1)[0]
    return re.split(r"\b(?:that|which|who|whose|even|when|while|because|where)\b|--|—|;|:",
                    first, maxsplit=1)[0]


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", s.lower()) if w not in STOP and len(w) > 2}


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def check(q: Question) -> list[Finding]:
    out: list[Finding] = []

    def add(rule: str, sev: str, msg: str, section: str = "") -> None:
        out.append(Finding(rule, sev, q.file, q.line, q.name, msg, section))

    ins = q.instructions or ""
    if q.instructions is not None and len(ins.strip()) < 25:
        add("thin-instructions", "info", f"instructions are {len(ins.strip())} chars: {ins!r}")
    if ins:
        if STATE_ANCHOR.search(ins):
            add("state-anchor", "info", "the instruction names one piece of state as the "
                "place to act; the model will treat it as authoritative", "§4")
        if ARITHMETIC.search(ins):
            add("arithmetic", "info", "asks the model to count, compare or order; do that "
                "in code", "§4")
        if VERDICT.search(ins):
            add("verdict-question", "info", "a general verdict; narrow, locatable questions "
                "keep their spread", "§6")

    if q.kind == "noul" and ins and q.true and NEGATION.search(_stem(ins)) and not NEGATION.search(q.true):
        add("polarity", "info", "the instruction is phrased negatively but `true` is positive: "
            "the model may answer the instruction's yes/no, not your `true`. Make a yes "
            "to the instruction mean `true`", "§1")

    sides = [(s, t) for s, t in (("true", q.true), ("false", q.false)) if t]
    for side, text in sides:
        if len(QUOTED_LIST.findall(text)) >= 1 and len(re.findall(r"""["'“‘`]""", text)) >= 6:
            add("word-list", "warn", f"`{side}` enumerates quoted surface forms: "
                f"{text[:90]!r}", "§1")
        elif SURFACE.search(text):
            add("surface-form", "warn", f"`{side}` is about words, not situations: "
                f"{text[:90]!r}", "§1")
    if q.true and q.false:
        if NEGATION_START.match(q.false.strip()) and _jaccard(q.true, q.false) > 0.35:
            add("false-is-negation", "info", "`false` is `true` negated; describe the "
                "other situation", "§1")
        elif _jaccard(q.true, q.false) > 0.7:
            add("criteria-overlap", "warn", "`true` and `false` use nearly the same words",
                "§1")

    if q.kind == "score" and q.levels is not None:
        if len(q.levels) < 3:
            add("score-levels", "warn", f"{len(q.levels)} level(s); a Score needs levels "
                "that describe distinct situations", "§1")
        bare = [x for x in q.levels if re.fullmatch(r"\W*\d+\W*|.{0,10}", x.strip())]
        if bare:
            add("score-levels", "warn", f"levels that are numbers or near-empty: {bare[:3]}",
                "§1")

    if q.kind == "choice":
        keys = list(q.options or {})
        escape = any(ESCAPE_KEY.match(k) for k in keys) or bool(ESCAPE_TEXT.search(ins))
        if q.options is not None and not escape and (keys or not q.options_dynamic):
            sample = ", ".join(keys[:4]) + ("…" if len(keys) > 4 else "")
            if ACTION.search(ins):
                add("no-escape", "info", f"no none-of-these option among: {sample}; fine if "
                    "some option always applies, as when choosing an action", "§3")
            else:
                add("no-escape", "warn", f"no none-of-these option among: {sample or '(none)'}",
                    "§3")
        elif q.options is None and not escape and q.options_dynamic and not ins:
            pass
    return out


# ---- driver --------------------------------------------------------------------------


def iter_files(roots: list[Path], include_tests: bool):
    for root in roots:
        files = [root] if root.is_file() else root.rglob("*")
        for p in files:
            if not p.is_file() or p.suffix not in {".py", ".js", ".ts", ".mjs", ".tsx", ".jsx", ".json"}:
                continue
            parts = set(p.relative_to(root).parts[:-1]) if root.is_dir() else set()
            if parts & SKIP_DIRS or (not include_tests and parts & TEST_DIRS):
                continue
            if not include_tests and re.match(r"(test_.*|.*_test\.py|.*\.test\.[jt]sx?)$", p.name):
                continue
            if p.stat().st_size > MAX_BYTES or p.name.endswith(".min.js"):
                continue
            if p.suffix == ".json" and p.name in {"package.json", "package-lock.json",
                                                   "tsconfig.json", "composer.json"}:
                continue
            yield root, p


def scan(roots: list[Path], include_tests: bool = False) -> tuple[list[Question], list[Finding]]:
    questions: list[Question] = []
    for root, p in iter_files(roots, include_tests):
        base = root if root.is_dir() else root.parent
        rel = str(p.relative_to(base))
        if p.suffix == ".py":
            questions += _py_questions(p, rel)
        elif p.suffix == ".json":
            questions += _json_questions(p, rel)
        else:
            questions += _js_questions(p, rel)
    findings = [f for q in questions for f in check(q)]
    return questions, findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--include-tests", action="store_true")
    ap.add_argument("--fail-on", choices=("warn", "info"), help="exit 1 on findings at/above")
    args = ap.parse_args(argv)

    questions, findings = scan(args.paths, args.include_tests)
    if args.json:
        json.dump(
            {"questions": [asdict(q) for q in questions], "findings": [asdict(f) for f in findings]},
            sys.stdout,
            indent=1,
        )
        print()
    else:
        by_kind = {k: sum(q.kind == k for q in questions) for k in KINDS}
        print(f"{len(questions)} questions ({by_kind['noul']} noul, {by_kind['choice']} choice, "
              f"{by_kind['score']} score), {len(findings)} findings")
        for f in sorted(findings, key=lambda f: (f.severity != "warn", f.file, f.line)):
            tag = f"{f.name or ''}".strip()
            print(f"  {f.severity:4} {f.rule:18} {f.file}:{f.line} {tag} {f.section}\n"
                  f"       {f.message}")
    gate = {"warn": {"warn"}, "info": {"warn", "info"}}.get(args.fail_on or "", set())
    return 1 if any(f.severity in gate for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
