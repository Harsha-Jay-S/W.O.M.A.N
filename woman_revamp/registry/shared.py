"""Shared commands that work across the major platforms."""

COMMANDS: dict[str, dict] = {
    "ls": {
        "keywords": ["list", "files", "folders", "show", "hidden", "verbose", "directory"],
        "templates": {
            "basic": "ls",
            "long": "ls -la",
            "tree": "ls -la {path}",
        },
        "intent_map": {"list": "basic", "status": "long"},
    },
    "cd": {
        "keywords": ["change directory", "folder", "move"],
        "templates": {"basic": "cd {path}"},
        "intent_map": {"run": "basic"},
    },
    "pwd": {
        "keywords": ["current directory", "where am i", "path"],
        "templates": {"basic": "pwd"},
        "intent_map": {"status": "basic", "list": "basic"},
    },
    "mkdir": {
        "keywords": ["create", "folder", "directory"],
        "templates": {"basic": "mkdir {path}", "parents": "mkdir -p {path}"},
        "intent_map": {"create": "basic"},
    },
    "touch": {
        "keywords": ["create", "file", "empty"],
        "templates": {"basic": "touch {file}"},
        "intent_map": {"create": "basic"},
    },
    "cp": {
        "keywords": ["copy", "duplicate", "files", "folders"],
        "templates": {
            "basic": "cp {source} {destination}",
            "recursive": "cp -r {source} {destination}",
        },
        "intent_map": {"copy": "basic", "move": "basic"},
    },
    "mv": {
        "keywords": ["move", "rename", "relocate", "files", "folders"],
        "templates": {
            "basic": "mv {source} {destination}",
            "rename": 'for f in *.{from_ext}; do mv -- "$f" "${f%.{from_ext}}.{to_ext}"; done',
        },
        "intent_map": {"move": "basic", "rename": "rename"},
    },
    "rm": {
        "keywords": ["delete", "remove", "erase", "files", "folders"],
        "templates": {
            "basic": "rm {path}",
            "recursive": "rm -r {path}",
            "force": "rm -rf {path}",
        },
        "intent_map": {"remove": "basic", "delete": "basic"},
    },
    "cat": {
        "keywords": ["read", "show", "file", "content"],
        "templates": {"basic": "cat {file}"},
        "intent_map": {"list": "basic", "search": "basic"},
    },
    "head": {
        "keywords": ["first", "lines", "read", "preview"],
        "templates": {"basic": "head -n {lines} {file}"},
        "intent_map": {"list": "basic"},
    },
    "tail": {
        "keywords": ["last", "lines", "monitor", "follow"],
        "templates": {"basic": "tail -n {lines} {file}", "follow": "tail -f {file}"},
        "intent_map": {"monitor": "follow", "list": "basic"},
    },
    "wc": {
        "keywords": ["count", "lines", "words", "bytes"],
        "templates": {"basic": "wc -l {file}", "words": "wc -w {file}"},
        "intent_map": {"status": "basic", "list": "basic"},
    },
    "git": {
        "keywords": [
            "version control",
            "commit",
            "branch",
            "merge",
            "stash",
            "clone",
            "diff",
            "undo",
        ],
        "templates": {
            "status": "git status",
            "log": "git log --oneline --graph --decorate -n 10",
            "branch": "git branch -a",
            "undo_commit": "git reset --soft HEAD~1",
            "clone": "git clone {url}",
            "diff": "git diff",
        },
        "intent_map": {
            "status": "status",
            "git": "status",
            "list": "branch",
            "search": "diff",
            "remove": "undo_commit",
        },
    },
    "docker": {
        "keywords": ["container", "image", "compose", "run", "build", "ps", "logs"],
        "templates": {
            "list": "docker ps",
            "all": "docker ps -a",
            "logs": "docker logs {container}",
            "run": "docker run --rm -it {image}",
            "compose_up": "docker compose up -d",
        },
        "intent_map": {
            "list": "list",
            "run": "run",
            "start": "compose_up",
            "status": "list",
        },
    },
    "curl": {
        "keywords": [
            "http",
            "url",
            "request",
            "download",
            "api",
            "headers",
            "post",
            "get",
        ],
        "templates": {
            "get": "curl -L {url}",
            "download": "curl -L -o {file} {url}",
            "headers": "curl -I {url}",
            "post": "curl -X POST -H 'Content-Type: application/json' -d '{json}' {url}",
        },
        "intent_map": {"download": "download", "search": "get", "run": "get"},
    },
    "wget": {
        "keywords": ["download", "fetch", "url", "mirror"],
        "templates": {
            "download": "wget {url}",
            "recursive": "wget -r -np -k {url}",
        },
        "intent_map": {"download": "download"},
    },
    "ssh": {
        "keywords": ["remote", "server", "login", "host", "key", "tunnel"],
        "templates": {
            "connect": "ssh {user}@{host}",
            "key_copy": "ssh-copy-id {user}@{host}",
            "tunnel": "ssh -L {local_port}:{target_host}:{target_port} {user}@{host}",
        },
        "intent_map": {"run": "connect", "network": "tunnel"},
    },
    "tar": {
        "keywords": ["archive", "compress", "extract", "gzip", "tgz", "bundle", "pack"],
        "templates": {
            "extract_gz": "tar -xzf {file}",
            "extract_bz2": "tar -xjf {file}",
            "compress": "tar -czf {archive}.tar.gz {target}",
            "list": "tar -tzf {file}",
        },
        "intent_map": {"extract": "extract_gz", "compress": "compress", "list": "list"},
    },
    "zip": {
        "keywords": ["archive", "compress", "zip", "bundle"],
        "templates": {
            "compress": "zip -r {archive}.zip {target}",
            "list": "zipinfo {file}",
        },
        "intent_map": {"compress": "compress", "list": "list"},
    },
    "unzip": {
        "keywords": ["extract", "zip", "archive", "unpack"],
        "templates": {
            "extract": "unzip {file}",
            "extract_to": "unzip {file} -d {dir}",
        },
        "intent_map": {"extract": "extract", "list": "extract"},
    },
    "python": {
        "keywords": ["script", "run", "module", "venv", "package"],
        "templates": {
            "run": "python {file}",
            "module": "python -m {module}",
            "venv": "python -m venv .venv",
        },
        "intent_map": {"run": "run", "create": "venv"},
    },
    "pip": {
        "keywords": ["package", "install", "upgrade", "uninstall", "requirements"],
        "templates": {
            "install": "pip install {package}",
            "upgrade": "pip install -U {package}",
            "requirements": "pip install -r requirements.txt",
        },
        "intent_map": {"install": "install", "update": "upgrade", "upgrade": "upgrade"},
    },
    "node": {
        "keywords": ["javascript", "run", "script", "package"],
        "templates": {"run": "node {file}", "version": "node -v"},
        "intent_map": {"run": "run"},
    },
    "npm": {
        "keywords": ["package", "install", "script", "node", "dependencies"],
        "templates": {
            "install": "npm install",
            "script": "npm run {script}",
            "update": "npm update",
        },
        "intent_map": {"install": "install", "run": "script", "update": "update"},
    },
    "jq": {
        "keywords": ["json", "parse", "filter", "query"],
        "templates": {
            "pretty": "jq '.' {file}",
            "key": "jq '.{path}' {file}",
        },
        "intent_map": {"search": "key", "list": "pretty", "convert": "pretty"},
    },
    "rsync": {
        "keywords": ["sync", "copy", "mirror", "backup"],
        "templates": {
            "copy": "rsync -av {source} {destination}",
            "mirror": "rsync -av --delete {source} {destination}",
        },
        "intent_map": {"copy": "copy", "move": "copy", "upload": "copy"},
    },
    "grep": {
        "keywords": ["search", "text", "pattern", "find", "match"],
        "templates": {
            "recursive": "grep -Rin {pattern} {path}",
            "simple": "grep -n {pattern} {file}",
            "case_insensitive": "grep -Rni {pattern} {path}",
        },
        "intent_map": {"search": "recursive", "list": "simple"},
    },
}
