import io
from pathlib import Path

import pytest

import install as I


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    for d in (".claude", ".hermes/skills", ".config/opencode"):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


STORE = Path(I.__file__).resolve().parent


def test_registry_is_sane():
    assert len({a.id for a in I.AGENTS}) == len(I.AGENTS) >= 15
    assert all(a.confidence in ("verified", "documented", "unverified") for a in I.AGENTS)
    assert all(a.skills.endswith("skills") for a in I.AGENTS)


def test_detects_only_what_exists(home):
    assert {a.id for a in I.AGENTS if I.detected(a)} == {"claude", "hermes", "opencode"}


def test_yes_installs_symlinks_into_detected_agents_only(home, capsys):
    assert I.main(["--yes"]) == 0
    for rel in (".claude/skills", ".hermes/skills", ".config/opencode/skills"):
        link = home / rel / "jev-questions"
        assert link.is_symlink() and link.resolve() == STORE
        assert (link / "SKILL.md").exists()
    assert not (home / ".codex").exists()  # an agent that is not installed is left alone


def test_second_run_is_a_no_op(home, capsys):
    I.main(["--yes"])
    capsys.readouterr()
    I.main(["--yes"])
    assert capsys.readouterr().out.count("already installed") == 3


def test_does_not_overwrite_something_else_unless_forced(home):
    mine = home / ".claude/skills/jev-questions"
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_text("someone else's skill")
    I.main(["--agents", "claude"])
    assert (mine / "SKILL.md").read_text() == "someone else's skill" and not mine.is_symlink()
    I.main(["--agents", "claude", "--force"])
    assert mine.is_symlink()
    assert (home / ".claude/skills/jev-questions.bak/SKILL.md").read_text() == "someone else's skill"


def test_copy_mode_copies_the_useful_parts_and_marks_them(home):
    I.main(["--agents", "claude", "--copy"])
    d = home / ".claude/skills/jev-questions"
    assert not d.is_symlink() and (d / "SKILL.md").exists()
    assert (d / "scripts/spread.py").exists() and (d / I.MARKER).exists()
    assert not (d / "tests").exists() and not (d / ".git").exists()


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


def test_path_installs_into_any_folder(home, tmp_path):
    out = tmp_path / "elsewhere" / "skills"
    I.main(["--path", str(out)])
    assert (out / "jev-questions").is_symlink()


def test_checklist_toggles_and_confirms(home):
    # detected ones start ticked; untick 1, tick 2 and 5-6, then confirm
    picked = I.choose(STORE, "install", tty=io.StringIO("1\n2 5-6\n\n"))
    assert [a.id for a in picked] == ["codex", "hermes", "antigravity", "gemini", "opencode"]


def test_checklist_all_none_and_detected(home):
    assert len(I.choose(STORE, "install", tty=io.StringIO("a\n\n"))) == len(I.AGENTS)
    assert I.choose(STORE, "install", tty=io.StringIO("n\n\n")) == []
    assert {a.id for a in I.choose(STORE, "install", tty=io.StringIO("n\nd\n\n"))} == {
        "claude", "hermes", "opencode"}


def test_checklist_quit_and_garbage(home, capsys):
    with pytest.raises(SystemExit):
        I.choose(STORE, "install", tty=io.StringIO("q\n"))
    picked = I.choose(STORE, "install", tty=io.StringIO("zzz 99\n\n"))
    assert len(picked) == 3  # junk input changes nothing


def test_checklist_eof_cancels(home):
    with pytest.raises(SystemExit):
        I.choose(STORE, "install", tty=io.StringIO(""))


def test_uninstall_checklist_ticks_what_is_installed(home):
    I.main(["--agents", "claude"])
    picked = I.choose(STORE, "uninstall", tty=io.StringIO("\n"))
    assert [a.id for a in picked] == ["claude"]
