#!/usr/bin/env python3
"""Install the jev-questions skill into the coding agents you use. Standard library only.

    python3 install.py                      pick agents from a checklist
    python3 install.py --list               show every known agent and where it would go
    python3 install.py --yes                install into every agent detected on this machine
    python3 install.py --agents claude,codex,hermes
    python3 install.py --all                every known agent, detected or not
    python3 install.py --uninstall          remove it again (asks the same way)

    curl -fsSL https://raw.githubusercontent.com/VBS2004/jev-questions-skill/main/install.py | python3 -

Options: --copy (copy files instead of symlinking), --dry-run (print, change nothing),
--force (replace something already at the target), --path DIR (also install into DIR),
--update (re-fetch the skill, then relink).

One copy of the skill lives in a store (this checkout, or ~/.local/share/jev-questions-skill
when run from a pipe) and each agent gets a symlink to it, so updating is one `git pull`.
Nothing is overwritten unless it is ours: a different file or folder at the target is
skipped with a message unless you pass --force, and --force moves it aside to `.bak`.

How sure each path is is shown in the list. "verified" means the folder exists on this
machine holding real SKILL.md skills, or the tool's own source says where it reads them;
"documented" is from the tool's docs; "unverified" is from memory of the tool's conventions
and has not been checked. For those, a wrong guess creates a harmless unused folder.
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

NAME = "jev-questions"
TARBALL = "https://github.com/VBS2004/jev-questions-skill/archive/refs/heads/main.tar.gz"
MARKER = ".installed-by-jev-questions"
COPY_PARTS = ("SKILL.md", "LICENSE", "README.md", "scripts", "examples")


@dataclass(frozen=True)
class Agent:
    id: str
    name: str
    skills: str  # skills folder, relative to home
    detect: tuple[str, ...]  # any of these existing under home means the tool is installed
    confidence: str  # verified | documented | unverified
    note: str = ""


AGENTS: tuple[Agent, ...] = (
    Agent("claude", "Claude Code", ".claude/skills", (".claude",), "verified"),
    Agent("codex", "OpenAI Codex CLI", ".codex/skills", (".codex",), "verified"),
    Agent("agents", "Shared standard (~/.agents)", ".agents/skills", (".agents",), "verified",
          "read by several tools; Omarchy links its skills here too"),
    Agent("hermes", "Hermes Agent", ".hermes/skills", (".hermes",), "verified",
          "scans the folder recursively for SKILL.md"),
    Agent("antigravity", "Google Antigravity", ".gemini/config/skills",
          (".gemini/antigravity", ".gemini/antigravity-ide", ".antigravity-ide"), "documented",
          "global customizations live in ~/.gemini/config/"),
    Agent("gemini", "Gemini CLI", ".gemini/skills", (".gemini/settings.json",), "unverified"),
    Agent("opencode", "OpenCode", ".config/opencode/skills", (".config/opencode",), "unverified"),
    Agent("copilot", "GitHub Copilot CLI", ".copilot/skills", (".copilot",), "unverified"),
    Agent("cursor", "Cursor", ".cursor/skills", (".cursor",), "unverified"),
    Agent("windsurf", "Windsurf", ".codeium/windsurf/skills", (".codeium/windsurf",), "unverified"),
    Agent("cline", "Cline", ".cline/skills", (".cline",), "unverified"),
    Agent("roo", "Roo Code", ".roo/skills", (".roo",), "unverified"),
    Agent("kiro", "Kiro", ".kiro/skills", (".kiro",), "unverified"),
    Agent("amp", "Amp", ".config/agents/skills", (".config/amp", ".config/agents"), "unverified"),
    Agent("goose", "Goose", ".config/goose/skills", (".config/goose",), "unverified"),
    Agent("droid", "Factory Droid", ".factory/skills", (".factory",), "unverified"),
    Agent("qwen", "Qwen Code", ".qwen/skills", (".qwen",), "unverified"),
    Agent("crush", "Crush", ".config/crush/skills", (".config/crush",), "unverified"),
    Agent("augment", "Augment (Auggie)", ".augment/skills", (".augment",), "unverified"),
    Agent("junie", "JetBrains Junie", ".junie/skills", (".junie",), "unverified"),
    Agent("vibe", "Mistral Vibe", ".vibe/skills", (".vibe",), "unverified"),
)
BY_ID = {a.id: a for a in AGENTS}


def home() -> Path:
    return Path(os.environ.get("HOME") or os.path.expanduser("~"))


def detected(a: Agent) -> bool:
    return any((home() / d).exists() for d in a.detect)


def target(a: Agent) -> Path:
    return home() / a.skills / NAME


# ---- the store -----------------------------------------------------------------------


def find_store(update: bool = False) -> Path:
    """Where the one real copy lives: this checkout, or a downloaded one."""
    here = Path(__file__).resolve().parent if "__file__" in globals() else None
    if here and (here / "SKILL.md").exists() and not update:
        return here
    if here and (here / "SKILL.md").exists() and update and (here / ".git").exists():
        os.system(f"git -C '{here}' pull --ff-only")
        return here
    store = Path(os.environ.get("XDG_DATA_HOME") or home() / ".local" / "share") / "jev-questions-skill"
    if (store / "SKILL.md").exists() and not update:
        return store
    print(f"downloading {TARBALL}")
    with urllib.request.urlopen(TARBALL, timeout=60) as resp:
        data = resp.read()
    tmp = store.with_name(store.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        top = tar.getmembers()[0].name.split("/")[0]
        for m in tar.getmembers():
            if m.name.split("/", 1)[0] != top or ".." in m.name:
                continue
            m.name = m.name.split("/", 1)[1] if "/" in m.name else ""
            if m.name and (m.isfile() or m.isdir()):  # never links or devices from a tarball
                tar.extract(m, tmp)
    shutil.rmtree(store, ignore_errors=True)
    store.parent.mkdir(parents=True, exist_ok=True)
    tmp.rename(store)
    return store


# ---- install / uninstall -------------------------------------------------------------


def is_ours(path: Path, store: Path) -> bool:
    if path.is_symlink():
        try:
            return path.resolve() == store.resolve()
        except OSError:
            return False
    return (path / MARKER).exists()


def install_one(a: Agent, store: Path, copy: bool, force: bool, dry: bool) -> str:
    dest = target(a)
    if dest.exists() or dest.is_symlink():
        if is_ours(dest, store):
            return "already installed"
        if not force:
            return f"skipped: something else is at {dest} (use --force to move it aside)"
        if dry:
            return f"would move {dest} aside and install"
        bak = dest.with_name(dest.name + ".bak")
        if bak.is_symlink() or bak.is_file():
            bak.unlink()
        elif bak.is_dir():
            shutil.rmtree(bak)
        dest.rename(bak)
    if dry:
        return f"would {'copy to' if copy else 'link'} {dest}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if copy:
        dest.mkdir()
        for part in COPY_PARTS:
            src = store / part
            if src.is_dir():
                shutil.copytree(src, dest / part, ignore=shutil.ignore_patterns("__pycache__"))
            elif src.exists():
                shutil.copy2(src, dest / part)
        (dest / MARKER).write_text("installed by jev-questions install.py\n")
        return f"copied to {dest}"
    dest.symlink_to(store, target_is_directory=True)
    return f"linked {dest} -> {store}"


def uninstall_one(a: Agent, store: Path, dry: bool) -> str:
    dest = target(a)
    if not (dest.exists() or dest.is_symlink()):
        return "not installed"
    if not is_ours(dest, store) and not (dest.is_symlink() and NAME in str(os.readlink(dest))):
        return f"left alone: {dest} was not installed by this script"
    if dry:
        return f"would remove {dest}"
    if dest.is_symlink():
        dest.unlink()
    else:
        shutil.rmtree(dest)
    return f"removed {dest}"


# ---- choosing ------------------------------------------------------------------------


def status(a: Agent, store: Path) -> str:
    d = target(a)
    if d.exists() or d.is_symlink():
        return "installed" if is_ours(d, store) else "occupied"
    return ""


def show(store: Path) -> None:
    print(f"{'#':>2}  {'':3} {'agent':30} {'found':5} {'path':34} {'confidence':11} state")
    for i, a in enumerate(AGENTS, 1):
        print(f"{i:2}  {'':3} {a.name:30} {'yes' if detected(a) else '-':5} "
              f"~/{a.skills:32} {a.confidence:11} {status(a, store)}")


def choose(store: Path, verb: str, tty=None) -> list[Agent]:
    """A numbered checklist on the terminal. Detected agents start ticked. `tty` is where
    answers are read from: /dev/tty when the script itself arrives on stdin (curl | python3)."""
    if tty is None:
        try:
            tty = open("/dev/tty") if not sys.stdin.isatty() else sys.stdin
        except OSError:
            raise SystemExit("no terminal to ask on: pass --agents a,b, --yes or --all "
                             "(see --list for the ids)")
    ticked = {a.id for a in AGENTS if detected(a)} if verb == "install" else {
        a.id for a in AGENTS if status(a, store) == "installed"}
    while True:
        print(f"\n{verb.capitalize()} jev-questions for which agents?\n")
        for i, a in enumerate(AGENTS, 1):
            box = "[x]" if a.id in ticked else "[ ]"
            tag = f"{a.confidence}" + (", detected" if detected(a) else "")
            st = status(a, store)
            print(f" {i:2}. {box} {a.name:30} ~/{a.skills:30} ({tag}){'  <- ' + st if st else ''}")
        print("\n numbers to toggle (e.g. 1 3 5-7) | a all | d detected | n none | "
              "Enter to continue | q quit")
        print("> ", end="", flush=True)
        line = tty.readline()
        if not line:
            raise SystemExit("\ncancelled")
        line = line.strip().lower()
        if line in ("q", "quit"):
            raise SystemExit("cancelled")
        if line == "":
            return [a for a in AGENTS if a.id in ticked]
        if line == "a":
            ticked = {a.id for a in AGENTS}
        elif line == "n":
            ticked = set()
        elif line == "d":
            ticked = {a.id for a in AGENTS if detected(a)}
        else:
            for tok in line.replace(",", " ").split():
                lo, _, hi = tok.partition("-")
                try:
                    nums = range(int(lo), int(hi or lo) + 1)
                except ValueError:
                    print(f"  ? {tok}")
                    continue
                for n in nums:
                    if 1 <= n <= len(AGENTS):
                        ticked ^= {AGENTS[n - 1].id}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="show known agents and exit")
    ap.add_argument("--agents", help="comma-separated ids, e.g. claude,codex,hermes")
    ap.add_argument("--all", action="store_true", help="every known agent, detected or not")
    ap.add_argument("--yes", "-y", action="store_true", help="every detected agent, no prompt")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--copy", action="store_true", help="copy instead of symlink")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--update", action="store_true", help="re-fetch the skill first")
    ap.add_argument("--path", action="append", default=[], help="also install into DIR/jev-questions")
    a = ap.parse_args(argv)

    store = find_store(a.update)
    if a.list:
        show(store)
        return 0

    verb = "uninstall" if a.uninstall else "install"
    if a.agents:
        ids = [x.strip() for x in a.agents.split(",") if x.strip()]
        bad = [i for i in ids if i not in BY_ID]
        if bad:
            raise SystemExit(f"unknown agent(s): {', '.join(bad)}; ids: {', '.join(BY_ID)}")
        picked = [BY_ID[i] for i in ids]
    elif a.all:
        picked = list(AGENTS)
    elif a.yes:
        picked = [x for x in AGENTS if detected(x)]
    elif a.path:
        picked = []
    else:
        picked = choose(store, verb)

    # --path DIR: an arbitrary skills folder, outside the registry
    extra = []
    for p in a.path:
        d = Path(p).expanduser().resolve()
        try:
            rel = str(d.relative_to(home()))
        except ValueError:
            rel = str(d)  # absolute: home() / absolute == absolute
        extra.append(Agent("path", str(d), rel, (), "verified"))
    if not picked and not extra:
        print("nothing selected")
        return 0
    print(f"\n{'dry run: ' if a.dry_run else ''}{verb} from {store}\n")
    for ag in picked + extra:
        res = (uninstall_one(ag, store, a.dry_run) if a.uninstall
               else install_one(ag, store, a.copy, a.force, a.dry_run))
        print(f"  {ag.name:30} {res}")
    if not a.uninstall and not a.dry_run:
        print("\nRestart the agent (or start a new session) so it picks the skill up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
