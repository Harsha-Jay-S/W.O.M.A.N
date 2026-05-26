"""Longer natural-language phrases mapped to canonical intents."""

INTENT_PHRASES: list[tuple[str, list[str]]] = [
    ("kill", ["get rid of", "shut down", "turn off", "stop the process", "kill whatever is"]),
    ("restart", ["restart the service", "bounce the service", "reload the service"]),
    ("status", ["what is running", "whats running", "show me running", "check status"]),
    ("search", ["look for", "find all", "search for", "locate", "where is"]),
    ("extract", ["unpack", "pull files from", "open archive", "get files out of"]),
    ("compress", ["make a zip", "create an archive", "bundle up", "compress these files"]),
    ("install", ["install this package", "set this up", "add this tool"]),
    ("update", ["refresh packages", "pull updates", "update my system"]),
    ("remove", ["get rid of", "remove this", "delete this", "uninstall this"]),
    ("monitor", ["watch in real time", "keep an eye on", "follow live"]),
    ("network", ["whats using port", "who is using port", "what is on port", "network port"]),
    ("disk", ["how much space", "whats taking space", "disk usage", "storage usage"]),
    ("process", ["which process", "running process", "process id", "pid of"]),
    ("git", ["undo my last commit", "show me branches", "what changed in git"]),
    ("copy", ["make a copy of", "duplicate this", "copy these files"]),
    ("move", ["rename all", "move these files", "relocate this"]),
    ("permissions", ["change permissions", "make it executable", "fix file rights"]),
    ("download", ["download this file", "save from url", "fetch from the internet"]),
    ("upload", ["push to remote", "send this file", "copy it up"]),
    ("run", ["run this script", "execute this", "start the app"]),
]
