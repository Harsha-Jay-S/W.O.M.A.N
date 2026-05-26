from .bootstrap import ensure_runtime_dependencies

ensure_runtime_dependencies()

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
