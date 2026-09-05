"""
Configuració de bases de dades SQLite amb SQLAlchemy
- auth.db global per usuaris
- gestor.db per institució
"""
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Dict
import os
import re

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from models import Base, User, UserPermissionAudit

BASE_DIR = Path(__file__).resolve().parent
# DATA_DIR apunta a la carpeta data/ a l'arrel del projecte (dos nivells amunt)
# Això permet multi-institució: data/centre1, data/centre2, etc.
PROJECT_DATA_ROOT = BASE_DIR.parent / "data"
DATA_BASE_DIR = Path(os.getenv("DATA_DIR", PROJECT_DATA_ROOT))


def _create_engine(db_path: Path):
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
        echo=False
    )


def get_auth_db_path() -> Path:
    # auth.db està a l'arrel de data/ (global per totes les institucions)
    return Path(os.getenv("AUTH_DB_PATH", DATA_BASE_DIR / "auth.db"))


AUTH_ENGINE = _create_engine(get_auth_db_path())
AuthSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=AUTH_ENGINE)


def create_auth_tables():
    """Crea només taules d'autenticació"""
    Base.metadata.create_all(
        bind=AUTH_ENGINE,
        tables=[User.__table__, UserPermissionAudit.__table__],
    )
    _ensure_user_permissions_column(AUTH_ENGINE)


def _ensure_user_permissions_column(engine):
    """Add nullable permissions JSON without changing legacy user behaviour."""
    with engine.begin() as conn:
        columns = conn.exec_driver_sql("PRAGMA table_info(users);").fetchall()
        if columns and "permissions" not in {column[1] for column in columns}:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN permissions TEXT")


def get_data_dir_for_institucio(institucio: str) -> Path:
    if not institucio:
        raise ValueError("Institucio buida")
    if not re.fullmatch(r"[a-z0-9_.-]+", institucio):
        raise ValueError("Institucio invalida")
    return DATA_BASE_DIR / institucio


def get_export_dir_for_institucio(institucio: str) -> Path:
    data_dir = get_data_dir_for_institucio(institucio)
    export_dir = None
    try:
        from repositories import ConfiguracioRepository
        with get_data_db_session(institucio) as db:
            export_dir = ConfiguracioRepository.get(db, "export_dir")
    except Exception:
        export_dir = None

    if export_dir:
        export_path = Path(export_dir)
        if not export_path.is_absolute():
            export_path = data_dir / export_path
    else:
        export_path = data_dir / "exports"

    export_path.mkdir(parents=True, exist_ok=True)
    return export_path


def _data_tables():
    auth_tables = {"users", "user_permission_audits"}
    return [table for name, table in Base.metadata.tables.items() if name not in auth_tables]


def create_data_tables(engine):
    """Crea taules de dades (exclou users)"""
    Base.metadata.create_all(bind=engine, tables=_data_tables())


def _ensure_substitucions_aula_column(engine):
    """Assegura que la taula substitucions té la columna aula (migració simple)."""
    try:
        with engine.connect() as conn:
            columns = conn.exec_driver_sql("PRAGMA table_info(substitucions);").fetchall()
            column_names = {col[1] for col in columns}
            if "aula" not in column_names:
                conn.exec_driver_sql("ALTER TABLE substitucions ADD COLUMN aula VARCHAR")
    except Exception:
        # Si la taula no existeix encara o ja està migrada, no cal fer res
        pass


def _ensure_timetable_version_columns(engine):
    """Add timetable metadata introduced after the first rescheduling release."""
    try:
        with engine.begin() as conn:
            columns = conn.exec_driver_sql("PRAGMA table_info(timetable_versions);").fetchall()
            names = {column[1] for column in columns}
            if columns and "effective_to" not in names:
                conn.exec_driver_sql("ALTER TABLE timetable_versions ADD COLUMN effective_to DATE")
            if columns and "resolutions_json" not in names:
                conn.exec_driver_sql("ALTER TABLE timetable_versions ADD COLUMN resolutions_json TEXT")
            if columns and "effective_ranges_json" not in names:
                conn.exec_driver_sql("ALTER TABLE timetable_versions ADD COLUMN effective_ranges_json TEXT")
    except Exception:
        pass


def _ensure_timetable_lesson_columns(engine):
    """Add lesson flags introduced after the first rescheduling release."""
    try:
        with engine.begin() as conn:
            columns = conn.exec_driver_sql("PRAGMA table_info(timetable_lessons);").fetchall()
            names = {column[1] for column in columns}
            if columns and "special" not in names:
                conn.exec_driver_sql(
                    "ALTER TABLE timetable_lessons ADD COLUMN special BOOLEAN NOT NULL DEFAULT 0"
                )
    except Exception:
        pass


def _ensure_schedule_adjustment_columns(engine):
    """Add review metadata introduced after confirmed adjustments were released."""
    try:
        with engine.begin() as conn:
            columns = conn.exec_driver_sql("PRAGMA table_info(schedule_adjustments);").fetchall()
            names = {column[1] for column in columns}
            if columns and "needs_review" not in names:
                conn.exec_driver_sql(
                    "ALTER TABLE schedule_adjustments ADD COLUMN needs_review BOOLEAN NOT NULL DEFAULT 0"
                )
    except Exception:
        pass


def _ensure_absence_case_columns(engine):
    """Add optional absence reasons while keeping legacy rows readable."""
    with engine.begin() as conn:
        columns = conn.exec_driver_sql("PRAGMA table_info(absence_cases);").fetchall()
        names = {column[1] for column in columns}
        if columns and "reason_type" not in names:
            conn.exec_driver_sql("ALTER TABLE absence_cases ADD COLUMN reason_type VARCHAR")
        if columns and "reason_detail" not in names:
            conn.exec_driver_sql("ALTER TABLE absence_cases ADD COLUMN reason_detail VARCHAR(200)")


def _ensure_active_absence_unique_index(engine):
    """Keep one active absence case per teacher and school date."""
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_absence_teacher_date "
            "ON absence_cases (professor_id, data) WHERE status != 'cancelled'"
        )


@lru_cache(maxsize=None)
def get_engine_for_institucio(institucio: str):
    data_dir = get_data_dir_for_institucio(institucio)
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "gestor.db"
    engine = _create_engine(db_path)
    create_data_tables(engine)
    _ensure_substitucions_aula_column(engine)
    _ensure_timetable_version_columns(engine)
    _ensure_timetable_lesson_columns(engine)
    _ensure_schedule_adjustment_columns(engine)
    _ensure_absence_case_columns(engine)
    _ensure_active_absence_unique_index(engine)
    return engine


def get_auth_db() -> Session:
    db = AuthSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_data_db(institucio: str):
    engine = get_engine_for_institucio(institucio)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_auth_db_session():
    db = AuthSessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_data_db_session(institucio: str):
    engine = get_engine_for_institucio(institucio)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session():
    """Compatibilitat: sessió de dades segons institució global configurada."""
    from config.settings import config

    instit = config.global_data.get("institucio") or os.getenv("APP_INSTITUCIO") or "exemple"
    with get_data_db_session(instit) as db:
        yield db
