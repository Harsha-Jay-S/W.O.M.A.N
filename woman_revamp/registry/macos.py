"""macOS-specific command registry."""

COMMANDS: dict[str, dict] = {
    "brew": {
        "keywords": ["package", "install", "update", "upgrade", "services"],
        "templates": {
            "install": "brew install {package}",
            "update": "brew update",
            "upgrade": "brew upgrade",
            "search": "brew search {package}",
        },
        "intent_map": {"install": "install", "update": "update", "upgrade": "upgrade"},
    },
    "open": {
        "keywords": ["file", "app", "url", "reveal", "show"],
        "templates": {
            "file": "open {file}",
            "url": "open {url}",
            "reveal": "open -R {file}",
        },
        "intent_map": {"run": "file", "list": "reveal"},
    },
    "pbcopy": {
        "keywords": ["clipboard", "copy", "paste"],
        "templates": {"copy": "pbcopy < {file}"},
        "intent_map": {"copy": "copy"},
    },
    "pbpaste": {
        "keywords": ["clipboard", "copy", "paste"],
        "templates": {"paste": "pbpaste"},
        "intent_map": {"copy": "paste", "list": "paste"},
    },
    "launchctl": {
        "keywords": ["service", "daemon", "start", "stop", "reload"],
        "templates": {
            "list": "launchctl list",
            "start": "launchctl start {label}",
            "stop": "launchctl stop {label}",
        },
        "intent_map": {"status": "list", "start": "start", "stop": "stop"},
    },
    "defaults": {
        "keywords": ["preferences", "settings", "plist", "config"],
        "templates": {
            "read": "defaults read {domain}",
            "write": "defaults write {domain} {key} {value}",
            "delete": "defaults delete {domain} {key}",
        },
        "intent_map": {"search": "read", "remove": "delete", "create": "write"},
    },
    "diskutil": {
        "keywords": ["disk", "volume", "partition", "mount"],
        "templates": {"list": "diskutil list", "info": "diskutil info {device}"},
        "intent_map": {"disk": "list", "status": "info"},
    },
    "screencapture": {
        "keywords": ["screenshot", "capture", "screen"],
        "templates": {
            "full": "screencapture {file}",
            "region": "screencapture -i {file}",
        },
        "intent_map": {"create": "full"},
    },
    "networksetup": {
        "keywords": ["network", "wifi", "dns", "interface"],
        "templates": {
            "list": "networksetup -listallhardwareports",
            "wifi": "networksetup -getairportnetwork {device}",
        },
        "intent_map": {"network": "list"},
    },
    "osascript": {
        "keywords": ["automation", "script", "dialog", "app"],
        "templates": {
            "dialog": "osascript -e 'display dialog \"{text}\"'",
            "run": "osascript {file}",
        },
        "intent_map": {"run": "run", "create": "dialog"},
    },
    "say": {
        "keywords": ["speak", "voice", "announce"],
        "templates": {"say": "say '{text}'"},
        "intent_map": {"run": "say"},
    },
    "system_profiler": {
        "keywords": ["hardware", "software", "system", "info"],
        "templates": {
            "hardware": "system_profiler SPHardwareDataType",
            "software": "system_profiler SPSoftwareDataType",
        },
        "intent_map": {"status": "hardware"},
    },
    "security": {
        "keywords": ["keychain", "password", "certificate", "security"],
        "templates": {
            "find": "security find-generic-password -l {label}",
            "unlock": "security unlock-keychain {file}",
        },
        "intent_map": {"search": "find"},
    },
    "xattr": {
        "keywords": ["metadata", "attributes", "quarantine"],
        "templates": {
            "list": "xattr -l {file}",
            "remove": "xattr -d {attribute} {file}",
        },
        "intent_map": {"list": "list", "remove": "remove"},
    },
    "mdfind": {
        "keywords": ["search", "spotlight", "files", "find"],
        "templates": {"search": "mdfind '{pattern}'"},
        "intent_map": {"search": "search"},
    },
}
