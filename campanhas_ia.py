import requests

# Segue o mesmo padrao de credenciais dos outros modulos: primeiro
# tenta o arquivo local (nunca vai pro Git), depois variavel de ambiente.
try:
    from credenciais_locais import GEMINI_API_KEY
except ImportError:
    import os
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Modelo gratuito do Gemini (camada free do Google AI Studio).
MODELO = "gemini-2.0-flash"
URL_BASE = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODELO}:generateContent"
)


def _montar_prompt(
    plataforma,
    produto,
    preco,
    comissao,
    vendas,
    link,
    observacoes,
):
    partes = [
        "Voce e uma criadora de conteudo de afiliada que divulga "
        "produtos de forma natural e autentica, sem exageros nem "
        "informacoes inventadas.",
        "",
        "Crie uma campanha de divulgacao para o produto abaixo, "
        "usando SOMENTE os dados fornecidos (nao invente preco, "
        "vendas, avaliacoes ou qualquer outro numero).",
        "",
        f"Produto: {produto}",
        f"Plataforma de origem: {plataforma}",
    ]

    if preco:
        partes.append(f"Preco: R$ {preco}")

    if comissao:
        partes.append(f"Comissao: {comissao}")

    if vendas:
        partes.append(f"Vendas: {vendas}")

    if link:
        partes.append(f"Link: {link}")

    if observacoes:
        partes.append(f"Observacoes adicionais: {observacoes}")

    partes += [
        "",
        "Gere a resposta EXATAMENTE neste formato, com estes titulos:",
        "",
        "LEGENDA INSTAGRAM:",
        "(texto curto e envolvente para o post/reels, ate 3 frases)",
        "",
        "ROTEIRO VIDEO (Shopee Video / Reels):",
        "(roteiro curto em 3 a 5 falas/cenas, para um video de 15-30s)",
        "",
        "DESCRICAO PINTEREST:",
        "(descricao otimizada para busca, ate 2 frases)",
        "",
        "HASHTAGS:",
        "(8 a 12 hashtags relevantes, separadas por espaco)",
    ]

    return "\n".join(partes)


def gerar_campanha(
    plataforma="",
    produto="",
    preco="",
    comissao="",
    vendas="",
    link="",
    observacoes="",
):
    """Gera o texto da campanha de divulgacao usando o Gemini.
    Levanta RuntimeError com mensagem amigavel em caso de falha -
    quem chama (o app) e responsavel por mostrar isso na tela."""

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "Chave da API do Gemini nao configurada. "
            "Adicione GEMINI_API_KEY em credenciais_locais.py "
            "(ou nos Secrets do GitHub, se for gerar o APK)."
        )

    if not produto:
        raise RuntimeError("Informe ao menos o nome do produto.")

    prompt = _montar_prompt(
        plataforma, produto, preco, comissao, vendas, link, observacoes
    )

    corpo = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 600,
        },
    }

    try:
        resposta = requests.post(
            f"{URL_BASE}?key={GEMINI_API_KEY}",
            json=corpo,
            timeout=30,
        )
    except requests.RequestException as erro:
        raise RuntimeError(f"Erro de conexao com o Gemini: {erro}")

    if resposta.status_code == 429:
        raise RuntimeError(
            "Limite gratuito do Gemini atingido no momento. "
            "Aguarde um pouco e tente novamente."
        )

    if resposta.status_code != 200:
        raise RuntimeError(
            f"Erro do Gemini (HTTP {resposta.status_code}): "
            f"{resposta.text[:200]}"
        )

    dados = resposta.json()

    try:
        texto = (
            dados["candidates"][0]
            ["content"]["parts"][0]["text"]
        )
    except (KeyError, IndexError):
        motivo_bloqueio = (
            dados.get("candidates", [{}])[0].get("finishReason")
            if dados.get("candidates")
            else dados.get("promptFeedback", {}).get("blockReason")
        )
        raise RuntimeError(
            "O Gemini nao retornou texto "
            f"(motivo: {motivo_bloqueio or 'desconhecido'})."
        )

    return texto.strip()
