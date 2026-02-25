from python.helpers.extension import Extension


class VedaIdentity(Extension):
    """
    Fired once at agent initialisation.
    Renames the agent to 'Veda' so all logs, UI headers,
    and tool output reflect the correct identity.
    """

    async def execute(self, **kwargs) -> None:
        self.agent.agent_name = "Veda"
