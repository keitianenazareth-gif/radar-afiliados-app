import os
import time
import json
import hashlib
import requests

# As credenciais vem, em ordem de prioridade:
# 1) de um arquivo local "credenciais_locais.py" (NUNCA vai pro Git,
#    e' criado automaticamente pelo GitHub Actions na hora de compilar
#    o APK, usando os "Secrets" do repositorio)
# 2) de variaveis de ambiente (util pra testar no Pydroid)
try:
    from credenciais_locais import SHOPEE_APP_ID as APP_ID
    from credenciais_locais import SHOPEE_SECRET as SECRET
except ImportError:
    APP_ID = os.environ.get("SHOPEE_APP_ID", "")
    SECRET = os.environ.get("SHOPEE_SECRET", "")

URL = "https://open-api.affiliate.shopee.com.br/graphql"


def numero(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def nota_oportunidade(produto):
    vendas = numero(produto.get("sales"))
    desconto = numero(produto.get("priceDiscountRate"))
    comissao = numero(produto.get("commissionRate"))
    extra = numero(produto.get("sellerCommissionRate"))
    valor = numero(produto.get("commission"))

    score_vendas = min(vendas / 500, 100)
    score_desconto = min(desconto, 100)
    score_comissao = min(comissao * 100, 100)
    score_extra = min(extra * 100, 100)
    score_valor = min(valor * 20, 100)

    pontuacao = (
        score_vendas * 0.30
        + score_desconto * 0.15
        + score_comissao * 0.25
        + score_extra * 0.20
        + score_valor * 0.10
    )
    return round(pontuacao, 1)


def classificar_nota(nota):
    if nota >= 45:
        return "FORTE"
    if nota >= 30:
        return "MEDIA"
    return "FRACA"


def motivos_produto(produto):
    motivos = []
    vendas = numero(produto.get("sales"))
    desconto = numero(produto.get("priceDiscountRate"))
    comissao = numero(produto.get("commission"))
    extra = numero(produto.get("sellerCommissionRate"))

    if vendas >= 50000:
        motivos.append(f"Muitas vendas: {int(vendas):,}".replace(",", "."))
    elif vendas >= 20000:
        motivos.append(f"Boa quantidade de vendas: {int(vendas):,}".replace(",", "."))

    if desconto >= 60:
        motivos.append(f"Desconto alto: {desconto:g}%")
    elif desconto >= 30:
        motivos.append(f"Bom desconto: {desconto:g}%")

    if comissao >= 3:
        motivos.append(f"Comissao excelente: R$ {comissao:.2f}")
    elif comissao >= 1:
        motivos.append(f"Boa comissao: R$ {comissao:.2f}")

    if extra >= 0.10:
        motivos.append("Comissao extra alta")

    return motivos


def _configuracao_opcao(opcao, termo=""):
    opcao = str(opcao)
    if opcao == "1":
        return "", 2, False
    if opcao == "2":
        return "", 5, True
    if opcao == "3":
        return "", 4, False
    if opcao == "4":
        if not termo.strip():
            raise ValueError("Digite o produto que deseja procurar.")
        return termo.strip(), 2, False
    if opcao == "5":
        return "", 2, False
    raise ValueError("Opcao invalida.")


def _consultar_api(keyword, sort_type, is_ams):
    if not APP_ID or not SECRET:
        raise RuntimeError(
            "Credenciais da Shopee nao configuradas. "
            "Defina SHOPEE_APP_ID e SHOPEE_SECRET."
        )

    # Escapa aspas no termo para nao quebrar a query GraphQL.
    keyword_seguro = keyword.replace("\\", "\\\\").replace('"', '\\"')

    query = f"""
{{
  productOfferV2(
    keyword: "{keyword_seguro}"
    page: 1
    limit: 20
    sortType: {sort_type}
    isAMSOffer: {str(is_ams).lower()}
  ) {{
    nodes {{
      itemId
      productName
      priceMin
      priceDiscountRate
      sales
      commissionRate
      sellerCommissionRate
      shopeeCommissionRate
      commission
      offerLink
      imageUrl
    }}
  }}
}}
"""

    payload = json.dumps(
        {"query": query},
        separators=(",", ":"),
        ensure_ascii=False,
    )

    timestamp = str(int(time.time()))
    base = APP_ID + timestamp + payload + SECRET
    signature = hashlib.sha256(base.encode("utf-8")).hexdigest()

    headers = {
        "Authorization": (
            f"SHA256 Credential={APP_ID}, "
            f"Timestamp={timestamp}, "
            f"Signature={signature}"
        ),
        "Content-Type": "application/json",
    }

    response = requests.post(
        URL,
        headers=headers,
        data=payload,
        timeout=30,
    )

    try:
        dados = response.json()
    except ValueError:
        raise RuntimeError(f"Resposta invalida da Shopee (HTTP {response.status_code}).")

    if "data" not in dados:
        erro = dados.get("errors") or dados
        raise RuntimeError(f"Erro da Shopee: {erro}")

    return dados.get("data", {}).get("productOfferV2", {}).get("nodes", []) or []


def buscar_produtos(opcao, termo="", limite=10):
    """Retorna uma lista estruturada de produtos pronta para a interface."""
    keyword, sort_type, is_ams = _configuracao_opcao(opcao, termo)
    produtos = _consultar_api(keyword, sort_type, is_ams)

    if str(opcao) == "1":
        produtos = sorted(
            produtos,
            key=lambda p: (
                numero(p.get("sales")),
                numero(p.get("commissionRate")),
            ),
            reverse=True,
        )

    elif str(opcao) == "2":
        produtos = sorted(
            produtos,
            key=lambda p: (
                numero(p.get("sellerCommissionRate")),
                numero(p.get("commission")),
            ),
            reverse=True,
        )

    elif str(opcao) == "3":
        produtos = sorted(
            produtos,
            key=lambda p: (
                numero(p.get("priceDiscountRate")),
                numero(p.get("sales")),
            ),
            reverse=True,
        )

    elif str(opcao) == "4":
        produtos = sorted(
            produtos,
            key=lambda p: numero(p.get("sales")),
            reverse=True,
        )

    elif str(opcao) == "5":
        produtos = sorted(
            produtos,
            key=nota_oportunidade,
            reverse=True,
        )

    resultado = []
    for posicao, produto in enumerate(produtos[:limite], start=1):
        item = dict(produto)
        item["posicao"] = posicao

        if str(opcao) == "5":
            nota = nota_oportunidade(item)
            item["nota"] = nota
            item["classificacao"] = classificar_nota(nota)
            item["motivos"] = motivos_produto(item)
        else:
            item["nota"] = None
            item["classificacao"] = ""
            item["motivos"] = []

        resultado.append(item)

    return resultado


def _imprimir_cli(produtos, opcao):
    print("\n===== MELHORES RESULTADOS =====")
    for produto in produtos:
        print(f"\n========== TOP {produto['posicao']} ==========")
        print("Produto:", produto.get("productName"))
        print("Preco: R$", produto.get("priceMin"))
        print("Desconto:", produto.get("priceDiscountRate"), "%")
        print("Vendas:", produto.get("sales"))
        print("Comissao total:", produto.get("commissionRate"))
        print("Comissao extra:", produto.get("sellerCommissionRate"))
        print("Valor comissao: R$", produto.get("commission"))

        if str(opcao) == "5":
            print("Nota oportunidade:", produto.get("nota"), "/100")
            print("Classificacao:", produto.get("classificacao"))
            if produto.get("motivos"):
                print("Motivos:")
                for motivo in produto["motivos"]:
                    print("-", motivo)

        print("Link:", produto.get("offerLink"))


def main():
    print("Escolha uma opcao:")
    print("1 - Produtos virais")
    print("2 - Maior comissao extra")
    print("3 - Promocoes")
    print("4 - Procurar produto")
    print("5 - Melhores oportunidades")

    opcao = input("Digite 1, 2, 3, 4 ou 5: ").strip()
    termo = ""
    if opcao == "4":
        termo = input("Digite o produto que deseja procurar: ").strip()

    try:
        produtos = buscar_produtos(opcao, termo)
        _imprimir_cli(produtos, opcao)
    except Exception as erro:
        print("Erro:", erro)


if __name__ == "__main__":
    main()
