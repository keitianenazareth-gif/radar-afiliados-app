"""
video_campanha.py
------------------
Geracao de video de campanha usando a API da Creatify.

Substitui a versao antiga que renderizava o video localmente
(Gemini TTS + edge-tts + moviepy com fade entre cenas). Agora o
Radar Afiliados apenas manda o link do produto pra API da Creatify
e recebe de volta a URL do video pronto. Isso resolve dois
problemas ao mesmo tempo:

  1. Qualidade do video (a Creatify gera com avatar, cenas e
     legendas automaticas, muito melhor que o TTS + fade simples).
  2. Memoria no Render Free (o servidor da Creatify que renderiza,
     o nosso servidor so faz chamadas de API leves).

Requer duas variaveis de ambiente (configurar tambem no painel do
Render, do mesmo jeito que GEMINI_API_KEY):

    CREATIFY_API_ID   -> "X-API-ID" do painel da Creatify
    CREATIFY_API_KEY  -> "X-API-KEY" do painel da Creatify

Onde pegar: app.creatify.ai -> Settings -> API (depois de assinar
o plano Iniciante ou Pro, que ja libera a API).
"""

import os
import time
import requests

CREATIFY_API_ID = os.environ.get("CREATIFY_API_ID")
CREATIFY_API_KEY = os.environ.get("CREATIFY_API_KEY")

BASE_URL = "https://api.creatify.ai/api"

HEADERS = {
    "Content-Type": "application/json",
    "X-API-ID": CREATIFY_API_ID,
    "X-API-KEY": CREATIFY_API_KEY,
}


class CreatifyError(Exception):
    """Erro generico ao falar com a API da Creatify."""
    pass


def _checar_credenciais():
    if not CREATIFY_API_ID or not CREATIFY_API_KEY:
        raise CreatifyError(
            "CREATIFY_API_ID / CREATIFY_API_KEY nao configurados. "
            "Confira as variaveis de ambiente no Render."
        )


def registrar_link(url_produto: str) -> str:
    """
    Passo 1: manda o link do produto pra Creatify extrair as
    informacoes da pagina (imagens, descricao, etc).
    Retorna o link_id que sera usado no proximo passo.
    """
    _checar_credenciais()
    resp = requests.post(
        f"{BASE_URL}/links/",
        headers=HEADERS,
        json={"url": url_produto},
        timeout=60,
    )
    if resp.status_code >= 400:
        raise CreatifyError(f"Erro ao registrar link ({resp.status_code}): {resp.text}")

    dados = resp.json()
    link_id = dados.get("id")
    if not link_id:
        raise CreatifyError(f"Resposta inesperada ao registrar link: {dados}")
    return link_id


def criar_video(
    link_id: str,
    roteiro: str | None = None,
    plataforma: str = "Instagram",
    idioma: str = "pt",
    duracao_segundos: int = 15,
    proporcao: str = "9x16",
) -> str:
    """
    Passo 2: pede pra Creatify gerar o video a partir do link
    ja registrado. Se um roteiro (script) ja foi gerado antes pelo
    Gemini (campanhas_ia.py) e quiser reaproveitar, passe em
    `roteiro` que ele sera usado como override_script.

    Retorna o video_id (o video comeca com status "pending").
    """
    _checar_credenciais()

    payload = {
        "link": link_id,
        "visual_style": "DynamicProductTemplate",
        "script_style": "BenefitsV2",
        "aspect_ratio": proporcao,
        "video_length": duracao_segundos,
        "language": idioma,
        "target_platform": plataforma,
        "model_version": "aurora_v1_fast",
    }
    if roteiro:
        payload["override_script"] = roteiro

    resp = requests.post(
        f"{BASE_URL}/link_to_videos/",
        headers=HEADERS,
        json=payload,
        timeout=60,
    )
    if resp.status_code >= 400:
        raise CreatifyError(f"Erro ao criar video ({resp.status_code}): {resp.text}")

    dados = resp.json()
    video_id = dados.get("id")
    if not video_id:
        raise CreatifyError(f"Resposta inesperada ao criar video: {dados}")
    return video_id


def checar_status(video_id: str) -> dict:
    """
    Consulta o status do video. Retorna o dict completo da API;
    os campos mais uteis sao:
      - status: "pending" | "in_progress" | "done" | "failed"
      - output: URL do video pronto (quando status == "done")
    """
    _checar_credenciais()
    resp = requests.get(
        f"{BASE_URL}/link_to_videos/{video_id}/",
        headers=HEADERS,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise CreatifyError(f"Erro ao checar status ({resp.status_code}): {resp.text}")
    return resp.json()


def gerar_video_produto(
    url_produto: str,
    roteiro: str | None = None,
    plataforma: str = "Instagram",
    duracao_segundos: int = 15,
    timeout_total_segundos: int = 300,
    intervalo_polling_segundos: int = 5,
) -> str:
    """
    Funcao principal de alto nivel, pra chamar direto do app_web.py
    no lugar da antiga geracao local.

    Faz o fluxo completo: registra o link -> pede o video -> fica
    checando o status ate ficar pronto (ou dar timeout) -> retorna
    a URL final do video.

    Uso (em app_web.py, na rota que hoje chama a geracao local):

        from video_campanha import gerar_video_produto

        try:
            url_video = gerar_video_produto(url_produto, roteiro=roteiro_gemini)
        except CreatifyError as e:
            # mostrar erro amigavel pro usuario
            ...
    """
    link_id = registrar_link(url_produto)
    video_id = criar_video(
        link_id,
        roteiro=roteiro,
        plataforma=plataforma,
        duracao_segundos=duracao_segundos,
    )

    tempo_decorrido = 0
    while tempo_decorrido < timeout_total_segundos:
        status_dados = checar_status(video_id)
        status = status_dados.get("status")

        if status == "done":
            url_video = status_dados.get("output")
            if not url_video:
                raise CreatifyError(f"Video marcado como 'done' mas sem URL de output: {status_dados}")
            return url_video

        if status == "failed":
            raise CreatifyError(f"Geracao de video falhou na Creatify: {status_dados}")

        time.sleep(intervalo_polling_segundos)
        tempo_decorrido += intervalo_polling_segundos

    raise CreatifyError(
        f"Timeout esperando o video ficar pronto (id={video_id}). "
        "Pode estar demorando mais que o normal — tente checar_status() "
        "de novo daqui a pouco, ou aumente timeout_total_segundos."
    )


if __name__ == "__main__":
    # Teste rapido pelo terminal:
    #   python video_campanha.py "https://shopee.com.br/produto-exemplo"
    import sys

    if len(sys.argv) < 2:
        print("Uso: python video_campanha.py <url_do_produto>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"Gerando video para: {url}")
    try:
        video_url = gerar_video_produto(url)
        print(f"Video pronto: {video_url}")
    except CreatifyError as erro:
        print(f"Erro: {erro}")
