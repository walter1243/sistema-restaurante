import os
from sqlalchemy import create_engine, text


def normalizar_database_url(url: str) -> str:
    valor = (url or "").strip()
    if not valor:
        raise RuntimeError("DATABASE_URL não foi informada.")

    eh_postgres = valor.startswith("postgres://") or valor.startswith("postgresql://")
    if not eh_postgres:
        return valor

    if "sslmode=" in valor.lower():
        return valor

    separador = "&" if "?" in valor else "?"
    return f"{valor}{separador}sslmode=require"


DATABASE_URL = normalizar_database_url(
    os.getenv(
        "DATABASE_URL",
        "postgresql://admin:VI53LLZuzp98ahh38ufYLSCqh9LjofRi@dpg-d6uv27k50q8c739b59o0-a.oregon-postgres.render.com/foodos",
    )
)

SUPER_ADMIN_NOME = (os.getenv("SUPER_ADMIN_NOME") or "Walter Junnys").strip()
SUPER_ADMIN_LOGIN = (os.getenv("SUPER_ADMIN_LOGIN") or "walterjunnys@gmail.com").strip().lower()
SUPER_ADMIN_SENHA = (os.getenv("SUPER_ADMIN_SENHA") or "wj92486656").strip()


engine = create_engine(DATABASE_URL, pool_pre_ping=True)

with engine.begin() as conn:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS config_sistema (
                chave VARCHAR(80) PRIMARY KEY,
                valor VARCHAR(2000) DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )

    conn.execute(
        text(
            """
            INSERT INTO config_sistema (chave, valor, updated_at)
            VALUES (:chave, :valor, CURRENT_TIMESTAMP)
            ON CONFLICT (chave)
            DO UPDATE SET valor = EXCLUDED.valor, updated_at = CURRENT_TIMESTAMP
            """
        ),
        [
            {"chave": "sa_nome_exibicao", "valor": SUPER_ADMIN_NOME},
            {"chave": "sa_email_login", "valor": SUPER_ADMIN_LOGIN},
            {"chave": "sa_senha", "valor": SUPER_ADMIN_SENHA},
        ],
    )

print("Super Gerente configurado com sucesso no banco.")
print(f"Login: {SUPER_ADMIN_LOGIN}")
