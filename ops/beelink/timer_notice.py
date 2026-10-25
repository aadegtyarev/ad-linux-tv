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

    def update(self, state):
        if state is None:
            self.state = None
            return self.view()
        generation = state.get("generation")
        if generation != self.generation:
            self.generation = generation
            self.editing = False
        self.state = state
        return self.view()

    def dismiss(self):
        self.dismissed = self.generation
        self.editing = False
        return self.view()

    def edit(self):
        if self.view()["warning"]:
            self.editing = True
        return self.view()

    def view(self):
        state = self.state or {}
        remaining = state.get("remaining_seconds", 0)
        visible = state.get("phase") == "countdown" and type(remaining) is int and remaining > 0
        warning = visible and remaining <= 120 and self.dismissed != self.generation
        return {
            "visible": visible,
            "warning": warning,
            "editing": warning and self.editing,
            "remaining": format_remaining(remaining) if visible else "",
        }
