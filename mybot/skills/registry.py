from __future__ import annotations

from pathlib import Path, PurePosixPath

import yaml


class MetadataLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError("Duplicate YAML key")
        result[key] = loader.construct_object(value_node)
    return result


MetadataLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


class SkillRegistry:
    max_skills = 32
    max_bytes = 65536
    max_metadata_bytes = 8192

    def __init__(self, root: Path):
        if Path(root).is_symlink():
            raise ValueError("Skills root cannot be a symlink")
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError("Skills directory does not exist")
        self._skills = {}
        for directory in sorted(self.root.iterdir(), key=lambda p: p.name):
            if directory.name.startswith("."):
                continue
            if directory.is_symlink():
                raise ValueError("Skill directories cannot be symlinks")
            if not directory.is_dir():
                continue
            if len(self._skills) >= self.max_skills:
                raise ValueError("Too many skills (maximum 32)")
            metadata = self._metadata(self._safe_file(directory / "SKILL.md"))
            name = metadata["name"]
            if name in self._skills:
                raise ValueError(f"Duplicate skill name: {name}")
            if name != directory.name:
                raise ValueError("Skill name must match its directory")
            self._skills[name] = metadata

    def _safe_file(self, path: Path) -> Path:
        relative = path.relative_to(self.root)
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Skill files and directories cannot be symlinks")
        if not path.resolve().is_relative_to(self.root) or not path.is_file():
            raise ValueError("Skill file is missing or outside its directory")
        if path.stat().st_size > self.max_bytes:
            raise ValueError("Skill file exceeds 65536 bytes")
        return path

    def _metadata(self, path: Path) -> dict:
        # Only consume frontmatter: the Markdown body is loaded on demand.
        with path.open("rb") as stream:
            if stream.readline(self.max_metadata_bytes + 1).rstrip(b"\r\n") != b"---":
                raise ValueError("SKILL.md must start with YAML frontmatter")
            header = bytearray()
            while True:
                line = stream.readline(self.max_metadata_bytes + 1)
                if not line or len(header) + len(line) > self.max_metadata_bytes:
                    raise ValueError("Missing or oversized YAML frontmatter")
                if line.rstrip(b"\r\n") == b"---":
                    break
                header.extend(line)
        try:
            metadata = yaml.load(header.decode("utf-8"), Loader=MetadataLoader)
        except (yaml.YAMLError, UnicodeError, TypeError, ValueError, RecursionError):
            raise ValueError("Invalid YAML frontmatter") from None
        if not isinstance(metadata, dict) or set(metadata) - {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}:
            raise ValueError("Invalid skill metadata fields")
        name, description = metadata.get("name"), metadata.get("description")
        if not isinstance(name, str) or not 1 <= len(name) <= 64 or (name != name.lower() or name.startswith("-") or name.endswith("-") or "--" in name or not all(c == "-" or c.isalnum() for c in name)):
            raise ValueError("Invalid skill name (1-64 lowercase alphanumeric characters/hyphens)")
        if not isinstance(description, str) or not description.strip() or len(description) > 1024:
            raise ValueError("Invalid skill description (1-1024 characters)")
        for key in ("license", "compatibility", "allowed-tools"):
            if key in metadata and (not isinstance(metadata[key], str) or not metadata[key].strip()):
                raise ValueError(f"Invalid {key}")
        if len(metadata.get("compatibility", "")) > 500:
            raise ValueError("compatibility exceeds 500 characters")
        extra = metadata.get("metadata", {})
        if not isinstance(extra, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in extra.items()):
            raise ValueError("metadata must map strings to strings")
        return metadata

    def index(self) -> list[dict]:
        return [{"name": name, "description": meta["description"]} for name, meta in sorted(self._skills.items())]

    def read(self, name: str, path: str = "SKILL.md") -> str:
        if not isinstance(name, str) or name not in self._skills:
            raise ValueError("Unknown skill name")
        relative = PurePosixPath(path)
        if relative.is_absolute() or ".." in relative.parts or "\\" in path or relative.as_posix() != path:
            raise ValueError("Invalid skill-relative path")
        if path != "SKILL.md" and (len(relative.parts) < 2 or relative.parts[0] != "references" or relative.suffix.lower() not in {".md", ".txt", ".rst"}):
            raise ValueError("Only references/ text documents can be read")
        skill_file = self._safe_file(self.root / name / "SKILL.md")
        if self._metadata(skill_file) != self._skills[name]:
            raise ValueError("Skill metadata changed; restart to refresh index")
        file = self._safe_file(self.root / name / relative)
        try:
            with file.open("rb") as stream:
                data = stream.read(self.max_bytes + 1)
            if len(data) > self.max_bytes:
                raise ValueError("Skill file exceeds size limit")
            text = data.decode("utf-8")
            if "\x00" in text:
                raise ValueError("Skill file is not a text document")
            return text
        except UnicodeError:
            raise ValueError("Skill file is not valid UTF-8") from None
