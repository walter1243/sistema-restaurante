from datetime import date, timedelta
from decimal import Decimal
import os
import secrets
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import Base, Restaurante


def normalizar_database_url(url: str) -> str:
    valor = (url or "").strip()
    if not valor:
        raise RuntimeError("DATABASE_URL nao informada")

    eh_postgres = valor.startswith("postgres://") or valor.startswith("postgresql://")
    if eh_postgres and "sslmode=" not in valor.lower():
        separador = "&" if "?" in valor else "?"
        valor = f"{valor}{separador}sslmode=require"

    return valor


DATABASE_URL = normalizar_database_url(
    os.getenv(
        "DATABASE_URL",
        "postgresql://admin:VI53LLZuzp98ahh38ufYLSCqh9LjofRi@dpg-d6uv27k50q8c739b59o0-a.oregon-postgres.render.com/foodos",
    )
)

EMAIL_ADMIN = (os.getenv("ADMIN_EMAIL") or "walterjunnys@gmail.com").strip().lower()
SENHA_ADMIN = (os.getenv("ADMIN_SENHA") or "wj92486656").strip()
NOME_UNIDADE = (os.getenv("ADMIN_UNIDADE") or "FoodOS Walter").strip()
SLUG = (os.getenv("ADMIN_SLUG") or "foodos-walter").strip().lower()

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)

# Garante que as tabelas existam antes de inserir credenciais.
Base.metadata.create_all(bind=engine)

session = Session()
try:
    restaurante = session.query(Restaurante).filter(Restaurante.email_admin == EMAIL_ADMIN).first()

    if restaurante:
        restaurante.senha_hash = SENHA_ADMIN
        restaurante.nome_unidade = restaurante.nome_unidade or NOME_UNIDADE
        restaurante.slug = restaurante.slug or SLUG
        restaurante.status_assinatura = "Ativo"
        restaurante.validade_assinatura = date.today() + timedelta(days=3650)
        if not (restaurante.token_acesso or "").strip():
            restaurante.token_acesso = secrets.token_urlsafe(24)
    else:
        slug_base = SLUG
        slug_final = slug_base
        indice = 1
        while session.query(Restaurante).filter(Restaurante.slug == slug_final).first():
            indice += 1
            slug_final = f"{slug_base}-{indice}"

        restaurante = Restaurante(
            restaurante_id=str(uuid.uuid4()),
            nome_unidade=NOME_UNIDADE,
            slug=slug_final,
            email_admin=EMAIL_ADMIN,
            senha_hash=SENHA_ADMIN,
            status_assinatura="Ativo",
            data_assinatura=date.today(),
            validade_assinatura=date.today() + timedelta(days=3650),
            token_acesso=secrets.token_urlsafe(24),
            valor_mensalidade=Decimal("0.00"),
        )
        session.add(restaurante)

    session.commit()
    print("Admin do painel pronto com sucesso.")
    print(f"email={restaurante.email_admin}")
    print(f"slug={restaurante.slug}")
finally:
    session.close()
