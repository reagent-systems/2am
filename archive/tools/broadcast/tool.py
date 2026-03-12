import asyncio

from claude_agent_sdk import tool


async def execute(args: dict, archive, bus, parent_id: str) -> str:
    """Direct callable for the workflow executor."""
    await bus.broadcast({"agent": parent_id, "message": args["message"]}, sender=parent_id)
    return "broadcast sent"


def make_tool(archive, bus, parent_id: str):

    @tool(
        "broadcast",
        "Publish a status message to the shared bus. All agents see this.",
        {"message": str},
    )
    async def broadcast_tool(args):
        asyncio.create_task(execute(args, archive, bus, parent_id))
        return {"content": [{"type": "text", "text": "broadcast sent"}]}

    return broadcast_tool
