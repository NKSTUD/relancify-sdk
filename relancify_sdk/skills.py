from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from agents import Agent

from relancify_sdk.local_agents import normalize_local_tools

MAX_SKILL_FILE_BYTES = 200_000
SKILLS_SECTION_TITLE = "Relancify skills"


@dataclass(frozen=True)
class Skill:
    """Reusable instructions with optional local code-first tools."""

    name: str
    instructions: str
    description: str | None = None
    tools: tuple[Any, ...] = field(default_factory=tuple)
    enabled: bool = True

    def __post_init__(self) -> None:
        name = _required_text(self.name, "skill name")
        instructions = _required_text(self.instructions, "skill instructions")
        description = _optional_text(self.description)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "instructions", instructions)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "tools", tuple(self.tools or ()))


def load_skill(
    path: str | Path,
    *,
    tools: Sequence[Any] = (),
) -> Skill:
    """Load a Markdown skill from a file or a directory containing SKILL.md."""
    skill_path = Path(path).expanduser()
    if skill_path.is_dir():
        skill_path = skill_path / "SKILL.md"
    if not skill_path.is_file():
        raise FileNotFoundError(f"Skill file not found: {skill_path}")

    file_size = skill_path.stat().st_size
    if file_size > MAX_SKILL_FILE_BYTES:
        raise ValueError(f"Skill file exceeds the {MAX_SKILL_FILE_BYTES}-byte limit")
    try:
        content = skill_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Skill files must use UTF-8 encoding") from exc

    metadata, instructions = _parse_frontmatter(content)
    name = metadata.get("name") or skill_path.parent.name or skill_path.stem
    description = metadata.get("description")
    return Skill(
        name=name,
        description=description,
        instructions=instructions,
        tools=tuple(tools),
    )


def with_skills(agent: Agent, skills: Sequence[Skill | Mapping[str, Any]]) -> Agent:
    """Return a copy of an Agents SDK agent with skills compiled locally."""
    normalized_skills = normalize_skills(skills)
    enabled_skills = [skill for skill in normalized_skills if skill.enabled]
    if not enabled_skills:
        return agent

    skill_instructions = _compile_skill_sections(enabled_skills)
    instructions = _merge_agent_instructions(agent.instructions, skill_instructions)
    skill_tools = [tool for skill in enabled_skills for tool in skill.tools]
    tools = normalize_local_tools([*agent.tools, *skill_tools])
    _ensure_unique_tool_names(tools)
    return replace(agent, instructions=instructions, tools=tools)


def normalize_skills(
    skills: Sequence[Skill | Mapping[str, Any]] | None,
) -> list[Skill]:
    normalized: list[Skill] = []
    names_in_use: set[str] = set()
    for raw_skill in skills or ():
        skill = (
            raw_skill
            if isinstance(raw_skill, Skill)
            else _skill_from_mapping(raw_skill)
        )
        normalized_name = skill.name.casefold()
        if normalized_name in names_in_use:
            raise ValueError(f"Duplicate skill name: {skill.name}")
        names_in_use.add(normalized_name)
        normalized.append(skill)
    return normalized


def serialize_skills(
    skills: Sequence[Skill | Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Serialize declarative skill data for a managed Relancify agent."""
    payload: list[dict[str, Any]] = []
    for skill in normalize_skills(skills):
        if skill.tools:
            raise ValueError(
                f"Skill '{skill.name}' has local tools. Apply it with with_skills() "
                "for code-first execution, or register the tools separately."
            )
        item: dict[str, Any] = {
            "name": skill.name,
            "instructions": skill.instructions,
            "enabled": skill.enabled,
        }
        if skill.description is not None:
            item["description"] = skill.description
        payload.append(item)
    return payload


def compose_persisted_skill_instructions(
    base_instructions: str,
    raw_skills: Any,
) -> str:
    if not isinstance(raw_skills, list):
        return str(base_instructions or "").strip()
    skills = normalize_skills(
        [skill for skill in raw_skills if isinstance(skill, Mapping)]
    )
    enabled_skills = [skill for skill in skills if skill.enabled]
    if not enabled_skills:
        return str(base_instructions or "").strip()
    skill_instructions = _compile_skill_sections(enabled_skills)
    base = str(base_instructions or "").strip()
    return f"{base}\n\n{skill_instructions}" if base else skill_instructions


def _skill_from_mapping(raw_skill: Mapping[str, Any]) -> Skill:
    if not isinstance(raw_skill, Mapping):
        raise TypeError("skills must contain Skill objects or mappings")
    raw_tools = raw_skill.get("tools") or ()
    if not isinstance(raw_tools, (list, tuple)):
        raise TypeError("skill tools must be a list or tuple")
    return Skill(
        name=str(raw_skill.get("name") or ""),
        description=raw_skill.get("description"),
        instructions=str(raw_skill.get("instructions") or ""),
        tools=tuple(raw_tools),
        enabled=bool(raw_skill.get("enabled", True)),
    )


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    normalized = content.lstrip("\ufeff")
    lines = normalized.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, normalized.strip()

    closing_index = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        ),
        None,
    )
    if closing_index is None:
        raise ValueError("Skill frontmatter is missing its closing '---'")

    metadata: dict[str, str] = {}
    for line in lines[1:closing_index]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition(":")
        if not separator:
            raise ValueError("Skill frontmatter entries must use 'key: value'")
        normalized_key = key.strip().lower()
        if normalized_key not in {"name", "description"}:
            continue
        metadata[normalized_key] = value.strip().strip("\"'")
    return metadata, "\n".join(lines[closing_index + 1 :]).strip()


def _compile_skill_sections(skills: Sequence[Skill]) -> str:
    sections: list[str] = []
    for skill in skills:
        section = f"### Skill: {skill.name}\n\n"
        if skill.description:
            section += f"{skill.description}\n\n"
        section += skill.instructions
        sections.append(section)
    return f"## {SKILLS_SECTION_TITLE}\n\n" + "\n\n".join(sections)


def _merge_agent_instructions(original: Any, skill_instructions: str) -> Any:
    if callable(original):

        async def dynamic_instructions(context: Any, current_agent: Agent) -> str:
            base = original(context, current_agent)
            if inspect.isawaitable(base):
                base = await base
            normalized_base = str(base or "").strip()
            if not normalized_base:
                return skill_instructions
            return f"{normalized_base}\n\n{skill_instructions}"

        return dynamic_instructions

    normalized_base = str(original or "").strip()
    if not normalized_base:
        return skill_instructions
    return f"{normalized_base}\n\n{skill_instructions}"


def _ensure_unique_tool_names(tools: Sequence[Any]) -> None:
    names_in_use: set[str] = set()
    for tool in tools:
        name = str(getattr(tool, "name", "") or "").strip()
        if not name:
            continue
        if name in names_in_use:
            raise ValueError(f"Duplicate tool name after applying skills: {name}")
        names_in_use.add(name)


def _required_text(value: Any, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
