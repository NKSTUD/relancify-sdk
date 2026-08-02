import asyncio

import pytest
from agents import Agent

from relancify_sdk import Skill, function_tool, load_skill, with_skills
from relancify_sdk.agent_runtime import build_registered_agent


class DummyHttpClient:
    pass


def test_load_skill_reads_frontmatter_from_directory(tmp_path) -> None:
    skill_directory = tmp_path / "billing"
    skill_directory.mkdir()
    (skill_directory / "SKILL.md").write_text(
        "---\nname: Billing expert\ndescription: Handles invoices\n---\n"
        "Verify every invoice before answering.\n",
        encoding="utf-8",
    )

    skill = load_skill(skill_directory)

    assert skill.name == "Billing expert"
    assert skill.description == "Handles invoices"
    assert skill.instructions == "Verify every invoice before answering."


def test_with_skills_compiles_instructions_and_local_tools() -> None:
    @function_tool
    def lookup_invoice(invoice_id: str) -> str:
        """Look up an invoice."""
        return invoice_id

    original = Agent(name="Support", instructions="Answer clearly.")
    compiled = with_skills(
        original,
        [
            Skill(
                name="Billing",
                description="Handles invoices.",
                instructions="Verify the invoice first.",
                tools=(lookup_invoice,),
            )
        ],
    )

    assert original.tools == []
    assert "### Skill: Billing" in compiled.instructions
    assert "Verify the invoice first." in compiled.instructions
    assert [tool.name for tool in compiled.tools] == ["lookup_invoice"]


def test_with_skills_supports_dynamic_agent_instructions() -> None:
    async def dynamic_instructions(_context, _agent):
        return "Dynamic base."

    compiled = with_skills(
        Agent(name="Support", instructions=dynamic_instructions),
        [Skill(name="Billing", instructions="Check invoices.")],
    )

    instructions = asyncio.run(compiled.instructions(None, compiled))

    assert instructions.startswith("Dynamic base.")
    assert "Check invoices." in instructions


def test_duplicate_skill_names_fail_early() -> None:
    with pytest.raises(ValueError, match="Duplicate skill name"):
        with_skills(
            Agent(name="Support"),
            [
                Skill(name="Billing", instructions="One"),
                Skill(name="billing", instructions="Two"),
            ],
        )


def test_registered_agent_compiles_persisted_skills() -> None:
    agent = build_registered_agent(
        config={
            "name": "Support",
            "modality": "text",
            "prompt": {"system": "Base instructions."},
            "llm": {"model": "support-fast"},
            "skills": [
                {
                    "name": "Billing",
                    "instructions": "Check the invoice.",
                    "enabled": True,
                }
            ],
        },
        client=DummyHttpClient(),
        agent_id="ag_12345678-1234-1234-1234-123456789abc",
    )

    assert "Base instructions." in agent.instructions
    assert "### Skill: Billing" in agent.instructions
