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
import re
import time
import requests

INSTAGRAM_USER_ID = os.environ.get("INSTAGRAM_USER_ID", "").strip()
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()

API_VERSION = "v22.0"
MAX_ITENS_CARROSSEL = 10
# Token do "login pelo Instagram" (comeca com IG) so funciona neste endereco;
# token do login pelo Facebook usa o outro.
_HOST = "graph.instagram.com" if INSTAGRAM_ACCESS_TOKEN.startswith("IG") else "graph.facebook.com"
BASE_URL = f"https://{_HOST}/{API_VERSION}"


class InstagramPublishError(Exception):
    """Erro generico ao publicar no Instagram."""
    pass


def _checar_credenciais():
    if not INSTAGRAM_USER_ID or not INSTAGRAM_ACCESS_TOKEN:
        raise InstagramPublishError(
            "INSTAGRAM_USER_ID / INSTAGRAM_ACCESS_TOKEN nao configurados. "
            "Confira as variaveis de ambiente no Render."
        )


def status_conta() -> dict:
    """So leitura: confere se o token funciona e qual conta ele publica
    (nao posta nada). A mensagem de erro vem do JSON da Meta, sem a URL,
    pra nao mostrar o token."""
    _checar_credenciais()
    resp = requests.get(
        f"{BASE_URL}/{INSTAGRAM_USER_ID}",
        params={
            "fields": "username,followers_count,media_count",
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        },
        timeout=30,
    )
    dados = resp.json()
    if resp.status_code >= 400:
        erro = dados.get("error", {})
        raise InstagramPublishError(
            f"Meta recusou (HTTP {resp.status_code}, codigo {erro.get('code')}): "
            f"{erro.get('message', 'sem detalhe')}"
        )
    return {campo: dados.get(campo) for campo in ("username", "followers_count", "media_count")}


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
        raise InstagramPublishError(f"Erro ao publicar: {dados}")
    return dados["id"]


def url_para_foto(url: str) -> str:
    """O Instagram so aceita foto JPEG. O Cloudinary (Galeria) converte sozinho
    quando o endereco termina em .jpg."""
    if "res.cloudinary.com" in url and "/image/upload/" in url:
        return re.sub(r"\.(png|webp|heic|heif|gif|jpeg|avif)(\?.*)?$", ".jpg", url, flags=re.IGNORECASE)
    return url


def _criar_container(campos: dict, descricao: str) -> str:
    _checar_credenciais()
    resp = requests.post(
        f"{BASE_URL}/{INSTAGRAM_USER_ID}/media",
        data={**campos, "access_token": INSTAGRAM_ACCESS_TOKEN},
        timeout=60,
    )
    dados = resp.json()
    if resp.status_code >= 400 or "id" not in dados:
        erro = dados.get("error", {}) if isinstance(dados, dict) else {}
        raise InstagramPublishError(
            f"Meta recusou {descricao}: {erro.get('error_user_msg') or erro.get('message') or dados}"
        )
    return dados["id"]


def _esperar_container(creation_id: str, limite_segundos: int = 180) -> None:
    decorrido = 0
    while decorrido < limite_segundos:
        status = checar_status_container(creation_id)
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise InstagramPublishError(f"O Instagram não conseguiu processar o arquivo (status={status}).")
        time.sleep(3)
        decorrido += 3
    raise InstagramPublishError("O Instagram demorou demais para processar o arquivo.")


def _item_do_carrossel(item: dict) -> str:
    if item.get("tipo") == "video":
        campos = {"media_type": "VIDEO", "video_url": item["url"]}
    else:
        campos = {"image_url": url_para_foto(item["url"])}
    return _criar_container({**campos, "is_carousel_item": "true"}, "um item do carrossel")


def publicar_midias(itens: list, legenda: str) -> str:
    """Publica 1 video (Reel), 1 foto ou um carrossel (2 a 10 itens).
    Cada item: {"tipo": "video"|"imagem", "url": ...}. Devolve o media_id."""
    if not 1 <= len(itens) <= MAX_ITENS_CARROSSEL:
        raise InstagramPublishError(f"Escolha de 1 a {MAX_ITENS_CARROSSEL} fotos ou vídeos.")
    if len(itens) == 1:
        if itens[0].get("tipo") == "video":
            return postar_reel(itens[0]["url"], legenda)
        container = _criar_container({"image_url": url_para_foto(itens[0]["url"]), "caption": legenda}, "a foto")
        _esperar_container(container)
        return publicar_container(container)
    filhos = [_item_do_carrossel(item) for item in itens]
    for filho in filhos:
        _esperar_container(filho, 120)
    container = _criar_container(
        {"media_type": "CAROUSEL", "children": ",".join(filhos), "caption": legenda}, "o carrossel"
    )
    _esperar_container(container)
    return publicar_container(container)


def dados_da_midia(media_id: str) -> dict:
    """Devolve shortcode (o codigo do post) e permalink (o link dele)."""
    _checar_credenciais()
    resp = requests.get(
        f"{BASE_URL}/{media_id}",
        params={"fields": "shortcode,permalink", "access_token": INSTAGRAM_ACCESS_TOKEN},
        timeout=30,
    )
    dados = resp.json()
    if resp.status_code >= 400:
        raise InstagramPublishError("Publicado, mas a Meta não devolveu o link do post.")
    return {"shortcode": dados.get("shortcode", ""), "permalink": dados.get("permalink", "")}


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
