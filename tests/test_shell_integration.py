"""Tests for shell integration snippet generator."""

from woman_revamp.shell_integration import generate_shell_integration


def test_generate_bash_contains_function():
    result = generate_shell_integration("bash")
    assert "woman()" in result
    assert "W.O.M.A.N" in result
    assert "fc -ln -1" in result


def test_generate_bash_includes_last_handling():
    result = generate_shell_integration("bash")
    assert '--last' in result or '"!!"' in result or "'!!'" in result


def test_generate_zsh_contains_function():
    result = generate_shell_integration("zsh")
    assert "woman()" in result
    assert "W.O.M.A.N" in result


def test_generate_zsh_uses_double_brackets():
    result = generate_shell_integration("zsh")
    assert "[[" in result


def test_generate_fish_contains_function():
    result = generate_shell_integration("fish")
    assert "function woman" in result
    assert "W.O.M.A.N" in result


def test_generate_unknown_shell():
    result = generate_shell_integration("tcsh")
    assert "Unsupported" in result


def test_generate_default_shell():
    result = generate_shell_integration()
    assert "woman()" in result


def test_all_three_shells_have_distinct_content():
    bash = generate_shell_integration("bash")
    zsh = generate_shell_integration("zsh")
    fish = generate_shell_integration("fish")
    assert bash != zsh
    assert zsh != fish
    assert fish != bash
