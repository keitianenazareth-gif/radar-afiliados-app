"""
instagram_publish.py
---------------------
Publica Reels no Instagram (@clubedoquero) via Instagram Graph API,
usando a URL do video ja pronto (gerado pela Creatify).

Pre-requisitos (feitos manualmente uma vez no Meta for Developers):
  - Conta Instagram profissional (Business/Creator) [ja tem]
  - Pagina do Facebook vinculada [ja tem]
  - App criado no Meta for Developers com produto "Instagram"
  - Token de acesso de longa duracao com permissao instagram_content_publish
  - ID da conta profissional do Instagram (IG_USER_ID)

Variaveis de ambiente necessarias (configurar no Render, igual as outras):

    INSTAGRAM_USER_ID       -> o IG_USER_ID (numero, nao o @usuario)
    INSTAGRAM_ACCESS_TOKEN  -> token de longa duracao

Fluxo da API (2 passos):
  1. POST /{ig-user-id}/media  -> cria um "container" com o video,
     legenda etc. Retorna um creation_id. O video fica sendo
     processado pelo Instagram (pode levar de segundos a poucos
     minutos).
  2. POST /{ig-user-id}/media_publish -> publica de fato, usando o
     creation_id do passo 1 (so funciona quando o processamento
     terminar).
"""

import os
import time
import requests

INSTAGRAM_USER_ID = os.environ.get("INSTAGRAM_USER_ID")
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")

API_VERSION = "v22.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"


class InstagramPublishError(Exception):
    """Erro generico ao publicar no Instagram."""
    pass


def _checar_credenciais():
    if not INSTAGRAM_USER_ID or not INSTAGRAM_ACCESS_TOKEN:
        raise InstagramPublishError(
            "INSTAGRAM_USER_ID / INSTAGRAM_ACCESS_TOKEN nao configurados. "
            "Confira as variaveis de ambiente no Render."
        )


def criar_container_reel(
    video_url: str,
    legenda: str,
    compartilhar_no_feed: bool = True,
) -> str:
    """
    Passo 1: cria o container do Reel a partir da URL publica do
    video (a mesma URL que a Creatify devolveu).

    Retorna o creation_id (usado no passo 2).
    """
    _checar_credenciais()

    resp = requests.post(
        f"{BASE_URL}/{INSTAGRAM_USER_ID}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": legenda,
            "share_to_feed": "true" if compartilhar_no_feed else "false",
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        },
        timeout=60,
    )
    dados = resp.json()
    if resp.status_code >= 400 or "id" not in dados:
        raise InstagramPublishError(f"Erro ao criar container do Reel: {dados}")
    return dados["id"]


def checar_status_container(creation_id: str) -> str:
    """
    Consulta se o video ja terminou de ser processado pelo Instagram.
    Retorna o status_code: "IN_PROGRESS" | "FINISHED" | "ERROR" | "EXPIRED"
    """
    _checar_credenciais()
    resp = requests.get(
        f"{BASE_URL}/{creation_id}",
        params={
            "fields": "status_code",
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        },
        timeout=30,
    )
    dados = resp.json()
    if resp.status_code >= 400:
        raise InstagramPublishError(f"Erro ao checar status do container: {dados}")
    return dados.get("status_code", "IN_PROGRESS")


def publicar_container(creation_id: str) -> str:
    """
    Passo 2: publica de fato o Reel no Instagram.
    Retorna o ID da midia publicada (media_id).
    """
    _checar_credenciais()
    resp = requests.post(
        f"{BASE_URL}/{INSTAGRAM_USER_ID}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        },
        timeout=30,
    )
    dados = resp.json()
    if resp.status_code >= 400 or "id" not in dados:
        raise InstagramPublishError(f"Erro ao publicar o Reel: {dados}")
    return dados["id"]


def postar_reel(
    video_url: str,
    legenda: str,
    compartilhar_no_feed: bool = True,
    timeout_total_segundos: int = 180,
    intervalo_polling_segundos: int = 5,
) -> str:
    """
    Funcao principal de alto nivel: cria o container, espera o
    Instagram processar o video e publica. Retorna o media_id
    do Reel publicado.

    Uso (em app_web.py, no botao "Postar no Instagram" apos aprovar
    o video gerado pela Creatify):

        from instagram_publish import postar_reel

        try:
            media_id = postar_reel(url_video_creatify, legenda_gerada)
        except InstagramPublishError as e:
            # mostrar erro amigavel pro usuario
            ...
    """
    creation_id = criar_container_reel(video_url, legenda, compartilhar_no_feed)

    tempo_decorrido = 0
    while tempo_decorrido < timeout_total_segundos:
        status = checar_status_container(creation_id)

        if status == "FINISHED":
            return publicar_container(creation_id)

        if status in ("ERROR", "EXPIRED"):
            raise InstagramPublishError(
                f"Processamento do video falhou no Instagram (status={status})."
            )

        time.sleep(intervalo_polling_segundos)
        tempo_decorrido += intervalo_polling_segundos

    raise InstagramPublishError(
        f"Timeout esperando o Instagram processar o video (creation_id={creation_id})."
    )


if __name__ == "__main__":
    # Teste rapido pelo terminal:
    #   python instagram_publish.py "https://url-do-video.mp4" "Legenda do post #afiliado"
    import sys

    if len(sys.argv) < 3:
        print('Uso: python instagram_publish.py "<url_do_video>" "<legenda>"')
        sys.exit(1)

    url_video, legenda_post = sys.argv[1], sys.argv[2]
    print("Publicando Reel...")
    try:
        media_id = postar_reel(url_video, legenda_post)
        print(f"Reel publicado! media_id={media_id}")
    except InstagramPublishError as erro:
        print(f"Erro: {erro}")
