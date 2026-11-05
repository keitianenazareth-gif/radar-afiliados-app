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

INSTAGRAM_USER_ID = os.environ.get("INSTAGRAM_USER_ID", "").strip()
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()

API_VERSION = "v22.0"
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


def diagnostico_comentarios() -> dict:
    """So leitura: testa se o token consegue listar os comentarios do post
    mais recente. Devolve so contagens e codigos de erro: nenhum nome, texto
    de comentario ou token. Nao envia nada."""
    _checar_credenciais()

    def _ler(caminho: str, campos: str) -> tuple:
        resp = requests.get(
            f"{BASE_URL}/{caminho}",
            params={"fields": campos, "limit": 25, "access_token": INSTAGRAM_ACCESS_TOKEN},
            timeout=30,
        )
        dados = resp.json()
        if resp.status_code >= 400:
            erro = dados.get("error", {})
            return None, {"http": resp.status_code, "codigo": erro.get("code"),
                          "mensagem": erro.get("message", "sem detalhe")}
        return dados.get("data", []), None

    posts, erro = _ler(f"{INSTAGRAM_USER_ID}/media", "shortcode,timestamp,comments_count")
    if erro:
        return {"le_posts": False, "le_comentarios": False, "erro": erro}
    resultado = []
    for post in posts:
        comentarios, erro = _ler(f"{post['id']}/comments", "id")
        resultado.append({
            "post": post.get("shortcode"),
            "data": post.get("timestamp"),
            "contagem_do_post": post.get("comments_count"),
            "comentarios_que_a_api_mostrou": None if erro else len(comentarios),
            "erro": erro,
        })
    return {"le_posts": True, "posts": resultado}


POST_DO_TESTE = "DfVzEmJjki8"
_FOTOS = "https://clube-doquero.vercel.app/imagens/"
_GRUPO = "https://chat.whatsapp.com/Cni0DXs99cx6vwDDwCSX9f"


def _cartao(titulo, foto, url):
    return {
        "title": titulo,
        "image_url": _FOTOS + foto,
        "default_action": {"type": "web_url", "url": url},
        "buttons": [
            {"type": "web_url", "url": url, "title": "Ver produto"},
            {"type": "web_url", "url": _GRUPO, "title": "Entrar no grupo"},
        ],
    }


MENSAGEM_DO_TESTE = {
    "attachment": {
        "type": "template",
        "payload": {
            "template_type": "generic",
            "elements": [
                _cartao("Potes com tampa de bambu", "potes.jpg", "https://s.shopee.com.br/6AmKY9yYcL"),
                _cartao("Mini umidificador", "umidificador.jpg", "https://s.shopee.com.br/2LZbwslENm"),
                _cartao("Tapete felpudo", "tapete.jpg", "https://s.shopee.com.br/3qOQ9VIPxA"),
                _cartao("Prateleira de banheiro", "prateleira.jpg", "https://s.shopee.com.br/1BNeYjpfkh"),
                _cartao("Cesto dobrável", "cesto.jpg", "https://s.shopee.com.br/gRONiGKOC"),
            ],
        },
    }
}


def comentarios_do_teste() -> list:
    """So leitura: comentarios do post do teste (id, conta e texto)."""
    _checar_credenciais()
    resp = requests.get(
        f"{BASE_URL}/{INSTAGRAM_USER_ID}/media",
        params={"fields": "shortcode", "limit": 25, "access_token": INSTAGRAM_ACCESS_TOKEN},
        timeout=30,
    )
    dados = resp.json()
    if resp.status_code >= 400:
        raise InstagramPublishError(f"Meta recusou: {dados.get('error', {}).get('message', 'sem detalhe')}")
    post = next((p for p in dados.get("data", []) if p.get("shortcode") == POST_DO_TESTE), None)
    if not post:
        raise InstagramPublishError("Post do teste nao encontrado.")
    resp = requests.get(
        f"{BASE_URL}/{post['id']}/comments",
        params={"fields": "id,username,text", "access_token": INSTAGRAM_ACCESS_TOKEN},
        timeout=30,
    )
    dados = resp.json()
    if resp.status_code >= 400:
        raise InstagramPublishError(f"Meta recusou: {dados.get('error', {}).get('message', 'sem detalhe')}")
    return dados.get("data", [])


def responder_comentario_teste(comment_id: str) -> dict:
    """Envia a mensagem fixa do teste como resposta privada a um comentario
    do post do teste. So aceita comentario cujo texto seja a palavra QUERO."""
    alvo = next((c for c in comentarios_do_teste() if c.get("id") == comment_id), None)
    if not alvo:
        raise InstagramPublishError("Esse comentario nao esta no post do teste.")
    if (alvo.get("text") or "").strip(" !.\n").upper() != "QUERO":
        raise InstagramPublishError("O texto desse comentario nao e QUERO.")
    resp = requests.post(
        f"{BASE_URL}/{INSTAGRAM_USER_ID}/messages",
        headers={"Authorization": f"Bearer {INSTAGRAM_ACCESS_TOKEN}"},
        json={"recipient": {"comment_id": comment_id}, "message": MENSAGEM_DO_TESTE},
        timeout=30,
    )
    dados = resp.json()
    if resp.status_code >= 400:
        erro = dados.get("error", {})
        return {"enviado": False, "http": resp.status_code, "codigo": erro.get("code"),
                "subcodigo": erro.get("error_subcode"), "mensagem": erro.get("message", "sem detalhe")}
    return {"enviado": True, "message_id": dados.get("message_id")}


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
