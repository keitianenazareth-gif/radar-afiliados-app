import re
import requests

# Cabecalho de navegador comum, para reduzir chance de bloqueio
# em sites que rejeitam requisicoes sem User-Agent. Isso NAO burla
# nenhuma protecao anti-bot mais forte (captcha, JS) - se o site
# bloquear mesmo assim, o app cai para preenchimento manual.
CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

PADRAO_OG_TITLE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
PADRAO_OG_IMAGE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
PADRAO_PRECO = re.compile(
    r'R\$\s*([\d]{1,3}(?:\.\d{3})*,\d{2})'
)


def buscar_metadados_link(url, timeout=10):
    """Tenta extrair nome, imagem e um preco aproximado de um link
    de produto colado manualmente. Retorna o que conseguir - nunca
    lanca excecao, so retorna campos vazios se falhar ou for bloqueado.
    """

    resultado = {
        "nome": "",
        "imagem": "",
        "preco_texto": "",
        "sucesso": False,
        "motivo": "",
    }

    if not url or not url.strip().startswith("http"):
        resultado["motivo"] = "Link invalido."
        return resultado

    try:
        resposta = requests.get(
            url.strip(),
            headers=CABECALHOS,
            timeout=timeout,
        )
    except requests.RequestException as erro:
        resultado["motivo"] = f"Nao consegui acessar o link: {erro}"
        return resultado

    if resposta.status_code != 200:
        resultado["motivo"] = (
            f"O site bloqueou a busca automatica (HTTP {resposta.status_code}). "
            "Preencha os dados manualmente."
        )
        return resultado

    html_pagina = resposta.text

    titulo = PADRAO_OG_TITLE.search(html_pagina)
    imagem = PADRAO_OG_IMAGE.search(html_pagina)
    preco = PADRAO_PRECO.search(html_pagina)

    if titulo:
        resultado["nome"] = titulo.group(1).strip()

    if imagem:
        resultado["imagem"] = imagem.group(1).strip()

    if preco:
        resultado["preco_texto"] = preco.group(1).strip()

    if resultado["nome"]:
        resultado["sucesso"] = True
    else:
        resultado["motivo"] = (
            "Nao encontrei os dados automaticamente. "
            "Preencha nome e preco manualmente."
        )

    return resultado
