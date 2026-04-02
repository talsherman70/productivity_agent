"""
Tests for app/core/conversation.py — ConversationHistory class.
"""
from app.core.conversation import ConversationHistory


class TestConversationHistory:
    def test_starts_empty(self):
        h = ConversationHistory()
        assert h.is_empty() is True
        assert h.get_messages() == []

    def test_add_user_message(self):
        h = ConversationHistory()
        h.add_user("Hello")
        messages = h.get_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"

    def test_add_assistant_message(self):
        h = ConversationHistory()
        h.add_assistant("Hi there")
        messages = h.get_messages()
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "Hi there"

    def test_messages_stored_in_order(self):
        h = ConversationHistory()
        h.add_user("First")
        h.add_assistant("Second")
        h.add_user("Third")
        messages = h.get_messages()
        assert messages[0]["content"] == "First"
        assert messages[1]["content"] == "Second"
        assert messages[2]["content"] == "Third"

    def test_is_empty_false_after_adding_message(self):
        h = ConversationHistory()
        h.add_user("Hello")
        assert h.is_empty() is False

    def test_get_messages_returns_copy(self):
        h = ConversationHistory()
        h.add_user("Hello")
        copy = h.get_messages()
        copy.append({"role": "user", "content": "injected"})
        # Original should not be affected
        assert len(h.get_messages()) == 1

    def test_last_user_message_returns_most_recent(self):
        h = ConversationHistory()
        h.add_user("First message")
        h.add_assistant("Response")
        h.add_user("Second message")
        assert h.last_user_message() == "Second message"

    def test_last_user_message_empty_history_returns_empty_string(self):
        h = ConversationHistory()
        assert h.last_user_message() == ""

    def test_last_user_message_only_assistant_messages(self):
        h = ConversationHistory()
        h.add_assistant("I said something")
        assert h.last_user_message() == ""

    def test_many_messages_stored_correctly(self):
        h = ConversationHistory()
        for i in range(10):
            h.add_user(f"User message {i}")
            h.add_assistant(f"Assistant message {i}")
        assert len(h.get_messages()) == 20
