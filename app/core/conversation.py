class ConversationHistory:
    """
    Stores the full back-and-forth conversation between the user and assistant.

    Each message is a dict with two keys:
      - "role": either "user" or "assistant"
      - "content": the text of the message

    The Anthropic API expects exactly this format, so we can pass
    history.get_messages() directly to the API without any transformation.
    """

    def __init__(self):
        self.messages: list = []

    def add_user(self, content: str) -> None:
        """Appends a user message to the history."""
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        """Appends an assistant message to the history."""
        self.messages.append({"role": "assistant", "content": content})

    def get_messages(self) -> list:
        """Returns a copy of the full message list."""
        return self.messages.copy()

    def is_empty(self) -> bool:
        return len(self.messages) == 0

    def last_user_message(self) -> str:
        """Returns the most recent user message, or empty string if none."""
        for msg in reversed(self.messages):
            if msg["role"] == "user":
                return msg["content"]
        return ""
