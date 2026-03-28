import uuid
from abc import ABC, abstractmethod
from app.core.conversation import ConversationHistory


class AbstractSessionStore(ABC):
    """
    Defines the interface that any session store must implement.

    Why this exists: right now sessions are stored in memory (lost on restart).
    Later, when you add PostgreSQL, you create a PostgresSessionStore that
    inherits from this class and implements the same four methods.
    Nothing else in the project needs to change — the orchestrator only
    ever talks to this interface, not to a specific implementation.
    """

    @abstractmethod
    def create_session(self) -> str:
        """Creates a new empty session and returns its unique ID."""
        ...

    @abstractmethod
    def get_history(self, session_id: str):
        """Returns the ConversationHistory for this session, or None if not found."""
        ...

    @abstractmethod
    def save_history(self, session_id: str, history: ConversationHistory) -> None:
        """Saves (overwrites) the conversation history for this session."""
        ...

    @abstractmethod
    def session_exists(self, session_id: str) -> bool:
        """Returns True if a session with this ID exists."""
        ...


class InMemorySessionStore(AbstractSessionStore):
    """
    Stores all sessions in a plain Python dictionary.
    Fast, simple, zero dependencies.
    All data is lost when the server restarts — that's expected for now.
    """

    def __init__(self):
        # Keys: session_id (str)
        # Values: ConversationHistory
        self._store: dict = {}

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        self._store[session_id] = ConversationHistory()
        return session_id

    def get_history(self, session_id: str):
        return self._store.get(session_id)

    def save_history(self, session_id: str, history: ConversationHistory) -> None:
        self._store[session_id] = history

    def session_exists(self, session_id: str) -> bool:
        return session_id in self._store


# This is the single shared store used across the whole app.
# Every request reads and writes to this same object.
# To switch to PostgreSQL later: replace InMemorySessionStore()
# with PostgresSessionStore() — one line change.
session_store = InMemorySessionStore()
