"""
robo_automatico.py
-------------------
Roda o pipeline inteiro sozinho, sem ninguem clicar em nada:

    1. Escolhe um produto novo da Shopee (o melhor "nota de
       oportunidade" que ainda nao foi postado recentemente).
    2. Gera o roteiro do video e a legenda (Gemini - campanhas_ia.py,
       seguindo o metodo VEND.IA ADS: gancho -> problema/desejo ->
       beneficio -> CTA).
    3. Gera uma foto nova da personagem fixa (Maya ou Clara, alternando
       a cada post) segurando o produto real (Kairogen).
    4. Monta o video com essa cena (web/video_campanha.py).
    5. Salva o video na Galeria (Cloudinary + Upstash).
    6. Posta como Reel no Instagram (@clubedoquero).
    7. Guarda o link do produto no historico (Upstash), pra nao
       repetir o mesmo produto numa proxima rodada.

Uso manual (pra testar):
    python robo_automatico.py

No GitHub Actions isso roda sozinho, em horarios agendados - ver
.github/workflows/robo-automatico.yml

Credenciais necessarias (variaveis de ambiente / Secrets do GitHub -
as mesmas ja usadas no Render):
    SHOPEE_APP_ID, SHOPEE_SECRET
    GEMINI_API_KEY
    UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN
    CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
    INSTAGRAM_USER_ID, INSTAGRAM_ACCESS_TOKEN
"""

from __future__ import annotations

import json
import os
import re
import sys

import requests

from shopee import buscar_produtos, numero
from campanhas_ia import gerar_campanha, gerar_roteiro_video
from web import galeria
from web.instagram_publish import InstagramPublishError, postar_reel
from web.kairogen_media import PERSONAGENS
from web.video_campanha import montar_video

CHAVE_HISTORICO = "robo:historico_links"
MAX_HISTORICO = 300

# Alterna entre as personagens fixas a cada post - ver PERSONAGENS em
# web/kairogen_media.py.
_NOMES_PERSONAGENS = list(PERSONAGENS.items())

_CABECALHOS_CAMPANHA = [
    "LEGENDA INSTAGRAM:",
    "ROTEIRO VIDEO (Shopee Video / Reels):",
    "DESCRICAO PINTEREST:",
    "HASHTAGS:",
]


def _upstash_cmd(cmd: list):
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
    if not url or not token:
        raise RuntimeError("Upstash nao configurado (UPSTASH_REDIS_REST_URL/TOKEN).")
    resp = requests.post(
        url, headers={"Authorization": f"Bearer {token}"}, json=cmd, timeout=15
    )
    resp.raise_for_status()
    return resp.json().get("result")


def _carregar_historico() -> list:
    bruto = _upstash_cmd(["GET", CHAVE_HISTORICO])
    if not bruto:
        return []
    try:
        return json.loads(bruto)
    except json.JSONDecodeError:
        return []


def _salvar_historico(links: list) -> None:
    _upstash_cmd(["SET", CHAVE_HISTORICO, json.dumps(links[-MAX_HISTORICO:])])


def _buscar_itens_shopee() -> list:
    """Mesma fonte/formato usado pela Visao Geral do site (opcao '5')."""
    produtos = buscar_produtos("5", "", limite=20)
    itens = [
        {
            "plataforma": "Shopee",
            "nome": str(p.get("productName") or "Produto"),
            "preco": numero(p.get("priceMin")),
            "comissao_texto": f"R$ {numero(p.get('commission')):.2f}",
            "vendas": int(numero(p.get("sales"))),
            "nota": p.get("nota") or 0,
            "link": str(p.get("offerLink") or ""),
            "imagem": str(p.get("imageUrl") or ""),
        }
        for p in produtos
    ]
    itens.sort(key=lambda i: i["nota"], reverse=True)
    return itens


def _escolher_produto(historico: list) -> dict | None:
    for item in _buscar_itens_shopee():
        if item["link"] and item["imagem"] and item["link"] not in historico:
            return item
    return None


def _extrair_secao(texto: str, cabecalho: str, proximos: list) -> str:
    resto = "|".join(re.escape(h) for h in proximos) or r"\Z"
    padrao = rf"{re.escape(cabecalho)}\s*\n(.*?)(?:\n(?:{resto})|\Z)"
    m = re.search(padrao, texto, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _montar_legenda_instagram(texto_campanha: str, roteiro: dict, produto: dict) -> str:
    legenda = _extrair_secao(
        texto_campanha, _CABECALHOS_CAMPANHA[0], _CABECALHOS_CAMPANHA[1:]
    )
    hashtags = _extrair_secao(texto_campanha, _CABECALHOS_CAMPANHA[3], [])

    if not legenda:
        legenda = roteiro.get("beneficio") or roteiro.get("titulo") or produto["nome"]

    partes = [legenda]
    if produto.get("link"):
        partes.append(f"Link na bio / comentario: {produto['link']}")
    if hashtags:
        partes.append(hashtags)
    return "\n\n".join(p for p in partes if p)


def rodar() -> None:
    print("Robo automatico - iniciando...")

    try:
        historico = _carregar_historico()
    except RuntimeError as erro:
        print(f"Aviso: nao consegui ler o historico ({erro}). Seguindo sem checar duplicados.")
        historico = []

    produto = _escolher_produto(historico)
    if produto is None:
        print("Nenhum produto novo agora (tudo que achei ja foi postado recentemente). Encerrando sem postar.")
        return

    print(f"Produto escolhido: {produto['nome']} | nota={produto['nota']} | {produto['link']}")

    roteiro = gerar_roteiro_video(
        plataforma=produto["plataforma"],
        produto=produto["nome"],
        preco=str(produto["preco"]),
        comissao=produto["comissao_texto"],
        vendas=str(produto["vendas"]),
        link=produto["link"],
    )
    print("Roteiro do video gerado.")

    texto_campanha = gerar_campanha(
        plataforma=produto["plataforma"],
        produto=produto["nome"],
        preco=str(produto["preco"]),
        comissao=produto["comissao_texto"],
        vendas=str(produto["vendas"]),
        link=produto["link"],
        observacoes="Crie conteudo natural para afiliada. Nao invente informacoes.",
    )
    legenda = _montar_legenda_instagram(texto_campanha, roteiro, produto)
    print("Legenda gerada.")

    # modo_ia="personagem": o Kairogen gera a Maya/Clara segurando o
    # produto real (as duas fotos - personagem e produto - vao como
    # referencia, pra nao sair produto errado). Alterna a cada post.
    nome_personagem, url_personagem = _NOMES_PERSONAGENS[len(historico) % len(_NOMES_PERSONAGENS)]
    print(f"Personagem desta rodada: {nome_personagem}")
    caminho_mp4, _motor_tts = montar_video(
        produto, roteiro, modo_ia="personagem", personagem_url=url_personagem
    )
    print(f"Video gerado em {caminho_mp4}")

    item_galeria = galeria.adicionar_item(caminho_mp4, "video", nome_original=produto["nome"])
    galeria_url = item_galeria.get("url")
    print(f"Salvo na Galeria: {galeria_url}")

    if not galeria_url:
        raise RuntimeError("A Galeria nao devolveu uma URL publica do video - nao da pra postar no Instagram.")

    media_id = postar_reel(galeria_url, legenda)
    print(f"Postado no Instagram! media_id={media_id}")

    historico.append(produto["link"])
    try:
        _salvar_historico(historico)
    except RuntimeError as erro:
        print(f"Aviso: nao consegui salvar o historico ({erro}). O produto pode repetir numa proxima rodada.")

    print("Concluido com sucesso.")


if __name__ == "__main__":
    try:
        rodar()
    except (RuntimeError, InstagramPublishError) as erro:
        print(f"ERRO: {erro}")
        sys.exit(1)
