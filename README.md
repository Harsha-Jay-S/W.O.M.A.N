# woman_revamp

Local command registry and scoring engine for `woman`.

This package is the offline fallback engine used by `woman.py`. It resolves common shell tasks from local rules and registry data, then asks for confirmation before execution.

## Layout

- `engine.py`: tokenization, typo correction, intent extraction, scoring, template filling.
- `registry/`: command knowledge base split by OS and shared commands.
- `cli.py`: interactive CLI that prints a command, asks `y/n`, then executes it on approval.

## Run

```bash
cd ~/woman
export PYTHONPATH="$HOME/woman:$PYTHONPATH"
python -m woman_revamp --list
python -m woman_revamp "extract this gzip file"
python -m woman_revamp --os linux --json "what is using port 8080"
```

## Behavior

- Normal queries return a suggested command and a confirmation prompt.
- `y` or `yes` executes the command.
- `n`, `Ctrl+C`, or `Ctrl+D` aborts cleanly.
- Very vague prompts should return `no confident local match`.

## Troubleshooting

- If Python cannot import `woman_revamp`, set `PYTHONPATH` to `~/woman` or run commands from inside that folder.
- If a vague prompt still produces a bad command, the query needs to be more specific.
- If you want to test without executing, press `n` at the confirmation prompt.

## Use with `woman`

`woman.py` now tries `woman_revamp` before `tldr` and `cheat.sh` if the package is on `PYTHONPATH`.

```bash
cd ~/woman
python woman.py "extract this gzip file"
```
