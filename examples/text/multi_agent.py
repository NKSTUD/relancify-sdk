from __future__ import annotations

import argparse

from examples.common import (
    ExampleSettings,
    create_client,
    run_example,
    select_text_model,
)
from relancify_sdk import Agent, RunConfig


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test a native multi-agent handoff through Relancify."
    )
    parser.add_argument(
        "message",
        nargs="?",
        default="Ma facture contient un montant incorrect, peux-tu la corriger ?",
        help="Message sent to the triage agent.",
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    settings = ExampleSettings.from_environment()

    with create_client(settings) as client:
        model = select_text_model(client, require_tool_calling=True)
        print(f"Modèle multi-agent sélectionné: {model}")

        billing_agent = Agent(
            name="Billing specialist",
            instructions=(
                "Tu traites uniquement les questions de facturation. "
                "Explique la résolution clairement en français."
            ),
            model=model,
        )
        technical_agent = Agent(
            name="Technical support specialist",
            instructions=(
                "Tu traites uniquement les problèmes techniques. "
                "Propose des étapes de diagnostic courtes en français."
            ),
            model=model,
        )
        triage_agent = Agent(
            name="Customer request triage",
            instructions=(
                "Tu es un routeur. Transfère toujours la demande au spécialiste "
                "Facturation ou Support technique le plus pertinent. "
                "Ne réponds jamais toi-même à la demande."
            ),
            model=model,
            handoffs=[billing_agent, technical_agent],
        )

        result = client.run(
            triage_agent,
            input=arguments.message,
            max_turns=5,
            run_config=RunConfig(tracing_disabled=True),
        )

        print(f"Agent final: {result.last_agent.name}")
        print(f"Réponse: {result.final_output}")


if __name__ == "__main__":
    run_example(main)
