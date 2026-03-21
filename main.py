from datetime import date, datetime, timedelta
from decimal import Decimal
import importlib
import json
import math
import os
import re
import secrets
import smtplib
import threading
import unicodedata
import uuid
from email.message import EmailMessage
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import quote, urlparse
import mercadopago

# ── Mercado Pago credentials ─────────────────────────────────────────────────
MP_ACCESS_TOKEN_DEFAULT = os.getenv(
    "MP_ACCESS_TOKEN",
    "APP_USR-5522921031209003-021910-dddd5ef66e282053181508421bc9b411-277267651",
)
MP_PUBLIC_KEY_DEFAULT = os.getenv(
    "MP_PUBLIC_KEY",
    "APP_USR-7733074d-f28f-4374-9c38-d875aa3ad421",
)

SUPER_ADMIN_NOME_DEFAULT = (os.getenv("SUPER_ADMIN_NOME") or "Walter Junnys").strip()
SUPER_ADMIN_LOGIN_DEFAULT = (os.getenv("SUPER_ADMIN_LOGIN") or "walterjunnys@gmail.com").strip().lower()
SUPER_ADMIN_SENHA_DEFAULT = (os.getenv("SUPER_ADMIN_SENHA") or "wj92486656").strip()

DEMO_RESTAURANTE_NOME = (os.getenv("DEMO_RESTAURANTE_NOME") or "Conta Demo").strip()
DEMO_RESTAURANTE_SLUG = (os.getenv("DEMO_RESTAURANTE_SLUG") or "conta-dono").strip().lower()
DEFAULT_RESTAURANTE_NOME = (os.getenv("DEFAULT_RESTAURANTE_NOME") or "Solar Supermercado").strip()
DEFAULT_RESTAURANTE_SLUG = (os.getenv("DEFAULT_RESTAURANTE_SLUG") or "solar").strip().lower()
DEFAULT_RESTAURANTE_EMAIL = (os.getenv("DEFAULT_RESTAURANTE_EMAIL") or "solar@restaurante.local").strip().lower()
DEFAULT_RESTAURANTE_SENHA = (os.getenv("DEFAULT_RESTAURANTE_SENHA") or "solar1234").strip()
DEFAULT_RESTAURANTE_PLAN_TYPE = (os.getenv("DEFAULT_RESTAURANTE_PLAN_TYPE") or "standard").strip().lower()

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, Numeric, String, create_engine, func, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


SQLITE_LOCAL_DATABASE_URL = "sqlite:///./restaurante.db"
SQLITE_VERCEL_DATABASE_URL = "sqlite:////tmp/banco.db"

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    if os.getenv("RENDER") or os.getenv("RENDER_EXTERNAL_URL"):
        raise RuntimeError("DATABASE_URL não configurada no ambiente Render.")
    if os.getenv("VERCEL") == "1":
        SQLALCHEMY_DATABASE_URL = SQLITE_VERCEL_DATABASE_URL
    else:
        SQLALCHEMY_DATABASE_URL = SQLITE_LOCAL_DATABASE_URL

if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

DATABASE_URL = SQLALCHEMY_DATABASE_URL


def normalizar_database_url(url: str) -> str:
    valor = (url or "").strip()
    if not valor:
        return SQLITE_VERCEL_DATABASE_URL if os.getenv("VERCEL") == "1" else SQLITE_LOCAL_DATABASE_URL

    eh_postgres = valor.startswith("postgres://") or valor.startswith("postgresql://")
    if not eh_postgres:
        return valor

    if "sslmode=" in valor.lower():
        return valor

    separador = "&" if "?" in valor else "?"
    return f"{valor}{separador}sslmode=require"


DATABASE_URL = normalizar_database_url(DATABASE_URL)


def ambiente_producao() -> bool:
    marcadores = ["VERCEL", "RENDER", "RENDER_EXTERNAL_URL", "VERCEL_ENV"]
    return any((os.getenv(chave) or "").strip() for chave in marcadores)


if ambiente_producao() and DATABASE_URL.startswith("sqlite"):
    print(
        "[WARN] DATABASE_URL de produção não configurada para PostgreSQL. "
        "Usando SQLite fallback; isso pode causar instabilidade/persistência temporária."
    )


def obter_origens_cors() -> list[str]:
    bruto = (os.getenv("CORS_ALLOWED_ORIGINS") or "").strip()
    if bruto:
        return [origem.strip().rstrip("/") for origem in bruto.split(",") if origem.strip()]

    return [
        "https://sistema-restaurante-sigma.vercel.app",
        "https://sistema-restaurante.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]


CORS_ALLOWED_ORIGINS = obter_origens_cors()
CORS_ALLOWED_ORIGIN_REGEX = os.getenv("CORS_ALLOWED_ORIGIN_REGEX") or r"https://.*\.vercel\.app$"
DEFAULT_PUSH_VAPID_PUBLIC_KEY = "BKsSyK2PVl66Xpo3e02aZi8MEnzaBJEqhqa8O9fdJLIAzDELTlm5CN2UpxvwAFtCsU5dqH_W3gZc8IXiIy-gY9I"
DEFAULT_PUSH_VAPID_PRIVATE_KEY = "MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgD0DmaOHZ54MbZCLjSUi4ARfykKYDWahFHJaFyswCImmhRANCAASrEsitj1Zeul6aN3tNmmYvDBJ82gSRKoamvDvX3SSyAMwxC05ZuQjdlKcb8ABbQrFOXah_1t4GXPCF4iMvoGPS"
PUSH_VAPID_PUBLIC_KEY = os.getenv("PUSH_VAPID_PUBLIC_KEY", DEFAULT_PUSH_VAPID_PUBLIC_KEY).strip()
PUSH_VAPID_PRIVATE_KEY = os.getenv("PUSH_VAPID_PRIVATE_KEY", DEFAULT_PUSH_VAPID_PRIVATE_KEY).strip()
PUSH_VAPID_CLAIMS_SUB = os.getenv("PUSH_VAPID_CLAIMS_SUB", "mailto:suporte@restaurante.local").strip()
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
ENTREGADOR_CODIGOS_CACHE: dict[str, dict] = {}


class Base(DeclarativeBase):
    pass


class Restaurante(Base):
    __tablename__ = "restaurantes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    restaurante_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    nome_unidade: Mapped[str] = mapped_column(String(120), index=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    email_admin: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    status_assinatura: Mapped[str] = mapped_column(String(20), default="Ativo", index=True)
    data_assinatura: Mapped[date] = mapped_column(Date, default=date.today)
    validade_assinatura: Mapped[date] = mapped_column(Date, default=lambda: date.today() + timedelta(days=30), index=True)
    token_acesso: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    valor_mensalidade: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    plano: Mapped[str] = mapped_column(String(30), default="basic")
    plan_type: Mapped[str] = mapped_column(String(20), default="basic")
    cnpj: Mapped[str] = mapped_column(String(30), default="")
    total_mesas: Mapped[int] = mapped_column(Integer, default=10)
    delivery_ativo: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_endereco_origem: Mapped[str] = mapped_column(String(255), default="")
    delivery_bairro: Mapped[str] = mapped_column(String(120), default="")
    delivery_cidade: Mapped[str] = mapped_column(String(120), default="")
    delivery_uf: Mapped[str] = mapped_column(String(2), default="")
    delivery_google_maps_api_key: Mapped[str] = mapped_column(String(255), default="")
    delivery_whatsapp_entregador: Mapped[str] = mapped_column(String(30), default="")
    whatsapp_api_ativo: Mapped[bool] = mapped_column(Boolean, default=False)
    whatsapp_phone_number_id: Mapped[str] = mapped_column(String(80), default="")
    whatsapp_access_token: Mapped[str] = mapped_column(String(255), default="")
    whatsapp_verify_token: Mapped[str] = mapped_column(String(120), default="")
    categorias_json: Mapped[list] = mapped_column(JSON, default=list)
    categoria_horarios_json: Mapped[dict] = mapped_column(JSON, default=dict)
    capa_cardapio_base64: Mapped[str] = mapped_column(String(1000000), default="")
    capa_posicao: Mapped[str] = mapped_column(String(20), default="center")
    logo_base64: Mapped[str] = mapped_column(String(1000000), default="")
    tema_cor_primaria: Mapped[str] = mapped_column(String(20), default="#3b82f6")
    tema_cor_secundaria: Mapped[str] = mapped_column(String(20), default="#10b981")
    tema_cor_destaque: Mapped[str] = mapped_column(String(20), default="#1e293b")
    estilo_botao: Mapped[str] = mapped_column(String(20), default="rounded")
    foto_perfil_base64: Mapped[str] = mapped_column(String(1000000), default="")
    reset_senha_token: Mapped[str | None] = mapped_column(String(120), nullable=True, default=None, index=True)
    reset_senha_expira_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    restaurante_id: Mapped[str] = mapped_column(ForeignKey("restaurantes.restaurante_id"), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(120), index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    perfil: Mapped[str] = mapped_column(String(30), default="gerente")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Cardapio(Base):
    __tablename__ = "cardapio"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    restaurante_id: Mapped[str] = mapped_column(ForeignKey("restaurantes.restaurante_id"), index=True)
    nome: Mapped[str] = mapped_column(String(120), index=True)
    preco: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    categoria: Mapped[str] = mapped_column(String(40), default="Comida")
    disponivel: Mapped[bool] = mapped_column(Boolean, default=True)
    descricao: Mapped[str] = mapped_column(String(500), default="")
    imagem_base64: Mapped[str] = mapped_column(String(1000000), default="")  # até 1MB de imagem em base64
    complementos_json: Mapped[list] = mapped_column(JSON, default=list)
    horario_inicio: Mapped[str] = mapped_column(String(5), default="")
    horario_fim: Mapped[str] = mapped_column(String(5), default="")


class Pedido(Base):
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    restaurante_id: Mapped[str] = mapped_column(ForeignKey("restaurantes.restaurante_id"), index=True)
    mesa: Mapped[str] = mapped_column(String(20), index=True)
    tipo_entrega: Mapped[str] = mapped_column(String(20), default="mesa", index=True)
    cliente_nome: Mapped[str] = mapped_column(String(120), default="")
    cliente_telefone: Mapped[str] = mapped_column(String(30), default="")
    entregador_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    endereco_entrega_json: Mapped[dict] = mapped_column(JSON, default=dict)
    lat_entregador: Mapped[float | None] = mapped_column(Float, nullable=True)
    long_entregador: Mapped[float | None] = mapped_column(Float, nullable=True)
    forma_pagamento: Mapped[str] = mapped_column(String(20), default="")
    itens: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="Pendente", index=True)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Entregador(Base):
    __tablename__ = "entregadores"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    restaurante_id: Mapped[str] = mapped_column(ForeignKey("restaurantes.restaurante_id"), index=True)
    nome: Mapped[str] = mapped_column(String(120), index=True)
    whatsapp: Mapped[str] = mapped_column(String(30), default="")
    email_login: Mapped[str] = mapped_column(String(120), default="", index=True)
    senha_hash: Mapped[str] = mapped_column(String(255), default="")
    foto_perfil_base64: Mapped[str] = mapped_column(String(1000000), default="")
    token_rastreamento: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    ultima_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    ultima_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    ultima_precisao: Mapped[float | None] = mapped_column(Float, nullable=True)
    ultima_atualizacao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    push_subscriptions_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MarketingEvento(Base):
    __tablename__ = "marketing_eventos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    sessao_id: Mapped[str] = mapped_column(String(80), index=True, default="")
    evento: Mapped[str] = mapped_column(String(60), index=True)
    pagina: Mapped[str] = mapped_column(String(120), default="")
    plano: Mapped[str] = mapped_column(String(30), default="")
    origem: Mapped[str] = mapped_column(String(80), default="")
    sucesso: Mapped[bool] = mapped_column(Boolean, default=False)
    detalhes_json: Mapped[dict] = mapped_column(JSON, default=dict)
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    ip: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ConfigSistema(Base):
    """Chave-valor para configurações globais (ex.: token Mercado Pago)."""
    __tablename__ = "config_sistema"

    chave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[str] = mapped_column(String(2000), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


SCHEMA_INICIALIZADO = False
SCHEMA_LOCK = threading.Lock()


def garantir_schema_db() -> None:
    """Cria tabelas automaticamente no primeiro acesso ao banco."""
    global SCHEMA_INICIALIZADO
    if SCHEMA_INICIALIZADO:
        return

    with SCHEMA_LOCK:
        if SCHEMA_INICIALIZADO:
            return
        Base.metadata.create_all(bind=engine)
        SCHEMA_INICIALIZADO = True


class PagamentoPendente(Base):
    """Registro criado antes de o usuário ir ao checkout — aguarda confirmação MP."""
    __tablename__ = "pagamentos_pendentes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    pending_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    dados_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="aguardando", index=True)  # aguardando | aprovado | rejeitado
    mp_payment_id: Mapped[str] = mapped_column(String(80), default="")
    mp_preference_id: Mapped[str] = mapped_column(String(120), default="")
    restaurante_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    admin_url: Mapped[str] = mapped_column(String(500), default="")
    cardapio_url: Mapped[str] = mapped_column(String(500), default="")
    email_enviado: Mapped[bool] = mapped_column(Boolean, default=False)
    email_erro: Mapped[str] = mapped_column(String(500), default="")
    email_enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    email_tentativas: Mapped[int] = mapped_column(Integer, default=0)
    email_ultima_tentativa_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class RestauranteCreate(BaseModel):
    nome_unidade: str
    slug: str
    email_admin: EmailStr
    senha_inicial: str = Field(min_length=4)
    valor_mensalidade: Decimal = Decimal("0.00")
    token_acesso: str | None = None
    validade_assinatura: date | None = None
    status_assinatura: str = Field(default="Ativo", pattern="^(Ativo|Inativo)$")
    plano: str = Field(default="basic", pattern="^(basic|pro|enterprise)$")


class RestaurantePublicSignup(BaseModel):
    nome_unidade: str = Field(min_length=2, max_length=120)
    email_admin: EmailStr
    senha_inicial: str = Field(min_length=4, max_length=120)
    slug: str | None = None
    telefone_admin: str | None = None
    plano: str = Field(default="basic", pattern="^(basic|pro|enterprise)$")


class CriarPreferenciaPayload(BaseModel):
    nome_unidade: str = Field(min_length=2, max_length=120)
    email_admin: EmailStr
    senha_inicial: str = Field(min_length=4, max_length=120)
    slug: str | None = None
    telefone_admin: str | None = None
    plano: str = Field(default="basic", pattern="^(basic|pro|enterprise)$")
    periodo: str = Field(default="mensal", pattern="^(mensal|semestral|anual)$")


class ConfigMPUpdate(BaseModel):
    access_token: str
    public_key: str


class ConfigSMTPUpdate(BaseModel):
    host: str
    port: int = Field(default=587, ge=1, le=65535)
    user: str = ""
    password: str = ""
    from_email: str
    tls: bool = True
    ssl: bool = False


class PlanosSaaSUpdate(BaseModel):
    basic: Decimal = Field(gt=0)
    pro: Decimal = Field(gt=0)
    enterprise: Decimal = Field(gt=0)


class AdminPerfilUpdatePayload(BaseModel):
    email_admin: EmailStr | None = None
    senha_atual: str | None = None
    nova_senha: str | None = Field(default=None, min_length=4, max_length=120)
    foto_perfil_base64: str | None = None


class AdminLoginPayload(BaseModel):
    email_admin: EmailStr
    senha: str = Field(min_length=4, max_length=120)


class AdminPasswordResetRequestPayload(BaseModel):
    email_admin: EmailStr


class AdminPasswordResetConfirmPayload(BaseModel):
    token_reset: str = Field(min_length=20, max_length=200)
    nova_senha: str = Field(min_length=4, max_length=120)


class ProcessarPagamentoPayload(BaseModel):
    """Dados vindos do MP Payment Brick no onSubmit."""
    model_config = {"extra": "allow"}

    pending_id: str
    payment_method_id: str
    transaction_amount: float | None = None   # ignoramos — usamos valor do DB
    token: str | None = None                  # cartão tokenizado
    installments: int | None = 1
    issuer_id: str | None = None
    payer: dict | None = None


class RestauranteSuperAdminUpdate(BaseModel):
    nome_unidade: str | None = None
    slug: str | None = None
    email_admin: EmailStr | None = None
    token_acesso: str | None = None
    valor_mensalidade: Decimal | None = None
    validade_assinatura: date | None = None
    status_assinatura: str | None = Field(default=None, pattern="^(Ativo|Inativo)$")
    plano: str | None = Field(default=None, pattern="^(basic|pro|enterprise)$")


class MarketingEventoPayload(BaseModel):
    sessao_id: str | None = None
    evento: str = Field(min_length=2, max_length=60)
    pagina: str | None = None
    plano: str | None = None
    origem: str | None = None
    sucesso: bool | None = None
    detalhes: dict | None = None


class RestauranteOut(BaseModel):
    id: int
    restaurante_id: str
    nome_unidade: str
    slug: str
    email_admin: str
    status_assinatura: str
    data_assinatura: date
    validade_assinatura: date
    token_acesso: str
    valor_mensalidade: Decimal
    foto_perfil_base64: str | None = None
    admin_url: str | None = None
    cardapio_url: str | None = None

    class Config:
        from_attributes = True


class CardapioCreate(BaseModel):
    token_acesso: str
    nome: str
    preco: Decimal
    categoria: str = "Comida"
    descricao: str = ""
    imagem_base64: str = ""
    complementos: list[dict] = Field(default_factory=list)
    disponivel: bool = True
    horario_inicio: str = ""
    horario_fim: str = ""


class CardapioUpdate(BaseModel):
    nome: str = None
    preco: Decimal = None
    categoria: str = None
    descricao: str = None
    imagem_base64: str = None
    complementos: list[dict] = None
    disponivel: bool = None
    horario_inicio: str = None
    horario_fim: str = None


class RestauranteConfigUpdate(BaseModel):
    nome_unidade: str | None = None
    cnpj: str | None = None
    total_mesas: int | None = None
    delivery_ativo: bool | None = None
    delivery_endereco_origem: str | None = None
    delivery_bairro: str | None = None
    delivery_cidade: str | None = None
    delivery_uf: str | None = None
    delivery_google_maps_api_key: str | None = None
    delivery_whatsapp_entregador: str | None = None
    whatsapp_api_ativo: bool | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_access_token: str | None = None
    whatsapp_verify_token: str | None = None
    categorias: list[str] | None = None
    categoria_horarios: dict | None = None
    capa_cardapio_base64: str | None = None
    capa_posicao: str | None = None
    logo_base64: str | None = None
    tema_cor_primaria: str | None = None
    tema_cor_secundaria: str | None = None
    tema_cor_destaque: str | None = None
    estilo_botao: str | None = None


class PedidoCreate(BaseModel):
    slug: str
    mesa: str
    itens: list[dict]
    tipo_entrega: str = Field(default="mesa", pattern="^(mesa|delivery)$")
    cliente_nome: str = ""
    cliente_telefone: str = ""
    endereco_entrega: dict = Field(default_factory=dict)


class PedidoStatusUpdate(BaseModel):
    status: str = Field(pattern="^(novo|preparando|pronto|em_entrega|entregue|cancelado|fechado)$")
    forma_pagamento: str | None = Field(default=None, pattern="^(dinheiro|cartao|pix)$")
    entregador_id: int | None = Field(default=None, gt=0)


class PedidoRastreioUpdate(BaseModel):
    entregador_id: int = Field(gt=0)


class PedidoDespachoAutomaticoPayload(BaseModel):
    entregador_id: int | None = Field(default=None, gt=0)
    frontend_base_url: str | None = Field(default=None, max_length=255)
    api_base_url: str | None = Field(default=None, max_length=255)


class PedidoDespacharPayload(BaseModel):
    entregador_id: int | None = Field(default=None, gt=0)
    frontend_base_url: str | None = Field(default=None, max_length=255)
    api_base_url: str | None = Field(default=None, max_length=255)


class AdminPedidoCreate(BaseModel):
    mesa: str
    itens: list[dict]
    status: str = Field(default="novo", pattern="^(novo|preparando|pronto|em_entrega|entregue|cancelado|fechado)$")
    tipo_entrega: str = Field(default="mesa", pattern="^(mesa|delivery)$")
    cliente_nome: str = ""
    cliente_telefone: str = ""
    endereco_entrega: dict = Field(default_factory=dict)


class ExtenderValidadePayload(BaseModel):
    nova_validade_assinatura: date


class EntregadorCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    whatsapp: str = Field(min_length=8, max_length=30)
    senha: str = Field(min_length=4, max_length=120)


class EntregadorUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    whatsapp: str | None = Field(default=None, min_length=8, max_length=30)
    email_login: str | None = None
    senha: str | None = Field(default=None, min_length=4, max_length=120)
    ativo: bool | None = None


class EntregadorLoginPayload(BaseModel):
    restaurante: str | None = Field(default=None, min_length=2, max_length=120)
    slug: str | None = Field(default=None, min_length=2, max_length=120)
    telefone: str | None = Field(default=None, min_length=8, max_length=30)
    email_login: str | None = None
    senha: str = Field(min_length=4, max_length=120)


class EntregadorPublicCreatePayload(BaseModel):
    restaurante: str | None = Field(default=None, min_length=2, max_length=120)
    slug: str | None = Field(default=None, min_length=2, max_length=120)
    nome: str = Field(min_length=2, max_length=120)
    telefone: str = Field(min_length=8, max_length=30)
    senha: str = Field(min_length=4, max_length=120)
    codigo_verificacao: str = Field(min_length=5, max_length=5)


class EntregadorCodigoSolicitacaoPayload(BaseModel):
    restaurante: str | None = Field(default=None, min_length=2, max_length=120)
    slug: str | None = Field(default=None, min_length=2, max_length=120)
    telefone: str = Field(min_length=8, max_length=30)


class EntregadorPerfilUpdatePayload(BaseModel):
    email_login: str | None = None
    whatsapp: str | None = Field(default=None, min_length=8, max_length=30)
    senha_atual: str | None = Field(default=None, min_length=4, max_length=120)
    nova_senha: str | None = Field(default=None, min_length=4, max_length=120)
    foto_perfil_base64: str | None = None


class EntregadorLocalizacaoPayload(BaseModel):
    latitude: float
    longitude: float
    precisao: float | None = None


class PedidoLocalizacaoUpdate(BaseModel):
    latitude: float
    longitude: float
    precisao: float | None = None
    token_rastreamento: str | None = None


class EntregadorPedidoStatusUpdate(BaseModel):
    status: str = Field(pattern="^(em_entrega|entregue)$")


class EntregadorPushSubscriptionPayload(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
    keys: dict = Field(default_factory=dict)


class EntregadorPushSubscriptionRemovePayload(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)


class WhatsAppTestePayload(BaseModel):
    telefone: str = Field(min_length=8, max_length=30)
    mensagem: str | None = Field(default=None, max_length=1000)


class SuperAdminCredenciaisUpdate(BaseModel):
    nome_exibicao: str | None = Field(default=None, min_length=2, max_length=120)
    email_login: EmailStr | None = None
    senha: str | None = Field(default=None, min_length=4, max_length=120)


class SuperAdminAuthPayload(BaseModel):
    email_login: EmailStr
    senha: str = Field(min_length=4, max_length=120)


app = FastAPI(title="SaaS Restaurante - Multi-tenancy por coluna")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_origin_regex=CORS_ALLOWED_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def middleware_validade_assinatura(request: Request, call_next):
    garantir_schema_db()
    path = request.url.path

    proteger = (
        path.startswith("/api/admin/")
        or path.startswith("/api/public/cardapio/")
        or path.startswith("/api/public/pedidos")
    )

    if not proteger:
        return await call_next(request)

    db = SessionLocal()
    try:
        restaurante: Restaurante | None = None

        if path.startswith("/api/public/cardapio/"):
            slug = extrair_slug_da_rota(path, "/api/public/cardapio")
            if slug:
                restaurante = db.query(Restaurante).filter(Restaurante.slug == slug).first()

        elif path.startswith("/api/public/pedidos"):
            payload = await extrair_payload_json(request)
            slug = payload.get("slug") if isinstance(payload, dict) else None
            if not slug:
                slug = (request.query_params.get("slug") or "").strip().lower()
            if slug:
                restaurante = db.query(Restaurante).filter(Restaurante.slug == str(slug).strip().lower()).first()

        elif path.startswith("/api/admin/"):
            slug = None
            if path.startswith("/api/admin/restaurante/"):
                slug = extrair_slug_da_rota(path, "/api/admin/restaurante")
            elif path.startswith("/api/admin/pedidos/"):
                slug = extrair_slug_da_rota(path, "/api/admin/pedidos")
            elif path.startswith("/api/admin/cardapio/"):
                slug = extrair_slug_da_rota(path, "/api/admin/cardapio")
            elif path.startswith("/api/admin/entregadores/"):
                slug = extrair_slug_da_rota(path, "/api/admin/entregadores")

            if slug:
                restaurante = db.query(Restaurante).filter(Restaurante.slug == slug).first()
            else:
                token_header = request.headers.get("token_acesso") or request.headers.get("token-acesso")
                token = token_header
                if not token:
                    payload = await extrair_payload_json(request)
                    token = payload.get("token_acesso")
                if token:
                    restaurante = db.query(Restaurante).filter(Restaurante.token_acesso == token).first()

        if restaurante and not assinatura_ativa(restaurante):
            if restaurante.validade_assinatura and date.today() > restaurante.validade_assinatura:
                bloquear_restaurante_por_validade_expirada(restaurante, db)
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Acesso bloqueado: validade da assinatura expirada",
                        "status_assinatura": "Inativo",
                        "validade_assinatura": restaurante.validade_assinatura.isoformat(),
                    },
                )

            return JSONResponse(
                status_code=403,
                content={"detail": "Acesso negado: assinatura inativa"},
            )

        if restaurante and (
            path.startswith("/api/admin/pedidos")
            or path.startswith("/api/admin/entregadores")
            or path.startswith("/api/public/pedidos")
            or path.startswith("/api/public/entregadores")
        ) and not plano_permite_pedidos_delivery(restaurante):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Plano basic não possui permissão para Delivery e Pedidos.",
                    "plan_type": obter_plan_type_restaurante(restaurante),
                    "permissions": obter_permissoes_plano(restaurante),
                },
            )

        return await call_next(request)
    finally:
        db.close()


def get_db():
    garantir_schema_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_restaurante_por_slug(db: Session, slug: str) -> Restaurante:
    restaurante = db.query(Restaurante).filter(Restaurante.slug == slug).first()
    if not restaurante:
        raise HTTPException(status_code=404, detail="Restaurante não encontrado")
    return restaurante


def get_restaurante_por_token(db: Session, token_acesso: str) -> Restaurante:
    restaurante = db.query(Restaurante).filter(Restaurante.token_acesso == token_acesso).first()
    if not restaurante:
        raise HTTPException(status_code=401, detail="Token inválido")
    return restaurante


def assinatura_ativa(restaurante: Restaurante) -> bool:
    if restaurante.status_assinatura != "Ativo":
        return False
    if not restaurante.validade_assinatura:
        return False
    return date.today() <= restaurante.validade_assinatura


def normalizar_plan_type(plan_type: str | None, plano_legacy: str | None = None) -> str:
    valor = (plan_type or "").strip().lower()
    if valor in {"basic", "standard", "premium"}:
        return valor

    legado = (plano_legacy or "").strip().lower()
    if legado in {"pro", "standard"}:
        return "standard"
    if legado in {"enterprise", "premium"}:
        return "premium"
    return "basic"


def obter_plan_type_restaurante(restaurante: Restaurante) -> str:
    return normalizar_plan_type(
        getattr(restaurante, "plan_type", ""),
        getattr(restaurante, "plano", ""),
    )


def plano_permite_pedidos_delivery(restaurante: Restaurante) -> bool:
    return obter_plan_type_restaurante(restaurante) in {"standard", "premium"}


def obter_permissoes_plano(restaurante: Restaurante) -> dict:
    permitido = plano_permite_pedidos_delivery(restaurante)
    return {
        "can_orders": permitido,
        "can_delivery": permitido,
    }


def extrair_slug_da_rota(path: str, prefixo: str) -> str | None:
    partes = [p for p in path.split("/") if p]
    prefixo_partes = [p for p in prefixo.split("/") if p]
    if len(partes) <= len(prefixo_partes):
        return None
    return partes[len(prefixo_partes)]


async def extrair_payload_json(request: Request) -> dict:
    try:
        if "application/json" not in (request.headers.get("content-type") or ""):
            return {}
        body = await request.body()
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def bloquear_restaurante_por_validade_expirada(restaurante: Restaurante, db: Session) -> None:
    if restaurante.status_assinatura != "Inativo":
        restaurante.status_assinatura = "Inativo"
        db.commit()


PLANOS_SAAS_VALOR = {
    "basic": Decimal("97.00"),
    "pro": Decimal("197.00"),
    "enterprise": Decimal("397.00"),
}


def obter_planos_saas_valores(db: Session) -> dict[str, Decimal]:
    valores: dict[str, Decimal] = {}
    for codigo, padrao in PLANOS_SAAS_VALOR.items():
        chave = f"saas_plano_{codigo}"
        cfg = db.get(ConfigSistema, chave)
        bruto = (cfg.valor.strip() if cfg and cfg.valor else "")
        try:
            valor = Decimal(bruto.replace(",", ".")) if bruto else padrao
        except Exception:
            valor = padrao
        if valor <= 0:
            valor = padrao
        valores[codigo] = valor.quantize(Decimal("0.01"))
    return valores


def salvar_planos_saas_valores(db: Session, valores: dict[str, Decimal]) -> dict[str, Decimal]:
    salvos: dict[str, Decimal] = {}
    for codigo, valor in valores.items():
        chave = f"saas_plano_{codigo}"
        v = Decimal(valor).quantize(Decimal("0.01"))
        obj = db.get(ConfigSistema, chave)
        if obj:
            obj.valor = str(v)
        else:
            db.add(ConfigSistema(chave=chave, valor=str(v)))
        salvos[codigo] = v
    db.commit()
    return salvos


def normalizar_telefone_whatsapp(telefone: str | None) -> str:
    digitos = "".join(ch for ch in str(telefone or "") if ch.isdigit())
    if digitos.startswith("00"):
        digitos = digitos[2:]
    if len(digitos) in {10, 11}:
        digitos = f"55{digitos}"
    if len(digitos) < 12 or len(digitos) > 15:
        return ""
    return digitos


def status_pedido_legivel(status: str) -> str:
    mapa = {
        "novo": "Recebido",
        "preparando": "Em preparo na cozinha",
        "pronto": "Pronto para retirada/entrega",
        "em_entrega": "Saiu para entrega",
        "entregue": "Entregue",
        "cancelado": "Cancelado",
        "fechado": "Fechado",
    }
    return mapa.get((status or "").lower(), status or "Atualizado")


def montar_texto_status_whatsapp(restaurante: Restaurante, pedido: Pedido, status: str) -> str:
    titulo = restaurante.nome_unidade or "Restaurante"
    status_legivel = status_pedido_legivel(status)
    nome_cliente = (pedido.cliente_nome or "Cliente").strip() or "Cliente"
    base = (
        f"Olá, {nome_cliente}!\n"
        f"Seu pedido #{pedido.id} no {titulo} foi atualizado.\n"
        f"Status atual: {status_legivel}."
    )
    if (pedido.tipo_entrega or "").lower() == "delivery":
        base += "\nAcompanhe que nossa equipe está cuidando de tudo por aqui."
    return base


def enviar_whatsapp_cloud_message(
    phone_number_id: str,
    access_token: str,
    telefone_destino: str,
    mensagem: str,
) -> dict:
    if not phone_number_id or not access_token:
        return {"ok": False, "erro": "Configuração WhatsApp incompleta"}

    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": telefone_destino,
        "type": "text",
        "text": {
            "preview_url": True,
            "body": mensagem,
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib_request.urlopen(req, timeout=12) as response:
            conteudo = response.read().decode("utf-8") if response else "{}"
            return {"ok": True, "resposta": json.loads(conteudo or "{}")}
    except urllib_error.HTTPError as exc:
        corpo = exc.read().decode("utf-8") if hasattr(exc, "read") else ""
        return {"ok": False, "erro": f"HTTP {exc.code}", "detalhes": corpo}
    except urllib_error.URLError as exc:
        return {"ok": False, "erro": f"Falha de conexão: {exc.reason}"}
    except Exception as exc:
        return {"ok": False, "erro": str(exc)}


def notificar_status_pedido_whatsapp(restaurante: Restaurante, pedido: Pedido, status: str) -> dict:
    if not restaurante.whatsapp_api_ativo:
        return {"enviado": False, "motivo": "whatsapp_desativado"}

    telefone_destino = normalizar_telefone_whatsapp(pedido.cliente_telefone)
    if not telefone_destino:
        return {"enviado": False, "motivo": "cliente_sem_whatsapp"}

    mensagem = montar_texto_status_whatsapp(restaurante, pedido, status)
    envio = enviar_whatsapp_cloud_message(
        phone_number_id=(restaurante.whatsapp_phone_number_id or "").strip(),
        access_token=(restaurante.whatsapp_access_token or "").strip(),
        telefone_destino=telefone_destino,
        mensagem=mensagem,
    )

    return {
        "enviado": bool(envio.get("ok")),
        "telefone": telefone_destino,
        "erro": envio.get("erro"),
        "detalhes": envio.get("detalhes"),
    }


def _normalizar_base_url(valor: str | None) -> str:
    texto = str(valor or "").strip()
    if not texto:
        return ""
    if not re.match(r"^https?://", texto, flags=re.IGNORECASE):
        return ""
    return texto.rstrip("/")


def _converter_base_api_para_frontend(api_base_url: str | None) -> str:
    base = _normalizar_base_url(api_base_url)
    if not base:
        return ""

    try:
        parsed = urlparse(base)
    except Exception:
        return ""

    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost"}:
        return base

    porta = parsed.port
    if porta in {8000, 8010, 8090, 8001, 5501}:
        return f"{parsed.scheme}://{host}:8022"

    return base


def _resolver_frontend_base_url(
    restaurante: Restaurante | None,
    request: Request | None = None,
    frontend_base_url: str | None = None,
    api_base_url: str | None = None,
) -> str:
    frontend_forcado = _normalizar_base_url(frontend_base_url)
    if frontend_forcado:
        return _converter_base_api_para_frontend(frontend_forcado) or frontend_forcado

    frontend_restaurante = _normalizar_base_url(getattr(restaurante, "url_base_publica", ""))
    if frontend_restaurante:
        return _converter_base_api_para_frontend(frontend_restaurante) or frontend_restaurante

    api_base = _normalizar_base_url(api_base_url)
    if not api_base and request:
        api_base = _normalizar_base_url(str(request.base_url))

    convertido = _converter_base_api_para_frontend(api_base)
    if convertido:
        return convertido

    return ""


def _formatar_endereco_texto(endereco: dict | None) -> str:
    if not isinstance(endereco, dict):
        return ""
    linha1 = ", ".join([p for p in [endereco.get("rua"), endereco.get("numero")] if p])
    linha2 = " - ".join([p for p in [endereco.get("bairro"), endereco.get("cidade"), endereco.get("uf")] if p])
    linha3 = " | ".join([p for p in [endereco.get("complemento"), endereco.get("referencia")] if p])
    return " · ".join([p for p in [linha1, linha2, linha3] if p])


def _montar_consulta_geocode_endereco(endereco: dict | None) -> str:
    if not isinstance(endereco, dict):
        return ""

    for campo in ["maps_formatado", "formatted_address", "address"]:
        valor = str(endereco.get(campo) or "").strip()
        if valor:
            return valor

    texto_base = _formatar_endereco_texto(endereco)
    if texto_base:
        return texto_base

    partes: list[str] = []
    ignorar = {
        "latitude",
        "longitude",
        "lat",
        "lng",
        "lon",
        "long",
        "latitude_destino",
        "longitude_destino",
        "lat_destino",
        "long_destino",
        "lon_destino",
        "maps_valido",
        "place_id",
    }
    for chave, valor in endereco.items():
        if str(chave or "").lower() in ignorar:
            continue
        texto = str(valor or "").strip()
        if texto:
            partes.append(texto)

    return ", ".join(partes)


UF_PARA_ESTADO: dict[str, str] = {
    "AC": "acre",
    "AL": "alagoas",
    "AP": "amapa",
    "AM": "amazonas",
    "BA": "bahia",
    "CE": "ceara",
    "DF": "distrito federal",
    "ES": "espirito santo",
    "GO": "goias",
    "MA": "maranhao",
    "MT": "mato grosso",
    "MS": "mato grosso do sul",
    "MG": "minas gerais",
    "PA": "para",
    "PB": "paraiba",
    "PR": "parana",
    "PE": "pernambuco",
    "PI": "piaui",
    "RJ": "rio de janeiro",
    "RN": "rio grande do norte",
    "RS": "rio grande do sul",
    "RO": "rondonia",
    "RR": "roraima",
    "SC": "santa catarina",
    "SP": "sao paulo",
    "SE": "sergipe",
    "TO": "tocantins",
}


def _normalizar_texto_geo(texto: str | None) -> str:
    base = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", base).strip().lower()


def _normalizar_uf_geo(uf: str | None) -> str:
    sigla = re.sub(r"[^A-Za-z]", "", str(uf or "")).upper().strip()
    if len(sigla) == 2 and sigla in UF_PARA_ESTADO:
        return sigla

    nome = _normalizar_texto_geo(uf)
    for chave, estado in UF_PARA_ESTADO.items():
        if nome == estado:
            return chave

    return ""


def _pontuar_resultado_nominatim(item: dict, cidade_alvo: str, uf_alvo: str) -> int:
    if not isinstance(item, dict):
        return -1

    score = 0
    display = _normalizar_texto_geo(item.get("display_name"))
    address = item.get("address") if isinstance(item.get("address"), dict) else {}

    cidade_resposta = _normalizar_texto_geo(
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("county")
    )
    estado_resposta = _normalizar_texto_geo(address.get("state"))

    uf_iso = ""
    for campo_iso in ["ISO3166-2-lvl4", "ISO3166-2-lvl6", "state_code"]:
        valor_iso = str(address.get(campo_iso) or "").strip().upper()
        if valor_iso.startswith("BR-") and len(valor_iso) >= 5:
            uf_iso = valor_iso[-2:]
            break

    if cidade_alvo:
        if cidade_alvo == cidade_resposta:
            score += 35
        elif cidade_alvo and cidade_alvo in display:
            score += 20

    if uf_alvo:
        estado_alvo = UF_PARA_ESTADO.get(uf_alvo, "")
        if uf_iso == uf_alvo:
            score += 40
        elif estado_alvo and estado_alvo == estado_resposta:
            score += 32
        elif estado_alvo and estado_alvo in display:
            score += 22

    return score


def _geocodificar_endereco_nominatim(
    endereco_texto: str,
    cidade: str | None = None,
    uf: str | None = None,
) -> tuple[float | None, float | None, str]:
    texto = str(endereco_texto or "").strip()
    if not texto:
        return None, None, ""

    cidade_alvo = _normalizar_texto_geo(cidade)
    uf_alvo = _normalizar_uf_geo(uf)

    consultas: list[str] = []
    if cidade_alvo and uf_alvo:
        consultas.append(f"{texto}, {cidade_alvo}, {uf_alvo}, Brasil")
    elif cidade_alvo:
        consultas.append(f"{texto}, {cidade_alvo}, Brasil")
    elif uf_alvo:
        consultas.append(f"{texto}, {uf_alvo}, Brasil")

    consulta_base = texto if "brasil" in texto.lower() else f"{texto}, Brasil"
    consultas.append(consulta_base)

    melhor: dict | None = None
    melhor_score = -1

    for consulta in consultas:
        url = (
            "https://nominatim.openstreetmap.org/search"
            f"?q={quote(consulta)}&format=json&limit=5&countrycodes=br&addressdetails=1"
        )
        req = urllib_request.Request(
            url,
            headers={
                "User-Agent": "SistemaRestaurante/1.0 (delivery-geocode)",
                "Accept-Language": "pt-BR,pt;q=0.9",
            },
        )

        try:
            with urllib_request.urlopen(req, timeout=6) as resposta:
                bruto = resposta.read().decode("utf-8", errors="ignore")
            dados = json.loads(bruto)
            if not isinstance(dados, list) or not dados:
                continue

            for item in dados:
                if not isinstance(item, dict):
                    continue
                lat = float(item.get("lat")) if item.get("lat") is not None else None
                lon = float(item.get("lon")) if item.get("lon") is not None else None
                if not _coordenada_valida(lat, lon):
                    continue

                score = _pontuar_resultado_nominatim(item, cidade_alvo, uf_alvo)
                if melhor is None or score > melhor_score:
                    melhor = item
                    melhor_score = score
        except (urllib_error.URLError, TimeoutError, ValueError, TypeError, json.JSONDecodeError):
            continue

    if not isinstance(melhor, dict):
        return None, None, ""

    score_minimo = -999
    if cidade_alvo and uf_alvo:
        score_minimo = 25
    elif uf_alvo:
        score_minimo = 20
    elif cidade_alvo:
        score_minimo = 15

    if melhor_score < score_minimo:
        return None, None, ""

    lat = float(melhor.get("lat")) if melhor.get("lat") is not None else None
    lon = float(melhor.get("lon")) if melhor.get("lon") is not None else None
    if not _coordenada_valida(lat, lon):
        return None, None, ""

    rotulo = str(melhor.get("display_name") or "").strip()
    return lat, lon, rotulo


def _coordenada_valida(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    if abs(lat) > 90 or abs(lon) > 180:
        return False
    if lat == 0 and lon == 0:
        return False
    return True


def _distancia_haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    raio_terra_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return raio_terra_km * c


def _normalizar_endereco_entrega(endereco: dict | None) -> dict:
    if not isinstance(endereco, dict):
        return {}

    endereco_normalizado = dict(endereco)
    for campo in [
        "rua",
        "numero",
        "bairro",
        "cidade",
        "uf",
        "complemento",
        "referencia",
        "maps_formatado",
        "place_id",
    ]:
        if campo in endereco_normalizado and endereco_normalizado.get(campo) is not None:
            endereco_normalizado[campo] = str(endereco_normalizado.get(campo) or "").strip()

    lat_bruta = endereco_normalizado.get("latitude", endereco_normalizado.get("lat"))
    lon_bruta = endereco_normalizado.get("longitude", endereco_normalizado.get("lng", endereco_normalizado.get("lon")))

    try:
        lat = float(lat_bruta) if lat_bruta is not None else None
        lon = float(lon_bruta) if lon_bruta is not None else None
    except (TypeError, ValueError):
        lat, lon = None, None

    cidade_ref = str(endereco_normalizado.get("cidade") or "").strip()
    uf_ref = str(endereco_normalizado.get("uf") or "").strip()

    consulta = _montar_consulta_geocode_endereco(endereco_normalizado)
    geo_lat, geo_lon, geo_label = _geocodificar_endereco_nominatim(
        consulta,
        cidade=cidade_ref,
        uf=uf_ref,
    )
    geo_valido = _coordenada_valida(geo_lat, geo_lon)

    if not _coordenada_valida(lat, lon):
        if geo_valido:
            lat, lon = geo_lat, geo_lon
            if geo_label and not str(endereco_normalizado.get("maps_formatado") or "").strip():
                endereco_normalizado["maps_formatado"] = geo_label
    elif geo_valido:
        distancia_km = _distancia_haversine_km(float(lat), float(lon), float(geo_lat), float(geo_lon))
        if distancia_km >= 30:
            lat, lon = geo_lat, geo_lon
            endereco_normalizado["coordenadas_ajustadas_backend"] = True
            endereco_normalizado["coordenadas_ajuste_motivo"] = "reconciliacao_geocode"
            endereco_normalizado["coordenadas_distancia_km"] = round(distancia_km, 3)
        if geo_label and not str(endereco_normalizado.get("maps_formatado") or "").strip():
            endereco_normalizado["maps_formatado"] = geo_label

    if _coordenada_valida(lat, lon):
        endereco_normalizado["latitude"] = lat
        endereco_normalizado["longitude"] = lon
        endereco_normalizado["lat"] = lat
        endereco_normalizado["lng"] = lon
        endereco_normalizado["lon"] = lon
        endereco_normalizado["maps_valido"] = True
    else:
        endereco_normalizado["latitude"] = None
        endereco_normalizado["longitude"] = None
        endereco_normalizado["lat"] = None
        endereco_normalizado["lng"] = None
        endereco_normalizado["lon"] = None
        endereco_normalizado["maps_valido"] = False

    if not str(endereco_normalizado.get("maps_formatado") or "").strip():
        endereco_normalizado["maps_formatado"] = _formatar_endereco_texto(endereco_normalizado)

    return endereco_normalizado


def _aplicar_fallback_coordenadas_endereco(
    endereco: dict | None,
    endereco_origem_restaurante: str | None,
) -> dict:
    if not isinstance(endereco, dict):
        return {}

    endereco_final = dict(endereco)
    lat_existente, lon_existente = _extrair_lat_lon_endereco(endereco_final)
    if _coordenada_valida(lat_existente, lon_existente):
        endereco_final["latitude"] = lat_existente
        endereco_final["longitude"] = lon_existente
        endereco_final["lat"] = lat_existente
        endereco_final["lng"] = lon_existente
        endereco_final["lon"] = lon_existente
        return endereco_final

    _ = endereco_origem_restaurante
    return _normalizar_endereco_entrega(endereco_final)


def _validar_endereco_delivery(endereco: dict) -> None:
    if not isinstance(endereco, dict):
        raise HTTPException(status_code=400, detail="Endereço de entrega inválido")

    campos_minimos = [
        str(endereco.get("rua") or "").strip(),
        str(endereco.get("numero") or "").strip(),
        str(endereco.get("bairro") or "").strip(),
        str(endereco.get("cidade") or "").strip(),
        str(endereco.get("uf") or "").strip(),
    ]
    if any(not valor for valor in campos_minimos):
        raise HTTPException(
            status_code=400,
            detail="Endereço de delivery incompleto. Preencha rua, número, bairro, cidade e UF.",
        )

    lat_bruta = endereco.get("latitude", endereco.get("lat"))
    lon_bruta = endereco.get("longitude", endereco.get("lng", endereco.get("lon")))
    try:
        lat = float(lat_bruta) if lat_bruta is not None else None
        lon = float(lon_bruta) if lon_bruta is not None else None
    except (TypeError, ValueError):
        lat, lon = None, None

    if not _coordenada_valida(lat, lon):
        raise HTTPException(
            status_code=400,
            detail="Endereço de delivery sem coordenadas válidas. Confirme o endereço no mapa antes de enviar.",
        )


def _marcar_entregador_online(
    db: Session,
    entregador: Entregador | None,
    *,
    commit: bool = False,
    intervalo_minimo_segundos: int = 20,
) -> bool:
    if not entregador:
        return False

    agora = datetime.utcnow()
    ultima = entregador.ultima_atualizacao
    if ultima and (agora - ultima).total_seconds() < max(0, int(intervalo_minimo_segundos or 0)):
        return False

    entregador.ultima_atualizacao = agora
    if commit:
        db.commit()
        db.refresh(entregador)
    else:
        db.flush()
    return True


def _selecionar_entregador_automatico(
    db: Session,
    restaurante_id: str,
    preferido_id: int | None = None,
    ignorar_pedido_id: int | None = None,
) -> Entregador | None:
    limite_online = datetime.utcnow() - timedelta(minutes=5)

    def entregador_disponivel(entregador_id: int) -> bool:
        q = db.query(Pedido).filter(
            Pedido.restaurante_id == restaurante_id,
            Pedido.entregador_id == entregador_id,
            Pedido.tipo_entrega == "delivery",
            Pedido.status.in_(["em_entrega"]),
        )
        if ignorar_pedido_id:
            q = q.filter(Pedido.id != ignorar_pedido_id)
        return q.first() is None

    def entregador_online(entregador: Entregador | None) -> bool:
        return bool(
            entregador
            and entregador.ultima_atualizacao
            and entregador.ultima_atualizacao >= limite_online
        )

    def entregador_apto(entregador: Entregador | None) -> bool:
        return bool(
            entregador
            and entregador.restaurante_id == restaurante_id
            and entregador.ativo
            and str(entregador.token_rastreamento or "").strip()
            and entregador_online(entregador)
            and entregador_disponivel(entregador.id)
        )

    if preferido_id:
        preferido = db.get(Entregador, preferido_id)
        if entregador_apto(preferido):
            return preferido

    online = db.query(Entregador).filter(
        Entregador.restaurante_id == restaurante_id,
        Entregador.ativo == True,
        Entregador.token_rastreamento.is_not(None),
        Entregador.ultima_atualizacao.is_not(None),
        Entregador.ultima_atualizacao >= limite_online,
    ).order_by(
        Entregador.id.asc(),
    ).all()

    candidatos = [entregador for entregador in online if entregador_apto(entregador)]
    if not candidatos:
        return None
    if len(candidatos) == 1:
        return candidatos[0]

    ids_candidatos = [entregador.id for entregador in candidatos]
    ultimas_corridas = {
        int(entregador_id): ultima_corrida
        for entregador_id, ultima_corrida in db.query(
            Pedido.entregador_id,
            func.max(Pedido.created_at),
        ).filter(
            Pedido.restaurante_id == restaurante_id,
            Pedido.tipo_entrega == "delivery",
            Pedido.entregador_id.in_(ids_candidatos),
        ).group_by(Pedido.entregador_id).all()
        if entregador_id
    }

    def ranking_distribuicao(entregador: Entregador) -> tuple[int, datetime, float, int]:
        ultima_corrida = ultimas_corridas.get(entregador.id)
        ultima_online = entregador.ultima_atualizacao or datetime.min
        return (
            0 if ultima_corrida is None else 1,
            ultima_corrida or datetime.min,
            -ultima_online.timestamp() if entregador.ultima_atualizacao else 0.0,
            entregador.id,
        )

    candidatos.sort(key=ranking_distribuicao)
    return candidatos[0]

    return None


def _backfill_deliveries_sem_entregador(
    db: Session,
    restaurante_id: str,
    preferido_id: int | None = None,
    limite: int | None = None,
) -> int:
    pedidos_sem_entregador = db.query(Pedido).filter(
        Pedido.restaurante_id == restaurante_id,
        Pedido.tipo_entrega == "delivery",
        Pedido.entregador_id.is_(None),
        Pedido.status.in_(["em_entrega"]),
    ).order_by(Pedido.created_at.asc(), Pedido.id.asc()).all()

    if limite is not None and limite >= 0:
        pedidos_sem_entregador = pedidos_sem_entregador[:limite]

    if not pedidos_sem_entregador:
        return 0

    vinculados = 0
    preferido_disponivel = preferido_id
    for pedido in pedidos_sem_entregador:
        entregador = _selecionar_entregador_automatico(
            db,
            restaurante_id,
            preferido_id=preferido_disponivel,
            ignorar_pedido_id=pedido.id,
        )
        if not entregador:
            break
        pedido.entregador_id = entregador.id
        db.flush()
        vinculados += 1
        preferido_disponivel = None

    if vinculados:
        db.commit()

    return vinculados


def _montar_links_rastreamento(
    restaurante: Restaurante,
    pedido: Pedido,
    token_rastreamento: str,
    frontend_base_url: str,
    api_base_url: str,
) -> tuple[str, str]:
    frontend_base = _normalizar_base_url(frontend_base_url)
    api_base = _normalizar_base_url(api_base_url)

    if not frontend_base and api_base:
        frontend_base = _converter_base_api_para_frontend(api_base) or api_base

    api_param = quote(api_base, safe="") if api_base else ""
    query_api = f"&api={api_param}" if api_param else ""
    link_entregador = (
        f"{frontend_base}/entregador.html"
        f"?slug={restaurante.slug}&pedido={pedido.id}&token={token_rastreamento}{query_api}"
    )
    link_cliente_frontend = (
        f"{frontend_base}/rastreio_entrega.html"
        f"?slug={restaurante.slug}&pedido={pedido.id}{query_api}"
    )
    link_cliente = (
        f"{api_base}/rastreio/{restaurante.slug}/{pedido.id}{f'?api={api_param}' if api_param else ''}"
        if api_base
        else link_cliente_frontend
    )

    if not frontend_base:
        link_entregador = f"entregador.html?slug={restaurante.slug}&pedido={pedido.id}&token={token_rastreamento}{query_api}"
        if not link_cliente:
            link_cliente = f"rastreio_entrega.html?slug={restaurante.slug}&pedido={pedido.id}{query_api}"

    return link_entregador, link_cliente


def _enviar_mensagens_despacho_delivery(
    restaurante: Restaurante,
    pedido: Pedido,
    entregador: Entregador,
    link_entregador: str,
    link_cliente: str,
) -> dict:
    if not restaurante.whatsapp_api_ativo:
        return {
            "cliente": {"enviado": False, "motivo": "aguardando_aceite_motoboy"},
            "motoboy": {"enviado": False, "motivo": "whatsapp_desativado"},
        }

    phone_number_id = (restaurante.whatsapp_phone_number_id or "").strip()
    access_token = (restaurante.whatsapp_access_token or "").strip()
    if not phone_number_id or not access_token:
        return {
            "cliente": {"enviado": False, "motivo": "aguardando_aceite_motoboy"},
            "motoboy": {"enviado": False, "motivo": "configuracao_incompleta"},
        }

    nome_restaurante = (restaurante.nome_unidade or "Restaurante").strip()
    nome_cliente = (pedido.cliente_nome or "Cliente").strip() or "Cliente"
    endereco_texto = _formatar_endereco_texto(pedido.endereco_entrega_json or {}) or "Endereço não informado"

    telefone_motoboy = normalizar_telefone_whatsapp(entregador.whatsapp)

    mensagem_motoboy = (
        f"Nova corrida #{pedido.id} - {nome_restaurante}.\n"
        f"Cliente: {nome_cliente}\n"
        f"Endereço: {endereco_texto}\n"
        f"Iniciar rastreio: {link_entregador}"
    )

    retorno_cliente = {"enviado": False, "motivo": "aguardando_aceite_motoboy"}
    retorno_motoboy = {"enviado": False, "motivo": "motoboy_sem_whatsapp_cadastrado"}

    if telefone_motoboy:
        envio_motoboy = enviar_whatsapp_cloud_message(
            phone_number_id=phone_number_id,
            access_token=access_token,
            telefone_destino=telefone_motoboy,
            mensagem=mensagem_motoboy,
        )
        retorno_motoboy = {
            "enviado": bool(envio_motoboy.get("ok")),
            "telefone": telefone_motoboy,
            "erro": envio_motoboy.get("erro"),
            "detalhes": envio_motoboy.get("detalhes"),
        }

    return {"cliente": retorno_cliente, "motoboy": retorno_motoboy}


def _enviar_link_cliente_apos_aceite_entregador(
    restaurante: Restaurante,
    pedido: Pedido,
    link_cliente: str,
) -> dict:
    if not restaurante.whatsapp_api_ativo:
        return {"enviado": False, "motivo": "whatsapp_desativado"}

    phone_number_id = (restaurante.whatsapp_phone_number_id or "").strip()
    access_token = (restaurante.whatsapp_access_token or "").strip()
    if not phone_number_id or not access_token:
        return {"enviado": False, "motivo": "configuracao_incompleta"}

    telefone_cliente = normalizar_telefone_whatsapp(pedido.cliente_telefone)
    if not telefone_cliente:
        return {"enviado": False, "motivo": "cliente_sem_whatsapp"}

    nome_restaurante = (restaurante.nome_unidade or "Restaurante").strip()
    nome_cliente = (pedido.cliente_nome or "Cliente").strip() or "Cliente"
    mensagem_cliente = (
        f"Olá, {nome_cliente}!\n"
        f"Seu pedido #{pedido.id} do {nome_restaurante} foi aceito pelo entregador e saiu para entrega.\n"
        f"Toque para rastrear em tempo real:\n{link_cliente}"
    )

    envio_cliente = enviar_whatsapp_cloud_message(
        phone_number_id=phone_number_id,
        access_token=access_token,
        telefone_destino=telefone_cliente,
        mensagem=mensagem_cliente,
    )

    return {
        "enviado": bool(envio_cliente.get("ok")),
        "telefone": telefone_cliente,
        "erro": envio_cliente.get("erro"),
        "detalhes": envio_cliente.get("detalhes"),
    }


def push_habilitado() -> bool:
    return bool(_obter_webpush_fn() and PUSH_VAPID_PUBLIC_KEY and PUSH_VAPID_PRIVATE_KEY)


def _obter_webpush_fn():
    try:
        modulo = importlib.import_module("pywebpush")
        return getattr(modulo, "webpush", None)
    except Exception:
        return None


def _normalizar_subscriptions_push(valor) -> list[dict]:
    if isinstance(valor, list):
        return [item for item in valor if isinstance(item, dict)]
    if isinstance(valor, str) and valor.strip():
        try:
            data = json.loads(valor)
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        except json.JSONDecodeError:
            return []
    return []


def _enviar_push_entregador(
    pedido: Pedido,
    entregador: Entregador,
    link_entregador: str,
    nome_restaurante: str,
) -> dict:
    webpush_fn = _obter_webpush_fn()
    if not push_habilitado():
        return {"enviado": False, "motivo": "push_desativado", "inscricoes": 0}

    subscriptions = _normalizar_subscriptions_push(entregador.push_subscriptions_json)
    if not subscriptions:
        return {"enviado": False, "motivo": "sem_inscricao", "inscricoes": 0}

    payload = json.dumps({
        "title": "Entrega",
        "body": f"Pedido #{pedido.id} do {nome_restaurante} disponível para entrega.",
        "tag": f"entrega-{pedido.id}",
        "url": link_entregador,
        "pedido_id": pedido.id,
    }, ensure_ascii=False)

    enviados = 0
    expirados: set[str] = set()

    for sub in subscriptions:
        endpoint = str(sub.get("endpoint") or "").strip()
        if not endpoint:
            continue
        try:
            webpush_fn(
                subscription_info=sub,
                data=payload,
                vapid_private_key=PUSH_VAPID_PRIVATE_KEY,
                vapid_claims={"sub": PUSH_VAPID_CLAIMS_SUB},
                ttl=90,
            )
            enviados += 1
        except Exception as erro:
            texto = str(erro)
            if "410" in texto or "404" in texto:
                expirados.add(endpoint)

    if expirados:
        entregador.push_subscriptions_json = [
            item for item in subscriptions
            if str(item.get("endpoint") or "").strip() not in expirados
        ]

    return {
        "enviado": enviados > 0,
        "quantidade_enviada": enviados,
        "inscricoes": len(subscriptions),
    }


def slugify_nome(texto: str) -> str:
    base = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-zA-Z0-9\s-]", "", base).strip().lower()
    base = re.sub(r"[\s_-]+", "-", base)
    return base.strip("-")[:60]


def gerar_slug_unico(db: Session, base_slug: str) -> str:
    slug = base_slug or "restaurante"
    tentativas = 1
    while db.query(Restaurante).filter(Restaurante.slug == slug).first():
        tentativas += 1
        slug = f"{base_slug}-{tentativas}"
    return slug


def inferir_plano_por_valor(valor: Decimal | float | int | None) -> str:
    try:
        valor_decimal = Decimal(str(valor or 0))
    except Exception:
        valor_decimal = Decimal("0")

    if valor_decimal >= PLANOS_SAAS_VALOR["enterprise"]:
        return "enterprise"
    if valor_decimal >= PLANOS_SAAS_VALOR["pro"]:
        return "pro"
    return "basic"


def obter_categorias_restaurante(restaurante: Restaurante) -> list[str]:
    categorias = restaurante.categorias_json or []
    if isinstance(categorias, str):
        try:
            categorias = json.loads(categorias)
        except json.JSONDecodeError:
            categorias = []
    return [c for c in categorias if isinstance(c, str) and c.strip()]


def obter_horarios_categoria(restaurante: Restaurante) -> dict:
    horarios = restaurante.categoria_horarios_json or {}
    if isinstance(horarios, str):
        try:
            horarios = json.loads(horarios)
        except json.JSONDecodeError:
            horarios = {}
    return horarios if isinstance(horarios, dict) else {}


def esta_disponivel_por_horario(horario_inicio: str, horario_fim: str) -> bool:
    if not horario_inicio or not horario_fim:
        return True

    agora = datetime.now().strftime("%H:%M")
    if horario_inicio <= horario_fim:
        return horario_inicio <= agora <= horario_fim
    return agora >= horario_inicio or agora <= horario_fim


def garantir_isolamento(slug: str, token_acesso: str, db: Session) -> Restaurante:
    restaurante_token = get_restaurante_por_token(db, token_acesso)
    slug_normalizado = (slug or "").strip().lower()

    if not slug_normalizado:
        return restaurante_token

    restaurante_slug = db.query(Restaurante).filter(Restaurante.slug == slug_normalizado).first()
    if not restaurante_slug:
        return restaurante_token

    if restaurante_slug.restaurante_id != restaurante_token.restaurante_id:
        # Quando o frontend estiver com slug antigo no cache, prioriza o token válido.
        return restaurante_token

    return restaurante_slug


def montar_admin_login_url(
    base_url: str | None,
    email_admin: str | None = None,
    slug: str | None = None,
) -> str | None:
    base = (base_url or "").rstrip("/")
    if not base:
        return None

    query_parts: list[str] = []
    email = (email_admin or "").strip().lower()
    if email:
        query_parts.append(f"email={quote(email)}")

    slug_normalizado = (slug or "").strip().lower()
    if slug_normalizado:
        query_parts.append(f"slug={quote(slug_normalizado)}")

    if query_parts:
        return f"{base}/admin.html?{'&'.join(query_parts)}"
    return f"{base}/admin.html"


def serializar_restaurante_out(restaurante: Restaurante, base_url: str | None = None) -> dict:
    base = (base_url or "").rstrip("/")
    admin_url = montar_admin_login_url(base, restaurante.email_admin, restaurante.slug)
    cardapio_url = f"{base}/index.html?slug={quote(restaurante.slug)}" if base else None
    return {
        "id": restaurante.id,
        "restaurante_id": restaurante.restaurante_id,
        "nome_unidade": restaurante.nome_unidade,
        "slug": restaurante.slug,
        "email_admin": restaurante.email_admin,
        "status_assinatura": restaurante.status_assinatura,
        "data_assinatura": restaurante.data_assinatura,
        "validade_assinatura": restaurante.validade_assinatura,
        "token_acesso": restaurante.token_acesso,
        "valor_mensalidade": restaurante.valor_mensalidade,
        "plano": (restaurante.plano or "basic").strip() or "basic",
        "foto_perfil_base64": restaurante.foto_perfil_base64,
        "admin_url": admin_url,
        "cardapio_url": cardapio_url,
    }


def _resolver_links_legais_por_admin_url(admin_url: str) -> tuple[str, str]:
    termos_env = (os.getenv("TERMS_URL") or "").strip()
    privacidade_env = (os.getenv("PRIVACY_URL") or "").strip()
    if termos_env and privacidade_env:
        return termos_env, privacidade_env

    origem = ""
    try:
        parsed = urlparse(admin_url or "")
        if parsed.scheme and parsed.netloc:
            origem = f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        origem = ""

    termos = termos_env or (f"{origem}/termos.html" if origem else "")
    privacidade = privacidade_env or (f"{origem}/privacidade.html" if origem else "")
    return termos, privacidade


def obter_config_smtp(db: Session | None = None) -> dict:
    """Retorna configuração SMTP unificada (DB sobrepõe ENV)."""
    host = (os.getenv("SMTP_HOST") or "").strip()
    porta = int((os.getenv("SMTP_PORT") or "587").strip() or "587")
    usuario = (os.getenv("SMTP_USER") or SUPER_ADMIN_LOGIN_DEFAULT or "").strip()
    senha = (os.getenv("SMTP_PASS") or "").strip()
    remetente = (os.getenv("SMTP_FROM") or usuario or SUPER_ADMIN_LOGIN_DEFAULT or "").strip()
    usar_ssl = (os.getenv("SMTP_SSL") or "").strip().lower() in {"1", "true", "yes", "sim"}
    usar_tls = (os.getenv("SMTP_TLS") or "1").strip().lower() in {"1", "true", "yes", "sim"}

    if db is not None:
        cfg_host = db.get(ConfigSistema, "smtp_host")
        cfg_port = db.get(ConfigSistema, "smtp_port")
        cfg_user = db.get(ConfigSistema, "smtp_user")
        cfg_pass = db.get(ConfigSistema, "smtp_pass")
        cfg_from = db.get(ConfigSistema, "smtp_from")
        cfg_tls = db.get(ConfigSistema, "smtp_tls")
        cfg_ssl = db.get(ConfigSistema, "smtp_ssl")

        if cfg_host and (cfg_host.valor or "").strip():
            host = cfg_host.valor.strip()
        if cfg_port and (cfg_port.valor or "").strip().isdigit():
            porta = int(cfg_port.valor.strip())
        if cfg_user and (cfg_user.valor or "").strip():
            usuario = cfg_user.valor.strip()
        if cfg_pass and (cfg_pass.valor or "").strip():
            senha = cfg_pass.valor.strip()
        if cfg_from and (cfg_from.valor or "").strip():
            remetente = cfg_from.valor.strip()
        if cfg_tls and (cfg_tls.valor or "").strip():
            usar_tls = (cfg_tls.valor or "").strip().lower() in {"1", "true", "yes", "sim"}
        if cfg_ssl and (cfg_ssl.valor or "").strip():
            usar_ssl = (cfg_ssl.valor or "").strip().lower() in {"1", "true", "yes", "sim"}

    if not remetente:
        remetente = usuario

    auth_ok = bool(senha) if usuario else True

    return {
        "host": host,
        "port": porta,
        "user": usuario,
        "password": senha,
        "from": remetente,
        "ssl": usar_ssl,
        "tls": usar_tls,
        "configured": bool(host and remetente and auth_ok),
    }


def enviar_email_acesso_restaurante(
    destinatario: str,
    nome_unidade: str,
    admin_url: str,
    cardapio_url: str,
    email_admin: str | None = None,
    senha_inicial: str | None = None,
    db: Session | None = None,
) -> dict:
    """Envia e-mail com links de acesso do cliente SaaS.

    Se SMTP não estiver configurado, retorna sem erro fatal.
    """
    smtp = obter_config_smtp(db)
    host = smtp["host"]
    porta = smtp["port"]
    usuario = smtp["user"]
    senha = smtp["password"]
    remetente = smtp["from"]
    usar_ssl = smtp["ssl"]
    usar_tls = smtp["tls"]

    if not host or not remetente or not destinatario:
        return {
            "ok": False,
            "enviado": False,
            "detail": "SMTP não configurado",
        }

    msg = EmailMessage()
    msg["Subject"] = f"Seu FoodOS esta pronto! Acesse seu Painel e Cardapio - {nome_unidade}"
    msg["From"] = remetente
    msg["To"] = destinatario

    email_login = (email_admin or destinatario or "").strip().lower()
    senha_texto = (senha_inicial or "").strip()
    termos_url, privacidade_url = _resolver_links_legais_por_admin_url(admin_url)
    termos_bloco = f"\nTermos de Uso: {termos_url}" if termos_url else ""
    privacidade_bloco = f"\nPolitica de Privacidade: {privacidade_url}" if privacidade_url else ""

    texto = (
        f"Ola! Seu restaurante agora e digital.\n\n"
        f"Seu FoodOS da unidade {nome_unidade} foi ativado com sucesso.\n\n"
        f"Painel Admin (privado):\n{admin_url}\n\n"
        f"Cardapio Publico:\n{cardapio_url}\n\n"
        f"Dados de acesso:\n"
        f"Login: {email_login}\n"
        f"Senha inicial: {senha_texto or 'A senha definida no momento da compra'}\n\n"
        f"Dica: altere sua senha no primeiro acesso."
        f"{termos_bloco}"
        f"{privacidade_bloco}"
    )

    html = f"""
    <html>
            <body style=\"margin:0;padding:0;background:#f3f6ff;font-family:Segoe UI,Arial,Helvetica,sans-serif;color:#0f172a;\">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f6ff;padding:24px 0;">
                    <tr>
                        <td align="center">
                            <table role="presentation" width="640" cellspacing="0" cellpadding="0" style="max-width:640px;background:#0b1220;border-radius:18px;overflow:hidden;border:1px solid #1f2a44;">
                                <tr>
                                    <td style="padding:26px 28px;background:linear-gradient(135deg,#4f46e5,#c026d3);color:#fff;">
                                        <div style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;opacity:.92;">FoodOS</div>
                                        <h1 style="margin:8px 0 6px;font-size:24px;line-height:1.2;">Seu restaurante agora e digital</h1>
                                        <p style="margin:0;font-size:14px;opacity:.96;">{nome_unidade} foi ativado com sucesso.</p>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding:24px 28px;background:#ffffff;">
                                        <p style="margin:0 0 14px;color:#334155;font-size:15px;">Seu pagamento foi confirmado e seus acessos ja estao prontos.</p>

                                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:14px 0 20px;">
                                            <tr>
                                                <td style="padding-bottom:10px;">
                                                    <a href="{admin_url}" style="display:inline-block;padding:12px 16px;border-radius:10px;background:#4f46e5;color:#fff;text-decoration:none;font-weight:700;">Abrir Painel Admin (Privado)</a>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td>
                                                    <a href="{cardapio_url}" style="display:inline-block;padding:12px 16px;border-radius:10px;background:#0f172a;color:#fff;text-decoration:none;font-weight:700;">Abrir Cardapio Publico</a>
                                                </td>
                                            </tr>
                                        </table>

                                        <div style="padding:14px;border:1px solid #dbe3ff;border-radius:12px;background:#f8faff;">
                                            <div style="font-size:13px;color:#475569;margin-bottom:6px;">Dados de acesso</div>
                                            <div style="font-size:14px;color:#0f172a;"><strong>Login:</strong> {email_login}</div>
                                            <div style="font-size:14px;color:#0f172a;"><strong>Senha inicial:</strong> {senha_texto or 'A senha definida no momento da compra'}</div>
                                        </div>

                                        <p style="margin:14px 0 0;font-size:13px;color:#64748b;">Dica de seguranca: altere sua senha no primeiro acesso.</p>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding:16px 28px;background:#f8fafc;border-top:1px solid #e2e8f0;">
                                        <div style="font-size:12px;color:#64748b;line-height:1.6;">
                                            Este e-mail contem links de acesso da sua conta.
                                            {f'<br><a href="{termos_url}" style="color:#334155;">Termos de Uso</a>' if termos_url else ''}
                                            {f' | <a href="{privacidade_url}" style="color:#334155;">Politica de Privacidade</a>' if privacidade_url else ''}
                                        </div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
      </body>
    </html>
    """

    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")

    try:
        if usar_ssl:
            with smtplib.SMTP_SSL(host, porta, timeout=20) as server:
                if usuario and senha:
                    server.login(usuario, senha)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, porta, timeout=20) as server:
                server.ehlo()
                if usar_tls:
                    server.starttls()
                    server.ehlo()
                if usuario and senha:
                    server.login(usuario, senha)
                server.send_message(msg)
        return {"ok": True, "enviado": True}
    except Exception as exc:
        return {
            "ok": False,
            "enviado": False,
            "detail": str(exc),
        }


def enviar_email_reset_senha_admin(
    destinatario: str,
    nome_unidade: str,
    reset_url: str,
    db: Session | None = None,
) -> dict:
    smtp = obter_config_smtp(db)
    host = smtp["host"]
    porta = smtp["port"]
    usuario = smtp["user"]
    senha = smtp["password"]
    remetente = smtp["from"]
    usar_ssl = smtp["ssl"]
    usar_tls = smtp["tls"]

    if not host or not remetente or not destinatario:
        return {"ok": False, "enviado": False, "detail": "SMTP não configurado"}

    msg = EmailMessage()
    msg["Subject"] = f"Recuperação de senha - {nome_unidade}"
    msg["From"] = remetente
    msg["To"] = destinatario

    texto = (
        f"Olá!\n\n"
        f"Recebemos uma solicitação para redefinir sua senha do painel admin.\n\n"
        f"Abra este link e defina uma nova senha:\n{reset_url}\n\n"
        f"Este link expira em 30 minutos.\n"
        f"Se você não solicitou, ignore este e-mail."
    )

    html = f"""
    <html>
      <body style=\"font-family:Arial,Helvetica,sans-serif;color:#0f172a;line-height:1.6\">
        <h2 style=\"margin:0 0 12px\">Recuperação de senha</h2>
        <p style=\"margin:0 0 12px\">Foi solicitada a troca de senha do painel admin do restaurante <strong>{nome_unidade}</strong>.</p>
        <p style=\"margin:0 0 12px\"><a href=\"{reset_url}\">Clique aqui para redefinir sua senha</a></p>
        <p style=\"margin:0 0 12px;color:#475569;\">Este link expira em 30 minutos.</p>
        <p style=\"color:#64748b;\">Se você não solicitou, ignore este e-mail.</p>
      </body>
    </html>
    """

    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")

    try:
        if usar_ssl:
            with smtplib.SMTP_SSL(host, porta, timeout=20) as server:
                if usuario and senha:
                    server.login(usuario, senha)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, porta, timeout=20) as server:
                server.ehlo()
                if usar_tls:
                    server.starttls()
                    server.ehlo()
                if usuario and senha:
                    server.login(usuario, senha)
                server.send_message(msg)
        return {"ok": True, "enviado": True}
    except Exception as exc:
        return {"ok": False, "enviado": False, "detail": str(exc)}


def obter_mp_sdk(db: Session) -> mercadopago.SDK:
    """Retorna SDK do Mercado Pago usando token salvo no DB ou o default."""
    cfg_token = db.get(ConfigSistema, "mp_access_token")
    token = (cfg_token.valor.strip() if cfg_token and cfg_token.valor.strip() else MP_ACCESS_TOKEN_DEFAULT)
    return mercadopago.SDK(token)


def obter_mp_public_key(db: Session) -> str:
    cfg = db.get(ConfigSistema, "mp_public_key")
    return (cfg.valor.strip() if cfg and cfg.valor.strip() else MP_PUBLIC_KEY_DEFAULT)


def remover_restaurantes_fake(db: Session) -> int:
    candidatos = db.query(Restaurante).filter(Restaurante.slug == DEMO_RESTAURANTE_SLUG).all()
    removidos = 0

    for restaurante in candidatos:
        # Remove apenas o seed demo para manter dados reais intactos.
        if (restaurante.nome_unidade or "").strip().lower() != (DEMO_RESTAURANTE_NOME or "").strip().lower():
            continue
        db.query(Cardapio).filter(Cardapio.restaurante_id == restaurante.restaurante_id).delete(synchronize_session=False)
        db.query(Pedido).filter(Pedido.restaurante_id == restaurante.restaurante_id).delete(synchronize_session=False)
        db.query(Entregador).filter(Entregador.restaurante_id == restaurante.restaurante_id).delete(synchronize_session=False)
        db.delete(restaurante)
        removidos += 1

    if removidos > 0:
        db.commit()
    return removidos


def garantir_credenciais_super_admin(db: Session) -> None:
    valores_padrao = {
        "sa_nome_exibicao": SUPER_ADMIN_NOME_DEFAULT,
        "sa_email_login": SUPER_ADMIN_LOGIN_DEFAULT,
        "sa_senha": SUPER_ADMIN_SENHA_DEFAULT,
    }

    alterado = False
    for chave, valor in valores_padrao.items():
        obj = db.get(ConfigSistema, chave)
        atual = (obj.valor or "").strip() if obj else ""
        if obj and atual:
            continue
        if obj:
            obj.valor = valor
        else:
            db.add(ConfigSistema(chave=chave, valor=valor))
        alterado = True

    if alterado:
        db.commit()


def obter_credenciais_super_admin(db: Session) -> dict:
    nome_cfg = db.get(ConfigSistema, "sa_nome_exibicao")
    email_cfg = db.get(ConfigSistema, "sa_email_login")
    senha_cfg = db.get(ConfigSistema, "sa_senha")

    nome = (nome_cfg.valor or "").strip() if nome_cfg else ""
    email = (email_cfg.valor or "").strip().lower() if email_cfg else ""
    senha = (senha_cfg.valor or "").strip() if senha_cfg else ""

    return {
        "nome_exibicao": nome or SUPER_ADMIN_NOME_DEFAULT,
        "email_login": email or SUPER_ADMIN_LOGIN_DEFAULT,
        "senha": senha or SUPER_ADMIN_SENHA_DEFAULT,
    }


def garantir_token_acesso_restaurante(restaurante: Restaurante, db: Session) -> Restaurante:
    token_atual = (restaurante.token_acesso or "").strip()
    if token_atual:
        return restaurante

    novo_token = ""
    while not novo_token:
        candidato = secrets.token_urlsafe(32)
        existe = db.query(Restaurante).filter(Restaurante.token_acesso == candidato).first()
        if not existe:
            novo_token = candidato

    restaurante.token_acesso = novo_token
    db.commit()
    db.refresh(restaurante)
    return restaurante


def garantir_restaurante_admin_padrao(db: Session) -> Restaurante:
    email = (SUPER_ADMIN_LOGIN_DEFAULT or "").strip().lower()
    senha = (SUPER_ADMIN_SENHA_DEFAULT or "").strip()
    if not email or not senha:
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")

    restaurante = db.query(Restaurante).filter(Restaurante.email_admin == email).first()
    if restaurante:
        alterado = False
        if (restaurante.senha_hash or "") != senha:
            restaurante.senha_hash = senha
            alterado = True
        if (restaurante.status_assinatura or "") != "Ativo":
            restaurante.status_assinatura = "Ativo"
            alterado = True
        if not restaurante.validade_assinatura or restaurante.validade_assinatura < date.today():
            restaurante.validade_assinatura = date.today() + timedelta(days=3650)
            alterado = True
        if not (restaurante.token_acesso or "").strip():
            restaurante.token_acesso = secrets.token_urlsafe(32)
            alterado = True
        if obter_plan_type_restaurante(restaurante) != "premium":
            restaurante.plan_type = "premium"
            restaurante.plano = "enterprise"
            alterado = True
        if alterado:
            db.commit()
            db.refresh(restaurante)
        return restaurante

    slug_base = "foodos-walter"
    slug = slug_base
    sufixo = 1
    while db.query(Restaurante).filter(Restaurante.slug == slug).first():
        sufixo += 1
        slug = f"{slug_base}-{sufixo}"

    novo = Restaurante(
        restaurante_id=str(uuid.uuid4()),
        nome_unidade="FoodOS Walter",
        slug=slug,
        email_admin=email,
        senha_hash=senha,
        status_assinatura="Ativo",
        data_assinatura=date.today(),
        validade_assinatura=date.today() + timedelta(days=3650),
        token_acesso=secrets.token_urlsafe(24),
        valor_mensalidade=Decimal("0.00"),
        plan_type="premium",
        plano="enterprise",
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


def garantir_restaurante_slug_padrao(db: Session) -> Restaurante:
    slug_alvo = (DEFAULT_RESTAURANTE_SLUG or "solar").strip().lower()
    if not slug_alvo:
        slug_alvo = "solar"

    restaurante = db.query(Restaurante).filter(Restaurante.slug == slug_alvo).first()
    if restaurante:
        alterado = False
        plan_type_alvo = normalizar_plan_type(DEFAULT_RESTAURANTE_PLAN_TYPE, "pro")
        if not (restaurante.token_acesso or "").strip():
            restaurante.token_acesso = secrets.token_urlsafe(24)
            alterado = True
        if (restaurante.nome_unidade or "").strip() != "Solar Supermercado":
            restaurante.nome_unidade = "Solar Supermercado"
            alterado = True
        if (restaurante.status_assinatura or "") != "Ativo":
            restaurante.status_assinatura = "Ativo"
            alterado = True
        if not restaurante.validade_assinatura or restaurante.validade_assinatura < date.today():
            restaurante.validade_assinatura = date.today() + timedelta(days=3650)
            alterado = True
        if (getattr(restaurante, "plano", "") or "").strip().lower() != "pro":
            restaurante.plano = "pro"
            alterado = True
        if obter_plan_type_restaurante(restaurante) != plan_type_alvo:
            restaurante.plan_type = plan_type_alvo
            alterado = True
        if not restaurante.delivery_ativo:
            restaurante.delivery_ativo = True
            alterado = True
        if alterado:
            db.commit()
            db.refresh(restaurante)
        return restaurante

    email_base = (DEFAULT_RESTAURANTE_EMAIL or f"{slug_alvo}@restaurante.local").strip().lower()
    email = email_base
    sufixo_email = 1
    while db.query(Restaurante).filter(Restaurante.email_admin == email).first():
        sufixo_email += 1
        if "@" in email_base:
            local, dominio = email_base.split("@", 1)
            email = f"{local}+{sufixo_email}@{dominio}"
        else:
            email = f"{email_base}+{sufixo_email}@restaurante.local"

    novo = Restaurante(
        restaurante_id=str(uuid.uuid4()),
        nome_unidade="Solar Supermercado",
        slug=slug_alvo,
        email_admin=email,
        senha_hash=DEFAULT_RESTAURANTE_SENHA or "solar1234",
        status_assinatura="Ativo",
        data_assinatura=date.today(),
        validade_assinatura=date.today() + timedelta(days=3650),
        token_acesso=secrets.token_urlsafe(24),
        valor_mensalidade=Decimal("0.00"),
        plano="pro",
        plan_type=normalizar_plan_type(DEFAULT_RESTAURANTE_PLAN_TYPE, "pro"),
        delivery_ativo=True,
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


def garantir_usuario_admin_restaurante(db: Session, restaurante: Restaurante) -> Usuario:
    email = (restaurante.email_admin or "").strip().lower()
    if not email:
        raise ValueError("Restaurante padrão sem email_admin para criar usuário admin")

    usuario = db.query(Usuario).filter(
        Usuario.restaurante_id == restaurante.restaurante_id,
        Usuario.email == email,
    ).first()

    if usuario:
        alterado = False
        if (usuario.perfil or "").strip().lower() != "admin":
            usuario.perfil = "admin"
            alterado = True
        if not usuario.ativo:
            usuario.ativo = True
            alterado = True
        if (usuario.senha_hash or "") != (restaurante.senha_hash or ""):
            usuario.senha_hash = restaurante.senha_hash or ""
            alterado = True
        if alterado:
            db.commit()
            db.refresh(usuario)
        return usuario

    novo_usuario = Usuario(
        restaurante_id=restaurante.restaurante_id,
        nome="Administrador Solar",
        email=email,
        senha_hash=restaurante.senha_hash or DEFAULT_RESTAURANTE_SENHA,
        perfil="admin",
        ativo=True,
    )
    db.add(novo_usuario)
    db.commit()
    db.refresh(novo_usuario)
    return novo_usuario


def garantir_config_smtp_padrao(db: Session) -> None:
    """Preenche config SMTP basica para Gmail quando ainda nao houver configuracao salva."""
    valores_padrao = {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": "587",
        "smtp_user": SUPER_ADMIN_LOGIN_DEFAULT,
        "smtp_from": SUPER_ADMIN_LOGIN_DEFAULT,
        "smtp_tls": "1",
        "smtp_ssl": "0",
    }

    alterado = False
    for chave, valor in valores_padrao.items():
        atual = db.get(ConfigSistema, chave)
        atual_valor = (atual.valor or "").strip() if atual else ""
        if atual and atual_valor:
            continue
        if atual:
            atual.valor = valor
        else:
            db.add(ConfigSistema(chave=chave, valor=valor))
        alterado = True

    if alterado:
        db.commit()


@app.on_event("startup")
def startup_event():
    garantir_schema_db()

    # Migração leve e idempotente para bancos já existentes (inclui Postgres).
    with engine.begin() as conn:
        inspector = inspect(conn)
        tabelas = set(inspector.get_table_names())

        if "cardapio" in tabelas:
            colunas_cardapio_global = {c["name"] for c in inspector.get_columns("cardapio")}
            if "imagem_base64" not in colunas_cardapio_global:
                conn.exec_driver_sql("ALTER TABLE cardapio ADD COLUMN imagem_base64 VARCHAR(1000000) DEFAULT ''")

        if "restaurantes" in tabelas:
            colunas_restaurantes_global = {c["name"] for c in inspector.get_columns("restaurantes")}
            if "plano" not in colunas_restaurantes_global:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN plano VARCHAR(30) DEFAULT 'basic'")
            if "plan_type" not in colunas_restaurantes_global:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN plan_type VARCHAR(20) DEFAULT 'basic'")

    if DATABASE_URL.startswith("sqlite"):
        with engine.begin() as conn:
            colunas = {
                row[1]
                for row in conn.exec_driver_sql("PRAGMA table_info(restaurantes)").fetchall()
            }
            if "cnpj" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN cnpj VARCHAR(30) DEFAULT ''")
            if "total_mesas" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN total_mesas INTEGER DEFAULT 10")
            if "delivery_ativo" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN delivery_ativo BOOLEAN DEFAULT 0")
            if "delivery_endereco_origem" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN delivery_endereco_origem VARCHAR(255) DEFAULT ''")
            if "delivery_bairro" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN delivery_bairro VARCHAR(120) DEFAULT ''")
            if "delivery_cidade" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN delivery_cidade VARCHAR(120) DEFAULT ''")
            if "delivery_uf" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN delivery_uf VARCHAR(2) DEFAULT ''")
            if "delivery_google_maps_api_key" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN delivery_google_maps_api_key VARCHAR(255) DEFAULT ''")
            if "delivery_whatsapp_entregador" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN delivery_whatsapp_entregador VARCHAR(30) DEFAULT ''")
            if "whatsapp_api_ativo" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN whatsapp_api_ativo BOOLEAN DEFAULT 0")
            if "whatsapp_phone_number_id" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN whatsapp_phone_number_id VARCHAR(80) DEFAULT ''")
            if "whatsapp_access_token" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN whatsapp_access_token VARCHAR(255) DEFAULT ''")
            if "whatsapp_verify_token" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN whatsapp_verify_token VARCHAR(120) DEFAULT ''")
            if "categorias_json" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN categorias_json JSON DEFAULT '[]'")
            if "categoria_horarios_json" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN categoria_horarios_json JSON DEFAULT '{}'")
            if "capa_cardapio_base64" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN capa_cardapio_base64 VARCHAR(1000000) DEFAULT ''")
            if "capa_posicao" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN capa_posicao VARCHAR(20) DEFAULT 'center'")
            if "logo_base64" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN logo_base64 VARCHAR(1000000) DEFAULT ''")
            if "tema_cor_primaria" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN tema_cor_primaria VARCHAR(20) DEFAULT '#3b82f6'")
            if "tema_cor_secundaria" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN tema_cor_secundaria VARCHAR(20) DEFAULT '#10b981'")
            if "tema_cor_destaque" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN tema_cor_destaque VARCHAR(20) DEFAULT '#1e293b'")
            if "estilo_botao" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN estilo_botao VARCHAR(20) DEFAULT 'rounded'")
            if "reset_senha_token" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN reset_senha_token VARCHAR(120)")
            if "reset_senha_expira_em" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN reset_senha_expira_em DATETIME")
            if "data_assinatura" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN data_assinatura DATE")
            if "validade_assinatura" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN validade_assinatura DATE")
            if "plano" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN plano VARCHAR(30) DEFAULT 'basic'")
            if "plan_type" not in colunas:
                conn.exec_driver_sql("ALTER TABLE restaurantes ADD COLUMN plan_type VARCHAR(20) DEFAULT 'basic'")

            conn.exec_driver_sql(
                """
                UPDATE restaurantes
                SET data_assinatura = COALESCE(data_assinatura, DATE(created_at), DATE('now'))
                """
            )
            conn.exec_driver_sql(
                """
                UPDATE restaurantes
                SET validade_assinatura = COALESCE(validade_assinatura, DATE('now', '+30 day'))
                """
            )
            conn.exec_driver_sql(
                """
                UPDATE restaurantes
                SET plano = COALESCE(NULLIF(plano, ''), 'basic')
                """
            )
            conn.exec_driver_sql(
                """
                UPDATE restaurantes
                SET plan_type = CASE
                    WHEN LOWER(COALESCE(NULLIF(plan_type, ''), '')) IN ('basic', 'standard', 'premium') THEN LOWER(plan_type)
                    WHEN LOWER(COALESCE(NULLIF(plano, ''), 'basic')) IN ('pro', 'standard') THEN 'standard'
                    WHEN LOWER(COALESCE(NULLIF(plano, ''), 'basic')) IN ('enterprise', 'premium') THEN 'premium'
                    ELSE 'basic'
                END
                """
            )

            colunas_cardapio = {
                row[1]
                for row in conn.exec_driver_sql("PRAGMA table_info(cardapio)").fetchall()
            }
            if "horario_inicio" not in colunas_cardapio:
                conn.exec_driver_sql("ALTER TABLE cardapio ADD COLUMN horario_inicio VARCHAR(5) DEFAULT ''")
            if "horario_fim" not in colunas_cardapio:
                conn.exec_driver_sql("ALTER TABLE cardapio ADD COLUMN horario_fim VARCHAR(5) DEFAULT ''")
            if "complementos_json" not in colunas_cardapio:
                conn.exec_driver_sql("ALTER TABLE cardapio ADD COLUMN complementos_json JSON DEFAULT '[]'")

            colunas_pedidos = {
                row[1]
                for row in conn.exec_driver_sql("PRAGMA table_info(pedidos)").fetchall()
            }
            if "tipo_entrega" not in colunas_pedidos:
                conn.exec_driver_sql("ALTER TABLE pedidos ADD COLUMN tipo_entrega VARCHAR(20) DEFAULT 'mesa'")
            if "cliente_nome" not in colunas_pedidos:
                conn.exec_driver_sql("ALTER TABLE pedidos ADD COLUMN cliente_nome VARCHAR(120) DEFAULT ''")
            if "cliente_telefone" not in colunas_pedidos:
                conn.exec_driver_sql("ALTER TABLE pedidos ADD COLUMN cliente_telefone VARCHAR(30) DEFAULT ''")
            if "endereco_entrega_json" not in colunas_pedidos:
                conn.exec_driver_sql("ALTER TABLE pedidos ADD COLUMN endereco_entrega_json JSON DEFAULT '{}'")
            if "forma_pagamento" not in colunas_pedidos:
                conn.exec_driver_sql("ALTER TABLE pedidos ADD COLUMN forma_pagamento VARCHAR(20) DEFAULT ''")
            if "entregador_id" not in colunas_pedidos:
                conn.exec_driver_sql("ALTER TABLE pedidos ADD COLUMN entregador_id INTEGER")
            if "lat_entregador" not in colunas_pedidos:
                conn.exec_driver_sql("ALTER TABLE pedidos ADD COLUMN lat_entregador FLOAT")
            if "long_entregador" not in colunas_pedidos:
                conn.exec_driver_sql("ALTER TABLE pedidos ADD COLUMN long_entregador FLOAT")

            colunas_entregadores = {
                row[1]
                for row in conn.exec_driver_sql("PRAGMA table_info(entregadores)").fetchall()
            }
            if "email_login" not in colunas_entregadores:
                conn.exec_driver_sql("ALTER TABLE entregadores ADD COLUMN email_login VARCHAR(120) DEFAULT ''")
            if "senha_hash" not in colunas_entregadores:
                conn.exec_driver_sql("ALTER TABLE entregadores ADD COLUMN senha_hash VARCHAR(255) DEFAULT ''")
            if "foto_perfil_base64" not in colunas_entregadores:
                conn.exec_driver_sql("ALTER TABLE entregadores ADD COLUMN foto_perfil_base64 VARCHAR(1000000) DEFAULT ''")
            if "push_subscriptions_json" not in colunas_entregadores:
                conn.exec_driver_sql("ALTER TABLE entregadores ADD COLUMN push_subscriptions_json JSON DEFAULT '[]'")

            # Tabela pagamentos_pendentes — colunas opcionais adicionadas em migração
            tabelas_existentes = {
                row[0]
                for row in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            if "pagamentos_pendentes" in tabelas_existentes:
                cols_pp = {
                    row[1]
                    for row in conn.exec_driver_sql("PRAGMA table_info(pagamentos_pendentes)").fetchall()
                }
                if "mp_preference_id" not in cols_pp:
                    conn.exec_driver_sql("ALTER TABLE pagamentos_pendentes ADD COLUMN mp_preference_id VARCHAR(120) DEFAULT ''")
                if "admin_url" not in cols_pp:
                    conn.exec_driver_sql("ALTER TABLE pagamentos_pendentes ADD COLUMN admin_url VARCHAR(500) DEFAULT ''")
                if "cardapio_url" not in cols_pp:
                    conn.exec_driver_sql("ALTER TABLE pagamentos_pendentes ADD COLUMN cardapio_url VARCHAR(500) DEFAULT ''")
                if "email_enviado" not in cols_pp:
                    conn.exec_driver_sql("ALTER TABLE pagamentos_pendentes ADD COLUMN email_enviado BOOLEAN DEFAULT 0")
                if "email_erro" not in cols_pp:
                    conn.exec_driver_sql("ALTER TABLE pagamentos_pendentes ADD COLUMN email_erro VARCHAR(500) DEFAULT ''")
                if "email_enviado_em" not in cols_pp:
                    conn.exec_driver_sql("ALTER TABLE pagamentos_pendentes ADD COLUMN email_enviado_em DATETIME")
                if "email_tentativas" not in cols_pp:
                    conn.exec_driver_sql("ALTER TABLE pagamentos_pendentes ADD COLUMN email_tentativas INTEGER DEFAULT 0")
                if "email_ultima_tentativa_em" not in cols_pp:
                    conn.exec_driver_sql("ALTER TABLE pagamentos_pendentes ADD COLUMN email_ultima_tentativa_em DATETIME")

    db = SessionLocal()
    try:
        remover_restaurantes_fake(db)
        garantir_credenciais_super_admin(db)
        garantir_restaurante_admin_padrao(db)
        restaurante_solar = garantir_restaurante_slug_padrao(db)
        garantir_usuario_admin_restaurante(db, restaurante_solar)
        garantir_config_smtp_padrao(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {
        "ok": True,
        "db_backend": "sqlite" if DATABASE_URL.startswith("sqlite") else "postgres",
    }


@app.get("/api/public/push/config")
def obter_push_config_publica():
    return {
        "ok": True,
        "enabled": push_habilitado(),
        "vapid_public_key": PUSH_VAPID_PUBLIC_KEY if push_habilitado() else "",
    }


@app.get("/api/public/cardapio-principal")
def obter_cardapio_principal_publico(request: Request, db: Session = Depends(get_db)):
    restaurante = None

    email_principal = (SUPER_ADMIN_LOGIN_DEFAULT or "").strip().lower()
    if email_principal:
        restaurante = db.query(Restaurante).filter(Restaurante.email_admin == email_principal).first()

    if not restaurante and DEMO_RESTAURANTE_SLUG:
        restaurante = db.query(Restaurante).filter(Restaurante.slug == DEMO_RESTAURANTE_SLUG).first()

    if not restaurante:
        restaurante = db.query(Restaurante).filter(Restaurante.status_assinatura == "Ativo").order_by(Restaurante.id.asc()).first()

    if not restaurante:
        restaurante = db.query(Restaurante).order_by(Restaurante.id.asc()).first()

    if not restaurante:
        raise HTTPException(status_code=404, detail="Nenhum restaurante disponível")

    if not assinatura_ativa(restaurante):
        raise HTTPException(status_code=403, detail="Nenhum restaurante ativo disponível")

    base_url = str(request.base_url).rstrip("/")
    out = serializar_restaurante_out(restaurante, base_url)
    return {
        "ok": True,
        "slug": restaurante.slug,
        "nome_unidade": restaurante.nome_unidade,
        "cardapio_url": out.get("cardapio_url"),
        "admin_url": out.get("admin_url"),
    }


@app.get("/api/super-admin/dashboard")
def super_admin_dashboard(db: Session = Depends(get_db)):
    total_restaurantes = db.query(func.count(Restaurante.id)).scalar() or 0
    ativos = db.query(func.count(Restaurante.id)).filter(Restaurante.status_assinatura == "Ativo").scalar() or 0
    faturamento_total = db.query(func.coalesce(func.sum(Restaurante.valor_mensalidade), 0)).filter(
        Restaurante.status_assinatura == "Ativo"
    ).scalar()

    return {
        "total_restaurantes": int(total_restaurantes),
        "restaurantes_ativos": int(ativos),
        "receita_mensal_estimada": float(faturamento_total or 0),
    }


@app.get("/api/super-admin/credenciais")
def obter_credenciais_super_admin_api(db: Session = Depends(get_db)):
    cred = obter_credenciais_super_admin(db)
    return {
        "ok": True,
        "nome_exibicao": cred["nome_exibicao"],
        "email_login": cred["email_login"],
        "senha_configurada": bool((cred["senha"] or "").strip()),
    }


@app.post("/api/super-admin/credenciais")
def salvar_credenciais_super_admin_api(payload: SuperAdminCredenciaisUpdate, db: Session = Depends(get_db)):
    cred_atual = obter_credenciais_super_admin(db)
    nome = (payload.nome_exibicao or cred_atual["nome_exibicao"]).strip()
    email = (payload.email_login or cred_atual["email_login"]).strip().lower()
    senha = (payload.senha or "").strip() or cred_atual["senha"]

    updates = {
        "sa_nome_exibicao": nome or SUPER_ADMIN_NOME_DEFAULT,
        "sa_email_login": email or SUPER_ADMIN_LOGIN_DEFAULT,
        "sa_senha": senha or SUPER_ADMIN_SENHA_DEFAULT,
    }

    for chave, valor in updates.items():
        obj = db.get(ConfigSistema, chave)
        if obj:
            obj.valor = valor
        else:
            db.add(ConfigSistema(chave=chave, valor=valor))
    db.commit()

    return {
        "ok": True,
        "nome_exibicao": updates["sa_nome_exibicao"],
        "email_login": updates["sa_email_login"],
    }


@app.post("/api/super-admin/auth/login")
def autenticar_super_admin(payload: SuperAdminAuthPayload, db: Session = Depends(get_db)):
    cred = obter_credenciais_super_admin(db)
    email = (payload.email_login or "").strip().lower()
    senha = (payload.senha or "").strip()

    email_config = (cred["email_login"] or "").strip().lower()
    senha_config = (cred["senha"] or "").strip()
    email_master = (SUPER_ADMIN_LOGIN_DEFAULT or "").strip().lower()
    senha_master = (SUPER_ADMIN_SENHA_DEFAULT or "").strip()

    credencial_config_ok = email == email_config and senha == senha_config
    credencial_master_ok = email == email_master and senha == senha_master

    if not (credencial_config_ok or credencial_master_ok):
        raise HTTPException(status_code=401, detail="Login ou senha inválidos")

    return {
        "ok": True,
        "nome_exibicao": cred["nome_exibicao"],
        "email_login": cred["email_login"],
    }


@app.post("/api/super-admin/cadastrar-restaurante", response_model=RestauranteOut)
def cadastrar_restaurante(payload: RestauranteCreate, request: Request, db: Session = Depends(get_db)):
    slug_normalizado = payload.slug.strip().lower()

    existente = db.query(Restaurante).filter(
        (Restaurante.slug == slug_normalizado) | (Restaurante.email_admin == payload.email_admin)
    ).first()
    if existente:
        raise HTTPException(status_code=400, detail="Slug ou e-mail já cadastrado")

    token = (payload.token_acesso or "").strip()
    if token and db.query(Restaurante).filter(Restaurante.token_acesso == token).first():
        raise HTTPException(status_code=400, detail="Token de acesso já cadastrado")

    restaurante = Restaurante(
        restaurante_id=str(uuid.uuid4()),
        nome_unidade=payload.nome_unidade,
        slug=slug_normalizado,
        email_admin=payload.email_admin,
        senha_hash=payload.senha_inicial,
        status_assinatura=payload.status_assinatura,
        data_assinatura=date.today(),
        validade_assinatura=payload.validade_assinatura or (date.today() + timedelta(days=30)),
        token_acesso=token or secrets.token_urlsafe(32),
        valor_mensalidade=payload.valor_mensalidade,
        plano=(payload.plano or "basic").strip() or "basic",
    )
    db.add(restaurante)
    db.commit()
    db.refresh(restaurante)
    base_url = str(request.base_url).rstrip("/")
    out = serializar_restaurante_out(restaurante, base_url)

    # Envio de e-mail é auxiliar e não deve bloquear o cadastro.
    if out.get("admin_url") and out.get("cardapio_url") and restaurante.email_admin:
        enviar_email_acesso_restaurante(
            destinatario=restaurante.email_admin,
            nome_unidade=restaurante.nome_unidade,
            admin_url=out["admin_url"],
            cardapio_url=out["cardapio_url"],
            email_admin=restaurante.email_admin,
            senha_inicial=payload.senha_inicial,
            db=db,
        )

    return out


@app.get("/api/public/planos")
def listar_planos_publicos(db: Session = Depends(get_db)):
    planos_saas = obter_planos_saas_valores(db)
    return {
        "ok": True,
        "planos": [
            {
                "codigo": "basic",
                "nome": "Basic",
                "valor_mensalidade": float(planos_saas["basic"]),
                "descricao": "Cardápio digital + pedidos + painel admin",
            },
            {
                "codigo": "pro",
                "nome": "Pro",
                "valor_mensalidade": float(planos_saas["pro"]),
                "descricao": "Tudo do Basic + delivery e rastreio",
            },
            {
                "codigo": "enterprise",
                "nome": "Enterprise",
                "valor_mensalidade": float(planos_saas["enterprise"]),
                "descricao": "Tudo do Pro + suporte prioritário",
            },
        ],
        "features": {
            "basic": ["Cardápio digital", "Painel admin", "Pedidos (mesa e delivery)", "Pagamentos Mercado Pago"],
            "pro": ["Tudo do Basic", "Módulo de entregadores", "Rastreio em tempo real", "App do entregador (PWA)"],
            "enterprise": ["Tudo do Pro", "Suporte prioritário via WhatsApp do dono", "Atendimento VIP"],
        },
    }


@app.post("/api/admin/auth/login")
def login_admin(payload: AdminLoginPayload, request: Request, db: Session = Depends(get_db)):
    email = payload.email_admin.strip().lower()
    senha = (payload.senha or "").strip()

    restaurante = db.query(Restaurante).filter(Restaurante.email_admin == email).first()
    credencial_master_ok = (
        email == (SUPER_ADMIN_LOGIN_DEFAULT or "").strip().lower()
        and senha == (SUPER_ADMIN_SENHA_DEFAULT or "").strip()
    )

    if (not restaurante or senha != (restaurante.senha_hash or "")) and credencial_master_ok:
        restaurante = garantir_restaurante_admin_padrao(db)

    if not restaurante or senha != (restaurante.senha_hash or ""):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")

    if not assinatura_ativa(restaurante):
        if restaurante.validade_assinatura and date.today() > restaurante.validade_assinatura:
            bloquear_restaurante_por_validade_expirada(restaurante, db)
            raise HTTPException(status_code=403, detail="Assinatura expirada")
        raise HTTPException(status_code=403, detail="Assinatura inativa")

    restaurante = garantir_token_acesso_restaurante(restaurante, db)

    base_url = str(request.base_url).rstrip("/")
    return {
        "ok": True,
        "slug": restaurante.slug,
        "token_acesso": restaurante.token_acesso,
        "nome_unidade": restaurante.nome_unidade,
        "email_admin": restaurante.email_admin,
        "status_assinatura": restaurante.status_assinatura,
        "validade_assinatura": restaurante.validade_assinatura.isoformat() if restaurante.validade_assinatura else None,
        "admin_url": montar_admin_login_url(base_url, restaurante.email_admin, restaurante.slug),
        "cardapio_url": f"{base_url}/index.html?slug={quote(restaurante.slug)}",
    }


@app.post("/api/admin/auth/solicitar-reset-senha")
def solicitar_reset_senha_admin(
    payload: AdminPasswordResetRequestPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    email = payload.email_admin.strip().lower()
    restaurante = db.query(Restaurante).filter(Restaurante.email_admin == email).first()

    if restaurante:
        token = secrets.token_urlsafe(32)
        restaurante.reset_senha_token = token
        restaurante.reset_senha_expira_em = datetime.utcnow() + timedelta(minutes=30)
        db.commit()

        base_url = str(request.base_url).rstrip("/")
        reset_url = f"{base_url}/admin.html?email={quote(restaurante.email_admin)}&reset={quote(token)}"
        enviar_email_reset_senha_admin(
            destinatario=restaurante.email_admin,
            nome_unidade=restaurante.nome_unidade,
            reset_url=reset_url,
            db=db,
        )

    return {
        "ok": True,
        "detail": "Se o e-mail existir, enviamos um link de recuperação.",
    }


@app.post("/api/admin/auth/confirmar-reset-senha")
def confirmar_reset_senha_admin(
    payload: AdminPasswordResetConfirmPayload,
    db: Session = Depends(get_db),
):
    token = (payload.token_reset or "").strip()
    nova_senha = (payload.nova_senha or "").strip()

    restaurante = db.query(Restaurante).filter(Restaurante.reset_senha_token == token).first()
    if not restaurante:
        raise HTTPException(status_code=400, detail="Token de recuperação inválido")

    if not restaurante.reset_senha_expira_em or datetime.utcnow() > restaurante.reset_senha_expira_em:
        raise HTTPException(status_code=400, detail="Token de recuperação expirado")

    restaurante.senha_hash = nova_senha
    restaurante.reset_senha_token = None
    restaurante.reset_senha_expira_em = None
    db.commit()

    return {
        "ok": True,
        "detail": "Senha redefinida com sucesso",
    }


@app.post("/api/public/analytics-evento")
def registrar_evento_marketing(
    payload: MarketingEventoPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    evento = MarketingEvento(
        sessao_id=(payload.sessao_id or "").strip()[:80],
        evento=payload.evento.strip().lower()[:60],
        pagina=(payload.pagina or "").strip()[:120],
        plano=(payload.plano or "").strip()[:30],
        origem=(payload.origem or "").strip()[:80],
        sucesso=bool(payload.sucesso) if payload.sucesso is not None else False,
        detalhes_json=payload.detalhes if isinstance(payload.detalhes, dict) else {},
        user_agent=(request.headers.get("user-agent") or "")[:255],
        ip=(request.client.host if request.client else "")[:80],
    )
    db.add(evento)
    db.commit()
    return {"ok": True, "evento_id": evento.id}


@app.get("/api/super-admin/analytics/conversao")
def resumo_conversao_marketing(db: Session = Depends(get_db)):
    hoje = date.today()
    inicio_30_dias = hoje - timedelta(days=29)

    total_eventos = db.query(func.count(MarketingEvento.id)).scalar() or 0
    total_visitas = db.query(func.count(MarketingEvento.id)).filter(MarketingEvento.evento == "page_view").scalar() or 0
    total_click_assinar = db.query(func.count(MarketingEvento.id)).filter(MarketingEvento.evento == "cta_assinar").scalar() or 0
    total_envios = db.query(func.count(MarketingEvento.id)).filter(MarketingEvento.evento == "cadastro_submit").scalar() or 0
    total_sucessos = db.query(func.count(MarketingEvento.id)).filter(MarketingEvento.evento == "cadastro_sucesso").scalar() or 0

    visitas_hoje = db.query(func.count(MarketingEvento.id)).filter(
        MarketingEvento.evento == "page_view",
        func.date(MarketingEvento.created_at) == hoje,
    ).scalar() or 0

    sucessos_hoje = db.query(func.count(MarketingEvento.id)).filter(
        MarketingEvento.evento == "cadastro_sucesso",
        func.date(MarketingEvento.created_at) == hoje,
    ).scalar() or 0

    ultimos = db.query(MarketingEvento).order_by(MarketingEvento.created_at.desc()).limit(20).all()

    rows_serie = (
        db.query(
            func.date(MarketingEvento.created_at).label("dia"),
            MarketingEvento.evento,
            func.count(MarketingEvento.id).label("total"),
        )
        .filter(
            MarketingEvento.created_at >= datetime.combine(inicio_30_dias, datetime.min.time()),
            MarketingEvento.evento.in_(["page_view", "cadastro_sucesso"]),
        )
        .group_by(func.date(MarketingEvento.created_at), MarketingEvento.evento)
        .all()
    )

    serie_mapa = {}
    for linha in rows_serie:
        dia = str(linha.dia)
        if dia not in serie_mapa:
            serie_mapa[dia] = {"visitas": 0, "sucessos": 0}
        if linha.evento == "page_view":
            serie_mapa[dia]["visitas"] = int(linha.total or 0)
        elif linha.evento == "cadastro_sucesso":
            serie_mapa[dia]["sucessos"] = int(linha.total or 0)

    serie_diaria_30_dias = []
    for i in range(30):
        dia_obj = inicio_30_dias + timedelta(days=i)
        dia_iso = dia_obj.isoformat()
        visitas_dia = int((serie_mapa.get(dia_iso) or {}).get("visitas", 0))
        sucessos_dia = int((serie_mapa.get(dia_iso) or {}).get("sucessos", 0))
        taxa_dia = (float(sucessos_dia) / float(visitas_dia) * 100.0) if visitas_dia else 0.0
        serie_diaria_30_dias.append(
            {
                "data": dia_iso,
                "visitas": visitas_dia,
                "sucessos": sucessos_dia,
                "taxa_conversao_percentual": round(taxa_dia, 2),
            }
        )

    taxa_conversao = (float(total_sucessos) / float(total_visitas) * 100.0) if total_visitas else 0.0

    return {
        "ok": True,
        "resumo": {
            "total_eventos": int(total_eventos),
            "visitas": int(total_visitas),
            "click_assinar": int(total_click_assinar),
            "cadastros_enviados": int(total_envios),
            "cadastros_sucesso": int(total_sucessos),
            "taxa_conversao_percentual": round(taxa_conversao, 2),
            "visitas_hoje": int(visitas_hoje),
            "sucessos_hoje": int(sucessos_hoje),
        },
        "serie_diaria_30_dias": serie_diaria_30_dias,
        "ultimos_eventos": [
            {
                "id": e.id,
                "sessao_id": e.sessao_id,
                "evento": e.evento,
                "pagina": e.pagina,
                "plano": e.plano,
                "origem": e.origem,
                "sucesso": e.sucesso,
                "detalhes": e.detalhes_json or {},
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in ultimos
        ],
    }


@app.post("/api/public/cadastro-restaurante")
def cadastrar_restaurante_publico(
    payload: RestaurantePublicSignup,
    request: Request,
    db: Session = Depends(get_db),
):
    email_normalizado = payload.email_admin.strip().lower()
    if db.query(Restaurante).filter(Restaurante.email_admin == email_normalizado).first():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")

    base_slug = slugify_nome(payload.slug if payload.slug else payload.nome_unidade)
    if not base_slug:
        base_slug = "restaurante"
    slug_final = gerar_slug_unico(db, base_slug)

    whatsapp = ""
    if payload.telefone_admin:
        whatsapp = "".join(ch for ch in payload.telefone_admin if ch.isdigit())[:30]

    planos_saas = obter_planos_saas_valores(db)
    valor_mensalidade = planos_saas.get(payload.plano, planos_saas["basic"])

    restaurante = Restaurante(
        restaurante_id=str(uuid.uuid4()),
        nome_unidade=payload.nome_unidade.strip(),
        slug=slug_final,
        email_admin=email_normalizado,
        senha_hash=payload.senha_inicial,
        status_assinatura="Ativo",
        data_assinatura=date.today(),
        validade_assinatura=date.today() + timedelta(days=30),
        token_acesso=secrets.token_urlsafe(32),
        valor_mensalidade=valor_mensalidade,
        delivery_whatsapp_entregador=whatsapp,
        plano=(payload.plano or "basic").strip() or "basic",
    )
    db.add(restaurante)
    db.commit()
    db.refresh(restaurante)

    base_url = str(request.base_url).rstrip("/")
    restaurante_out = serializar_restaurante_out(restaurante, base_url)

    if restaurante_out.get("admin_url") and restaurante_out.get("cardapio_url") and restaurante.email_admin:
        enviar_email_acesso_restaurante(
            destinatario=restaurante.email_admin,
            nome_unidade=restaurante.nome_unidade,
            admin_url=restaurante_out["admin_url"],
            cardapio_url=restaurante_out["cardapio_url"],
            email_admin=restaurante.email_admin,
            senha_inicial=payload.senha_inicial,
            db=db,
        )

    return {
        "ok": True,
        "restaurante_id": restaurante.restaurante_id,
        "nome_unidade": restaurante.nome_unidade,
        "slug": restaurante.slug,
        "email_admin": restaurante.email_admin,
        "token_acesso": restaurante.token_acesso,
        "plano": payload.plano,
        "valor_mensalidade": float(restaurante.valor_mensalidade),
        "validade_assinatura": restaurante.validade_assinatura.isoformat(),
        "admin_url": restaurante_out["admin_url"],
        "cardapio_url": restaurante_out["cardapio_url"],
    }


# ─── Mercado Pago: Checkout Bricks ───────────────────────────────────────────

@app.post("/api/public/criar-preferencia-pagamento")
def criar_preferencia_pagamento(
    payload: CriarPreferenciaPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """Cria o registro pendente e retorna pending_id + valor_total + public_key.
    O pagamento em si é feito pelo Bricks via /processar-pagamento.
    """
    email_normalizado = payload.email_admin.strip().lower()
    if db.query(Restaurante).filter(Restaurante.email_admin == email_normalizado).first():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")

    planos_saas = obter_planos_saas_valores(db)
    valor_mensal = float(planos_saas.get(payload.plano, planos_saas["basic"]))
    PERIODOS = {
        "mensal":    {"meses": 1,  "desconto": 0.00, "label": "Mensal"},
        "semestral": {"meses": 6,  "desconto": 0.05, "label": "Semestral"},
        "anual":     {"meses": 12, "desconto": 0.20, "label": "Anual"},
    }
    cfg = PERIODOS.get(payload.periodo, PERIODOS["mensal"])
    meses = cfg["meses"]
    desconto = cfg["desconto"]
    valor_total = round(valor_mensal * meses * (1 - desconto), 2)
    nomes_plano = {"basic": "Basic", "pro": "Pro", "enterprise": "Enterprise"}
    nome_plano = nomes_plano.get(payload.plano, payload.plano.title())
    descricao_plano = f"Plano {nome_plano} {cfg['label']} ({meses}x) — CardápioOnline"

    pending_id = secrets.token_urlsafe(24)
    dados = payload.model_dump()
    dados["email_admin"] = email_normalizado
    dados["valor_total"] = valor_total
    dados["descricao_plano"] = descricao_plano

    db.add(PagamentoPendente(pending_id=pending_id, dados_json=dados, status="aguardando"))
    db.commit()

    return {
        "ok": True,
        "pending_id": pending_id,
        "valor_total": valor_total,
        "descricao_plano": descricao_plano,
        "public_key": obter_mp_public_key(db),
    }


@app.post("/api/public/processar-pagamento")
def processar_pagamento(
    payload: ProcessarPagamentoPayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """Recebe o formData do MP Payment Brick, cria o pagamento no MP e cria a conta se aprovado."""
    pendente = db.query(PagamentoPendente).filter(
        PagamentoPendente.pending_id == payload.pending_id
    ).first()
    if not pendente:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

    # Já aprovado (dupla submissão)
    if pendente.status == "aprovado":
        base_url = str(request.base_url).rstrip("/")
        _tentar_enviar_email_acesso_automatico(pendente, base_url, db)
        return {"status": "approved", "_conta": {
            "admin_url": pendente.admin_url, "cardapio_url": pendente.cardapio_url
        }}

    dados = pendente.dados_json or {}
    valor_total = float(dados.get("valor_total", 97.0))
    descricao = dados.get("descricao_plano", "Plano CardápioOnline")

    sdk = obter_mp_sdk(db)
    base_url = str(request.base_url).rstrip("/")
    is_local = any(h in base_url for h in ("127.0.0.1", "localhost", "0.0.0.0"))

    payment_data: dict = {
        "transaction_amount": valor_total,          # sempre nosso valor — nunca o do cliente
        "description": descricao,
        "payment_method_id": payload.payment_method_id,
        "external_reference": payload.pending_id,
        "payer": payload.payer or {},
    }
    if payload.token:
        payment_data["token"] = payload.token
        payment_data["installments"] = payload.installments or 1
    if payload.issuer_id:
        payment_data["issuer_id"] = payload.issuer_id
    if not is_local:
        payment_data["notification_url"] = f"{base_url}/api/public/webhook-mercadopago"

    try:
        mp_resp = sdk.payment().create(payment_data)
        payment = mp_resp.get("response", {})
        if mp_resp.get("status") not in (200, 201):
            cause = payment.get("message") or payment.get("cause") or str(payment)
            raise ValueError(cause)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erro ao processar pagamento: {exc}")

    payment_id = str(payment.get("id") or "")
    payment_status = payment.get("status", "")

    if payment_status == "approved":
        try:
            _criar_conta_a_partir_de_pagamento(pendente, payment_id, base_url, db)
        except Exception:
            db.rollback()
    elif payment_status in ("rejected", "cancelled"):
        pendente.status = "rejeitado"
        db.commit()

    result = dict(payment)
    if pendente.status == "aprovado":
        result["_conta"] = {
            "admin_url": pendente.admin_url,
            "cardapio_url": pendente.cardapio_url,
        }
    return result


def _obter_restaurante_do_pagamento_pendente(pendente: PagamentoPendente, db: Session) -> Restaurante | None:
    restaurante = None
    if pendente.restaurante_id:
        restaurante = db.query(Restaurante).filter(Restaurante.restaurante_id == pendente.restaurante_id).first()
    if restaurante:
        return restaurante

    email_normalizado = ((pendente.dados_json or {}).get("email_admin") or "").strip().lower()
    if email_normalizado:
        restaurante = db.query(Restaurante).filter(Restaurante.email_admin == email_normalizado).first()
    return restaurante


def _tentar_enviar_email_acesso_automatico(
    pendente: PagamentoPendente,
    base_url: str,
    db: Session,
    forcar: bool = False,
) -> dict:
    if pendente.status != "aprovado":
        return {"ok": False, "enviado": False, "detail": "Pagamento ainda não aprovado"}

    if pendente.email_enviado and not forcar:
        return {"ok": True, "enviado": True, "detail": "E-mail já enviado"}

    agora = datetime.utcnow()
    cooldown_segundos = 20
    if (not forcar) and pendente.email_ultima_tentativa_em and (agora - pendente.email_ultima_tentativa_em).total_seconds() < cooldown_segundos:
        return {"ok": False, "enviado": False, "detail": "Aguardando próxima tentativa automática"}

    restaurante = _obter_restaurante_do_pagamento_pendente(pendente, db)
    if not restaurante:
        pendente.email_enviado = False
        pendente.email_erro = "Restaurante não encontrado para envio automático"
        pendente.email_tentativas = int(pendente.email_tentativas or 0) + 1
        pendente.email_ultima_tentativa_em = agora
        db.commit()
        return {"ok": False, "enviado": False, "detail": pendente.email_erro}

    out = serializar_restaurante_out(restaurante, base_url)
    envio = enviar_email_acesso_restaurante(
        destinatario=restaurante.email_admin,
        nome_unidade=restaurante.nome_unidade,
        admin_url=out.get("admin_url") or "",
        cardapio_url=out.get("cardapio_url") or "",
        email_admin=restaurante.email_admin,
        senha_inicial=(pendente.dados_json or {}).get("senha_inicial") or "",
        db=db,
    )

    pendente.restaurante_id = restaurante.restaurante_id
    pendente.admin_url = out.get("admin_url") or pendente.admin_url or ""
    pendente.cardapio_url = out.get("cardapio_url") or pendente.cardapio_url or ""
    pendente.email_enviado = bool(envio.get("enviado"))
    pendente.email_erro = str(envio.get("detail") or "")[:500]
    pendente.email_enviado_em = agora if pendente.email_enviado else None
    pendente.email_tentativas = int(pendente.email_tentativas or 0) + 1
    pendente.email_ultima_tentativa_em = agora
    db.commit()

    return envio


def _criar_conta_a_partir_de_pagamento(
    pendente: PagamentoPendente,
    mp_payment_id: str,
    base_url: str,
    db: Session,
) -> None:
    """Cria o restaurante no banco e marca o registro pendente como aprovado.
    Idempotente — pode ser chamado múltiplas vezes sem efeitos colaterais.
    """
    if pendente.status == "aprovado":
        _tentar_enviar_email_acesso_automatico(pendente, base_url, db)
        return  # já processado

    dados = pendente.dados_json or {}
    email_normalizado = (dados.get("email_admin") or "").strip().lower()

    restaurante = db.query(Restaurante).filter(
        Restaurante.email_admin == email_normalizado
    ).first()

    if not restaurante:
        base_slug = slugify_nome(dados.get("slug") or dados.get("nome_unidade") or "restaurante")
        if not base_slug:
            base_slug = "restaurante"
        slug_final = gerar_slug_unico(db, base_slug)
        whatsapp = ""
        if dados.get("telefone_admin"):
            whatsapp = "".join(ch for ch in str(dados["telefone_admin"]) if ch.isdigit())[:30]
        plano = dados.get("plano", "basic")
        planos_saas = obter_planos_saas_valores(db)
        valor_mensalidade = planos_saas.get(plano, planos_saas["basic"])

        restaurante = Restaurante(
            restaurante_id=str(uuid.uuid4()),
            nome_unidade=(dados.get("nome_unidade") or "Restaurante").strip(),
            slug=slug_final,
            email_admin=email_normalizado,
            senha_hash=dados.get("senha_inicial", ""),
            status_assinatura="Ativo",
            data_assinatura=date.today(),
            validade_assinatura=date.today() + timedelta(days=30),
            token_acesso=secrets.token_urlsafe(32),
            valor_mensalidade=valor_mensalidade,
            delivery_whatsapp_entregador=whatsapp,
        )
        db.add(restaurante)
        db.flush()

    out = serializar_restaurante_out(restaurante, base_url)
    pendente.status = "aprovado"
    pendente.restaurante_id = restaurante.restaurante_id
    pendente.admin_url = out["admin_url"] or ""
    pendente.cardapio_url = out["cardapio_url"] or ""
    if mp_payment_id:
        pendente.mp_payment_id = mp_payment_id
    db.commit()

    _tentar_enviar_email_acesso_automatico(pendente, base_url, db)


@app.get("/api/public/status-pagamento/{pending_id}")
def status_pagamento(pending_id: str, request: Request, db: Session = Depends(get_db)):
    """Polling usado pelo frontend. Verifica ativamente com o MP se ainda aguardando."""
    pendente = db.query(PagamentoPendente).filter(PagamentoPendente.pending_id == pending_id).first()
    if not pendente:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

    # Se ainda aguardando, busca ativamente pagamentos aprovados no MP pelo external_reference
    if pendente.status == "aguardando":
        try:
            sdk = obter_mp_sdk(db)
            search_resp = sdk.payment().search({"external_reference": pending_id, "status": "approved"})
            results = (search_resp.get("response") or {}).get("results") or []
            if results:
                payment = results[0]
                if payment.get("status") == "approved":
                    base_url = str(request.base_url).rstrip("/")
                    try:
                        _criar_conta_a_partir_de_pagamento(
                            pendente,
                            str(payment.get("id") or ""),
                            base_url,
                            db,
                        )
                    except Exception:
                        db.rollback()
            else:
                # Também tenta buscar por status "pending" (PIX ainda não confirmado)
                search_pend = sdk.payment().search({"external_reference": pending_id})
                all_results = (search_pend.get("response") or {}).get("results") or []
                for pag in all_results:
                    if pag.get("status") in ("rejected", "cancelled"):
                        pendente.status = "rejeitado"
                        db.commit()
                        break
        except Exception:
            pass  # falha silenciosa — apenas retorna o status atual do DB

    if pendente.status == "aprovado" and not pendente.email_enviado:
        base_url = str(request.base_url).rstrip("/")
        _tentar_enviar_email_acesso_automatico(pendente, base_url, db)

    return {
        "status": pendente.status,
        "admin_url": pendente.admin_url or None,
        "cardapio_url": pendente.cardapio_url or None,
        "restaurante_id": pendente.restaurante_id or None,
        "slug": (pendente.dados_json or {}).get("slug") or None,
        "email_enviado": bool(pendente.email_enviado),
        "email_erro": (pendente.email_erro or None),
        "email_enviado_em": pendente.email_enviado_em.isoformat() if pendente.email_enviado_em else None,
        "email_tentativas": int(pendente.email_tentativas or 0),
        "email_ultima_tentativa_em": pendente.email_ultima_tentativa_em.isoformat() if pendente.email_ultima_tentativa_em else None,
    }


@app.get("/api/super-admin/diagnostico-email")
def diagnostico_email(db: Session = Depends(get_db)):
    smtp = obter_config_smtp(db)
    usuario = smtp["user"]
    return {
        "ok": True,
        "smtp_configurado": bool(smtp["configured"]),
        "host": smtp["host"],
        "porta": smtp["port"],
        "usuario_preview": (usuario[:3] + "***" + usuario[-4:]) if len(usuario) > 8 else ("***" if usuario else ""),
        "from": smtp["from"],
        "ssl": smtp["ssl"],
        "tls": smtp["tls"],
        "origem": "banco" if db.get(ConfigSistema, "smtp_host") else "env",
    }


@app.get("/api/super-admin/config-smtp")
def obter_config_smtp_super_admin(db: Session = Depends(get_db)):
    smtp = obter_config_smtp(db)
    senha_cfg = db.get(ConfigSistema, "smtp_pass")
    senha_definida = bool(senha_cfg and (senha_cfg.valor or "").strip())
    return {
        "ok": True,
        "host": smtp["host"],
        "port": smtp["port"],
        "user": smtp["user"],
        "from": smtp["from"],
        "tls": smtp["tls"],
        "ssl": smtp["ssl"],
        "password_configured": senha_definida,
    }


@app.post("/api/super-admin/config-smtp")
def salvar_config_smtp(payload: ConfigSMTPUpdate, db: Session = Depends(get_db)):
    host = (payload.host or "").strip()
    user = (payload.user or "").strip()
    from_email = (payload.from_email or "").strip() or user or SUPER_ADMIN_LOGIN_DEFAULT
    password = (payload.password or "").strip()
    if not host:
        raise HTTPException(status_code=400, detail="SMTP host é obrigatório")

    updates = {
        "smtp_host": host,
        "smtp_port": str(int(payload.port)),
        "smtp_user": user,
        "smtp_from": from_email,
        "smtp_tls": "1" if payload.tls else "0",
        "smtp_ssl": "1" if payload.ssl else "0",
    }

    for chave, valor in updates.items():
        obj = db.get(ConfigSistema, chave)
        if obj:
            obj.valor = valor
        else:
            db.add(ConfigSistema(chave=chave, valor=valor))

    if password:
        obj = db.get(ConfigSistema, "smtp_pass")
        if obj:
            obj.valor = password
        else:
            db.add(ConfigSistema(chave="smtp_pass", valor=password))

    db.commit()
    return {"ok": True, "message": "Configuração SMTP salva com sucesso."}


@app.post("/api/super-admin/pagamentos/{pending_id}/reenviar-email-acesso")
def reenviar_email_acesso_pagamento(pending_id: str, request: Request, db: Session = Depends(get_db)):
    pendente = db.query(PagamentoPendente).filter(PagamentoPendente.pending_id == pending_id).first()
    if not pendente:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")
    if pendente.status != "aprovado":
        raise HTTPException(status_code=409, detail="Pagamento ainda não aprovado")

    base_url = str(request.base_url).rstrip("/")
    restaurante = _obter_restaurante_do_pagamento_pendente(pendente, db)
    if not restaurante:
        raise HTTPException(status_code=404, detail="Restaurante do pagamento não encontrado")

    out = serializar_restaurante_out(restaurante, base_url)
    envio = _tentar_enviar_email_acesso_automatico(pendente, base_url, db, forcar=True)

    return {
        "ok": bool(envio.get("ok")),
        "enviado": bool(envio.get("enviado")),
        "detail": envio.get("detail") or ("E-mail reenviado com sucesso" if envio.get("enviado") else "Falha ao reenviar e-mail"),
        "email": restaurante.email_admin,
        "admin_url": out.get("admin_url"),
        "cardapio_url": out.get("cardapio_url"),
    }


@app.post("/api/public/webhook-mercadopago")
async def webhook_mercadopago(
    request: Request,
    db: Session = Depends(get_db),
):
    """Webhook chamado pelo Mercado Pago ao aprovar/recusar um pagamento."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "detail": "body inválido"}, status_code=200)

    tipo = body.get("type") or body.get("topic")
    dados = body.get("data") or {}
    payment_id = str(dados.get("id") or body.get("id") or "").strip()

    # MP também envia query-string ?type=payment&data.id=...
    if not payment_id:
        payment_id = str(request.query_params.get("data.id") or "").strip()
    if not tipo:
        tipo = request.query_params.get("type") or request.query_params.get("topic") or ""

    if tipo not in ("payment", "merchant_order") or not payment_id:
        return JSONResponse({"ok": True, "detail": "ignorado"}, status_code=200)

    try:
        sdk = obter_mp_sdk(db)
        pay_resp = sdk.payment().get(int(payment_id))
        payment = pay_resp.get("response", {})
    except Exception as exc:
        return JSONResponse({"ok": False, "detail": str(exc)}, status_code=200)

    pay_status = payment.get("status", "")
    external_ref = str(payment.get("external_reference") or "").strip()

    if not external_ref:
        return JSONResponse({"ok": True, "detail": "sem external_reference"}, status_code=200)

    pendente = db.query(PagamentoPendente).filter(PagamentoPendente.pending_id == external_ref).first()
    if not pendente:
        return JSONResponse({"ok": True, "detail": "pending não encontrado"}, status_code=200)

    # Atualiza ID do pagamento MP no registro pendente
    if not pendente.mp_payment_id:
        pendente.mp_payment_id = payment_id
        db.flush()

    if pay_status == "approved" and pendente.status != "aprovado":
        base_url = str(request.base_url).rstrip("/")
        try:
            _criar_conta_a_partir_de_pagamento(pendente, payment_id, base_url, db)
        except Exception:
            db.rollback()
    elif pay_status == "approved" and pendente.status == "aprovado" and not pendente.email_enviado:
        base_url = str(request.base_url).rstrip("/")
        try:
            _tentar_enviar_email_acesso_automatico(pendente, base_url, db)
        except Exception:
            db.rollback()

    elif pay_status in ("rejected", "cancelled", "refunded"):
        if pendente.status == "aguardando":
            pendente.status = "rejeitado"
            db.commit()

    return JSONResponse({"ok": True}, status_code=200)


# ─── Super Admin: configuração Mercado Pago ───────────────────────────────────

@app.get("/api/super-admin/config-mp")
def obter_config_mp(db: Session = Depends(get_db)):
    cfg_token = db.get(ConfigSistema, "mp_access_token")
    cfg_key = db.get(ConfigSistema, "mp_public_key")
    token = cfg_token.valor if cfg_token else ""
    key = cfg_key.valor if cfg_key else ""
    # Máscarar parcialmente o token para não expor no frontend
    def mascarar(v: str) -> str:
        if len(v) > 12:
            return v[:10] + "***" + v[-6:]
        return "***" if v else ""
    return {
        "access_token_configurado": bool(token or MP_ACCESS_TOKEN_DEFAULT),
        "access_token_preview": mascarar(token or MP_ACCESS_TOKEN_DEFAULT),
        "public_key_configurado": bool(key or MP_PUBLIC_KEY_DEFAULT),
        "public_key_preview": mascarar(key or MP_PUBLIC_KEY_DEFAULT),
        "usando_default": not token,
    }


@app.get("/api/super-admin/planos")
def obter_planos_super_admin(db: Session = Depends(get_db)):
    planos_saas = obter_planos_saas_valores(db)
    return {
        "ok": True,
        "planos": {
            "basic": float(planos_saas["basic"]),
            "pro": float(planos_saas["pro"]),
            "enterprise": float(planos_saas["enterprise"]),
        },
    }


@app.post("/api/super-admin/planos")
def salvar_planos_super_admin(payload: PlanosSaaSUpdate, db: Session = Depends(get_db)):
    salvos = salvar_planos_saas_valores(
        db,
        {
            "basic": payload.basic,
            "pro": payload.pro,
            "enterprise": payload.enterprise,
        },
    )
    return {
        "ok": True,
        "message": "Valores dos planos atualizados.",
        "planos": {
            "basic": float(salvos["basic"]),
            "pro": float(salvos["pro"]),
            "enterprise": float(salvos["enterprise"]),
        },
    }


@app.post("/api/super-admin/config-mp")
def salvar_config_mp(
    payload: ConfigMPUpdate,
    db: Session = Depends(get_db),
):
    access_token = payload.access_token.strip()
    public_key = payload.public_key.strip()
    if not access_token.startswith("APP_USR-"):
        raise HTTPException(status_code=400, detail="Access token inválido (deve começar com APP_USR-)")
    if not public_key.startswith("APP_USR-"):
        raise HTTPException(status_code=400, detail="Public key inválida (deve começar com APP_USR-)")

    for chave, valor in [("mp_access_token", access_token), ("mp_public_key", public_key)]:
        obj = db.get(ConfigSistema, chave)
        if obj:
            obj.valor = valor
        else:
            db.add(ConfigSistema(chave=chave, valor=valor))
    db.commit()
    return {"ok": True, "message": "Credenciais Mercado Pago salvas com sucesso."}


@app.get("/api/super-admin/restaurantes", response_model=list[RestauranteOut])
def listar_restaurantes(request: Request, db: Session = Depends(get_db)):
    base_url = str(request.base_url).rstrip("/")
    restaurantes = db.query(Restaurante).order_by(Restaurante.id.desc()).all()
    return [serializar_restaurante_out(restaurante, base_url) for restaurante in restaurantes]


@app.post("/api/super-admin/restaurantes/{restaurante_id}/reenviar-email-acesso")
def reenviar_email_acesso_restaurante_super_admin(
    restaurante_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    restaurante = db.get(Restaurante, restaurante_id)
    if not restaurante:
        raise HTTPException(status_code=404, detail="Restaurante não encontrado")

    if not restaurante.email_admin:
        raise HTTPException(status_code=400, detail="Restaurante sem e-mail de responsável cadastrado")

    base_url = str(request.base_url).rstrip("/")
    out = serializar_restaurante_out(restaurante, base_url)
    envio = enviar_email_acesso_restaurante(
        destinatario=restaurante.email_admin,
        nome_unidade=restaurante.nome_unidade,
        admin_url=out.get("admin_url") or "",
        cardapio_url=out.get("cardapio_url") or "",
        email_admin=restaurante.email_admin,
        senha_inicial=None,
        db=db,
    )

    return {
        "ok": bool(envio.get("ok")),
        "enviado": bool(envio.get("enviado")),
        "detail": envio.get("detail") or ("E-mail enviado com sucesso" if envio.get("enviado") else "Falha ao enviar e-mail"),
        "restaurante_id": restaurante.id,
        "nome_unidade": restaurante.nome_unidade,
        "email": restaurante.email_admin,
        "admin_url": out.get("admin_url"),
        "cardapio_url": out.get("cardapio_url"),
    }


@app.patch("/api/super-admin/restaurantes/{restaurante_id}")
def atualizar_restaurante_super_admin(
    restaurante_id: int,
    payload: RestauranteSuperAdminUpdate,
    db: Session = Depends(get_db),
):
    restaurante = db.get(Restaurante, restaurante_id)
    if not restaurante:
        raise HTTPException(status_code=404, detail="Restaurante não encontrado")

    if payload.nome_unidade is not None:
        restaurante.nome_unidade = payload.nome_unidade.strip() or restaurante.nome_unidade

    if payload.slug is not None:
        novo_slug = payload.slug.strip().lower()
        if not novo_slug:
            raise HTTPException(status_code=400, detail="Slug inválido")
        slug_existente = db.query(Restaurante).filter(
            Restaurante.slug == novo_slug,
            Restaurante.id != restaurante_id,
        ).first()
        if slug_existente:
            raise HTTPException(status_code=400, detail="Slug já cadastrado")
        restaurante.slug = novo_slug

    if payload.email_admin is not None:
        novo_email = str(payload.email_admin).strip().lower()
        email_existente = db.query(Restaurante).filter(
            Restaurante.email_admin == novo_email,
            Restaurante.id != restaurante_id,
        ).first()
        if email_existente:
            raise HTTPException(status_code=400, detail="E-mail já cadastrado")
        restaurante.email_admin = novo_email

    if payload.token_acesso is not None:
        novo_token = payload.token_acesso.strip()
        if not novo_token:
            raise HTTPException(status_code=400, detail="Token inválido")
        token_existente = db.query(Restaurante).filter(
            Restaurante.token_acesso == novo_token,
            Restaurante.id != restaurante_id,
        ).first()
        if token_existente:
            raise HTTPException(status_code=400, detail="Token já cadastrado")
        restaurante.token_acesso = novo_token

    if payload.valor_mensalidade is not None:
        restaurante.valor_mensalidade = payload.valor_mensalidade

    if payload.validade_assinatura is not None:
        restaurante.validade_assinatura = payload.validade_assinatura

    if payload.status_assinatura is not None:
        restaurante.status_assinatura = payload.status_assinatura

    if payload.plano is not None:
        restaurante.plano = payload.plano
        # Ajusta valor_mensalidade automaticamente se não fornecido
        if payload.valor_mensalidade is None:
            from sqlalchemy.orm import Session as _Session
            planos_val = obter_planos_saas_valores(db)
            restaurante.valor_mensalidade = planos_val.get(payload.plano, restaurante.valor_mensalidade)

    db.commit()
    db.refresh(restaurante)

    return {
        "ok": True,
        "id": restaurante.id,
        "nome_unidade": restaurante.nome_unidade,
        "slug": restaurante.slug,
        "email_admin": restaurante.email_admin,
        "token_acesso": restaurante.token_acesso,
        "valor_mensalidade": float(restaurante.valor_mensalidade),
        "validade_assinatura": restaurante.validade_assinatura.isoformat() if restaurante.validade_assinatura else None,
        "status_assinatura": restaurante.status_assinatura,
        "plano": restaurante.plano or "basic",
    }


@app.delete("/api/super-admin/restaurantes/{restaurante_id}")
def excluir_restaurante_super_admin(restaurante_id: int, db: Session = Depends(get_db)):
    restaurante = db.get(Restaurante, restaurante_id)
    if not restaurante:
        raise HTTPException(status_code=404, detail="Restaurante não encontrado")

    rid = restaurante.restaurante_id
    db.query(Cardapio).filter(Cardapio.restaurante_id == rid).delete(synchronize_session=False)
    db.query(Pedido).filter(Pedido.restaurante_id == rid).delete(synchronize_session=False)
    db.query(Usuario).filter(Usuario.restaurante_id == rid).delete(synchronize_session=False)
    db.query(Entregador).filter(Entregador.restaurante_id == rid).delete(synchronize_session=False)
    db.delete(restaurante)
    db.commit()
    return {"ok": True, "restaurante_id": restaurante_id}


@app.patch("/api/super-admin/restaurantes/{restaurante_id}/assinatura")
def atualizar_assinatura(restaurante_id: int, status: str = Query(..., pattern="^(Ativo|Inativo)$"), db: Session = Depends(get_db)):
    restaurante = db.get(Restaurante, restaurante_id)
    if not restaurante:
        raise HTTPException(status_code=404, detail="Restaurante não encontrado")
    restaurante.status_assinatura = status
    db.commit()
    return {"ok": True, "restaurante_id": restaurante_id, "status_assinatura": status}


@app.patch("/api/super-admin/restaurantes/{restaurante_id}/validade")
def extender_validade_assinatura(
    restaurante_id: int,
    payload: ExtenderValidadePayload,
    db: Session = Depends(get_db),
):
    restaurante = db.get(Restaurante, restaurante_id)
    if not restaurante:
        raise HTTPException(status_code=404, detail="Restaurante não encontrado")

    restaurante.validade_assinatura = payload.nova_validade_assinatura
    if payload.nova_validade_assinatura >= date.today():
        restaurante.status_assinatura = "Ativo"

    db.commit()
    db.refresh(restaurante)

    return {
        "ok": True,
        "restaurante_id": restaurante.id,
        "data_assinatura": restaurante.data_assinatura.isoformat() if restaurante.data_assinatura else None,
        "validade_assinatura": restaurante.validade_assinatura.isoformat() if restaurante.validade_assinatura else None,
        "status_assinatura": restaurante.status_assinatura,
    }


@app.get("/api/public/cardapio/{slug}")
def obter_cardapio_por_slug(slug: str, mesa: str = Query(...), db: Session = Depends(get_db)):
    restaurante = get_restaurante_por_slug(db, slug)

    if not assinatura_ativa(restaurante):
        raise HTTPException(status_code=403, detail="Acesso negado: assinatura inativa")

    horarios_categoria = obter_horarios_categoria(restaurante)
    produtos = db.query(Cardapio).filter(
        Cardapio.restaurante_id == restaurante.restaurante_id,
        Cardapio.disponivel == True,  # noqa: E712
    ).all()

    produtos_filtrados = []
    for p in produtos:
        horario_inicio = p.horario_inicio or ""
        horario_fim = p.horario_fim or ""
        if not horario_inicio and not horario_fim:
            horario_categoria = horarios_categoria.get(p.categoria, {}) if isinstance(horarios_categoria, dict) else {}
            horario_inicio = horario_categoria.get("inicio", "")
            horario_fim = horario_categoria.get("fim", "")

        if esta_disponivel_por_horario(horario_inicio, horario_fim):
            produtos_filtrados.append((p, horario_inicio, horario_fim))

    return {
        "restaurante": {
            "id": restaurante.id,
            "restaurante_id": restaurante.restaurante_id,
            "nome_unidade": restaurante.nome_unidade,
            "slug": restaurante.slug,
            "plan_type": obter_plan_type_restaurante(restaurante),
            "permissions": obter_permissoes_plano(restaurante),
            "cnpj": restaurante.cnpj,
            "total_mesas": restaurante.total_mesas,
            "capa_cardapio": restaurante.capa_cardapio_base64,
            "capa_posicao": restaurante.capa_posicao,
            "logo": restaurante.logo_base64,
            "tema_cor_primaria": restaurante.tema_cor_primaria,
            "tema_cor_secundaria": restaurante.tema_cor_secundaria,
            "tema_cor_destaque": restaurante.tema_cor_destaque,
            "estilo_botao": restaurante.estilo_botao,
            "delivery_ativo": restaurante.delivery_ativo,
            "delivery_endereco_origem": restaurante.delivery_endereco_origem,
            "delivery_bairro": restaurante.delivery_bairro,
            "delivery_cidade": restaurante.delivery_cidade,
            "delivery_uf": restaurante.delivery_uf,
            "delivery_google_maps_api_key": restaurante.delivery_google_maps_api_key,
            "delivery_whatsapp_entregador": restaurante.delivery_whatsapp_entregador,
        },
        "mesa": mesa,
        "categorias": obter_categorias_restaurante(restaurante),
        "horarios_categoria": horarios_categoria,
        "produtos": [
            {
                "id": p.id,
                "nome": p.nome,
                "preco": float(p.preco),
                "categoria": p.categoria,
                "descricao": p.descricao,
                "imagem": p.imagem_base64,
                "complementos": p.complementos_json or [],
                "disponivel": p.disponivel,
                "horario_inicio": hi,
                "horario_fim": hf,
            }
            for p, hi, hf in produtos_filtrados
        ],
    }


@app.get("/api/admin/restaurante/{slug}")
def obter_configuracao_restaurante(slug: str, token_acesso: str = Header(...), db: Session = Depends(get_db)):
    restaurante = garantir_isolamento(slug, token_acesso, db)
    return {
        "id": restaurante.id,
        "restaurante_id": restaurante.restaurante_id,
        "nome_unidade": restaurante.nome_unidade,
        "slug": restaurante.slug,
        "plan_type": obter_plan_type_restaurante(restaurante),
        "permissions": obter_permissoes_plano(restaurante),
        "cnpj": restaurante.cnpj,
        "total_mesas": restaurante.total_mesas,
        "delivery_ativo": restaurante.delivery_ativo,
        "delivery_endereco_origem": restaurante.delivery_endereco_origem,
        "delivery_bairro": restaurante.delivery_bairro,
        "delivery_cidade": restaurante.delivery_cidade,
        "delivery_uf": restaurante.delivery_uf,
        "delivery_google_maps_api_key": restaurante.delivery_google_maps_api_key,
        "delivery_whatsapp_entregador": restaurante.delivery_whatsapp_entregador,
        "whatsapp_api_ativo": restaurante.whatsapp_api_ativo,
        "whatsapp_phone_number_id": restaurante.whatsapp_phone_number_id,
        "whatsapp_access_token": restaurante.whatsapp_access_token,
        "whatsapp_verify_token": restaurante.whatsapp_verify_token,
        "categorias": obter_categorias_restaurante(restaurante),
        "horarios_categoria": obter_horarios_categoria(restaurante),
        "capa_cardapio": restaurante.capa_cardapio_base64,
        "capa_posicao": restaurante.capa_posicao,
        "logo": restaurante.logo_base64,
        "tema_cor_primaria": restaurante.tema_cor_primaria,
        "tema_cor_secundaria": restaurante.tema_cor_secundaria,
        "tema_cor_destaque": restaurante.tema_cor_destaque,
        "estilo_botao": restaurante.estilo_botao,
        "token_acesso": restaurante.token_acesso,
    }


@app.get("/api/admin/restaurante/{slug}/perfil")
def obter_perfil_admin(slug: str, token_acesso: str = Header(...), db: Session = Depends(get_db)):
    restaurante = garantir_isolamento(slug, token_acesso, db)

    pagamentos = (
        db.query(PagamentoPendente)
        .filter(
            PagamentoPendente.restaurante_id == restaurante.restaurante_id,
            PagamentoPendente.status == "aprovado",
        )
        .order_by(PagamentoPendente.created_at.desc())
        .limit(12)
        .all()
    )

    historico = []
    for p in pagamentos:
        dados = p.dados_json if isinstance(p.dados_json, dict) else {}
        historico.append(
            {
                "pending_id": p.pending_id,
                "mp_payment_id": p.mp_payment_id or None,
                "valor_total": float(dados.get("valor_total") or 0),
                "descricao_plano": dados.get("descricao_plano") or "",
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
        )

    return {
        "ok": True,
        "nome_unidade": restaurante.nome_unidade,
        "email_admin": restaurante.email_admin,
        "foto_perfil_base64": restaurante.foto_perfil_base64 or "",
        "status_assinatura": restaurante.status_assinatura,
        "data_assinatura": restaurante.data_assinatura.isoformat() if restaurante.data_assinatura else None,
        "validade_assinatura": restaurante.validade_assinatura.isoformat() if restaurante.validade_assinatura else None,
        "valor_mensalidade": float(restaurante.valor_mensalidade or 0),
        "plano": (restaurante.plano or "basic").strip() or "basic",
        "plan_type": obter_plan_type_restaurante(restaurante),
        "permissions": obter_permissoes_plano(restaurante),
        "pagamentos_aprovados": len(historico),
        "historico_pagamentos": historico,
    }


@app.patch("/api/admin/restaurante/{slug}/perfil")
def atualizar_perfil_admin(
    slug: str,
    payload: AdminPerfilUpdatePayload,
    token_acesso: str = Header(...),
    db: Session = Depends(get_db),
):
    restaurante = garantir_isolamento(slug, token_acesso, db)

    if payload.email_admin is not None:
        novo_email = str(payload.email_admin).strip().lower()
        existente = db.query(Restaurante).filter(
            Restaurante.email_admin == novo_email,
            Restaurante.id != restaurante.id,
        ).first()
        if existente:
            raise HTTPException(status_code=400, detail="E-mail já cadastrado")
        restaurante.email_admin = novo_email

    if payload.nova_senha is not None:
        senha_atual = (payload.senha_atual or "").strip()
        if not senha_atual:
            raise HTTPException(status_code=400, detail="Informe a senha atual para alterar a senha")
        if senha_atual != (restaurante.senha_hash or ""):
            raise HTTPException(status_code=400, detail="Senha atual inválida")
        restaurante.senha_hash = payload.nova_senha.strip()

    if payload.foto_perfil_base64 is not None:
        restaurante.foto_perfil_base64 = payload.foto_perfil_base64.strip()

    db.commit()
    db.refresh(restaurante)

    return {
        "ok": True,
        "nome_unidade": restaurante.nome_unidade,
        "email_admin": restaurante.email_admin,
        "foto_perfil_base64": restaurante.foto_perfil_base64 or "",
        "status_assinatura": restaurante.status_assinatura,
        "validade_assinatura": restaurante.validade_assinatura.isoformat() if restaurante.validade_assinatura else None,
        "valor_mensalidade": float(restaurante.valor_mensalidade or 0),
        "plan_type": obter_plan_type_restaurante(restaurante),
        "permissions": obter_permissoes_plano(restaurante),
    }


@app.put("/api/admin/restaurante/{slug}")
def atualizar_configuracao_restaurante(
    slug: str,
    payload: RestauranteConfigUpdate,
    token_acesso: str = Header(...),
    db: Session = Depends(get_db),
):
    restaurante = garantir_isolamento(slug, token_acesso, db)

    if payload.nome_unidade is not None:
        restaurante.nome_unidade = payload.nome_unidade.strip() or restaurante.nome_unidade
    if payload.cnpj is not None:
        restaurante.cnpj = payload.cnpj.strip()
    if payload.total_mesas is not None:
        restaurante.total_mesas = max(1, int(payload.total_mesas))
    if payload.delivery_ativo is not None:
        restaurante.delivery_ativo = bool(payload.delivery_ativo)
    if payload.delivery_endereco_origem is not None:
        restaurante.delivery_endereco_origem = payload.delivery_endereco_origem.strip()
    if payload.delivery_bairro is not None:
        restaurante.delivery_bairro = payload.delivery_bairro.strip()[:120]
    if payload.delivery_cidade is not None:
        restaurante.delivery_cidade = payload.delivery_cidade.strip()[:120]
    if payload.delivery_uf is not None:
        uf_normalizada = re.sub(r"[^A-Za-z]", "", payload.delivery_uf).strip().upper()[:2]
        restaurante.delivery_uf = uf_normalizada
    if payload.delivery_google_maps_api_key is not None:
        restaurante.delivery_google_maps_api_key = payload.delivery_google_maps_api_key.strip()
    if payload.delivery_whatsapp_entregador is not None:
        restaurante.delivery_whatsapp_entregador = payload.delivery_whatsapp_entregador.strip()
    if payload.whatsapp_api_ativo is not None:
        restaurante.whatsapp_api_ativo = bool(payload.whatsapp_api_ativo)
    if payload.whatsapp_phone_number_id is not None:
        restaurante.whatsapp_phone_number_id = "".join(ch for ch in payload.whatsapp_phone_number_id if ch.isdigit())[:80]
    if payload.whatsapp_access_token is not None:
        restaurante.whatsapp_access_token = payload.whatsapp_access_token.strip()[:255]
    if payload.whatsapp_verify_token is not None:
        restaurante.whatsapp_verify_token = payload.whatsapp_verify_token.strip()[:120]
    if payload.categorias is not None:
        restaurante.categorias_json = [c.strip() for c in payload.categorias if c and c.strip()]
    if payload.categoria_horarios is not None:
        restaurante.categoria_horarios_json = payload.categoria_horarios if isinstance(payload.categoria_horarios, dict) else {}
    if payload.capa_cardapio_base64 is not None:
        restaurante.capa_cardapio_base64 = payload.capa_cardapio_base64
    if payload.capa_posicao is not None:
        capa_posicoes_validas = {"top", "center", "bottom"}
        restaurante.capa_posicao = payload.capa_posicao if payload.capa_posicao in capa_posicoes_validas else "center"
    if payload.logo_base64 is not None:
        restaurante.logo_base64 = payload.logo_base64
    if payload.tema_cor_primaria is not None:
        restaurante.tema_cor_primaria = payload.tema_cor_primaria
    if payload.tema_cor_secundaria is not None:
        restaurante.tema_cor_secundaria = payload.tema_cor_secundaria
    if payload.tema_cor_destaque is not None:
        restaurante.tema_cor_destaque = payload.tema_cor_destaque
    if payload.estilo_botao is not None:
        restaurante.estilo_botao = payload.estilo_botao if payload.estilo_botao in {"rounded", "pill", "soft"} else "rounded"

    db.commit()
    db.refresh(restaurante)

    return {
        "ok": True,
        "slug": restaurante.slug,
        "token_acesso": restaurante.token_acesso,
        "nome_unidade": restaurante.nome_unidade,
        "cnpj": restaurante.cnpj,
        "total_mesas": restaurante.total_mesas,
        "delivery_ativo": restaurante.delivery_ativo,
        "delivery_endereco_origem": restaurante.delivery_endereco_origem,
        "delivery_bairro": restaurante.delivery_bairro,
        "delivery_cidade": restaurante.delivery_cidade,
        "delivery_uf": restaurante.delivery_uf,
        "delivery_google_maps_api_key": restaurante.delivery_google_maps_api_key,
        "delivery_whatsapp_entregador": restaurante.delivery_whatsapp_entregador,
        "whatsapp_api_ativo": restaurante.whatsapp_api_ativo,
        "whatsapp_phone_number_id": restaurante.whatsapp_phone_number_id,
        "whatsapp_access_token": restaurante.whatsapp_access_token,
        "whatsapp_verify_token": restaurante.whatsapp_verify_token,
        "categorias": obter_categorias_restaurante(restaurante),
        "horarios_categoria": obter_horarios_categoria(restaurante),
        "capa_cardapio": restaurante.capa_cardapio_base64,
        "capa_posicao": restaurante.capa_posicao,
        "logo": restaurante.logo_base64,
        "tema_cor_primaria": restaurante.tema_cor_primaria,
        "tema_cor_secundaria": restaurante.tema_cor_secundaria,
        "tema_cor_destaque": restaurante.tema_cor_destaque,
        "estilo_botao": restaurante.estilo_botao,
    }


@app.post("/api/public/pedidos")
def criar_pedido_publico(payload: PedidoCreate, db: Session = Depends(get_db)):
    restaurante = get_restaurante_por_slug(db, payload.slug)

    if not assinatura_ativa(restaurante):
        raise HTTPException(status_code=403, detail="Acesso negado: assinatura inativa")

    total = Decimal("0.00")
    for item in payload.itens:
        qtd = Decimal(str(item.get("quantidade", 1)))
        preco = Decimal(str(item.get("preco_unitario", 0)))
        total += qtd * preco

    tipo_entrega = (payload.tipo_entrega or "mesa").lower()
    if tipo_entrega not in {"mesa", "delivery"}:
        tipo_entrega = "mesa"

    mesa_pedido = payload.mesa
    if tipo_entrega == "delivery":
        mesa_pedido = "DELIVERY"

    endereco_entrega_normalizado = _normalizar_endereco_entrega(
        payload.endereco_entrega if isinstance(payload.endereco_entrega, dict) else {}
    )
    if tipo_entrega == "delivery":
        endereco_entrega_normalizado = _aplicar_fallback_coordenadas_endereco(
            endereco_entrega_normalizado,
            restaurante.delivery_endereco_origem,
        )
        _validar_endereco_delivery(endereco_entrega_normalizado)

    pedido = Pedido(
        restaurante_id=restaurante.restaurante_id,
        mesa=mesa_pedido,
        tipo_entrega=tipo_entrega,
        cliente_nome=payload.cliente_nome.strip() if payload.cliente_nome else "",
        cliente_telefone=payload.cliente_telefone.strip() if payload.cliente_telefone else "",
        endereco_entrega_json=endereco_entrega_normalizado,
        itens=payload.itens,
        status="novo",
        total=total,
    )

    db.add(pedido)
    db.commit()
    db.refresh(pedido)

    return {"ok": True, "pedido_id": pedido.id, "restaurante_id": restaurante.restaurante_id}


@app.get("/api/public/pedidos/status")
def listar_status_pedidos_publico(
    slug: str = Query(...),
    pedido_ids: str = Query(...),
    db: Session = Depends(get_db),
):
    restaurante = get_restaurante_por_slug(db, slug.strip().lower())

    ids_parseados: list[int] = []
    for parte in str(pedido_ids or "").split(","):
        valor = parte.strip()
        if not valor:
            continue
        try:
            numero = int(valor)
            if numero > 0 and numero not in ids_parseados:
                ids_parseados.append(numero)
        except ValueError:
            continue

    if not ids_parseados:
        return {"ok": True, "statuses": []}

    ids_parseados = ids_parseados[:60]

    pedidos = db.query(Pedido).filter(
        Pedido.restaurante_id == restaurante.restaurante_id,
        Pedido.id.in_(ids_parseados),
    ).all()

    return {
        "ok": True,
        "statuses": [
            {
                "pedido_id": p.id,
                "status": p.status,
                "tipo_entrega": p.tipo_entrega,
                "updated_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in pedidos
        ],
    }


@app.get("/api/admin/entregadores/{slug}")
def listar_entregadores_admin(slug: str, token_acesso: str = Header(...), db: Session = Depends(get_db)):
    restaurante = garantir_isolamento(slug, token_acesso, db)
    entregadores = db.query(Entregador).filter(
        Entregador.restaurante_id == restaurante.restaurante_id
    ).order_by(Entregador.nome.asc()).all()

    limite_online = datetime.utcnow() - timedelta(minutes=5)

    retorno = []
    for e in entregadores:
        pedidos_em_entrega = db.query(Pedido).filter(
            Pedido.restaurante_id == restaurante.restaurante_id,
            Pedido.entregador_id == e.id,
            Pedido.tipo_entrega == "delivery",
            Pedido.status.in_(["em_entrega"]),
        ).order_by(Pedido.created_at.asc()).all()

        online = bool(
            e.ativo
            and e.ultima_atualizacao
            and e.ultima_atualizacao >= limite_online
        )
        em_entrega = len(pedidos_em_entrega) > 0

        retorno.append({
            "id": e.id,
            "nome": e.nome,
            "whatsapp": e.whatsapp,
            "email_login": e.email_login,
            "senha": e.senha_hash,
            "token_rastreamento": e.token_rastreamento,
            "ativo": e.ativo,
            "online": online,
            "em_entrega": em_entrega,
            "disponivel": bool(e.ativo) and online and not em_entrega,
            "corridas_abertas": len(pedidos_em_entrega),
            "pedido_ativo_id": pedidos_em_entrega[0].id if pedidos_em_entrega else None,
            "status_operacao": (
                "inativo" if not e.ativo else
                "em_entrega" if em_entrega else
                "online" if online else
                "offline"
            ),
            "ultima_latitude": e.ultima_latitude,
            "ultima_longitude": e.ultima_longitude,
            "ultima_precisao": e.ultima_precisao,
            "ultima_atualizacao": e.ultima_atualizacao.isoformat() if e.ultima_atualizacao else None,
        })

    return retorno


@app.post("/api/admin/entregadores/{slug}")
def criar_entregador_admin(
    slug: str,
    payload: EntregadorCreate,
    token_acesso: str = Header(...),
    db: Session = Depends(get_db),
):
    restaurante = garantir_isolamento(slug, token_acesso, db)
    whatsapp_limpo = "".join(ch for ch in payload.whatsapp if ch.isdigit())
    senha = (payload.senha or "").strip()

    if len(whatsapp_limpo) < 8:
        raise HTTPException(status_code=400, detail="WhatsApp inválido")
    if len(senha) < 4:
        raise HTTPException(status_code=400, detail="Senha inválida")

    existe_whatsapp = db.query(Entregador).filter(
        Entregador.restaurante_id == restaurante.restaurante_id,
        Entregador.whatsapp == whatsapp_limpo,
    ).first()
    if existe_whatsapp:
        raise HTTPException(status_code=400, detail="Telefone do entregador já cadastrado")

    entregador = Entregador(
        restaurante_id=restaurante.restaurante_id,
        nome=payload.nome.strip(),
        whatsapp=whatsapp_limpo,
        email_login=whatsapp_limpo,
        senha_hash=senha,
        token_rastreamento=secrets.token_urlsafe(24),
        ativo=True,
    )
    db.add(entregador)
    db.commit()
    db.refresh(entregador)

    return {
        "ok": True,
        "id": entregador.id,
        "nome": entregador.nome,
        "whatsapp": entregador.whatsapp,
        "login_telefone": entregador.whatsapp,
        "token_rastreamento": entregador.token_rastreamento,
    }


@app.patch("/api/admin/entregadores/{slug}/{entregador_id}")
def atualizar_entregador_admin(
    slug: str,
    entregador_id: int,
    payload: EntregadorUpdate,
    token_acesso: str = Header(...),
    db: Session = Depends(get_db),
):
    restaurante = garantir_isolamento(slug, token_acesso, db)
    entregador = db.get(Entregador, entregador_id)
    if not entregador or entregador.restaurante_id != restaurante.restaurante_id:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")

    if payload.whatsapp is not None or payload.email_login is not None or payload.senha is not None:
        raise HTTPException(
            status_code=403,
            detail="Credenciais do entregador são somente para consulta no painel admin",
        )

    if payload.nome is not None:
        entregador.nome = payload.nome.strip()
    if payload.ativo is not None:
        entregador.ativo = bool(payload.ativo)

    db.commit()
    return {"ok": True, "id": entregador.id}


def _excluir_entregador_admin_core(
    restaurante: Restaurante,
    entregador_id: int,
    db: Session,
):
    entregador = db.get(Entregador, entregador_id)
    if not entregador or entregador.restaurante_id != restaurante.restaurante_id:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")

    db.query(Pedido).filter(
        Pedido.restaurante_id == restaurante.restaurante_id,
        Pedido.entregador_id == entregador.id,
        Pedido.tipo_entrega == "delivery",
        Pedido.status.in_(["novo", "preparando", "pronto", "em_entrega"]),
    ).update(
        {
            Pedido.entregador_id: None,
            Pedido.lat_entregador: None,
            Pedido.long_entregador: None,
        },
        synchronize_session=False,
    )

    db.delete(entregador)
    db.commit()
    return {"ok": True, "id": entregador_id}


@app.delete("/api/admin/entregadores/{slug}/{entregador_id}")
def excluir_entregador_admin(
    slug: str,
    entregador_id: int,
    token_acesso: str = Header(...),
    db: Session = Depends(get_db),
):
    restaurante = garantir_isolamento(slug, token_acesso, db)
    return _excluir_entregador_admin_core(restaurante, entregador_id, db)


@app.post("/api/admin/entregadores/{slug}/{entregador_id}")
def excluir_entregador_admin_post(
    slug: str,
    entregador_id: int,
    token_acesso: str = Header(...),
    db: Session = Depends(get_db),
):
    restaurante = garantir_isolamento(slug, token_acesso, db)
    return _excluir_entregador_admin_core(restaurante, entregador_id, db)


@app.post("/api/public/entregadores/login")
def login_entregador_publico(payload: EntregadorLoginPayload, db: Session = Depends(get_db)):
    identificador = str(payload.restaurante or payload.slug or "").strip()
    slug = identificador.lower()
    telefone = "".join(ch for ch in str(payload.telefone or payload.email_login or "") if ch.isdigit())
    senha = (payload.senha or "").strip()

    if len(telefone) < 8:
        raise HTTPException(status_code=400, detail="Informe o telefone do entregador para login")

    restaurante: Restaurante | None = None
    entregador: Entregador | None = None

    if identificador:
        slug_convertido = slugify_nome(identificador)
        restaurante = db.query(Restaurante).filter(
            (Restaurante.slug == slug)
            | (Restaurante.slug == slug_convertido)
            | (func.lower(Restaurante.nome_unidade) == slug)
        ).first()
        if not restaurante:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        if not assinatura_ativa(restaurante):
            raise HTTPException(status_code=403, detail="Restaurante com assinatura inativa")

        plano_restaurante = (restaurante.plano or "basic").strip().lower()
        if plano_restaurante == "basic":
            raise HTTPException(
                status_code=403,
                detail="O plano Basic não inclui o módulo de entregadores. Faça upgrade para o plano Pro ou Enterprise.",
            )

        entregador = db.query(Entregador).filter(
            Entregador.restaurante_id == restaurante.restaurante_id,
            (Entregador.whatsapp == telefone) | (Entregador.email_login == telefone),
        ).first()
    else:
        candidatos = db.query(Entregador).filter(
            (Entregador.whatsapp == telefone) | (Entregador.email_login == telefone)
        ).all()
        if not candidatos:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")
        if len(candidatos) > 1:
            raise HTTPException(status_code=409, detail="Informe o nome do restaurante para concluir o login")

        entregador = candidatos[0]
        restaurante = db.query(Restaurante).filter(
            Restaurante.restaurante_id == entregador.restaurante_id
        ).first()
        if not restaurante:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")
        if not assinatura_ativa(restaurante):
            raise HTTPException(status_code=403, detail="Restaurante com assinatura inativa")

        plano_restaurante = (restaurante.plano or "basic").strip().lower()
        if plano_restaurante == "basic":
            raise HTTPException(
                status_code=403,
                detail="O plano Basic não inclui o módulo de entregadores. Faça upgrade para o plano Pro ou Enterprise.",
            )

    if entregador and (not str(entregador.whatsapp or '').strip() or not str(entregador.senha_hash or '').strip()):
        raise HTTPException(status_code=409, detail="Entregador sem acesso configurado. Atualize telefone e senha no painel admin.")

    if not entregador or senha != (entregador.senha_hash or ""):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    if not entregador.ativo:
        raise HTTPException(status_code=403, detail="Entregador inativo")

    _marcar_entregador_online(db, entregador, commit=True, intervalo_minimo_segundos=0)

    return {
        "ok": True,
        "restaurante": restaurante.nome_unidade,
        "slug": restaurante.slug,
        "restaurante_nome": restaurante.nome_unidade,
        "entregador": {
            "id": entregador.id,
            "nome": entregador.nome,
            "login_telefone": entregador.whatsapp,
            "email_login": entregador.email_login,
            "whatsapp": entregador.whatsapp,
            "foto_perfil_base64": entregador.foto_perfil_base64 or "",
        },
        "token_rastreamento": entregador.token_rastreamento,
    }


@app.get("/api/public/entregadores/{token_rastreamento}/perfil")
def obter_perfil_entregador_publico(
    token_rastreamento: str,
    db: Session = Depends(get_db),
):
    entregador = db.query(Entregador).filter(Entregador.token_rastreamento == token_rastreamento).first()
    if not entregador:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")

    _marcar_entregador_online(db, entregador, commit=True)

    restaurante = db.query(Restaurante).filter(
        Restaurante.restaurante_id == entregador.restaurante_id
    ).first()

    return {
        "ok": True,
        "entregador": {
            "id": entregador.id,
            "nome": entregador.nome,
            "login_telefone": entregador.whatsapp,
            "email_login": entregador.email_login,
            "whatsapp": entregador.whatsapp,
            "foto_perfil_base64": entregador.foto_perfil_base64 or "",
        },
        "restaurante": {
            "nome": restaurante.nome_unidade if restaurante else "",
            "slug": restaurante.slug if restaurante else "",
        },
    }


@app.patch("/api/public/entregadores/{token_rastreamento}/perfil")
def atualizar_perfil_entregador_publico(
    token_rastreamento: str,
    payload: EntregadorPerfilUpdatePayload,
    db: Session = Depends(get_db),
):
    entregador = db.query(Entregador).filter(Entregador.token_rastreamento == token_rastreamento).first()
    if not entregador:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")

    if payload.email_login is not None:
        telefone_login = "".join(ch for ch in str(payload.email_login or "") if ch.isdigit())
        if len(telefone_login) < 8:
            raise HTTPException(status_code=400, detail="Telefone de login inválido")
        existe = db.query(Entregador).filter(
            Entregador.restaurante_id == entregador.restaurante_id,
            Entregador.email_login == telefone_login,
            Entregador.id != entregador.id,
        ).first()
        if existe:
            raise HTTPException(status_code=400, detail="Telefone de login já está em uso")
        entregador.email_login = telefone_login
        entregador.whatsapp = telefone_login

    if payload.whatsapp is not None:
        whatsapp_limpo = "".join(ch for ch in payload.whatsapp if ch.isdigit())
        if len(whatsapp_limpo) < 8:
            raise HTTPException(status_code=400, detail="WhatsApp inválido")
        existe_whatsapp = db.query(Entregador).filter(
            Entregador.restaurante_id == entregador.restaurante_id,
            Entregador.whatsapp == whatsapp_limpo,
            Entregador.id != entregador.id,
        ).first()
        if existe_whatsapp:
            raise HTTPException(status_code=400, detail="WhatsApp já está em uso")
        entregador.whatsapp = whatsapp_limpo
        entregador.email_login = whatsapp_limpo

    if payload.nova_senha is not None:
        senha_atual = (payload.senha_atual or "").strip()
        if senha_atual != (entregador.senha_hash or ""):
            raise HTTPException(status_code=400, detail="Senha atual inválida")
        entregador.senha_hash = payload.nova_senha.strip()

    if payload.foto_perfil_base64 is not None:
        entregador.foto_perfil_base64 = str(payload.foto_perfil_base64 or "").strip()

    db.commit()
    db.refresh(entregador)

    return {
        "ok": True,
        "entregador": {
            "id": entregador.id,
            "nome": entregador.nome,
            "login_telefone": entregador.whatsapp,
            "email_login": entregador.email_login,
            "whatsapp": entregador.whatsapp,
            "foto_perfil_base64": entregador.foto_perfil_base64 or "",
        },
    }


@app.get("/api/public/entregadores/{token_rastreamento}")
def obter_entregador_publico(
    token_rastreamento: str,
    pedido_id: int | None = None,
    db: Session = Depends(get_db),
):
    entregador = db.query(Entregador).filter(Entregador.token_rastreamento == token_rastreamento).first()
    if not entregador:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")
    if not entregador.ativo:
        raise HTTPException(status_code=403, detail="Entregador inativo")

    _marcar_entregador_online(db, entregador, commit=True)

    restaurante = db.query(Restaurante).filter(
        Restaurante.restaurante_id == entregador.restaurante_id
    ).first()

    limite_online = datetime.utcnow() - timedelta(minutes=5)
    entregador_online = bool(
        entregador.ultima_atualizacao
        and entregador.ultima_atualizacao >= limite_online
    )

    _backfill_deliveries_sem_entregador(
        db,
        entregador.restaurante_id,
        preferido_id=entregador.id,
        limite=1,
    )

    resp: dict = {
        "ok": True,
        "nome": entregador.nome,
        "ativo": entregador.ativo,
        "online": entregador_online,
        "slug": restaurante.slug if restaurante else "",
        "restaurante_nome": restaurante.nome_unidade if restaurante else "",
        "restaurante_cidade": (restaurante.delivery_cidade if restaurante else "") or "",
        "restaurante_uf": (restaurante.delivery_uf if restaurante else "") or "",
    }

    pedido_ativo = db.query(Pedido).filter(
        Pedido.restaurante_id == entregador.restaurante_id,
        Pedido.entregador_id == entregador.id,
        Pedido.tipo_entrega == "delivery",
        Pedido.status.in_(["em_entrega"]),
    ).order_by(Pedido.id.desc()).first()

    if pedido_ativo:
        resp["pedido_ativo"] = {
            "id": pedido_ativo.id,
            "status": pedido_ativo.status,
            "cliente_nome": pedido_ativo.cliente_nome,
            "cliente_telefone": pedido_ativo.cliente_telefone,
        }
    else:
        resp["pedido_ativo"] = None

    resp["disponivel"] = resp["pedido_ativo"] is None
    resp["status_operacao"] = "disponivel" if resp["disponivel"] else "ocupado"

    # Se pedido_id fornecido, retorna endereços da corrida
    if pedido_id:
        pedido = db.get(Pedido, pedido_id)
        if pedido and pedido.restaurante_id == entregador.restaurante_id:
            resp["endereco_entrega"] = pedido.endereco_entrega_json or {}
            resp["endereco_restaurante"] = restaurante.delivery_endereco_origem if restaurante else ""
            resp["restaurante_nome"] = restaurante.nome_unidade if restaurante else ""
            resp["restaurante_cidade"] = (restaurante.delivery_cidade if restaurante else "") or ""
            resp["restaurante_uf"] = (restaurante.delivery_uf if restaurante else "") or ""
            resp["pedido_status"] = pedido.status
            resp["cliente_nome"] = pedido.cliente_nome
            resp["cliente_telefone"] = pedido.cliente_telefone

    return resp


@app.post("/api/public/entregadores/{token_rastreamento}/push-subscription")
def registrar_push_subscription_entregador_publico(
    token_rastreamento: str,
    payload: EntregadorPushSubscriptionPayload,
    db: Session = Depends(get_db),
):
    entregador = db.query(Entregador).filter(Entregador.token_rastreamento == token_rastreamento).first()
    if not entregador:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")

    endpoint = str(payload.endpoint or "").strip()
    p256dh = str((payload.keys or {}).get("p256dh") or "").strip()
    auth = str((payload.keys or {}).get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Subscription inválida")

    atual = _normalizar_subscriptions_push(entregador.push_subscriptions_json)
    novo_item = {
        "endpoint": endpoint,
        "keys": {
            "p256dh": p256dh,
            "auth": auth,
        },
    }

    filtrado = [item for item in atual if str(item.get("endpoint") or "").strip() != endpoint]
    filtrado.append(novo_item)
    entregador.push_subscriptions_json = filtrado
    db.commit()

    return {"ok": True, "inscricoes": len(filtrado)}


@app.post("/api/public/entregadores/{token_rastreamento}/push-subscription/remover")
def remover_push_subscription_entregador_publico(
    token_rastreamento: str,
    payload: EntregadorPushSubscriptionRemovePayload,
    db: Session = Depends(get_db),
):
    entregador = db.query(Entregador).filter(Entregador.token_rastreamento == token_rastreamento).first()
    if not entregador:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")

    endpoint = str(payload.endpoint or "").strip()
    atual = _normalizar_subscriptions_push(entregador.push_subscriptions_json)
    filtrado = [item for item in atual if str(item.get("endpoint") or "").strip() != endpoint]
    entregador.push_subscriptions_json = filtrado
    db.commit()

    return {"ok": True, "inscricoes": len(filtrado)}


@app.patch("/api/public/entregadores/{token_rastreamento}/pedidos/{pedido_id}/status")
def atualizar_status_pedido_entregador_publico(
    token_rastreamento: str,
    pedido_id: int,
    payload: EntregadorPedidoStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    entregador = db.query(Entregador).filter(Entregador.token_rastreamento == token_rastreamento).first()
    if not entregador:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")
    if not entregador.ativo:
        raise HTTPException(status_code=403, detail="Entregador inativo")

    pedido = db.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if pedido.restaurante_id != entregador.restaurante_id:
        raise HTTPException(status_code=403, detail="Pedido não pertence ao entregador")
    if (pedido.tipo_entrega or "").lower() != "delivery":
        raise HTTPException(status_code=400, detail="Pedido não é delivery")

    if not pedido.entregador_id:
        pedido.entregador_id = entregador.id

    if pedido.entregador_id != entregador.id:
        raise HTTPException(status_code=403, detail="Pedido vinculado a outro entregador")

    status_atual = (pedido.status or "").lower()
    status_novo = (payload.status or "").lower()
    restaurante = db.get(Restaurante, entregador.restaurante_id)
    notificacao_cliente = {"enviado": False, "motivo": "status_inalterado"}

    if status_novo == "em_entrega":
        if status_atual not in {"pronto", "em_entrega"}:
            raise HTTPException(status_code=409, detail="Pedido ainda não está pronto para iniciar corrida")

        pedido.status = "em_entrega"

        if status_atual != "em_entrega" and restaurante:
            api_base = _normalizar_base_url(str(request.base_url)) if request else ""
            frontend_base = _resolver_frontend_base_url(
                restaurante=restaurante,
                request=request,
                api_base_url=api_base,
            )

            link_cliente = ""
            if frontend_base:
                _, link_cliente = _montar_links_rastreamento(
                    restaurante=restaurante,
                    pedido=pedido,
                    token_rastreamento=(entregador.token_rastreamento or ""),
                    frontend_base_url=frontend_base,
                    api_base_url=api_base,
                )

            if link_cliente:
                notificacao_cliente = _enviar_link_cliente_apos_aceite_entregador(
                    restaurante=restaurante,
                    pedido=pedido,
                    link_cliente=link_cliente,
                )
            else:
                notificacao_cliente = {"enviado": False, "motivo": "link_cliente_indisponivel"}

    elif status_novo == "entregue":
        if status_atual != "em_entrega":
            raise HTTPException(status_code=409, detail="Pedido precisa estar em entrega para finalizar")
        pedido.status = "entregue"
        _backfill_deliveries_sem_entregador(
            db,
            entregador.restaurante_id,
            preferido_id=entregador.id,
            limite=1,
        )
    else:
        raise HTTPException(status_code=400, detail="Status inválido para o entregador")

    db.commit()

    return {
        "ok": True,
        "pedido_id": pedido.id,
        "status": pedido.status,
        "entregador_id": entregador.id,
        "whatsapp_cliente": notificacao_cliente,
    }


@app.post("/api/public/entregadores/{token_rastreamento}/localizacao")
def atualizar_localizacao_entregador(
    token_rastreamento: str,
    payload: EntregadorLocalizacaoPayload,
    db: Session = Depends(get_db),
):
    entregador = db.query(Entregador).filter(Entregador.token_rastreamento == token_rastreamento).first()
    if not entregador:
        raise HTTPException(status_code=404, detail="Entregador não encontrado")
    if not entregador.ativo:
        raise HTTPException(status_code=403, detail="Entregador inativo")

    entregador.ultima_latitude = payload.latitude
    entregador.ultima_longitude = payload.longitude
    entregador.ultima_precisao = payload.precisao
    entregador.ultima_atualizacao = datetime.utcnow()

    pedido_ativo = db.query(Pedido).filter(
        Pedido.restaurante_id == entregador.restaurante_id,
        Pedido.entregador_id == entregador.id,
        Pedido.tipo_entrega == "delivery",
        Pedido.status.in_(["em_entrega"]),
    ).order_by(Pedido.created_at.desc()).first()
    if pedido_ativo:
        pedido_ativo.lat_entregador = payload.latitude
        pedido_ativo.long_entregador = payload.longitude
    else:
        _backfill_deliveries_sem_entregador(
            db,
            entregador.restaurante_id,
            preferido_id=entregador.id,
            limite=1,
        )

    db.commit()

    return {"ok": True, "id": entregador.id, "atualizado_em": entregador.ultima_atualizacao.isoformat()}


@app.get("/api/admin/pedidos/{slug}")
def listar_pedidos_admin(slug: str, token_acesso: str = Header(...), db: Session = Depends(get_db)):
    restaurante_slug = garantir_isolamento(slug, token_acesso, db)

    _backfill_deliveries_sem_entregador(db, restaurante_slug.restaurante_id)

    pedidos = db.query(Pedido).filter(
        Pedido.restaurante_id == restaurante_slug.restaurante_id
    ).order_by(Pedido.created_at.desc()).all()

    return [
        {
            "id": p.id,
            "mesa": p.mesa,
            "tipo_entrega": p.tipo_entrega,
            "cliente_nome": p.cliente_nome,
            "cliente_telefone": p.cliente_telefone,
            "entregador_id": p.entregador_id,
            "endereco_entrega": p.endereco_entrega_json or {},
            "lat_entregador": p.lat_entregador,
            "long_entregador": p.long_entregador,
            "forma_pagamento": p.forma_pagamento or "",
            "status": p.status,
            "itens": p.itens,
            "total": float(p.total),
            "created_at": p.created_at.isoformat(),
        }
        for p in pedidos
    ]


@app.patch("/api/admin/pedidos/{slug}/{pedido_id}/status")
def atualizar_status_pedido_admin(
    slug: str,
    pedido_id: int,
    payload: PedidoStatusUpdate,
    token_acesso: str = Header(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    restaurante = garantir_isolamento(slug, token_acesso, db)
    pedido = db.get(Pedido, pedido_id)
    if not pedido or pedido.restaurante_id != restaurante.restaurante_id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado para este restaurante")

    status_anterior = (pedido.status or "").lower()
    pedido.status = payload.status
    status_novo = (payload.status or "").lower()

    if (pedido.tipo_entrega or "").lower() == "delivery" and payload.entregador_id:
        entregador_escolhido = db.get(Entregador, payload.entregador_id)
        if not entregador_escolhido or entregador_escolhido.restaurante_id != restaurante.restaurante_id:
            raise HTTPException(status_code=404, detail="Entregador selecionado não encontrado")
        if not entregador_escolhido.ativo:
            raise HTTPException(status_code=400, detail="Entregador selecionado está inativo")

        ocupado = db.query(Pedido).filter(
            Pedido.restaurante_id == restaurante.restaurante_id,
            Pedido.entregador_id == entregador_escolhido.id,
            Pedido.tipo_entrega == "delivery",
            Pedido.status.in_(["em_entrega"]),
            Pedido.id != pedido.id,
        ).first()
        if ocupado:
            raise HTTPException(status_code=409, detail="Entregador selecionado já está em outra entrega")

        pedido.entregador_id = entregador_escolhido.id

    if (pedido.tipo_entrega or "").lower() == "delivery" and status_novo == "em_entrega":
        endereco_normalizado = _normalizar_endereco_entrega(pedido.endereco_entrega_json or {})
        endereco_normalizado = _aplicar_fallback_coordenadas_endereco(
            endereco_normalizado,
            restaurante.delivery_endereco_origem,
        )
        _validar_endereco_delivery(endereco_normalizado)
        pedido.endereco_entrega_json = endereco_normalizado

    if (
        (pedido.tipo_entrega or "").lower() == "delivery"
        and not pedido.entregador_id
        and status_novo == "em_entrega"
    ):
        entregador_auto = _selecionar_entregador_automatico(db, restaurante.restaurante_id)
        if entregador_auto:
            pedido.entregador_id = entregador_auto.id

    if (
        (pedido.tipo_entrega or "").lower() == "delivery"
        and status_novo == "em_entrega"
        and not pedido.entregador_id
    ):
        raise HTTPException(
            status_code=409,
            detail="Nenhum entregador vinculado a este pedido. Selecione um entregador ativo antes de enviar para entrega.",
        )

    if payload.forma_pagamento is not None:
        pedido.forma_pagamento = payload.forma_pagamento
    db.commit()

    notificacao = {"enviado": False, "motivo": "status_inalterado"}
    if status_anterior != (payload.status or "").lower():
        notificacao = notificar_status_pedido_whatsapp(restaurante, pedido, payload.status)

    despacho_delivery = {
        "link_entregador": "",
        "link_cliente": "",
        "whatsapp": {
            "cliente": {"enviado": False, "motivo": "nao_aplicavel"},
            "motoboy": {"enviado": False, "motivo": "nao_aplicavel"},
        },
        "push": {"enviado": False, "motivo": "nao_aplicavel", "inscricoes": 0},
    }

    if (
        (pedido.tipo_entrega or "").lower() == "delivery"
        and status_anterior != status_novo
        and status_novo == "em_entrega"
    ):
        entregador = db.get(Entregador, pedido.entregador_id) if pedido.entregador_id else None
        if entregador and entregador.ativo:
            api_base = _normalizar_base_url(str(request.base_url)) if request else ""
            frontend_base = _resolver_frontend_base_url(
                restaurante=restaurante,
                request=request,
                api_base_url=api_base,
            )

            link_entregador = ""
            link_cliente = ""
            if frontend_base or api_base:
                link_entregador, link_cliente = _montar_links_rastreamento(
                    restaurante=restaurante,
                    pedido=pedido,
                    token_rastreamento=(entregador.token_rastreamento or ""),
                    frontend_base_url=frontend_base,
                    api_base_url=api_base,
                )

            whatsapp_envio = _enviar_mensagens_despacho_delivery(
                restaurante=restaurante,
                pedido=pedido,
                entregador=entregador,
                link_entregador=link_entregador,
                link_cliente=link_cliente,
            )
            push_envio = _enviar_push_entregador(
                pedido=pedido,
                entregador=entregador,
                link_entregador=link_entregador,
                nome_restaurante=(restaurante.nome_unidade or "Restaurante"),
            )

            if push_envio.get("inscricoes") and push_envio.get("enviado") is not None:
                db.commit()

            despacho_delivery = {
                "link_entregador": link_entregador,
                "link_cliente": link_cliente,
                "whatsapp": whatsapp_envio,
                "push": push_envio,
            }
        else:
            despacho_delivery = {
                "link_entregador": "",
                "link_cliente": "",
                "whatsapp": {
                    "cliente": {"enviado": False, "motivo": "entregador_invalido"},
                    "motoboy": {"enviado": False, "motivo": "entregador_invalido"},
                },
                "push": {"enviado": False, "motivo": "entregador_invalido", "inscricoes": 0},
            }

    return {
        "ok": True,
        "pedido_id": pedido_id,
        "status": payload.status,
        "entregador_id": pedido.entregador_id,
        "whatsapp_notificacao": notificacao,
        "delivery_despacho": despacho_delivery,
    }


@app.patch("/api/pedidos/{pedido_id}/localizacao")
def atualizar_localizacao_pedido(
    pedido_id: int,
    payload: PedidoLocalizacaoUpdate,
    db: Session = Depends(get_db),
):
    pedido = db.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    if (pedido.tipo_entrega or "").lower() != "delivery":
        raise HTTPException(status_code=400, detail="Localização só é permitida para pedido delivery")

    status_atual = (pedido.status or "").lower()
    if status_atual in {"entregue", "cancelado", "fechado"}:
        raise HTTPException(status_code=409, detail="Rastreamento encerrado para este pedido")

    if not pedido.entregador_id:
        raise HTTPException(status_code=400, detail="Pedido sem entregador vinculado")

    entregador = db.get(Entregador, pedido.entregador_id)
    if not entregador or entregador.restaurante_id != pedido.restaurante_id:
        raise HTTPException(status_code=404, detail="Entregador não encontrado para este pedido")

    token_payload = (payload.token_rastreamento or "").strip()
    if token_payload and token_payload != (entregador.token_rastreamento or ""):
        raise HTTPException(status_code=403, detail="Token de rastreamento inválido")

    pedido.lat_entregador = payload.latitude
    pedido.long_entregador = payload.longitude
    entregador.ultima_latitude = payload.latitude
    entregador.ultima_longitude = payload.longitude
    entregador.ultima_precisao = payload.precisao
    entregador.ultima_atualizacao = datetime.utcnow()
    db.commit()

    return {
        "ok": True,
        "pedido_id": pedido.id,
        "status": pedido.status,
        "lat_entregador": pedido.lat_entregador,
        "long_entregador": pedido.long_entregador,
        "atualizado_em": entregador.ultima_atualizacao.isoformat() if entregador.ultima_atualizacao else None,
    }


def _extrair_lat_lon_endereco(endereco: dict | None) -> tuple[float | None, float | None]:
    if not isinstance(endereco, dict):
        return None, None

    lat_val = (
        endereco.get("latitude")
        or endereco.get("lat")
        or endereco.get("latitude_destino")
        or endereco.get("lat_destino")
    )
    lon_val = (
        endereco.get("longitude")
        or endereco.get("lng")
        or endereco.get("lon")
        or endereco.get("long")
        or endereco.get("longitude_destino")
        or endereco.get("long_destino")
        or endereco.get("lon_destino")
    )

    try:
        lat_num = float(lat_val) if lat_val is not None else None
        lon_num = float(lon_val) if lon_val is not None else None
    except (TypeError, ValueError):
        return None, None

    if not _coordenada_valida(lat_num, lon_num):
        return None, None

    return lat_num, lon_num


def _chave_codigo_entregador(restaurante_id: str, telefone: str) -> str:
    return f"{restaurante_id}:{telefone}"


def _gerar_codigo_entregador() -> str:
    return str(secrets.randbelow(90000) + 10000)


def _normalizar_codigo_digitado(valor: str | None) -> str:
    return "".join(ch for ch in str(valor or "") if ch.isdigit())[:5]


def _limpar_codigos_expirados_entregador() -> None:
    agora = datetime.utcnow()
    expirados = [
        chave for chave, registro in ENTREGADOR_CODIGOS_CACHE.items()
        if not isinstance(registro, dict) or not registro.get("expira_em") or registro.get("expira_em") <= agora
    ]
    for chave in expirados:
        ENTREGADOR_CODIGOS_CACHE.pop(chave, None)


def _validar_codigo_entregador(restaurante_id: str, telefone: str, codigo_digitado: str) -> None:
    _limpar_codigos_expirados_entregador()
    chave = _chave_codigo_entregador(restaurante_id, telefone)
    registro = ENTREGADOR_CODIGOS_CACHE.get(chave) or {}
    codigo_salvo = str(registro.get("codigo") or "")
    expira_em = registro.get("expira_em")

    if not codigo_salvo or not expira_em or expira_em <= datetime.utcnow():
        ENTREGADOR_CODIGOS_CACHE.pop(chave, None)
        raise HTTPException(status_code=400, detail="Código expirado ou não solicitado. Gere um novo código.")

    if codigo_digitado != codigo_salvo:
        raise HTTPException(status_code=400, detail="Código de verificação inválido.")


@app.post("/api/public/entregadores/solicitar-codigo")
def solicitar_codigo_entregador_publico(
    payload: EntregadorCodigoSolicitacaoPayload,
    db: Session = Depends(get_db),
):
    identificador = str(payload.restaurante or payload.slug or "").strip()
    telefone = "".join(ch for ch in str(payload.telefone or "") if ch.isdigit())

    if not identificador:
        raise HTTPException(status_code=400, detail="Informe o restaurante para gerar o código")
    if len(telefone) < 8:
        raise HTTPException(status_code=400, detail="Informe um telefone válido")

    slug = identificador.lower()
    slug_convertido = slugify_nome(identificador)
    restaurante = db.query(Restaurante).filter(
        (Restaurante.slug == slug)
        | (Restaurante.slug == slug_convertido)
        | (func.lower(Restaurante.nome_unidade) == slug)
    ).first()
    if not restaurante:
        raise HTTPException(status_code=404, detail="Restaurante não encontrado")

    if not assinatura_ativa(restaurante):
        raise HTTPException(status_code=403, detail="Restaurante com assinatura inativa")

    existe = db.query(Entregador).filter(
        Entregador.restaurante_id == restaurante.restaurante_id,
        (Entregador.whatsapp == telefone) | (Entregador.email_login == telefone),
    ).first()
    if existe:
        raise HTTPException(status_code=400, detail="Telefone já cadastrado para este restaurante")

    codigo = _gerar_codigo_entregador()
    expira_em = datetime.utcnow() + timedelta(minutes=8)
    chave = _chave_codigo_entregador(restaurante.restaurante_id, telefone)
    ENTREGADOR_CODIGOS_CACHE[chave] = {
        "codigo": codigo,
        "expira_em": expira_em,
        "restaurante_id": restaurante.restaurante_id,
        "telefone": telefone,
    }

    mensagem = (
        f"Código de cadastro do entregador: {codigo}. "
        f"Validade: 8 minutos."
    )
    telefone_whatsapp = normalizar_telefone_whatsapp(telefone)
    envio = {"ok": False, "motivo": "whatsapp_desativado"}
    if restaurante.whatsapp_api_ativo:
        envio = enviar_whatsapp_cloud_message(
            phone_number_id=(restaurante.whatsapp_phone_number_id or "").strip(),
            access_token=(restaurante.whatsapp_access_token or "").strip(),
            telefone_destino=telefone_whatsapp,
            mensagem=mensagem,
        )

    return {
        "ok": True,
        "slug": restaurante.slug,
        "restaurante_nome": restaurante.nome_unidade,
        "telefone": telefone,
        "codigo_enviado_whatsapp": bool(envio.get("ok")),
        "codigo_copia": codigo,
        "expira_em": expira_em.isoformat(),
    }


@app.get("/api/public/pedidos/{pedido_id}/rastreamento")
def obter_rastreamento_pedido_publico(
    pedido_id: int,
    slug: str = Query(...),
    db: Session = Depends(get_db),
):
    restaurante = get_restaurante_por_slug(db, slug.strip().lower())
    pedido = db.get(Pedido, pedido_id)
    if not pedido or pedido.restaurante_id != restaurante.restaurante_id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    if (pedido.tipo_entrega or "").lower() != "delivery":
        raise HTTPException(status_code=400, detail="Pedido não é delivery")

    entregador = db.get(Entregador, pedido.entregador_id) if pedido.entregador_id else None
    status_atual = (pedido.status or "").lower()
    rastreamento_ativo = status_atual not in {"entregue", "cancelado", "fechado"}

    endereco_destino = _aplicar_fallback_coordenadas_endereco(
        pedido.endereco_entrega_json or {},
        restaurante.delivery_endereco_origem,
    )
    lat_destino, lon_destino = _extrair_lat_lon_endereco(endereco_destino)

    return {
        "ok": True,
        "pedido": {
            "id": pedido.id,
            "status": pedido.status,
            "cliente_nome": pedido.cliente_nome,
            "cliente_telefone": pedido.cliente_telefone,
            "rastreamento_ativo": rastreamento_ativo,
        },
        "entregador": {
            "id": entregador.id if entregador else None,
            "nome": entregador.nome if entregador else None,
            "ativo": entregador.ativo if entregador else False,
            "ultima_atualizacao": entregador.ultima_atualizacao.isoformat() if entregador and entregador.ultima_atualizacao else None,
            "lat": pedido.lat_entregador,
            "lon": pedido.long_entregador,
        },
        "restaurante": {
            "nome": restaurante.nome_unidade,
            "endereco": restaurante.delivery_endereco_origem,
            "google_maps_api_key": restaurante.delivery_google_maps_api_key,
            "cidade": restaurante.delivery_cidade,
            "uf": restaurante.delivery_uf,
        },
        "destino": {
            "endereco": endereco_destino,
            "lat": lat_destino,
            "lon": lon_destino,
        },
    }


@app.post("/api/public/entregadores/cadastro")
def cadastrar_entregador_publico(payload: EntregadorPublicCreatePayload, db: Session = Depends(get_db)):
    identificador = str(payload.restaurante or payload.slug or "").strip()
    nome = str(payload.nome or "").strip()
    telefone = "".join(ch for ch in str(payload.telefone or "") if ch.isdigit())
    senha = (payload.senha or "").strip()
    codigo_verificacao = _normalizar_codigo_digitado(payload.codigo_verificacao)

    if len(nome) < 2:
        raise HTTPException(status_code=400, detail="Informe o nome do entregador")
    if len(telefone) < 8:
        raise HTTPException(status_code=400, detail="Informe um telefone válido")
    if len(senha) < 4:
        raise HTTPException(status_code=400, detail="Informe uma senha válida")
    if len(codigo_verificacao) != 5:
        raise HTTPException(status_code=400, detail="Informe o código de verificação com 5 dígitos")
    if not identificador:
        raise HTTPException(status_code=400, detail="Informe o restaurante para concluir o cadastro")

    slug = identificador.lower()
    slug_convertido = slugify_nome(identificador)
    restaurante = db.query(Restaurante).filter(
        (Restaurante.slug == slug)
        | (Restaurante.slug == slug_convertido)
        | (func.lower(Restaurante.nome_unidade) == slug)
    ).first()
    if not restaurante:
        raise HTTPException(status_code=404, detail="Restaurante não encontrado")

    if not assinatura_ativa(restaurante):
        raise HTTPException(status_code=403, detail="Restaurante com assinatura inativa")

    _validar_codigo_entregador(restaurante.restaurante_id, telefone, codigo_verificacao)

    existe = db.query(Entregador).filter(
        Entregador.restaurante_id == restaurante.restaurante_id,
        (Entregador.whatsapp == telefone) | (Entregador.email_login == telefone),
    ).first()
    if existe:
        raise HTTPException(status_code=400, detail="Telefone já cadastrado para este restaurante")

    entregador = Entregador(
        restaurante_id=restaurante.restaurante_id,
        nome=nome,
        whatsapp=telefone,
        email_login=telefone,
        senha_hash=senha,
        token_rastreamento=secrets.token_urlsafe(24),
        ativo=True,
        ultima_atualizacao=datetime.utcnow(),
    )
    db.add(entregador)
    db.commit()
    db.refresh(entregador)
    ENTREGADOR_CODIGOS_CACHE.pop(_chave_codigo_entregador(restaurante.restaurante_id, telefone), None)

    return {
        "ok": True,
        "token_rastreamento": entregador.token_rastreamento,
        "slug": restaurante.slug,
        "restaurante_nome": restaurante.nome_unidade,
        "entregador": {
            "id": entregador.id,
            "nome": entregador.nome,
            "login_telefone": entregador.whatsapp,
            "whatsapp": entregador.whatsapp,
        },
    }


@app.post("/api/admin/restaurante/{slug}/whatsapp/teste")
def enviar_whatsapp_teste(
    slug: str,
    payload: WhatsAppTestePayload,
    token_acesso: str = Header(...),
    db: Session = Depends(get_db),
):
    restaurante = garantir_isolamento(slug, token_acesso, db)

    if not restaurante.whatsapp_api_ativo:
        raise HTTPException(status_code=400, detail="WhatsApp API está desativada")

    telefone_destino = normalizar_telefone_whatsapp(payload.telefone)
    if not telefone_destino:
        raise HTTPException(status_code=400, detail="Telefone inválido para WhatsApp")

    mensagem = (payload.mensagem or "").strip() or f"Teste de integração WhatsApp do {restaurante.nome_unidade}."
    envio = enviar_whatsapp_cloud_message(
        phone_number_id=(restaurante.whatsapp_phone_number_id or "").strip(),
        access_token=(restaurante.whatsapp_access_token or "").strip(),
        telefone_destino=telefone_destino,
        mensagem=mensagem,
    )

    if not envio.get("ok"):
        raise HTTPException(
            status_code=502,
            detail={
                "mensagem": "Falha ao enviar mensagem pelo WhatsApp",
                "erro": envio.get("erro"),
                "detalhes": envio.get("detalhes"),
            },
        )

    return {"ok": True, "telefone": telefone_destino, "resposta_api": envio.get("resposta", {})}


@app.get("/api/public/whatsapp/webhook")
def verificar_webhook_whatsapp(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
    db: Session = Depends(get_db),
):
    if hub_mode != "subscribe":
        raise HTTPException(status_code=400, detail="Modo de verificação inválido")

    restaurante = db.query(Restaurante).filter(
        Restaurante.whatsapp_api_ativo == True,
        Restaurante.whatsapp_verify_token == hub_verify_token,
    ).first()

    if not restaurante:
        raise HTTPException(status_code=403, detail="Verify token inválido")

    return PlainTextResponse(content=hub_challenge or "")


@app.post("/api/public/whatsapp/webhook")
async def receber_webhook_whatsapp(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return {"ok": True, "recebido": bool(payload)}


@app.patch("/api/admin/pedidos/{slug}/{pedido_id}/rastreio")
def vincular_rastreio_pedido_admin(
    slug: str,
    pedido_id: int,
    payload: PedidoRastreioUpdate,
    token_acesso: str = Header(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    restaurante = garantir_isolamento(slug, token_acesso, db)

    pedido = db.get(Pedido, pedido_id)
    if not pedido or pedido.restaurante_id != restaurante.restaurante_id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado para este restaurante")

    if (pedido.tipo_entrega or "").lower() != "delivery":
        raise HTTPException(status_code=400, detail="Rastreio só pode ser vinculado em pedidos delivery")

    entregador = db.get(Entregador, payload.entregador_id)
    if not entregador or entregador.restaurante_id != restaurante.restaurante_id:
        raise HTTPException(status_code=404, detail="Entregador não encontrado para este restaurante")

    if not entregador.ativo:
        raise HTTPException(status_code=400, detail="Entregador está inativo")

    pedido.entregador_id = entregador.id
    db.commit()

    api_base = _normalizar_base_url(str(request.base_url)) if request else ""
    frontend_base = _resolver_frontend_base_url(
        restaurante=restaurante,
        request=request,
        api_base_url=api_base,
    )

    link_entregador = f"entregador.html?slug={restaurante.slug}&pedido={pedido.id}&token={entregador.token_rastreamento}"
    link_cliente = f"rastreio_entrega.html?slug={restaurante.slug}&pedido={pedido.id}"
    if frontend_base or api_base:
        link_entregador, link_cliente = _montar_links_rastreamento(
            restaurante=restaurante,
            pedido=pedido,
            token_rastreamento=(entregador.token_rastreamento or ""),
            frontend_base_url=frontend_base,
            api_base_url=api_base,
        )

    return {
        "ok": True,
        "pedido_id": pedido.id,
        "entregador_id": entregador.id,
        "entregador_nome": entregador.nome,
        "token_rastreamento": entregador.token_rastreamento,
        "link_entregador": link_entregador,
        "links": {
            "entregador": link_entregador,
            "cliente": link_cliente,
        },
        "api_entregador_validar": f"/api/public/entregadores/{entregador.token_rastreamento}",
        "api_entregador_localizacao": f"/api/public/entregadores/{entregador.token_rastreamento}/localizacao",
    }


@app.post("/api/admin/pedidos/{slug}/{pedido_id}/despacho-automatico")
def despacho_automatico_delivery_admin(
    slug: str,
    pedido_id: int,
    payload: PedidoDespachoAutomaticoPayload,
    token_acesso: str = Header(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    restaurante = garantir_isolamento(slug, token_acesso, db)

    pedido = db.get(Pedido, pedido_id)
    if not pedido or pedido.restaurante_id != restaurante.restaurante_id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado para este restaurante")

    if (pedido.tipo_entrega or "").lower() != "delivery":
        raise HTTPException(status_code=400, detail="Despacho automático disponível apenas para delivery")

    status_atual = (pedido.status or "").lower()
    if status_atual not in {"pronto", "em_entrega"}:
        raise HTTPException(status_code=409, detail="Pedido ainda não está pronto para despacho automático")

    endereco_normalizado = _normalizar_endereco_entrega(pedido.endereco_entrega_json or {})
    endereco_normalizado = _aplicar_fallback_coordenadas_endereco(
        endereco_normalizado,
        restaurante.delivery_endereco_origem,
    )
    _validar_endereco_delivery(endereco_normalizado)
    pedido.endereco_entrega_json = endereco_normalizado

    entregador: Entregador | None = None
    if payload.entregador_id:
        entregador = db.get(Entregador, payload.entregador_id)
        if not entregador or entregador.restaurante_id != restaurante.restaurante_id:
            raise HTTPException(status_code=404, detail="Entregador selecionado não encontrado")
        if not entregador.ativo:
            raise HTTPException(status_code=400, detail="Entregador selecionado está inativo")
        ocupado = db.query(Pedido).filter(
            Pedido.restaurante_id == restaurante.restaurante_id,
            Pedido.entregador_id == entregador.id,
            Pedido.tipo_entrega == "delivery",
            Pedido.status.in_(["em_entrega"]),
            Pedido.id != pedido.id,
        ).first()
        if ocupado:
            entregador = None

    if not entregador:
        entregador = _selecionar_entregador_automatico(
            db,
            restaurante.restaurante_id,
            preferido_id=pedido.entregador_id,
        )

    if not entregador:
        raise HTTPException(status_code=409, detail="Nenhum entregador cadastrado, online e disponível para despacho automático")

    pedido.entregador_id = entregador.id
    pedido.status = "em_entrega"
    db.commit()
    db.refresh(pedido)

    frontend_base = _normalizar_base_url(payload.frontend_base_url)
    api_base = _normalizar_base_url(payload.api_base_url)

    if not api_base and request:
        api_base = _normalizar_base_url(str(request.base_url))
    frontend_base = _resolver_frontend_base_url(
        restaurante=restaurante,
        request=request,
        frontend_base_url=frontend_base,
        api_base_url=api_base,
    )

    link_entregador = ""
    link_cliente = ""
    if frontend_base or api_base:
        link_entregador, link_cliente = _montar_links_rastreamento(
            restaurante=restaurante,
            pedido=pedido,
            token_rastreamento=(entregador.token_rastreamento or ""),
            frontend_base_url=frontend_base,
            api_base_url=api_base,
        )

    whatsapp_envio = _enviar_mensagens_despacho_delivery(
        restaurante=restaurante,
        pedido=pedido,
        entregador=entregador,
        link_entregador=link_entregador,
        link_cliente=link_cliente,
    )
    push_envio = _enviar_push_entregador(
        pedido=pedido,
        entregador=entregador,
        link_entregador=link_entregador,
        nome_restaurante=(restaurante.nome_unidade or "Restaurante"),
    )

    if push_envio.get("inscricoes") and push_envio.get("enviado") is not None:
        db.commit()

    return {
        "ok": True,
        "pedido_id": pedido.id,
        "status": pedido.status,
        "entregador_id": entregador.id,
        "entregador": {
            "id": entregador.id,
            "nome": entregador.nome,
            "whatsapp": entregador.whatsapp,
            "token_rastreamento": entregador.token_rastreamento,
        },
        "links": {
            "entregador": link_entregador,
            "cliente": link_cliente,
        },
        "whatsapp": whatsapp_envio,
        "push": push_envio,
    }


@app.post("/api/pedidos/{pedido_id}/despachar")
@app.patch("/api/pedidos/{pedido_id}/despachar")
def despachar_pedido_admin_direto(
    pedido_id: int,
    slug: str = Query(...),
    payload: PedidoDespacharPayload | None = None,
    token_acesso: str = Header(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    payload_final = PedidoDespachoAutomaticoPayload(
        entregador_id=(payload.entregador_id if payload else None),
        frontend_base_url=(payload.frontend_base_url if payload else None),
        api_base_url=(payload.api_base_url if payload else None),
    )

    return despacho_automatico_delivery_admin(
        slug=slug,
        pedido_id=pedido_id,
        payload=payload_final,
        token_acesso=token_acesso,
        request=request,
        db=db,
    )


@app.post("/api/admin/pedidos/{slug}")
def criar_pedido_admin(
    slug: str,
    payload: AdminPedidoCreate,
    token_acesso: str = Header(...),
    db: Session = Depends(get_db),
):
    restaurante = garantir_isolamento(slug, token_acesso, db)

    total = Decimal("0.00")
    for item in payload.itens:
        qtd = Decimal(str(item.get("quantidade", 1)))
        preco = Decimal(str(item.get("preco_unitario", 0)))
        total += qtd * preco

    endereco_entrega_normalizado = _normalizar_endereco_entrega(
        payload.endereco_entrega if isinstance(payload.endereco_entrega, dict) else {}
    )
    if (payload.tipo_entrega or "").lower() == "delivery":
        endereco_entrega_normalizado = _aplicar_fallback_coordenadas_endereco(
            endereco_entrega_normalizado,
            restaurante.delivery_endereco_origem,
        )
        _validar_endereco_delivery(endereco_entrega_normalizado)

    pedido = Pedido(
        restaurante_id=restaurante.restaurante_id,
        mesa=payload.mesa,
        tipo_entrega=payload.tipo_entrega,
        cliente_nome=payload.cliente_nome.strip() if payload.cliente_nome else "",
        cliente_telefone=payload.cliente_telefone.strip() if payload.cliente_telefone else "",
        endereco_entrega_json=endereco_entrega_normalizado,
        itens=payload.itens,
        status=payload.status,
        total=total,
    )
    if (payload.tipo_entrega or "").lower() == "delivery" and (payload.status or "").lower() == "em_entrega":
        entregador_auto = _selecionar_entregador_automatico(db, restaurante.restaurante_id)
        if entregador_auto:
            pedido.entregador_id = entregador_auto.id

    db.add(pedido)
    db.commit()
    db.refresh(pedido)
    return {"ok": True, "pedido_id": pedido.id, "restaurante_id": pedido.restaurante_id}


@app.get("/api/admin/cardapio/{slug}")
def listar_cardapio_admin(slug: str, token_acesso: str = Header(...), db: Session = Depends(get_db)):
    restaurante = garantir_isolamento(slug, token_acesso, db)
    itens = db.query(Cardapio).filter(Cardapio.restaurante_id == restaurante.restaurante_id).order_by(Cardapio.id.desc()).all()
    return [
        {
            "id": item.id,
            "nome": item.nome,
            "preco": float(item.preco),
            "categoria": item.categoria,
            "descricao": item.descricao,
            "imagem": item.imagem_base64,
            "complementos": item.complementos_json or [],
            "disponivel": item.disponivel,
            "horario_inicio": item.horario_inicio,
            "horario_fim": item.horario_fim,
        }
        for item in itens
    ]


@app.post("/api/admin/cardapio")
def criar_item_cardapio(payload: CardapioCreate, db: Session = Depends(get_db)):
    restaurante = get_restaurante_por_token(db, payload.token_acesso)

    item = Cardapio(
        restaurante_id=restaurante.restaurante_id,
        nome=payload.nome,
        preco=payload.preco,
        categoria=payload.categoria,
        descricao=payload.descricao,
        imagem_base64=payload.imagem_base64,
        complementos_json=payload.complementos or [],
        disponivel=payload.disponivel,
        horario_inicio=payload.horario_inicio,
        horario_fim=payload.horario_fim,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    return {
        "ok": True,
        "id": item.id,
        "restaurante_id": item.restaurante_id,
        "nome": item.nome,
    }


@app.patch("/api/admin/cardapio/{slug}/{item_id}")
def editar_item_cardapio(
    slug: str,
    item_id: int,
    payload: CardapioUpdate,
    token_acesso: str = Header(...),
    db: Session = Depends(get_db),
):
    restaurante = garantir_isolamento(slug, token_acesso, db)
    item = db.get(Cardapio, item_id)
    
    if not item or item.restaurante_id != restaurante.restaurante_id:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    
    if payload.nome is not None:
        item.nome = payload.nome
    if payload.preco is not None:
        item.preco = payload.preco
    if payload.categoria is not None:
        item.categoria = payload.categoria
    if payload.descricao is not None:
        item.descricao = payload.descricao
    if payload.imagem_base64 is not None:
        item.imagem_base64 = payload.imagem_base64
    if payload.complementos is not None:
        item.complementos_json = payload.complementos
    if payload.disponivel is not None:
        item.disponivel = payload.disponivel
    if payload.horario_inicio is not None:
        item.horario_inicio = payload.horario_inicio
    if payload.horario_fim is not None:
        item.horario_fim = payload.horario_fim
    
    db.commit()
    return {"ok": True, "id": item.id, "nome": item.nome}


@app.delete("/api/admin/cardapio/{slug}/{item_id}")
def deletar_item_cardapio(
    slug: str,
    item_id: int,
    token_acesso: str = Header(...),
    db: Session = Depends(get_db),
):
    restaurante = garantir_isolamento(slug, token_acesso, db)
    item = db.get(Cardapio, item_id)
    
    if not item or item.restaurante_id != restaurante.restaurante_id:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    
    db.delete(item)
    db.commit()
    return {"ok": True, "id": item_id}


@app.get("/rastreio/{slug}/{pedido_id}")
def redirecionar_rastreio_publico(
    slug: str,
    pedido_id: int,
    request: Request,
    api: str | None = Query(default=None),
):
    api_base = _normalizar_base_url(api) if api else _normalizar_base_url(str(request.base_url))
    frontend_base = _resolver_frontend_base_url(
        restaurante=None,
        request=request,
        api_base_url=api_base,
    )

    slug_param = quote(slug, safe="")
    destino = f"/rastreio_entrega.html?slug={slug_param}&pedido={pedido_id}"
    if frontend_base:
        destino = f"{frontend_base}{destino}"

    if api_base:
        api_param = quote(api_base, safe="")
        separador = "&" if "?" in destino else "?"
        destino = f"{destino}{separador}api={api_param}"

    return RedirectResponse(url=destino, status_code=307)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.get("/api/public/contato-enterprise")
def contato_enterprise(slug: str = Query(...), db: Session = Depends(get_db)):
    """Retorna o WhatsApp de suporte enterprise — somente para clientes enterprise ativos."""
    restaurante = db.query(Restaurante).filter(Restaurante.slug == slug.strip().lower()).first()
    if not restaurante:
        raise HTTPException(status_code=404, detail="Restaurante não encontrado")
    if (restaurante.plano or "basic").strip().lower() != "enterprise":
        raise HTTPException(status_code=403, detail="Recurso disponível apenas no plano Enterprise")
    if not assinatura_ativa(restaurante):
        raise HTTPException(status_code=403, detail="Assinatura inativa")
    cfg = db.get(ConfigSistema, "saas_wpp_enterprise")
    wpp = (cfg.valor.strip() if cfg and cfg.valor else "").replace(" ", "").replace("-", "")
    if not wpp:
        raise HTTPException(status_code=503, detail="Contato enterprise não configurado ainda. Entre em contato diretamente com o suporte.")
    return {"ok": True, "whatsapp": wpp, "mensagem": "Contato direto com o dono da plataforma — exclusivo Enterprise."}


@app.get("/api/super-admin/config-enterprise")
def obter_config_enterprise(db: Session = Depends(get_db)):
    cfg = db.get(ConfigSistema, "saas_wpp_enterprise")
    return {"ok": True, "wpp_enterprise": (cfg.valor.strip() if cfg and cfg.valor else "")}


@app.post("/api/super-admin/config-enterprise")
def salvar_config_enterprise(payload: dict, db: Session = Depends(get_db)):
    wpp = str(payload.get("wpp_enterprise") or "").strip()
    obj = db.get(ConfigSistema, "saas_wpp_enterprise")
    if obj:
        obj.valor = wpp
    else:
        db.add(ConfigSistema(chave="saas_wpp_enterprise", valor=wpp))
    db.commit()
    return {"ok": True, "wpp_enterprise": wpp}


if os.getenv("VERCEL") != "1":
    app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="frontend")
