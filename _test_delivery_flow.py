import json
import sys
from urllib import request, error

BASE = "http://127.0.0.1:8000"
CREDS = [
    {"email_admin": "walterjunnys@gmail.com", "senha": "wj92486656"},
    {"email_admin": "dono@restauranteonline.com", "senha": "dono1234"},
]

def http_json(method: str, url: str, payload=None, timeout=20):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = body
            return resp.status, parsed
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = body
        return e.code, parsed


def main():
    status, health = http_json("GET", f"{BASE}/health")
    print("HEALTH", status, health)
    if status != 200:
        raise SystemExit("API não respondeu em /health")

    login_data = None
    for cred in CREDS:
        code, data = http_json("POST", f"{BASE}/api/admin/auth/login", cred)
        if code == 200 and isinstance(data, dict) and data.get("slug"):
            login_data = data
            print("LOGIN_OK", data.get("email_admin"), "slug=", data.get("slug"))
            break

    if not login_data:
        raise SystemExit("Falha no login com credenciais conhecidas")

    slug = login_data["slug"]
    code, pedidos_payload = http_json("GET", f"{BASE}/api/admin/pedidos/{slug}")
    if code != 200:
        raise SystemExit(f"Falha ao carregar pedidos: {code} {pedidos_payload}")

    if isinstance(pedidos_payload, dict):
        pedidos = pedidos_payload.get("pedidos") or pedidos_payload.get("items") or []
    elif isinstance(pedidos_payload, list):
        pedidos = pedidos_payload
    else:
        pedidos = []

    if not pedidos:
        raise SystemExit("Nenhum pedido encontrado para teste")

    escolhido = None
    for p in pedidos:
        txt = " ".join(str(p.get(k, "")).lower() for k in ("tipo_entrega", "entrega", "metodo_entrega", "status"))
        if "delivery" in txt:
            escolhido = p
            break
    if not escolhido:
        escolhido = pedidos[0]

    pedido_id = escolhido.get("id")
    status_antigo = escolhido.get("status")
    print("PEDIDO", pedido_id, "status_antigo=", status_antigo)

    code, patch_resp = http_json(
        "PATCH",
        f"{BASE}/api/admin/pedidos/{slug}/{pedido_id}/status",
        {"status": "em_entrega"},
    )
    print("PATCH_CODE", code)
    print("PATCH_BODY", json.dumps(patch_resp, ensure_ascii=False, indent=2))

    if code != 200:
        raise SystemExit("PATCH status falhou")

    dd = patch_resp.get("delivery_despacho") if isinstance(patch_resp, dict) else None
    if dd:
        print("DELIVERY_DESPACHO_PRESENTE", True)
        print("LINK_ENTREGADOR", dd.get("link_entregador") or dd.get("url_entregador"))
        print("WHATS_MOTOBOY", dd.get("whatsapp", {}).get("motoboy") if isinstance(dd.get("whatsapp"), dict) else None)
    else:
        print("DELIVERY_DESPACHO_PRESENTE", False)


if __name__ == "__main__":
    main()
