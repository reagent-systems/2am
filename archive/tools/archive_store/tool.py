from claude_agent_sdk import tool


def make_tool(archive, bus, parent_id: str):

    @tool(
        "archive_store",
        "Store a discovery, skill, workflow, or knowledge in the shared archive for other agents to find.",
        {"content": str, "type": str, "name": str},
    )
    async def archive_store(args):
        type_ = args.get("type", "knowledge")
        name = args.get("name", "")
        if type_ == "skill":
            id_ = archive.add_skill(name, args["content"])
        elif type_ == "tool":
            id_ = archive.add_tool(name, args["content"])
        elif type_ == "workflow":
            id_ = archive.add_workflow(name, args["content"])
        else:
            id_ = archive.add_knowledge(args["content"], source=name)
        return {"content": [{"type": "text", "text": f"Stored as {type_} with id={id_}"}]}

    return archive_store
