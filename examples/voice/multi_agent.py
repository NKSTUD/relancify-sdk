from __future__ import annotations

import argparse
from typing import Literal

from pydantic import BaseModel

from examples.common import (
    ExampleSettings,
    RuntimeProbe,
    build_voice_agent_payload,
    cleanup_agents,
    close_runtime_probe,
    create_client,
    open_runtime_probe,
    prepare_voice_agent,
    run_example,
    select_text_model,
)
from relancify_sdk import Agent, RunConfig


class VoiceRoute(BaseModel):
    destination: Literal["sales", "support"]
    reason: str


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Route an initial request to one of two voice agents, then create "
            "the selected agent's runtime session."
        )
    )
    parser.add_argument(
        "message",
        nargs="?",
        default="Mon abonnement ne fonctionne plus depuis ce matin.",
        help="Initial message used by the routing agent.",
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    settings = ExampleSettings.from_environment()
    created_agent_ids: list[str] = []
    runtime_probe: RuntimeProbe | None = None

    with create_client(settings) as client:
        try:
            sales_agent = client.agents.create(
                build_voice_agent_payload(
                    client,
                    name="SDK example - Voice sales",
                    instructions=(
                        "Tu es le spécialiste commercial. Tu présentes les offres, "
                        "les prix et les possibilités d'abonnement en français."
                    ),
                    first_message="Bonjour, vous êtes avec le service commercial.",
                )
            )
            sales_agent_id = str(sales_agent["id"])
            created_agent_ids.append(sales_agent_id)
            prepare_voice_agent(client, sales_agent)
            print(f"Agent vocal commercial prêt: {sales_agent_id}")

            support_agent = client.agents.create(
                build_voice_agent_payload(
                    client,
                    name="SDK example - Voice support",
                    instructions=(
                        "Tu es le spécialiste support. Tu diagnostiques les incidents "
                        "et les problèmes de compte en français."
                    ),
                    first_message="Bonjour, vous êtes avec le support technique.",
                )
            )
            support_agent_id = str(support_agent["id"])
            created_agent_ids.append(support_agent_id)
            prepare_voice_agent(client, support_agent)
            print(f"Agent vocal support prêt: {support_agent_id}")

            routing_model = select_text_model(
                client,
                require_structured_output=True,
            )
            router = Agent(
                name="Voice entry router",
                instructions=(
                    "Classe la demande initiale. Choisis sales pour une demande "
                    "commerciale, de prix ou d'abonnement. Choisis support pour "
                    "un incident, un dysfonctionnement ou un problème de compte."
                ),
                model=routing_model,
                output_type=VoiceRoute,
            )
            routing_result = client.invoke(
                router,
                input=arguments.message,
                run_config=RunConfig(tracing_disabled=True),
            )
            route = routing_result.final_output
            if not isinstance(route, VoiceRoute):
                raise RuntimeError("The routing agent returned an invalid result.")

            selected_agent_id = (
                sales_agent_id
                if route.destination == "sales"
                else support_agent_id
            )
            print(
                f"Route choisie: {route.destination} "
                f"(raison={route.reason}, agent={selected_agent_id})"
            )
            runtime_probe = open_runtime_probe(client, selected_agent_id)
            print(
                "Le routeur choisit l'agent avant l'ouverture du canal audio. "
                "Un transfert pendant l'appel nécessite un outil de handoff "
                "runtime configuré côté agent."
            )
        finally:
            close_runtime_probe(client, runtime_probe)
            cleanup_agents(
                client,
                created_agent_ids,
                keep_resources=settings.keep_resources,
            )


if __name__ == "__main__":
    run_example(main)
