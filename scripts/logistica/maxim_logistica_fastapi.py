"""Script de referência para módulo logístico FastAPI (FoodOS / estilo Maxim).

Este arquivo documenta como consumir os endpoints já implementados em main.py:
- GET  /api/public/logistica/{slug}/config-mapa
- POST /api/public/logistica/{slug}/cotar-frete
- GET  /api/public/logistica/geocode-reverso
- GET  /api/admin/logistica/{slug}/zonas
- POST /api/admin/logistica/{slug}/zonas
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

API_BASE = "https://sistema-restaurante-api.onrender.com"


@dataclass
class Ponto:
    lat: float
    lon: float


def obter_config_mapa(slug: str) -> dict[str, Any]:
    r = requests.get(f"{API_BASE}/api/public/logistica/{slug}/config-mapa", timeout=12)
    r.raise_for_status()
    return r.json()


def cotar_frete(slug: str, destino: Ponto) -> dict[str, Any]:
    r = requests.post(
        f"{API_BASE}/api/public/logistica/{slug}/cotar-frete",
        json={"lat": destino.lat, "lon": destino.lon},
        timeout=12,
    )
    r.raise_for_status()
    return r.json()


def geocode_reverso(ponto: Ponto) -> dict[str, Any]:
    r = requests.get(
        f"{API_BASE}/api/public/logistica/geocode-reverso",
        params={"lat": ponto.lat, "lon": ponto.lon},
        timeout=12,
    )
    r.raise_for_status()
    return r.json()


def main() -> None:
    slug = "solar"
    cfg = obter_config_mapa(slug)
    print("Config mapa:", cfg.get("ok"), "zonas:", len(cfg.get("zonas") or []))

    destino = Ponto(lat=-12.165, lon=-46.345)
    quote = cotar_frete(slug, destino)
    print("Frete:", quote)

    end = geocode_reverso(destino)
    print("Endereco:", end.get("display_name"))


if __name__ == "__main__":
    main()
