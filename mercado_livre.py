import os
import requests

# Mesmo padrao de credenciais do shopee.py: primeiro tenta o arquivo
# local (gerado pelo GitHub Actions, nunca commitado), depois cai
# para variavel de ambiente.
try:
    from credenciais_locais import ML_ACCESS_TOKEN
except ImportError:
    ML_ACCESS_TOKEN = os.environ.get("ML_ACCESS_TOKEN", "")


def buscar_produtos_ml(termo="ofertas", limite=15):
    """Retorna produtos do Mercado Livre com nota de oportunidade,
    no mesmo formato usado pela Visao Geral do Radar Afiliados."""

    url = "https://api.mercadolibre.com/products/search"

    parametros = {
        "status": "active",
        "site_id": "MLB",
        "q": termo or "ofertas",
    }

    cabecalhos = {}

    if ML_ACCESS_TOKEN:
        cabecalhos["Authorization"] = f"Bearer {ML_ACCESS_TOKEN}"

    try:
        resposta = requests.get(
            url,
            params=parametros,
            headers=cabecalhos,
            timeout=15,
        )

        if resposta.status_code != 200:
            return []

        resultados = resposta.json().get("results") or []

    except requests.RequestException:
        return []

    produtos = []

    for item in resultados[:limite]:
        preco = float(item.get("price") or 0)
        original = float(item.get("original_price") or 0)
        vendidos = int(item.get("sold_quantity") or 0)

        desconto = 0
        if original > 0 and preco > 0:
            desconto = round(((original - preco) / original) * 100, 1)

        nota = min(vendidos / 50, 60) + min(desconto, 40)

        produtos.append({
            "plataforma": "Mercado Livre",
            "nome": str(item.get("title") or "Produto sem nome"),
            "preco": preco,
            "desconto": desconto,
            "vendas": vendidos,
            "comissao_texto": "Não informado",
            "nota": round(nota, 1),
            "link": str(item.get("permalink") or ""),
        })

    return produtos
