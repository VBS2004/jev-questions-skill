import io
from pathlib import Path

import pytest

import install as I


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    for d in (".claude", ".hermes/skills", ".config/opencode"):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


STORE = Path(I.__file__).resolve().parent
SRC = STORE / "skills" / "jev-questions"


def test_table_parses_into_a_big_sane_registry():
    assert len(I.AGENTS) >= 60
    assert len({a.id for a in I.AGENTS}) == len(I.AGENTS)
    for a in I.AGENTS:
        assert a.project and (a.glob is None or a.glob.endswith("skills") or "skills" in a.glob)
    claude = I.BY_ID["claude-code"]
    assert claude.glob == ".claude/skills" and claude.project == ".claude/skills"
    assert I.BY_ID["claude"] is claude  # aliases
    assert I.BY_ID["codex"].project == ".agents/skills" and I.BY_ID["codex"].glob == ".codex/skills"


def test_shared_folder_tools_are_one_row():
    shared = I.BY_ID["cline"]
    assert shared.glob == ".agents/skills" and "Zed" in shared.name and "Warp" in shared.name
    assert I.BY_ID["zed"] is shared and I.BY_ID["pi"] is shared


def test_detects_only_what_exists(home):
    found = {a.id for a in I.AGENTS if I.detected(a)}
    assert {"claude-code", "hermes-agent", "opencode"} <= found
    assert "codex" not in found and "cursor" not in found


def test_gemini_cli_is_not_detected_just_because_antigravity_uses_dot_gemini(home):
    (home / ".gemini" / "antigravity").mkdir(parents=True)
    assert not I.detected(I.BY_ID["gemini-cli"]) and I.detected(I.BY_ID["antigravity"])


def test_yes_symlinks_into_found_agents_only(home):
    assert I.main(["--yes"]) == 0
    for rel in (".claude/skills", ".hermes/skills", ".config/opencode/skills"):
        link = home / rel / "jev-questions"
        assert link.is_symlink() and link.resolve() == SRC.resolve()
        assert (link / "SKILL.md").exists() and (link / "scripts/spread.py").exists()
    assert not (home / ".codex").exists()


def test_the_installed_skill_is_just_the_skill(home):
    I.main(["--agents", "claude", "--copy"])
    d = home / ".claude/skills/jev-questions"
    assert (d / "SKILL.md").exists() and (d / "scripts").is_dir() and (d / I.MARKER).exists()
    assert not (d / "tests").exists() and not (d / "install.py").exists()
    assert not (d / "scripts/__pycache__").exists()


def test_second_run_is_a_no_op(home, capsys):
    I.main(["--yes"])
    capsys.readouterr()
    I.main(["--yes"])
    assert capsys.readouterr().out.count("already installed") >= 3


def test_does_not_overwrite_something_else_unless_forced(home):
    mine = home / ".claude/skills/jev-questions"
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_text("someone else's skill")
    I.main(["--agents", "claude"])
    assert (mine / "SKILL.md").read_text() == "someone else's skill" and not mine.is_symlink()
    I.main(["--agents", "claude", "--force"])
    assert mine.is_symlink()
    assert (home / ".claude/skills/jev-questions.bak/SKILL.md").read_text() == "someone else's skill"


def test_tools_that_share_a_folder_install_once(home, capsys):
    I.main(["--agents", "cline,zed,pi"])
    out = capsys.readouterr().out
    assert out.count("linked") == 1
    assert (home / ".agents/skills/jev-questions").is_symlink()


def test_uninstall_removes_ours_and_leaves_foreign_alone(home):
    I.main(["--agents", "claude,hermes", "--copy"])
    foreign = home / ".config/opencode/skills/jev-questions"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("not ours")
    I.main(["--agents", "claude,hermes,opencode", "--uninstall"])
    assert not (home / ".claude/skills/jev-questions").exists()
    assert not (home / ".hermes/skills/jev-questions").exists()
    assert (foreign / "SKILL.md").read_text() == "not ours"


def test_dry_run_changes_nothing(home, capsys):
    I.main(["--yes", "--dry-run"])
    assert not (home / ".claude/skills").exists()
    assert "would link" in capsys.readouterr().out


def test_unknown_agent_is_an_error(home):
    with pytest.raises(SystemExit) as e:
        I.main(["--agents", "claude,nope"])
    assert "nope" in str(e.value)


def test_project_scope_copies_into_the_project(home, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    import os
    os.chdir(proj)
    I.main(["--agents", "claude,codex", "--project"])
    assert (proj / ".claude/skills/jev-questions/SKILL.md").exists()
    assert not (proj / ".claude/skills/jev-questions").is_symlink()  # committable
    assert (proj / ".agents/skills/jev-questions/SKILL.md").exists()  # codex's project folder
    assert not (home / ".claude/skills/jev-questions").exists()


def test_project_only_agent_has_no_global_install(home, capsys):
    I.main(["--agents", "eve"])
    assert "no global folder" in capsys.readouterr().out


def test_path_installs_into_any_folder(home, tmp_path):
    out = tmp_path / "elsewhere" / "skills"
    I.main(["--path", str(out)])
    assert (out / "jev-questions").is_symlink()


def test_checklist_lists_found_agents_first_and_toggles(home):
    rows = I.ordered()
    found = [a for a in rows if I.detected(a)]
    assert rows[: len(found)] == found
    picked = I.choose(STORE, "install", tty=io.StringIO("n\n1 2\n\n"))
    assert picked == rows[:2]


def test_checklist_all_none_found_and_ranges(home):
    assert len(I.choose(STORE, "install", tty=io.StringIO("a\n\n"))) == len(I.AGENTS)
    assert I.choose(STORE, "install", tty=io.StringIO("n\n\n")) == []
    found = {a.id for a in I.AGENTS if I.detected(a)}
    assert {a.id for a in I.choose(STORE, "install", tty=io.StringIO("n\nd\n\n"))} == found
    assert len(I.choose(STORE, "install", tty=io.StringIO("n\n1-5\n\n"))) == 5


def test_checklist_quit_garbage_and_eof(home):
    with pytest.raises(SystemExit):
        I.choose(STORE, "install", tty=io.StringIO("q\n"))
    with pytest.raises(SystemExit):
        I.choose(STORE, "install", tty=io.StringIO(""))
    found = [a for a in I.AGENTS if I.detected(a)]
    assert len(I.choose(STORE, "install", tty=io.StringIO("zzz 9999\n\n"))) == len(found)


def test_interactive_flow_asks_scope_then_installs(home, tmp_path):
    import os
    proj = tmp_path / "p"
    proj.mkdir()
    os.chdir(proj)
    # tick only item 1 (a found agent), confirm, answer "p" to the scope question
    first = I.ordered()[0]
    I.main([], tty=io.StringIO("n\n1\n\np\n"))
    assert (proj / first.project / "jev-questions/SKILL.md").exists()


def test_uninstall_checklist_ticks_what_is_installed(home):
    I.main(["--agents", "claude"])
    picked = I.choose(STORE, "uninstall", tty=io.StringIO("\n"))
    assert [a.id for a in picked] == ["claude-code"]
