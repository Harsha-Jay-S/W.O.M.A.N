"""Windows-specific command registry."""

COMMANDS: dict[str, dict] = {
    "Get-ChildItem": {
        "keywords": ["list", "files", "folders", "recursive", "hidden"],
        "templates": {
            "list": "Get-ChildItem",
            "recursive": "Get-ChildItem -Recurse",
            "hidden": "Get-ChildItem -Force",
        },
        "intent_map": {"list": "list", "search": "recursive"},
    },
    "Select-String": {
        "keywords": ["search", "text", "pattern", "grep"],
        "templates": {
            "simple": "Select-String -Pattern '{pattern}' -Path {file}",
            "recursive": "Get-ChildItem -Recurse | Select-String -Pattern '{pattern}'",
        },
        "intent_map": {"search": "simple", "list": "simple"},
    },
    "Get-Process": {
        "keywords": ["process", "pid", "memory", "cpu"],
        "templates": {
            "list": "Get-Process",
            "name": "Get-Process -Name {process}",
            "pid": "Get-Process -Id {pid}",
        },
        "intent_map": {"process": "list", "status": "list"},
    },
    "Stop-Process": {
        "keywords": ["kill", "terminate", "stop", "process", "pid"],
        "templates": {
            "pid": "Stop-Process -Id {pid}",
            "name": "Stop-Process -Name {process}",
        },
        "intent_map": {"kill": "pid", "stop": "pid"},
    },
    "Get-Service": {
        "keywords": ["service", "status", "start", "stop", "windows"],
        "templates": {
            "list": "Get-Service",
            "status": "Get-Service -Name {service}",
        },
        "intent_map": {"status": "list", "start": "list"},
    },
    "Set-Service": {
        "keywords": ["service", "start", "stop", "disable", "enable"],
        "templates": {
            "start": "Set-Service -Name {service} -Status Running",
            "stop": "Set-Service -Name {service} -Status Stopped",
        },
        "intent_map": {"start": "start", "stop": "stop"},
    },
    "netstat": {
        "keywords": ["network", "port", "listening", "connection"],
        "templates": {
            "listening": "netstat -ano | findstr LISTENING",
            "ports": "netstat -ano",
        },
        "intent_map": {"network": "ports", "status": "listening"},
    },
    "taskkill": {
        "keywords": ["kill", "process", "pid", "force"],
        "templates": {
            "pid": "taskkill /PID {pid}",
            "force": "taskkill /PID {pid} /F",
            "name": "taskkill /IM {process}.exe /F",
        },
        "intent_map": {"kill": "pid", "stop": "pid"},
    },
    "ipconfig": {
        "keywords": ["network", "dns", "ip", "adapter"],
        "templates": {
            "all": "ipconfig /all",
            "flush": "ipconfig /flushdns",
        },
        "intent_map": {"network": "all", "status": "all"},
    },
    "winget": {
        "keywords": ["install", "update", "upgrade", "package"],
        "templates": {
            "install": "winget install {package}",
            "upgrade": "winget upgrade {package}",
            "search": "winget search {package}",
        },
        "intent_map": {"install": "install", "update": "upgrade", "upgrade": "upgrade"},
    },
    "choco": {
        "keywords": ["install", "update", "upgrade", "package"],
        "templates": {
            "install": "choco install {package}",
            "upgrade": "choco upgrade {package}",
            "search": "choco search {package}",
        },
        "intent_map": {"install": "install", "update": "upgrade"},
    },
    "where": {
        "keywords": ["locate", "find", "binary", "executable"],
        "templates": {"default": "where {command}"},
        "intent_map": {"search": "default"},
    },
    "Get-Content": {
        "keywords": ["read", "tail", "head", "file", "content"],
        "templates": {
            "head": "Get-Content {file} -TotalCount {lines}",
            "tail": "Get-Content {file} -Tail {lines} -Wait",
        },
        "intent_map": {"list": "head", "monitor": "tail"},
    },
    "Copy-Item": {
        "keywords": ["copy", "duplicate", "files"],
        "templates": {
            "copy": "Copy-Item {source} {destination}",
            "recursive": "Copy-Item {source} {destination} -Recurse",
        },
        "intent_map": {"copy": "copy", "move": "copy"},
    },
    "Move-Item": {
        "keywords": ["move", "rename", "relocate"],
        "templates": {
            "move": "Move-Item {source} {destination}",
            "rename": "Move-Item {source} {destination}",
        },
        "intent_map": {"move": "move"},
    },
    "Remove-Item": {
        "keywords": ["delete", "remove", "erase", "file"],
        "templates": {"remove": "Remove-Item {path}", "force": "Remove-Item {path} -Recurse -Force"},
        "intent_map": {"remove": "remove", "delete": "remove"},
    },
    "Get-NetTCPConnection": {
        "keywords": ["network", "port", "tcp", "connection", "listening"],
        "templates": {"listening": "Get-NetTCPConnection -State Listen", "port": "Get-NetTCPConnection -LocalPort {port}"},
        "intent_map": {"network": "port", "status": "listening"},
    },
    "Test-Connection": {
        "keywords": ["ping", "network", "host"],
        "templates": {"basic": "Test-Connection {host}"},
        "intent_map": {"network": "basic"},
    },
    "icacls": {
        "keywords": ["permissions", "acl", "access"],
        "templates": {"grant": "icacls {path} /grant {user}:F", "list": "icacls {path}"},
        "intent_map": {"permissions": "list"},
    },
    "netsh": {
        "keywords": ["network", "interface", "dns", "proxy"],
        "templates": {"interface": "netsh interface show interface", "dns": "netsh interface ip show dns"},
        "intent_map": {"network": "interface"},
    },
    "New-Item": {
        "keywords": ["create", "new", "file", "folder"],
        "templates": {"file": "New-Item {path} -ItemType File", "dir": "New-Item {path} -ItemType Directory"},
        "intent_map": {"create": "file"},
    },
}
