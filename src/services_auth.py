from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants import ALL_ROLES
from src.models import AuthLog, User


@dataclass
class AuthResult:
    ok: bool
    message: str
    user: User | None = None


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _log_auth(session: Session, username: str, sucesso: bool, motivo: str) -> None:
    session.add(AuthLog(username=username or "", sucesso=sucesso, motivo=motivo, ip_origem="local"))


def authenticate_user(session: Session, username: str, password: str) -> AuthResult:
    username_norm = (username or "").strip()
    if not username_norm or not password:
        _log_auth(session, username_norm, False, "Credenciais vazias")
        session.commit()
        return AuthResult(False, "Informe usuário e senha.")

    user = session.execute(select(User).where(User.username == username_norm)).scalar_one_or_none()
    if user is None:
        _log_auth(session, username_norm, False, "Usuário não encontrado")
        session.commit()
        return AuthResult(False, "Usuário ou senha inválidos.")

    if not user.is_active:
        _log_auth(session, username_norm, False, "Usuário inativo")
        session.commit()
        return AuthResult(False, "Usuário inativo.")

    if not _verify_password(password, user.password_hash):
        _log_auth(session, username_norm, False, "Senha inválida")
        session.commit()
        return AuthResult(False, "Usuário ou senha inválidos.")

    _log_auth(session, username_norm, True, "Login efetuado")
    session.commit()
    return AuthResult(True, "Login efetuado com sucesso.", user=user)


def create_user(
    session: Session,
    username: str,
    password: str,
    perfil: str,
    must_change_password: bool = True,
    is_active: bool = True,
) -> User:
    username_norm = (username or "").strip()
    perfil_norm = (perfil or "").strip().upper()

    if not username_norm:
        raise ValueError("Username obrigatório.")
    if not password:
        raise ValueError("Senha obrigatória.")
    if perfil_norm not in ALL_ROLES:
        raise ValueError(f"Perfil inválido: {perfil_norm}")

    existing = session.execute(select(User).where(User.username == username_norm)).scalar_one_or_none()
    if existing:
        raise ValueError(f"Usuário {username_norm} já existe.")

    user = User(
        username=username_norm,
        password_hash=_hash_password(password),
        perfil=perfil_norm,
        is_active=is_active,
        must_change_password=must_change_password,
    )
    session.add(user)
    return user


def change_password(
    session: Session,
    username: str,
    old_password: str,
    new_password: str,
    force: bool = False,
) -> None:
    username_norm = (username or "").strip()
    user = session.execute(select(User).where(User.username == username_norm)).scalar_one_or_none()
    if user is None:
        raise ValueError("Usuário não encontrado.")
    if not force and not _verify_password(old_password, user.password_hash):
        raise ValueError("Senha atual inválida.")
    if not new_password:
        raise ValueError("Nova senha obrigatória.")
    user.password_hash = _hash_password(new_password)
    user.must_change_password = False
    user.updated_at = datetime.now()


def set_user_active(session: Session, username: str, is_active: bool) -> None:
    username_norm = (username or "").strip()
    user = session.execute(select(User).where(User.username == username_norm)).scalar_one_or_none()
    if user is None:
        raise ValueError("Usuário não encontrado.")
    user.is_active = is_active
    user.updated_at = datetime.now()


def require_role(user: User, allowed_roles: set[str] | list[str] | tuple[str, ...]) -> None:
    allowed = set(allowed_roles)
    if user.perfil not in allowed:
        raise PermissionError(f"Acesso negado para perfil {user.perfil}.")
