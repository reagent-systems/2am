from claude_agent_sdk import tool


async def execute(args: dict, archive, bus, parent_id: str) -> str:
    """Direct callable for the workflow executor."""
    results = archive.search(args["query"], k=args.get("k", 5), type_=args.get("type"))
    return archive.format_context(results) or "No results found."


def make_tool(archive, bus, parent_id: str):

    @tool(
        "archive_search",
        "Search the archive for relevant skills, tools, workflows, or knowledge.",
        {"query": str, "type": str, "k": int},
    )
    async def archive_search(args):
        text = await execute(args, archive, bus, parent_id)
        return {"content": [{"type": "text", "text": text}]}

    return archive_search
