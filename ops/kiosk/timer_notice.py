"""Presentation state for the TV countdown badge and warning."""


def format_remaining(seconds):
    seconds = max(0, int(seconds))
    if seconds <= 120:
        return f"{seconds // 60}:{seconds % 60:02d}"
    return f"{(seconds + 59) // 60} мин"


class TimerNotice:
    def __init__(self):
        self.state = None
        self.generation = None
        self.dismissed = None
        self.editing = False
        self.expanded = False
        self.hovered = False

    def update(self, state):
        if state is None:
            self.state = None
            return self.view()
        generation = state.get("generation")
        if generation != self.generation:
            self.generation = generation
            self.editing = False
            self.expanded = False
            self.hovered = False
        self.state = state
        return self.view()

    def dismiss(self):
        self.dismissed = self.generation
        self.editing = False
        self.expanded = False
        self.hovered = False
        return self.view()

    def toggle(self):
        self.expanded = not self.view()["expanded"]
        self.hovered = False
        if not self.expanded:
            self.editing = False
        return self.view()

    def hover(self, active):
        self.hovered = bool(active)
        return self.view()

    def edit(self):
        if self.view()["visible"]:
            self.editing = True
            self.expanded = True
        return self.view()

    def view(self):
        state = self.state or {}
        remaining = state.get("remaining_seconds", 0)
        visible = state.get("phase") == "countdown" and type(remaining) is int and remaining > 0
        warning = visible and remaining <= 120 and self.dismissed != self.generation
        return {
            "visible": visible,
            "warning": warning,
            "editing": visible and self.editing,
            "expanded": visible and (warning or self.expanded or self.hovered or self.editing),
            "remaining": format_remaining(remaining) if visible else "",
        }
