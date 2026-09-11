"""Geracao de imagem/video com IA (Kairogen) para o vídeo de campanha.

Dois modos, escolhidos por quem chama (ver web/video_campanha.py):

  fundo_ia(prompt)
      "Jeito A" - gera uma imagem de FUNDO/cenario com IA (~1 credito).
      A foto REAL do produto continua sendo colada por cima depois,
      sem nenhuma alteracao - o Kairogen so desenha o que fica atras.

  video_ia(imagem_produto_url, prompt)
      "Jeito B" - anima a FOTO REAL do produto: a URL da foto e enviada
      ao Kairogen como "primeiro quadro" (first_frame) e ele devolve um
      video de verdade a partir dela. A duracao fica travada em
      DURACAO_VIDEO_MAX segundos para o custo nunca passar de
      TETO_CREDITOS_VIDEO creditos (pedido explicito: teto de 50).

Os dois usam web.kairogen_auth.get_access_token() (token OAuth que se
renova sozinho) e a mesma API REST do Kairogen:
    POST /generations           -> cria a geracao (cobra os creditos na hora)
    GET  /generations/<id>      -> acompanha ate status = COMPLETED/FAILED
"""

from __future__ import annotations

import os
import time
import uuid

import requests

from web.kairogen_auth import get_access_token

API_BASE = "https://api.kairogen.ai"
PASTA_SAIDA = os.path.join(os.path.dirname(__file__), "static", "kairogen")

MODELO_FUNDO = "z-image-turbo"          # imagem, ~1 credito
MODELO_VIDEO = "grok-imagine-video-v1"  # video, image-to-video via first_frame

# grok-imagine-video-v1 cobra por segundo; 10s/720p = ~19 creditos
# (testado em 11/09/2026). Mantemos bem abaixo do teto de 50 pedido,
# com folga para o Kairogen reajustar preco sem estourar o orcamento.
DURACAO_VIDEO_MAX = 10
TETO_CREDITOS_VIDEO = 50


class KairogenMediaError(RuntimeError):
    """Falha ao gerar imagem/video pelo Kairogen - mensagem amigavel
    para mostrar na tela (quem chama nao precisa tratar outra excecao)."""


def _cabecalho():
    return {"Authorization": f"Bearer {get_access_token()}"}


def _criar_geracao(model: str, params: dict) -> tuple[str, int | None]:
    try:
        resp = requests.post(
            f"{API_BASE}/generations",
            headers={**_cabecalho(), "Content-Type": "application/json"},
            json={"model": model, "params": params},
            timeout=30,
        )
    except requests.RequestException as erro:
        raise KairogenMediaError(f"Erro de conexao com o Kairogen: {erro}") from erro

    corpo = resp.json() if resp.content else {}
    if resp.status_code not in (200, 201):
        msg = corpo.get("message") or corpo.get("code") or f"HTTP {resp.status_code}"
        raise KairogenMediaError(f"Kairogen recusou a geracao: {msg}")

    gid = corpo.get("generationId")
    if not gid:
        raise KairogenMediaError("Kairogen nao devolveu um ID de geracao.")
    return gid, corpo.get("creditsUsed") or corpo.get("cost")


def _aguardar_geracao(generation_id: str, timeout: int, intervalo: int = 5) -> str:
    """Espera a geracao terminar e devolve a URL do arquivo pronto."""
    limite = time.time() + timeout
    ultimo_status = None
    while time.time() < limite:
        try:
            resp = requests.get(
                f"{API_BASE}/generations/{generation_id}",
                headers=_cabecalho(),
                timeout=20,
            )
            corpo = resp.json() if resp.status_code == 200 else {}
        except (requests.RequestException, ValueError):
            corpo = {}

        status = corpo.get("status")
        ultimo_status = status or ultimo_status
        if status == "COMPLETED":
            urls = corpo.get("outputUrls") or []
            if not urls:
                raise KairogenMediaError("Kairogen concluiu mas nao devolveu arquivo.")
            return urls[0]
        if status == "FAILED":
            raise KairogenMediaError(
                f"Geracao falhou no Kairogen ({corpo.get('error') or corpo.get('errorCode') or 'motivo desconhecido'})."
            )
        time.sleep(intervalo)

    raise KairogenMediaError(
        f"O Kairogen demorou demais para responder (ultimo status: {ultimo_status or 'sem resposta'})."
    )


def _baixar(url: str, caminho: str) -> str:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "wb") as arquivo:
        arquivo.write(resp.content)
    return caminho


def fundo_ia(prompt: str, vertical: bool = True) -> str:
    """'Jeito A': gera um PNG de fundo/cenario com IA. Retorna o
    caminho do arquivo local. ~1 credito, ~1min."""
    if not prompt or not prompt.strip():
        raise KairogenMediaError("Prompt do fundo IA vazio.")
    params = {
        "prompt": prompt.strip(),
        "size": "9:16" if vertical else "16:9",
        "numImages": 1,
    }
    gid, _ = _criar_geracao(MODELO_FUNDO, params)
    url = _aguardar_geracao(gid, timeout=90)
    caminho = os.path.join(PASTA_SAIDA, f"fundo-{uuid.uuid4().hex[:10]}.png")
    return _baixar(url, caminho)


def video_ia(imagem_produto_url: str, prompt: str, duracao: int = DURACAO_VIDEO_MAX) -> str:
    """'Jeito B': anima a FOTO REAL do produto. 'imagem_produto_url'
    precisa ser uma URL publica (a foto que ja vem da Shopee/Mercado
    Livre/Amazon serve). Retorna o caminho do .mp4 baixado.

    Duracao travada em DURACAO_VIDEO_MAX (10s = ~19 creditos, testado
    em 11/09/2026) - bem abaixo do teto de 50 pedido."""
    if not imagem_produto_url:
        raise KairogenMediaError(
            "Este produto nao tem uma foto com URL publica - o video IA "
            "precisa de uma foto real pra animar."
        )
    if not prompt or not prompt.strip():
        raise KairogenMediaError("Prompt do video IA vazio.")

    duracao = max(1, min(int(duracao), DURACAO_VIDEO_MAX))
    params = {
        "prompt": prompt.strip(),
        "first_frame": imagem_produto_url,
        "duration": duracao,
        "resolution": "720p",
    }
    gid, creditos = _criar_geracao(MODELO_VIDEO, params)
    if creditos and creditos > TETO_CREDITOS_VIDEO:
        # So aconteceria se o Kairogen mudar o preco; a duracao travada
        # acima ja deveria impedir isso, mas nao ha como cancelar uma
        # cobranca que ja foi feita na criacao - so avisamos com clareza.
        raise KairogenMediaError(
            f"Atencao: essa geracao custou {creditos} creditos, acima do "
            f"teto configurado ({TETO_CREDITOS_VIDEO}). Avise quem mantem o "
            "app - o custo do Kairogen pode ter mudado."
        )
    url = _aguardar_geracao(gid, timeout=300)
    caminho = os.path.join(PASTA_SAIDA, f"video-{uuid.uuid4().hex[:10]}.mp4")
    return _baixar(url, caminho)
