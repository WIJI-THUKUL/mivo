"""Plugin: todo - a visible task list so the agent can plan multi-step work."""
from rich.text import Text

ICON = {"pending": "☐", "in_progress": "◐", "done": "☑"}


def register(api):
    def render(todos):
        if not todos:
            return "(no tasks)"
        return "\n".join(f"{ICON.get(t.get('status'), '☐')} {t.get('content', '')}" for t in todos)

    def todo_write(a):
        api.state["todos"] = a.get("todos", [])
        api.console.print(Text(render(api.state["todos"]), style="cyan"))
        return "Todo list updated:\n" + render(api.state["todos"])

    api.tool(
        "todo_write",
        "Create or update the task list for a multi-step job. Send the FULL list each time. "
        "Status is one of: pending, in_progress, done.",
        {"type": "object",
         "properties": {"todos": {"type": "array", "items": {
             "type": "object",
             "properties": {"content": {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "done"]}},
             "required": ["content", "status"]}}},
         "required": ["todos"]},
        todo_write,
        permission="safe",
    )
    api.command("todo", lambda arg: api.console.print(render(api.state["todos"])), "Show the task list")
