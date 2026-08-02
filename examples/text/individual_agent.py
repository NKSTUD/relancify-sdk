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

            agent = client.agents.create(
                name="SDK example - Text individual",
                interaction_mode="chat",
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

            first_turn = client.run(agent_id, "Présente-toi en une phrase.")
            print(f"run: {first_turn.output}")

            conversation_id = first_turn.conversation_id
            if conversation_id:
                second_turn = client.run(
                    agent_id,
                    "Résume ta réponse précédente en cinq mots.",
                    conversation_id=str(conversation_id),
                )
                print(f"Conversation poursuivie: {second_turn.output}")

            print("stream: ", end="", flush=True)
            stream = client.stream(agent_id, "Compte de un à cinq, en toutes lettres.")
            for event in stream:
                if event.type == "output.delta":
                    print(event.delta or "", end="", flush=True)
            print()
            if stream.result:
                billing = stream.result.billing or {}
                print(
                    "Streaming terminé "
                    f"(crédits débités={billing.get('credits_debited', 'n/a')})."
                )

            local_result = client.run(
                agent_id,
                "Donne uniquement le mot OK.",
                execution="local",
                run_config=RunConfig(tracing_disabled=True),
            )
            print(f"Relancify local: {local_result.output}")
        finally:
            cleanup_agents(
                client,
                created_agent_ids,
                keep_resources=settings.keep_resources,
            )


if __name__ == "__main__":
    run_example(main)
