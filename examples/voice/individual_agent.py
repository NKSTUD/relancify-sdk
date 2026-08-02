from __future__ import annotations

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
)


def main() -> None:
    settings = ExampleSettings.from_environment()
    created_agent_ids: list[str] = []
    runtime_probe: RuntimeProbe | None = None

    with create_client(settings) as client:
        try:
            payload = build_voice_agent_payload(
                client,
                name="SDK example - Voice individual",
                instructions=(
                    "Tu es un assistant vocal de test Relancify. "
                    "Réponds en français avec des phrases courtes."
                ),
                first_message="Bonjour, je suis prêt pour le test vocal.",
            )
            agent = client.agents.create(**payload)
            agent_id = str(agent["id"])
            created_agent_ids.append(agent_id)
            print(f"Agent vocal créé: {agent_id} (runtime LiveKit géré)")

            prepare_voice_agent(client, agent)
            runtime_probe = open_runtime_probe(client, agent_id)
            print(
                "Le plan de contrôle vocal est validé jusqu'aux identifiants "
                "de connexion. Utilisez l'option de transport affichée dans "
                "votre client audio."
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
