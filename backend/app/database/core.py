from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


class Database:
    def __init__(self, url: str, *, echo: bool = False) -> None:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace(
                "postgresql://", "postgresql+psycopg://", 1
            )
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.url = url
        self.engine: Engine = create_engine(
            url,
            echo=echo,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._enable_sqlite_foreign_keys)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    @staticmethod
    def sqlite_url(path: str | Path) -> str:
        return f"sqlite:///{Path(path).resolve().as_posix()}"

    @staticmethod
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        inspector = inspect(self.engine)
        table_names = set(inspector.get_table_names())
        with self.engine.begin() as connection:
            owner_tables = (
                "study_sessions",
                "documents",
                "chat_sessions",
                "model_runs",
            )
            for table_name in owner_tables:
                if table_name not in table_names:
                    continue
                columns = {
                    column["name"]
                    for column in inspector.get_columns(table_name)
                }
                if "user_id" not in columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE {table_name} "
                            "ADD COLUMN user_id VARCHAR(64)"
                        )
                    )
                connection.execute(
                    text(
                        f"CREATE INDEX IF NOT EXISTS "
                        f"ix_{table_name}_user_id ON {table_name} (user_id)"
                    )
                )
            if "documents" in table_names:
                columns = {column["name"] for column in inspector.get_columns("documents")}
                if "study_session_id" not in columns:
                    connection.execute(
                        text("ALTER TABLE documents ADD COLUMN study_session_id VARCHAR(64)")
                    )
            if "chat_sessions" in table_names:
                columns = {
                    column["name"]
                    for column in inspector.get_columns("chat_sessions")
                }
                if "study_session_id" not in columns:
                    connection.execute(
                        text("ALTER TABLE chat_sessions ADD COLUMN study_session_id VARCHAR(64)")
                    )

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def health(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
