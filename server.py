import os
import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

mcp = FastMCP("estoque-now")

BASE_URL = "https://api.estoquenow.com.br"
CLIENT_ID = os.environ["ESTOQUE_CLIENT_ID"]
CLIENT_SECRET = os.environ["ESTOQUE_CLIENT_SECRET"]


async def _get_token() -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{BASE_URL}/v1/oauth2/token",
            json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
        )
        r.raise_for_status()
        return r.json()["data"]["token"]


def _clean_image_url(url: str) -> str:
    if "timthumb" in url:
        url = url.split("timthumb?src=")[-1].split("&w=")[0]
    return url


@mcp.tool()
async def buscar_itens_disponiveis(query: str, data_evento: str) -> str:
    """
    Busca itens disponíveis para locação no Studio Paty Pickler Locações.

    Regras de uso:
    - Inclua SEMPRE o tipo de peça na query (ex: 'mesa batizado', 'biombo jardim encantado').
    - NUNCA use só o tema (ex: nunca 'batizado' sem o tipo de peça).
    - data_evento no formato DD/MM/AAAA.
    - Sequência obrigatória: 1ª busca = mesa, 2ª = biombo/painel, 3ª em diante = complementos.
    - NUNCA comece por vasos, flores ou acessórios.
    """
    token = await _get_token()

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE_URL}/v1/inventory/availability",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "search": query,
                "start_date": data_evento,
                "end_date": data_evento,
                "management_type": "rent",
                "page": 1,
                "per_page": 5,
                "only_in_stock": 1,
                "sort_by": "unit_price",
                "sort_order": "desc",
            },
        )
        r.raise_for_status()
        data = r.json()

    items = data.get("data", {}).get("items", [])
    total = data.get("recordsFiltered", 0)

    if not items:
        return f"Nenhum item encontrado para '{query}' na data {data_evento}. Tente outra variação (ex: 'mesa provençal', 'aparador')."

    lines = [f"Total disponível: {total} itens para '{query}' em {data_evento}.\n"]

    for i, item in enumerate(items[:5], 1):
        name = item.get("name", "")
        price = item.get("unit_price", "")
        qty = item.get("qtd_available", 0)
        img = _clean_image_url(item.get("url_image", ""))

        lines.append(f"{i}. {name} — R${price} (qty: {qty})")
        if i == 1 and img:
            lines.append(f"   foto: {img}")

    return "\n".join(lines)


async def health(request: Request):
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp_app = mcp.streamable_http_app()

    app = Starlette(
        routes=[
            Route("/health", health),
            Mount("/", app=mcp_app),
        ]
    )

    uvicorn.run(app, host="0.0.0.0", port=port)
