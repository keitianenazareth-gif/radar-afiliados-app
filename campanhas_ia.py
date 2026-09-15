import requests

# Segue o mesmo padrao de credenciais dos outros modulos: primeiro
# tenta o arquivo local (nunca vai pro Git), depois variavel de ambiente.
try:
    from credenciais_locais import GEMINI_API_KEY
except ImportError:
    import os
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Modelo gratuito do Gemini (camada free do Google AI Studio).
# gemini-2.0-flash foi descontinuado pelo Google; 3.6-flash e' o
# substituto recomendado.
MODELO = "gemini-3.6-flash"
URL_BASE = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODELO}:generateContent"
)


# ---------------------------------------------------------------------------
# Metodo VEND.IA ADS: formula de copywriting (material da Keiti) usada
# pra guiar o Gemini a escrever ganchos/estrutura/CTA que realmente
# prendem atencao, em vez de uma descricao generica do produto.
# ---------------------------------------------------------------------------

_METODO_VENDIA = """
Siga o metodo VEND.IA ADS pra estruturar o texto:

FORMULA: GANCHO -> PROBLEMA/DESEJO -> DEMONSTRACAO -> BENEFICIO -> OFERTA -> CTA
(nem todo criativo precisa dos 6 blocos, mas comece SEMPRE por um gancho forte)

Regra de ouro: nao venda o video, venda a ideia. O gancho faz a pessoa
parar. A estrutura mantem o interesse. A oferta e o CTA dao direcao.

Exemplos de ganchos (adapte um deles ao produto, nao copie literal):
- "Eu nao esperava que isso funcionasse tao bem."
- "Se voce esta procurando [beneficio], olha isso."
- "Pare de fazer [erro/problema] desse jeito."
- "Eu descobri um jeito muito mais simples de [resultado]."
- "Olha o que da pra fazer com [produto]."
- "3 segundos e voce vai entender por que isso chama atencao."

Exemplos de CTA (adapte um, curto e direto):
- "Confira os detalhes."
- "Quero aproveitar."
- "Veja como funciona."
- "Descubra se faz sentido pra voce."
- "Comece agora."
""".strip()


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
        _METODO_VENDIA,
        "",
        "Gere a resposta EXATAMENTE neste formato, com estes titulos:",
        "",
        "LEGENDA INSTAGRAM:",
        "(comece com um gancho forte, ate 3 frases, termine com um CTA)",
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
            # O gemini-3.x "pensa" antes de responder e esses tokens
            # contam no limite; deixamos folga para nao cortar o texto.
            "maxOutputTokens": 2048,
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

    if resposta.status_code == 503:
        raise RuntimeError(
            "O Gemini esta com alta demanda no momento (HTTP 503). "
            "Aguarde alguns segundos e tente novamente."
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


# ---------------------------------------------------------------------------
# Roteiro estruturado para o gerador de video (web/video_campanha.py)
# ---------------------------------------------------------------------------

_ESQUEMA_ROTEIRO = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string"},
        "beneficio": {"type": "string"},
        "narracao": {"type": "string"},
        "cenas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "texto_tela": {"type": "string"},
                    "segundos": {"type": "number"},
                },
                "required": ["texto_tela", "segundos"],
            },
        },
    },
    "required": ["titulo", "beneficio", "narracao", "cenas"],
}


def gerar_roteiro_video(
    plataforma="",
    produto="",
    preco="",
    comissao="",
    vendas="",
    link="",
):
    """Pede ao Gemini um roteiro ENXUTO e ESTRUTURADO (JSON) para montar
    um video curto de 15-30s:

        {
          "titulo": "chamada curta (ate ~6 palavras)",
          "beneficio": "1 frase com o principal beneficio",
          "narracao": "texto corrido de 40-70 palavras para falar em ~20s",
          "cenas": [{"texto_tela": "frase curta", "segundos": 4}, ...]
        }

    Levanta RuntimeError com mensagem amigavel em caso de falha.
    """

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "Chave da API do Gemini nao configurada. "
            "Adicione GEMINI_API_KEY em credenciais_locais.py."
        )

    if not produto:
        raise RuntimeError("Informe ao menos o nome do produto.")

    dados_produto = [f"Produto: {produto}"]
    if plataforma:
        dados_produto.append(f"Plataforma: {plataforma}")
    if preco:
        dados_produto.append(f"Preco: R$ {preco}")
    if comissao:
        dados_produto.append(f"Comissao: {comissao}")
    if vendas:
        dados_produto.append(f"Vendas: {vendas}")
    if link:
        dados_produto.append(f"Link: {link}")

    prompt = (
        "Voce e uma criadora de conteudo de afiliada. Crie um roteiro "
        "para um video vertical curto (15 a 30 segundos) divulgando o "
        "produto abaixo. Use SOMENTE os dados fornecidos - nao invente "
        "preco, numeros, avaliacoes nem caracteristicas.\n\n"
        + "\n".join(dados_produto)
        + "\n\n" + _METODO_VENDIA + "\n\n"
        "Regras:\n"
        "- 'titulo': o GANCHO do roteiro, ate 6 palavras, pra parar o "
        "scroll (nao e so o nome do produto).\n"
        "- 'beneficio': 1 frase curta com o principal beneficio real.\n"
        "- 'narracao': texto corrido, 40 a 70 palavras, seguindo a "
        "formula gancho -> problema/desejo -> beneficio -> CTA, tom "
        "natural de conversa, pra ser lido em voz alta em ~20 "
        "segundos. Sem emojis, sem hashtags, sem marcadores.\n"
        "- 'cenas': 3 a 5 itens que acompanham a formula (comece pelo "
        "gancho, mostre o beneficio/demonstracao no meio, feche com "
        "oferta+CTA na ultima cena). Cada 'texto_tela' e uma frase "
        "MUITO curta (ate ~7 palavras) que aparece escrita na tela. "
        "'segundos' entre 3 e 6. A soma dos segundos deve ficar entre "
        "15 e 30."
    )

    corpo = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            # O gemini-3.x "pensa" antes de responder e esses tokens
            # contam no limite. O pensamento as vezes passa de 1800
            # tokens; com folga ampla o JSON nao sai truncado.
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
            "responseSchema": _ESQUEMA_ROTEIRO,
        },
    }

    import json
    import time as _time

    roteiro = None
    ultimo_erro = ""
    # O modelo ocasionalmente devolve JSON truncado/invalido; tenta de novo.
    for tentativa in range(3):
        try:
            resposta = requests.post(
                f"{URL_BASE}?key={GEMINI_API_KEY}", json=corpo, timeout=40
            )
        except requests.RequestException as erro:
            raise RuntimeError(f"Erro de conexao com o Gemini: {erro}")

        if resposta.status_code == 429:
            raise RuntimeError(
                "Limite gratuito do Gemini atingido no momento. "
                "Aguarde um pouco e tente novamente."
            )
        if resposta.status_code in (500, 503):
            ultimo_erro = f"HTTP {resposta.status_code}"
            _time.sleep(2 * (tentativa + 1))
            continue
        if resposta.status_code != 200:
            raise RuntimeError(
                f"Erro do Gemini (HTTP {resposta.status_code}): "
                f"{resposta.text[:200]}"
            )

        try:
            candidato = resposta.json()["candidates"][0]
            partes = candidato["content"]["parts"]
            texto = "".join(p.get("text", "") for p in partes)
            roteiro = json.loads(texto)
            break
        except (KeyError, IndexError, ValueError) as erro:
            ultimo_erro = str(erro) or "JSON invalido"
            _time.sleep(1)

    if roteiro is None:
        raise RuntimeError(
            "O Gemini nao retornou um roteiro valido. Tente novamente. "
            f"({ultimo_erro})"
        )

    cenas = [
        {
            "texto_tela": str(cena.get("texto_tela", "")).strip(),
            "segundos": max(2.0, min(8.0, float(cena.get("segundos", 4) or 4))),
        }
        for cena in roteiro.get("cenas", [])
        if str(cena.get("texto_tela", "")).strip()
    ]

    if not roteiro.get("narracao") or not cenas:
        raise RuntimeError("O roteiro veio incompleto (sem narracao ou cenas).")

    return {
        "titulo": str(roteiro.get("titulo", "")).strip() or produto,
        "beneficio": str(roteiro.get("beneficio", "")).strip(),
        "narracao": str(roteiro["narracao"]).strip(),
        "cenas": cenas,
    }
