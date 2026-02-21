from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from src.constants import CONFIG_KEY_SALDO_FORMULA, DEFAULT_DB_PATH, DEFAULT_SALDO_FORMULA
from src.models import AppConfig, Base


def create_engine_sqlite(db_path: str | Path = DEFAULT_DB_PATH) -> Engine:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, expire_on_commit=False)


def ensure_default_config(session: Session, updated_by: str = "system") -> None:
    payload = json.dumps(DEFAULT_SALDO_FORMULA, ensure_ascii=True)
    existing = session.get(AppConfig, CONFIG_KEY_SALDO_FORMULA)
    if existing:
        if existing.value_json != payload:
            existing.value_json = payload
            existing.updated_by = updated_by
        return
    session.add(
        AppConfig(
            key=CONFIG_KEY_SALDO_FORMULA,
            value_json=payload,
            updated_by=updated_by,
        )
    )


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    SessionLocal = get_session_factory(engine)
    with SessionLocal() as session:
        with session.begin():
            ensure_default_config(session)


def _seed_admin(session: Session, username: str = "admin", password: str = "Admin@123") -> tuple[bool, str]:
    from src.services_auth import create_user

    try:
        create_user(
            session,
            username=username,
            password=password,
            perfil="ADMIN",
            must_change_password=True,
            is_active=True,
        )
        return True, "Usuário ADMIN criado."
    except ValueError as exc:
        if "já existe" in str(exc):
            return False, "Usuário ADMIN já existe."
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Inicialização do banco SisGesPA")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="Caminho do SQLite")
    parser.add_argument("--init", action="store_true", help="Criar estrutura de tabelas")
    parser.add_argument("--seed-admin", action="store_true", help="Criar usuário admin padrão")
    parser.add_argument("--admin-user", default="admin", help="Username do admin inicial")
    parser.add_argument("--admin-password", default="Admin@123", help="Senha temporária do admin inicial")
    args = parser.parse_args()

    engine = create_engine_sqlite(args.db_path)

    if args.init:
        init_db(engine)
        print("Banco inicializado com sucesso.")

    if args.seed_admin:
        init_db(engine)
        SessionLocal = get_session_factory(engine)
        with SessionLocal() as session:
            with session.begin():
                created, message = _seed_admin(
                    session,
                    username=args.admin_user,
                    password=args.admin_password,
                )
        print(message)
        if created:
            print("Senha temporária criada com troca obrigatória no primeiro login.")

    if not args.init and not args.seed_admin:
        parser.print_help()


if __name__ == "__main__":
    main()
