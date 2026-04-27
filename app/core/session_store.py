import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
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


class SQLiteSessionStore(AbstractSessionStore):
    """
    Persists sessions and conversation history in a SQLite database
    (or any SQLAlchemy-supported database via DATABASE_URL in .env).

    Schema:
      sessions  — one row per session (session_id, created_at, updated_at)
      messages  — one row per message (session_id, role, content, created_at)
    """

    def __init__(self):
        from app.core.database import create_tables, SessionLocal, SessionModel, MessageModel, PhoneSessionModel
        create_tables()
        self._SessionLocal = SessionLocal
        self._SessionModel = SessionModel
        self._MessageModel = MessageModel
        self._PhoneSessionModel = PhoneSessionModel

    # ── Interface ─────────────────────────────────────────────────────────────

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        with self._SessionLocal() as db:
            db.add(self._SessionModel(session_id=session_id))
            db.commit()
        return session_id

    def get_history(self, session_id: str):
        with self._SessionLocal() as db:
            session = db.get(self._SessionModel, session_id)
            if session is None:
                return None

            rows = (
                db.query(self._MessageModel)
                .filter_by(session_id=session_id)
                .order_by(self._MessageModel.id)
                .all()
            )

        history = ConversationHistory()
        for row in rows:
            if row.role == "user":
                history.add_user(row.content)
            elif row.role == "assistant":
                history.add_assistant(row.content)
        return history

    def save_history(self, session_id: str, history: ConversationHistory) -> None:
        with self._SessionLocal() as db:
            # Delete existing messages and rewrite — simple and correct
            db.query(self._MessageModel).filter_by(session_id=session_id).delete()
            for msg in history.get_messages():
                db.add(self._MessageModel(
                    session_id=session_id,
                    role=msg["role"],
                    content=msg["content"] if isinstance(msg["content"], str)
                            else str(msg["content"]),
                ))
            # Touch updated_at
            session = db.get(self._SessionModel, session_id)
            if session:
                session.updated_at = datetime.now(timezone.utc)
            db.commit()

    def session_exists(self, session_id: str) -> bool:
        with self._SessionLocal() as db:
            return db.get(self._SessionModel, session_id) is not None

    def get_or_create_by_phone(self, phone: str) -> str:
        """
        Returns the session_id for a WhatsApp phone number.
        Creates a new session if this phone number hasn't been seen before.
        """
        with self._SessionLocal() as db:
            mapping = db.get(self._PhoneSessionModel, phone)
            if mapping:
                return mapping.session_id

            session_id = str(uuid.uuid4())
            db.add(self._SessionModel(session_id=session_id))
            db.add(self._PhoneSessionModel(phone=phone, session_id=session_id))
            db.commit()
            return session_id


# ── Singleton ─────────────────────────────────────────────────────────────────
# SQLiteSessionStore persists across server restarts.
# To use PostgreSQL: set DATABASE_URL=postgresql://... in .env
session_store = SQLiteSessionStore()
