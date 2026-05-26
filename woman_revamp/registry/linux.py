"""Linux-specific command registry."""

COMMANDS: dict[str, dict] = {
    "find": {
        "keywords": ["files", "directories", "search", "name", "type", "mtime", "size", "delete", "older"],
        "templates": {
            "name": "find {path} -name '{pattern}'",
            "type": "find {path} -type {kind}",
            "directories": "find {path} -type d",
            "files": "find {path} -type f",
            "mtime": "find {path} -type {kind} -mtime {days}",
            "size": "find {path} -type f -size {size}",
            "delete": "find {path} -type f -name '{pattern}' -delete",
        },
        "intent_map": {"search": "name", "list": "directories", "remove": "delete"},
    },
    "lsof": {
        "keywords": ["port", "socket", "network", "process", "open files", "listening"],
        "templates": {
            "port": "lsof -i :{port}",
            "process": "lsof -p {pid}",
            "all": "lsof -i",
        },
        "intent_map": {"network": "port", "process": "process", "status": "all"},
    },
    "ss": {
        "keywords": ["socket", "port", "listening", "network", "connections"],
        "templates": {
            "listening": "ss -tulpn",
            "ports": "ss -ltnp",
        },
        "intent_map": {"network": "listening", "status": "listening"},
    },
    "ip": {
        "keywords": ["interface", "address", "route", "link", "network"],
        "templates": {
            "addr": "ip addr show",
            "link": "ip link show",
            "route": "ip route show",
        },
        "intent_map": {"network": "addr", "list": "addr"},
    },
    "systemctl": {
        "keywords": ["service", "daemon", "status", "start", "stop", "restart", "enable", "disable"],
        "templates": {
            "status": "systemctl status {service}",
            "start": "systemctl start {service}",
            "stop": "systemctl stop {service}",
            "restart": "systemctl restart {service}",
            "enable": "systemctl enable {service}",
            "disable": "systemctl disable {service}",
        },
        "intent_map": {"status": "status", "start": "start", "stop": "stop", "restart": "restart"},
    },
    "journalctl": {
        "keywords": ["logs", "journal", "service", "errors", "follow", "today"],
        "templates": {
            "follow": "journalctl -f",
            "errors": "journalctl -p err -b",
            "service": "journalctl -u {service} -f",
        },
        "intent_map": {"monitor": "follow", "status": "errors"},
    },
    "df": {
        "keywords": ["disk", "space", "filesystem", "usage"],
        "templates": {
            "human": "df -h",
            "inode": "df -hi",
        },
        "intent_map": {"disk": "human", "status": "human"},
    },
    "du": {
        "keywords": ["disk", "size", "usage", "folders", "largest"],
        "templates": {
            "summary": "du -sh {path}",
            "largest": "du -ah {path} | sort -hr | head -n 20",
        },
        "intent_map": {"disk": "summary", "status": "summary"},
    },
    "ps": {
        "keywords": ["process", "pid", "memory", "cpu", "jobs"],
        "templates": {
            "tree": "ps auxf",
            "cpu": "ps aux --sort=-%cpu | head",
            "mem": "ps aux --sort=-%mem | head",
        },
        "intent_map": {"process": "tree", "status": "tree"},
    },
    "kill": {
        "keywords": ["terminate", "stop", "process", "pid"],
        "templates": {
            "pid": "kill {pid}",
            "force": "kill -9 {pid}",
        },
        "intent_map": {"kill": "pid", "stop": "pid"},
    },
    "pkill": {
        "keywords": ["name", "process", "terminate", "kill"],
        "templates": {"name": "pkill -f {process}"},
        "intent_map": {"kill": "name", "stop": "name"},
    },
    "top": {
        "keywords": ["cpu", "memory", "process", "monitor"],
        "templates": {"interactive": "top", "batch": "top -b -n 1"},
        "intent_map": {"monitor": "interactive", "status": "interactive"},
    },
    "chmod": {
        "keywords": ["permissions", "executable", "read", "write", "execute"],
        "templates": {
            "executable": "chmod +x {file}",
            "recursive": "chmod -R {mode} {path}",
        },
        "intent_map": {"permissions": "executable", "run": "executable"},
    },
    "chown": {
        "keywords": ["owner", "group", "permissions"],
        "templates": {"owner": "chown {user}:{group} {path}"},
        "intent_map": {"permissions": "owner"},
    },
    "apt": {
        "keywords": ["package", "install", "remove", "update", "upgrade", "search"],
        "templates": {
            "update": "sudo apt update",
            "upgrade": "sudo apt upgrade",
            "install": "sudo apt install {package}",
            "remove": "sudo apt remove {package}",
            "search": "apt search {package}",
        },
        "intent_map": {"install": "install", "update": "update", "upgrade": "upgrade", "remove": "remove"},
    },
    "mount": {
        "keywords": ["filesystem", "disk", "attach", "mount", "volume"],
        "templates": {"list": "mount | column -t", "mount": "sudo mount {device} {path}"},
        "intent_map": {"disk": "list"},
    },
    "umount": {
        "keywords": ["unmount", "filesystem", "disk"],
        "templates": {"umount": "sudo umount {path}"},
        "intent_map": {"disk": "umount"},
    },
    "xargs": {
        "keywords": ["batch", "many", "arguments", "pipe"],
        "templates": {"default": "xargs {command}"},
        "intent_map": {"run": "default"},
    },
    "awk": {
        "keywords": ["field", "csv", "columns", "filter", "print"],
        "templates": {"print": "awk '{print ${column}}' {file}", "csv": "awk -F, '{print $1}' {file}"},
        "intent_map": {"search": "print", "list": "print"},
    },
    "sed": {
        "keywords": ["replace", "edit", "stream", "text"],
        "templates": {"replace": "sed -i 's/{old}/{new}/g' {file}", "delete": "sed '/{pattern}/d' {file}"},
        "intent_map": {"convert": "replace", "remove": "delete"},
    },
    "ping": {
        "keywords": ["network", "host", "connectivity"],
        "templates": {"basic": "ping {host}", "count": "ping -c {count} {host}"},
        "intent_map": {"network": "basic"},
    },
    "traceroute": {
        "keywords": ["network", "route", "host"],
        "templates": {"trace": "traceroute {host}"},
        "intent_map": {"network": "trace"},
    },
}
