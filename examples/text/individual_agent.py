from __future__ import annotations

from examples.common import (
    ExampleSettings,
    cleanup_agents,
    create_client,
    run_example,
    select_text_model,
)
from relancify_sdk import RunConfig


def main() -> None:
    settings = ExampleSettings.from_environment()
    created_agent_ids: list[str] = []

    with create_client(settings) as client:
        try:
            model = select_text_model(client)
            print(f"Modèle texte sélectionné: {model}")

            agent = client.agents.create_text(
                name="SDK example - Text individual",
                instructions=(
                    "Tu es un assistant de test Relancify. Réponds en français, "
                    "de manière concise, et indique clairement lorsque tu ne sais pas."
                ),
                model=model,
                status="active",
                rag_enabled=False,
                temperature=0.2,
                session={"language": "fr"},
            )
            agent_id = str(agent["id"])
            created_agent_ids.append(agent_id)
            print(f"Agent texte créé: {agent_id}")

            first_turn = client.agents.run_text(
                agent_id,
                input="Présente-toi en une phrase.",
            )
            print(f"run_text: {first_turn.get('output')}")

            conversation_id = first_turn.get("conversation_id")
            if conversation_id:
                second_turn = client.agents.run_text(
                    agent_id,
                    input="Résume ta réponse précédente en cinq mots.",
                    conversation_id=str(conversation_id),
                )
                print(f"Conversation poursuivie: {second_turn.get('output')}")

            print("stream_text: ", end="", flush=True)
            completed_event = None
            for event in client.agents.stream_text(
                agent_id,
                input="Compte de un à cinq, en toutes lettres.",
            ):
                if event["event"] == "output.delta":
                    print(event["data"].get("delta", ""), end="", flush=True)
                elif event["event"] == "run.completed":
                    completed_event = event["data"]
            print()
            if completed_event:
                billing = completed_event.get("billing", {})
                print(
                    "Streaming terminé "
                    f"(crédits débités={billing.get('credits_debited', 'n/a')})."
                )

            native_result = client.invoke(
                agent_id,
                input="Donne uniquement le mot OK.",
                run_config=RunConfig(tracing_disabled=True),
            )
            print(f"Relancify invoke: {native_result.final_output}")
        finally:
            cleanup_agents(
                client,
                created_agent_ids,
                keep_resources=settings.keep_resources,
            )


if __name__ == "__main__":
    run_example(main)
