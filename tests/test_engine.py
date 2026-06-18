from woman_revamp.config import WomanConfig
from woman_revamp.engine import call_local_registry, fill_template


def test_fill_template_requires_days():
    assert (
        fill_template(
            "find {path} -type {kind} -mtime {days}", {"path": ".", "kind": "d"}
        )
        is None
    )


def test_fill_template_renders_when_complete():
    assert (
        fill_template(
            "find {path} -type {kind} -mtime {days}",
            {"path": ".", "kind": "d", "days": "7"},
        )
        == "find . -type d -mtime 7"
    )


def test_directory_query_prefers_directory_find():
    rendered = call_local_registry(
        "find all directories in this folder",
        context="Current directory: /home/jayharsha\nFiles:",
        os_info="linux",
    )
    assert rendered == "find /home/jayharsha -type d"


def test_config_defaults_to_300_lines():
    assert WomanConfig().man_page_limit == 300
