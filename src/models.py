from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


NUMERIC_20_2 = Numeric(20, 2, asdecimal=True)


class Base(DeclarativeBase):
    pass


class IdDim(Base):
    __tablename__ = "id_dim"
    __table_args__ = (
        UniqueConstraint(
            "grupo",
            "ai",
            "ao_ai",
            "po_ai",
            "ao_pa",
            "po_pa",
            "fr",
            "nd",
            "ugr",
            "uge",
            "moeda",
            "ug_exterior",
            name="uq_id_dim_chave_natural",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grupo: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    ai: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    ao_ai: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    po_ai: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    ao_pa: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    po_pa: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    fr: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    nd: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    ugr: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    uge: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    moeda: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    ug_exterior: Mapped[str] = mapped_column(String(60), nullable=False, default="")

    saldo: Mapped["Saldos"] = relationship(
        "Saldos",
        back_populates="id_dim",
        uselist=False,
        cascade="all, delete-orphan",
    )
    solicitacoes: Mapped[list["Solicitacao"]] = relationship("Solicitacao", back_populates="id_dim")


class Saldos(Base):
    __tablename__ = "saldos"

    id: Mapped[int] = mapped_column(ForeignKey("id_dim.id", ondelete="RESTRICT"), primary_key=True)
    bd_id_origem: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    titulo_ai: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    ugr_sigla: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    uge_sigla: Mapped[str] = mapped_column(String(60), nullable=False, default="")

    valor_pa_ini: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    valor_pa_aju: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    dif_planejamento_real: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    sol_lib_cred: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    sol_bloq: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    sol_desbloq: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    aprovado: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    liberado: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    bloqueado: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    corte: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    devolvido: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    saldo: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    pedidos_em_tramite: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    bandeja_dgom: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    a_atender: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))

    gerente: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    ods: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    aprovador: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    irp_pa: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    gerente_meta_codigo: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    gerente_meta_sigla: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    ods_meta_codigo: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    ods_meta_sigla: Mapped[str] = mapped_column(String(120), nullable=False, default="")

    id_dim: Mapped[IdDim] = relationship("IdDim", back_populates="saldo")


class Solicitacao(Base):
    __tablename__ = "solicitacoes"

    sol_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero_solicitacao: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    id: Mapped[int | None] = mapped_column(ForeignKey("id_dim.id", ondelete="SET NULL"), nullable=True, index=True)
    pendente_cadastro: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    pendencia_motivo: Mapped[str | None] = mapped_column(String(255), nullable=True)

    sol_data_criacao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sol_prioridade: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    sol_origem: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    sol_situacao: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    sol_tipo: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    sol_data_situacao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sol_setor_atual: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    sol_perfil_atual: Mapped[str] = mapped_column(String(120), nullable=False, default="")

    pa_grupo: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    pa_ai: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    pa_ao_ai: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    pa_po_ai: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    pa_ao_pa: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    pa_po_pa: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    pa_fr: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    pa_nd: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    pa_ugr: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    pa_uge: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    pa_moeda: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    pa_ug_exterior: Mapped[str] = mapped_column(String(60), nullable=False, default="")

    sol_grupo: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    sol_ai: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    sol_ao_pa: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    sol_po_pa: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    sol_fr: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    sol_nd: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    sol_ugr: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    sol_uge: Mapped[str] = mapped_column(String(60), nullable=False, default="")

    solicitado: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    atendido: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    em_atendimento: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    devolvido: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    saldo_a_atender: Mapped[Decimal] = mapped_column(NUMERIC_20_2, nullable=False, default=Decimal("0"))
    nc: Mapped[str] = mapped_column(String(120), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    id_dim: Mapped[IdDim | None] = relationship("IdDim", back_populates="solicitacoes")


class AuditoriaEvento(Base):
    __tablename__ = "auditoria_eventos"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, index=True)
    usuario: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    acao: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    entidade: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    chave: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    antes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    depois_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    justificativa: Mapped[str | None] = mapped_column(Text, nullable=True)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    perfil: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )


class AuthLog(Base):
    __tablename__ = "auth_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, index=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    sucesso: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    motivo: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    ip_origem: Mapped[str] = mapped_column(String(120), nullable=False, default="local")


class AppConfig(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_by: Mapped[str] = mapped_column(String(120), nullable=False, default="system")

