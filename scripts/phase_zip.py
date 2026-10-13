"""Validate CRC, required files and safe ZIP paths before extracting."""
import json
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

zip_path, tag, dest = sys.argv[1:]
with ZipFile(zip_path) as archive:
    names = archive.namelist()
    required = {"mybot/main.py", "mybot/agent/loop.py", "pyproject.toml", "uv.lock",
                "config/config.example.json", f"docs/phases/{tag}.md"}
    assert required <= set(names), f"Missing files: {required - set(names)}"
    assert len(names) == len(set(names)), "Duplicate ZIP entries"
    for entry in archive.infolist():
        path = PurePosixPath(entry.filename)
        assert not path.is_absolute() and ".." not in path.parts and "\\" not in entry.filename, "Unsafe ZIP path"
        assert not stat.S_ISLNK(entry.external_attr >> 16), "Symlinks are not allowed"
        assert not any(p in {".git", ".venv", ".mybot_state", "__pycache__", "node_modules"} or p.startswith("._") or p == ".env" or p.startswith(".env.") for p in path.parts), "Forbidden archive entry"
        assert entry.filename != "config/config.json", "Local credentials are forbidden"
        assert path.suffix not in {".pyc", ".pem", ".key", ".p12", ".zip"}, "Private key/cache/archive entry"
    for name in names:
        if not name.endswith("/"):
            data = archive.read(name)
            try:
                document = json.loads(data)
            except (ValueError, UnicodeError):
                document = None
            assert not (isinstance(document, dict) and {"version", "turns"} <= document.keys()), f"Session data is forbidden: {name}"
            assert not re.search(rb"(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)", data), f"Possible credential in {name}"
    assert archive.testzip() is None, "ZIP CRC error"
    template = json.loads(archive.read("config/config.example.json"))
    for provider in template.get("llm", {}).get("providers", {}).values():
        key = provider.get("api_key")
        assert not key or key.startswith("YOUR_"), "Config template contains a real key"
    archive.extractall(dest)
print(f"Validated and extracted {tag}: {len(names)} entries")
