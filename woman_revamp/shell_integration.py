"""Shell integration snippet generator for woman."""

from __future__ import annotations

BASH_FUNCTION = """\
# W.O.M.A.N shell integration
# Source this file or add to ~/.bashrc
woman() {
    if [ "$1" = "--last" ] || [ "$1" = "!!" ]; then
        local last_cmd=$(fc -ln -1 2>/dev/null || echo "")
        shift
        command woman --context "last command: $last_cmd" "$@"
    elif [ "$1" = "search" ]; then
        shift
        command woman "$@"
    else
        command woman "$@"
    fi
}
"""

ZSH_FUNCTION = """\
# W.O.M.A.N shell integration
# Source this file or add to ~/.zshrc
woman() {
    if [[ "$1" == "--last" || "$1" == "!!" ]]; then
        local last_cmd=$(fc -ln -1 2>/dev/null || echo "")
        shift
        command woman --context "last command: $last_cmd" "$@"
    elif [[ "$1" == "search" ]]; then
        shift
        command woman "$@"
    else
        command woman "$@"
    fi
}
"""

FISH_FUNCTION = """\
# W.O.M.A.N shell integration
# Source this file or add to ~/.config/fish/config.fish
function woman --wraps woman
    if test "$argv[1]" = "--last" -o "$argv[1]" = "!!"
        set -l last_cmd (history | head -n1)
        set -e argv[1]
        command woman --context "last command: $last_cmd" $argv
    else
        command woman $argv
    end
end
"""


def generate_shell_integration(shell: str = "bash") -> str:
    """Return the shell integration snippet for the given shell."""
    text = {
        "bash": BASH_FUNCTION,
        "zsh": ZSH_FUNCTION,
        "fish": FISH_FUNCTION,
    }.get(shell)
    if text is None:
        return f"echo 'Unsupported shell: {shell}. Use bash, zsh, or fish.'"
    return text
