"""Explicit, content-addressed experimental skills; no native registry changes."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from . import PACKAGE_DIR

LIBRARY_ROOT = PACKAGE_DIR / "skills"
CONTAINER_ROOT = "/workspace/.benchmark-skills"
DELIVERY_MODE = "on-demand-catalog-v1"
_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def validate_selection(value: object) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(name, str) or len(name) > 64 or not _NAME.fullmatch(name)
        for name in value
    ):
        raise ValueError("experiment_skills must be a list of lowercase hyphenated skill names")
    if len(value) != len(set(value)):
        raise ValueError("experiment_skills must not contain duplicates")
    return sorted(value)


def validate_source(value: object) -> None:
    if not isinstance(value, dict) or set(value) - {"path", "sha256"}:
        raise ValueError("experiment_skill_library accepts only path and optional sha256")
    if not isinstance(value.get("path"), str) or not value["path"]:
        raise ValueError("experiment_skill_library.path must be a nonempty string")
    if "sha256" in value and (
        not isinstance(value["sha256"], str)
        or not re.fullmatch(r"[a-f0-9]{64}", value["sha256"])
    ):
        raise ValueError("experiment_skill_library.sha256 must be a SHA-256 digest")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()


@dataclass(frozen=True)
class SkillFile:
    path: str
    content: bytes
    executable: bool

    def manifest(self) -> dict:
        return {"path": self.path, "bytes": len(self.content),
                "sha256": hashlib.sha256(self.content).hexdigest(),
                "executable": self.executable}


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    files: tuple[SkillFile, ...]

    def manifest(self) -> dict:
        return {"name": self.name, "description": self.description,
                "entrypoint": f"{CONTAINER_ROOT}/{self.name}/SKILL.md",
                "files": [file.manifest() for file in self.files]}


@dataclass(frozen=True)
class SkillBundle:
    """Immutable bytes shared by workers, copied into each execution's evidence."""

    skills: tuple[Skill, ...]

    def manifest(self) -> dict:
        return {"delivery": DELIVERY_MODE, "skills": [s.manifest() for s in self.skills]}

    @property
    def sha256(self) -> str:
        return _digest(self.manifest())

    def catalog(self) -> str:
        rows = ["\n\n## Additional experimental skills",
                "The following optional skills are available as read-only files. "
                "Read a skill's SKILL.md with your file or shell tools when relevant; "
                "load its supporting files only as needed. Paths inside a skill "
                "are relative to its directory. You may copy files to writable "
                "workspace locations if needed. Using a skill is optional.", ""]
        for skill in self.skills:
            rows.append(f"- {skill.name}: {skill.description} "
                        f"(SKILL.md: {CONTAINER_ROOT}/{skill.name}/SKILL.md)")
        return "\n".join(rows) + "\n"

    def materialize(self, destination: Path) -> None:
        """Create a selected-only snapshot or verify an existing one; never overwrite."""
        if any(p.is_symlink() for p in (destination, *destination.parents)):
            raise ValueError(f"skill snapshot cannot be a symlink: {destination}")
        if destination.exists():
            names = {s.name for s in self.skills}
            if {p.name for p in destination.iterdir()} != names:
                raise ValueError(f"skill snapshot has unexpected entries: {destination}")
            existing = load_bundle(destination, sorted(names))
            if existing != self:
                raise ValueError(f"skill snapshot content mismatch: {destination}")
            return
        destination.mkdir(parents=True, exist_ok=False)
        destination.chmod(0o755)
        for skill in self.skills:
            for file in skill.files:
                path = destination / skill.name / file.path
                directory = destination
                for component in path.relative_to(destination).parts[:-1]:
                    directory = directory / component
                    directory.mkdir(exist_ok=True)
                    directory.chmod(0o755)
                with path.open("xb") as stream:
                    stream.write(file.content)
                path.chmod(0o755 if file.executable else 0o644)


def _frontmatter(content: bytes, name: str) -> str:
    # Lazy import: the empty/default condition does not load a YAML parser.
    import yaml

    try:
        lines = content.decode("utf-8").splitlines()
        if not lines or lines[0] != "---":
            raise ValueError("missing YAML frontmatter")
        end = lines.index("---", 1)
        node = yaml.compose("\n".join(lines[1:end]), Loader=yaml.SafeLoader)
        if not isinstance(node, yaml.MappingNode):
            raise ValueError("frontmatter must be a mapping")
        keys = [key.value for key, _ in node.value]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate frontmatter keys")
        meta = yaml.safe_load("\n".join(lines[1:end]))
        if meta.get("name") != name:
            raise ValueError("frontmatter name must match the directory name")
        description = meta.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("frontmatter requires a nonempty description")
        if not "\n".join(lines[end + 1:]).strip():
            raise ValueError("SKILL.md requires an instruction body")
        return " ".join(description.split())
    except (UnicodeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(f"Invalid {name}/SKILL.md: {exc}") from exc


def load_bundle(root: Path, selection: list[str]) -> SkillBundle:
    names = validate_selection(selection)
    # A disabled condition never scans or opens the library.
    if not names:
        return SkillBundle(())
    root = root.absolute()
    if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
        raise ValueError(f"skill library must be a real directory without symlinks: {root}")
    skills = []
    for name in names:
        directory = root / name
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"Unknown skill or symlink directory: {name}")
        files = []

        def visit(parent: Path) -> None:
            for path in sorted(parent.iterdir()):
                mode = path.lstat().st_mode
                if stat.S_ISDIR(mode):
                    visit(path)
                elif stat.S_ISREG(mode):
                    # No reference/data/script file is implicitly omitted.
                    files.append(SkillFile(path.relative_to(directory).as_posix(),
                                           path.read_bytes(), bool(mode & 0o111)))
                else:
                    raise ValueError(f"Skill contains a symlink or special file: {path}")

        visit(directory)
        files.sort(key=lambda file: file.path)
        entrypoint = next((f for f in files if f.path == "SKILL.md"), None)
        if entrypoint is None:
            raise ValueError(f"Skill {name} is missing SKILL.md")
        skills.append(Skill(name, _frontmatter(entrypoint.content, name), tuple(files)))
    return SkillBundle(tuple(skills))


def bundle_for_profile(raw: dict, profile_path: Path) -> SkillBundle:
    selection = raw["condition_profile"]["overrides"].get("experiment_skills", [])
    if not selection:
        return SkillBundle(())
    source = raw.get("experiment_skill_library")
    root = LIBRARY_ROOT
    if source is not None:
        validate_source(source)
        root = Path(source["path"])
        if not root.is_absolute():
            root = profile_path.parent / root
    bundle = load_bundle(root, selection)
    if source and source.get("sha256", bundle.sha256) != bundle.sha256:
        raise ValueError("Selected experimental skills differ from the pinned SHA-256")
    return bundle
