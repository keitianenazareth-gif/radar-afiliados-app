"""
robo_instagram.py
-----------------
Responde sozinho, por mensagem privada, a quem comenta QUERO nos posts
escolhidos na pagina /instagram-robo.

O Railway chama rodar() a cada 10 minutos (junto com o robo do WhatsApp).
Desligado, ele so le os comentarios e conta quantos estao esperando; nao envia.

Regras:
    - so nos posts cadastrados e so em comentarios com menos de 7 dias
      (limite da Meta para a resposta privada);
    - so QUERO e variacoes curtas ("eu quero", "quero o link"), nunca "nao quero";
    - uma mensagem por comentario, e no maximo max_por_vez por execucao
      (o resto fica para os proximos 10 minutos);
    - guarda so o codigo do comentario: nada de nome nem do texto.

Tudo fica no Upstash (mesmo banco do robo do WhatsApp):
    instagram:config       ligado/desligado e posts com seus produtos
    instagram:respondidos  {codigo do comentario: quando}
    instagram:log          ultimos envios
    instagram:execucao     resumo da ultima execucao
"""

from __future__ import annotations

import random
import re
import time
from datetime import datetime, timezone

import requests

import whatsapp_dados as dados
from web import instagram_publish as ig

CHAVE_CONFIG = "instagram:config"
CHAVE_RESPONDIDOS = "instagram:respondidos"
CHAVE_LOG = "instagram:log"
CHAVE_EXECUCAO = "instagram:execucao"
CHAVE_TRAVA = "instagram:trava"

DIAS_LIMITE_META = 7
DIAS_GUARDAR_CODIGO = 14
MAX_LOG = 100
MAX_PRODUTOS = 9  # a Meta aceita 10 cartoes, e o primeiro e' a capa
PAUSA = (3, 8)  # segundos entre uma mensagem e outra
ERROS_PARA_PARAR = {4, 17, 32, 190, 613}  # limite de uso ou token invalido

FOTOS = "https://clube-doquero.vercel.app/imagens/"
GRUPO = "https://chat.whatsapp.com/Cni0DXs99cx6vwDDwCSX9f"

# Comentarios dos testes de 05/11, que ja receberam mensagem.
JA_RESPONDIDOS_NOS_TESTES = (
    "18447822565130321", "18146530204599204", "18128633878857546",
    "18098578454445689", "18026871884946115",
)

CONFIG_PADRAO = {
    "ativo": False,
    "max_por_vez": 20,
    "posts": {
        "DfVzEmJjki8": {
            "nome": "Carrossel 01: parece caro, mas não é",
            "produtos": [
                {"titulo": "Potes com tampa de bambu", "foto": FOTOS + "potes.jpg",
                 "link": "https://s.shopee.com.br/6AmKY9yYcL"},
                {"titulo": "Mini umidificador", "foto": FOTOS + "umidificador.jpg",
                 "link": "https://s.shopee.com.br/2LZbwslENm"},
                {"titulo": "Tapete felpudo", "foto": FOTOS + "tapete.jpg",
                 "link": "https://s.shopee.com.br/3qOQ9VIPxA"},
                {"titulo": "Prateleira de banheiro", "foto": FOTOS + "prateleira.jpg",
                 "link": "https://s.shopee.com.br/1BNeYjpfkh"},
                {"titulo": "Cesto dobrável", "foto": FOTOS + "cesto.jpg",
                 "link": "https://s.shopee.com.br/gRONiGKOC"},
            ],
        },
    },
}

_VARIACOES = re.compile(
    r"(eu )?(tambem |tbm )?que+ro+"
    r"( (sim|muito|demais|tambem|tbm|link|o link|os links|todos))?"
    r"( (por favor|pfv|pf))?"
)


def eh_quero(texto: str) -> bool:
    """So o pedido curto: emoji e pontuacao nao contam; "nao quero" fica de fora."""
    limpo = " ".join(re.sub(r"[^a-z ]+", " ", dados.normalizar(texto)).split())
    return bool(_VARIACOES.fullmatch(limpo))


# ---------------------------------------------------------------- dados

def ler_config() -> dict:
    config = dict(CONFIG_PADRAO)
    salvo = dados._ler_json(CHAVE_CONFIG, {})
    if isinstance(salvo, dict):
        config.update({k: v for k, v in salvo.items() if k in CONFIG_PADRAO})
    return config


def salvar_config(novos: dict) -> None:
    config = ler_config()
    config.update({k: v for k, v in novos.items() if k in CONFIG_PADRAO})
    dados._gravar_json(CHAVE_CONFIG, config)


def ler_respondidos() -> dict:
    salvo = dados._ler_json(CHAVE_RESPONDIDOS, None)
    if isinstance(salvo, dict):
        return salvo
    agora = time.time()
    return {codigo: agora for codigo in JA_RESPONDIDOS_NOS_TESTES}


def _salvar_respondidos(respondidos: dict) -> None:
    limite = time.time() - DIAS_GUARDAR_CODIGO * 86400
    dados._gravar_json(CHAVE_RESPONDIDOS, {k: v for k, v in respondidos.items() if v >= limite})


def ler_log() -> list:
    log = dados._ler_json(CHAVE_LOG, [])
    return list(reversed(log)) if isinstance(log, list) else []


def _registrar(titulo: str, ok: bool = True, erro: str = "") -> None:
    log = dados._ler_json(CHAVE_LOG, [])
    if not isinstance(log, list):
        log = []
    log.append({"quando": f"{dados.agora_brasil():%d/%m %H:%M}", "titulo": titulo, "ok": ok, "erro": erro})
    dados._gravar_json(CHAVE_LOG, log[-MAX_LOG:])


def ler_execucao() -> dict:
    execucao = dados._ler_json(CHAVE_EXECUCAO, {})
    return execucao if isinstance(execucao, dict) else {}


# ---------------------------------------------------------------- produtos

def ler_produtos(texto: str) -> tuple:
    """Uma linha por produto: titulo | link da foto | link do produto.
    Devolve (produtos, problemas)."""
    produtos, problemas = [], []
    for numero, linha in enumerate(texto.splitlines(), start=1):
        if not linha.strip():
            continue
        partes = [p.strip() for p in linha.split("|")]
        if len(partes) != 3 or not all(partes):
            problemas.append(f"Linha {numero}: use título | link da foto | link do produto.")
        elif len(partes[0]) > 80:
            problemas.append(f"Linha {numero}: o título passa de 80 letras.")
        elif not all(p.startswith("https://") for p in partes[1:]):
            problemas.append(f"Linha {numero}: os links precisam começar com https://.")
        else:
            produtos.append({"titulo": partes[0], "foto": partes[1], "link": partes[2]})
    if len(produtos) > MAX_PRODUTOS:
        problemas.append(f"São no máximo {MAX_PRODUTOS} produtos por post.")
    if not produtos and not problemas:
        problemas.append("Coloque pelo menos 1 produto.")
    return produtos, problemas


def codigo_do_post(texto: str) -> str:
    """Aceita o link do post ou so o codigo."""
    texto = texto.strip()
    achado = re.search(r"instagram\.com/(?:[\w.]+/)?(?:p|reel)/([\w-]+)", texto)
    if achado:
        return achado.group(1)
    return texto if re.fullmatch(r"[\w-]{5,20}", texto) else ""


def montar_mensagem(post: dict) -> dict:
    """Capa padrao + um cartao por produto, todos com o botao do grupo."""
    botao_grupo = {"type": "web_url", "url": GRUPO, "title": "Entrar no grupo"}
    cartoes = [{
        "title": "Oi! Que bom ter você aqui 💛",
        "subtitle": "Deslize para ver os links",
        "image_url": FOTOS + "capa-direct.jpg",
        "buttons": [botao_grupo],
    }]
    for p in (post.get("produtos") or [])[:MAX_PRODUTOS]:
        cartoes.append({
            "title": p["titulo"],
            "image_url": p["foto"],
            "default_action": {"type": "web_url", "url": p["link"]},
            "buttons": [{"type": "web_url", "url": p["link"], "title": "Ver produto"}, botao_grupo],
        })
    return {"attachment": {"type": "template", "payload": {"template_type": "generic", "elements": cartoes}}}


# ---------------------------------------------------------------- Meta

def _ler_meta(caminho: str, params: dict) -> dict:
    ig._checar_credenciais()
    try:
        resp = requests.get(f"{ig.BASE_URL}/{caminho}",
                            params={**params, "access_token": ig.INSTAGRAM_ACCESS_TOKEN}, timeout=30)
        corpo = resp.json()
    except (requests.RequestException, ValueError) as erro:
        # A mensagem original pode trazer o endereco com o token: nao repassar.
        raise ig.InstagramPublishError(f"Sem resposta da Meta ({type(erro).__name__}).") from None
    if resp.status_code >= 400:
        detalhe = corpo.get("error", {})
        raise ig.InstagramPublishError(
            f"Meta recusou (codigo {detalhe.get('code')}): {detalhe.get('message', 'sem detalhe')}")
    return corpo


def _ids_dos_posts() -> dict:
    corpo = _ler_meta(f"{ig.INSTAGRAM_USER_ID}/media", {"fields": "shortcode", "limit": 50})
    return {p.get("shortcode"): p.get("id") for p in corpo.get("data", [])}


def _comentarios(media_id: str) -> list:
    saida, depois = [], ""
    for _ in range(5):  # ate 250 comentarios por post em cada execucao
        params = {"fields": "id,text,timestamp", "limit": 50}
        if depois:
            params["after"] = depois
        corpo = _ler_meta(f"{media_id}/comments", params)
        saida += corpo.get("data", [])
        depois = corpo.get("paging", {}).get("cursors", {}).get("after", "")
        if not corpo.get("paging", {}).get("next"):
            break
    return saida


def _dentro_do_prazo(carimbo: str) -> bool:
    try:
        quando = datetime.strptime(str(carimbo), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - quando).total_seconds() < DIAS_LIMITE_META * 86400


def _enviar(comment_id: str, mensagem: dict) -> tuple:
    """Devolve (situacao, detalhe). Situacao: "ok", "repetir" (tenta na proxima
    execucao; a Meta recusa uma segunda mensagem, entao nao duplica), "parar"
    (limite de uso ou token) ou "erro" (nao adianta tentar de novo)."""
    try:
        resp = requests.post(
            f"{ig.BASE_URL}/{ig.INSTAGRAM_USER_ID}/messages",
            headers={"Authorization": f"Bearer {ig.INSTAGRAM_ACCESS_TOKEN}"},
            json={"recipient": {"comment_id": comment_id}, "message": mensagem},
            timeout=30,
        )
        corpo = resp.json()
    except (requests.RequestException, ValueError) as erro:
        return "repetir", f"Sem resposta da Meta ({type(erro).__name__})."
    if resp.status_code < 400:
        return "ok", ""
    detalhe = corpo.get("error", {})
    texto = f"Meta recusou (codigo {detalhe.get('code')}): {detalhe.get('message', 'sem detalhe')}"
    if detalhe.get("code") in ERROS_PARA_PARAR:
        return "parar", texto
    return ("repetir" if resp.status_code >= 500 else "erro"), texto


# ---------------------------------------------------------------- execucao

def _procurar_pendentes(config: dict, respondidos: dict) -> tuple:
    """Devolve (pendentes, resumo). Pendente = (codigo do post, codigo do comentario)."""
    pendentes, nao_achados = [], []
    ids = _ids_dos_posts()
    for codigo in config.get("posts") or {}:
        media_id = ids.get(codigo)
        if not media_id:
            nao_achados.append(codigo)
            continue
        for c in _comentarios(media_id):
            if (c.get("id") not in respondidos and eh_quero(c.get("text"))
                    and _dentro_do_prazo(c.get("timestamp"))):
                pendentes.append((codigo, c["id"]))
    return pendentes, nao_achados


def rodar() -> dict:
    """Uma execucao. Nunca deixa o erro subir: o robo do WhatsApp roda em seguida."""
    resumo = {"quando": f"{dados.agora_brasil():%d/%m %H:%M}", "ativo": False,
              "esperando": 0, "enviadas": 0, "erro": ""}
    tem_trava = False
    try:
        tem_trava = dados._cmd(["SET", CHAVE_TRAVA, "1", "NX", "EX", "600"]) == "OK"
        if not tem_trava:
            resumo["erro"] = "Outra execução ainda estava em andamento."
            return resumo
        config = ler_config()
        resumo["ativo"] = bool(config.get("ativo"))
        respondidos = ler_respondidos()
        pendentes, nao_achados = _procurar_pendentes(config, respondidos)
        resumo["esperando"] = len(pendentes)
        if nao_achados:
            resumo["erro"] = "Post não encontrado: " + ", ".join(nao_achados)
        if not config.get("ativo"):
            print(f"Instagram: robo desligado, {len(pendentes)} comentario(s) esperando.")
            return resumo
        for n, (post, comentario) in enumerate(pendentes[: int(config.get("max_por_vez") or 0)]):
            if n:
                time.sleep(random.randint(*PAUSA))
            situacao, detalhe = _enviar(comentario, montar_mensagem(config["posts"][post]))
            if situacao == "repetir":
                print(f"Instagram: tento de novo depois ({detalhe}).")
                continue
            if situacao == "parar":
                resumo["erro"] = detalhe
                _registrar("Robô parou nesta execução", ok=False, erro=detalhe)
                break
            respondidos[comentario] = time.time()
            _salvar_respondidos(respondidos)
            if situacao == "ok":
                resumo["enviadas"] += 1
                resumo["esperando"] -= 1
                _registrar(f"Mensagem enviada (post {post})")
            else:
                resumo["esperando"] -= 1
                _registrar(f"Não enviada (post {post})", ok=False, erro=detalhe)
        print(f"Instagram: {resumo['enviadas']} enviada(s), {resumo['esperando']} esperando.")
        return resumo
    except (ig.InstagramPublishError, RuntimeError) as erro:
        resumo["erro"] = str(erro)[:300]
        print(f"Instagram: {resumo['erro']}")
        return resumo
    finally:
        try:
            if tem_trava:
                dados._cmd(["DEL", CHAVE_TRAVA])
                dados._gravar_json(CHAVE_EXECUCAO, resumo)
        except RuntimeError as erro:
            print(f"Instagram: nao gravei o resumo ({erro}).")


if __name__ == "__main__":
    print(rodar())
