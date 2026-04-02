"""
Tests for app/core/session_store.py — InMemorySessionStore.
"""
from app.core.session_store import InMemorySessionStore
from app.core.conversation import ConversationHistory


class TestInMemorySessionStore:
    def setup_method(self):
        """Create a fresh store before each test."""
        self.store = InMemorySessionStore()

    def test_create_session_returns_string(self):
        sid = self.store.create_session()
        assert isinstance(sid, str)
        assert len(sid) > 0

    def test_create_session_returns_unique_ids(self):
        ids = {self.store.create_session() for _ in range(10)}
        assert len(ids) == 10  # all 10 are unique

    def test_session_exists_after_creation(self):
        sid = self.store.create_session()
        assert self.store.session_exists(sid) is True

    def test_session_does_not_exist_for_random_id(self):
        assert self.store.session_exists("made-up-id") is False

    def test_get_history_returns_conversation_history(self):
        sid = self.store.create_session()
        history = self.store.get_history(sid)
        assert isinstance(history, ConversationHistory)

    def test_get_history_returns_none_for_unknown_session(self):
        result = self.store.get_history("does-not-exist")
        assert result is None

    def test_new_session_history_is_empty(self):
        sid = self.store.create_session()
        history = self.store.get_history(sid)
        assert history.is_empty() is True

    def test_save_and_retrieve_history(self):
        sid = self.store.create_session()
        history = ConversationHistory()
        history.add_user("hello")
        self.store.save_history(sid, history)

        retrieved = self.store.get_history(sid)
        assert retrieved.get_messages()[0]["content"] == "hello"

    def test_save_overwrites_previous_history(self):
        sid = self.store.create_session()

        h1 = ConversationHistory()
        h1.add_user("first")
        self.store.save_history(sid, h1)

        h2 = ConversationHistory()
        h2.add_user("second")
        self.store.save_history(sid, h2)

        result = self.store.get_history(sid)
        assert result.get_messages()[0]["content"] == "second"

    def test_multiple_sessions_are_independent(self):
        sid1 = self.store.create_session()
        sid2 = self.store.create_session()

        h1 = self.store.get_history(sid1)
        h1.add_user("session 1 message")
        self.store.save_history(sid1, h1)

        h2 = self.store.get_history(sid2)
        assert h2.is_empty()  # session 2 not affected

    def test_store_starts_empty(self):
        assert self.store.session_exists("anything") is False
