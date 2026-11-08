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
    instagram:direct       situacao de cada conversa do Direct, sem o texto

Direct (chave propria, tambem comeca desligada): responde so quem escreveu nas
ultimas 24 horas (regra da Meta). A primeira mensagem recebe o convite do grupo
e "quero" recebe os cartoes do ultimo post cadastrado. Assunto de pedido, conversa
que a Keiti ja esta atendendo e qualquer outra mensagem nao recebem resposta:
ficam como aviso no relatorio.
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
CHAVE_DIRECT = "instagram:direct"
CHAVE_PUBLICADOS = "instagram:publicados"
MAX_PUBLICADOS = 30

DIAS_LIMITE_META = 7
DIAS_GUARDAR_CODIGO = 14
HORAS_JANELA_DIRECT = 24
MENSAGENS_OLHADAS = 5
MAX_LOG = 100
MAX_PRODUTOS = 9  # a Meta aceita 10 cartoes, e o primeiro e' a capa
PAUSA = (3, 8)  # segundos entre uma mensagem e outra
ERROS_PARA_PARAR = {4, 17, 32, 190, 613}  # limite de uso ou token invalido

FOTOS = "https://clube-doquero.vercel.app/imagens/"
GRUPO = "https://chat.whatsapp.com/KzZ1GGjCru9FnmH0U4Jvs4"

# Comentarios dos testes de 05/11, que ja receberam mensagem.
JA_RESPONDIDOS_NOS_TESTES = (
    "18447822565130321", "18146530204599204", "18128633878857546",
    "18098578454445689", "18026871884946115",
)

CONFIG_PADRAO = {
    "ativo": False,
    "direct_ativo": False,
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

BOAS_VINDAS = ("Oi! Que bom ter você aqui 💛 Todo dia tem achadinhos com desconto no nosso "
               "grupo do WhatsApp. Toca no botão para entrar")
PERGUNTA_PRONTA = "Quero entrar no grupo"
# Sobre isso o robo nao responde: a Keiti ve no relatorio.
_ASSUNTO_PARA_PESSOA = re.compile(
    r"pedido|entreg|troca|trocar|devol|reembols|rastre|nao chegou|problema|reclam|defeito|cancel")

_VARIACOES = re.compile(
    r"(eu )?(tambem |tbm )?que+ro+"
    r"( (sim|muito|demais|tambem|tbm|link|o link|os links|todos))?"
    r"( (por favor|pfv|pf))?"
)


def eh_quero(texto: str) -> bool:
    """So o pedido curto: emoji e pontuacao nao contam; "nao quero" fica de fora."""
    limpo = " ".join(re.sub(r"[^a-z ]+", " ", dados.normalizar(texto)).split())
    return bool(_VARIACOES.fullmatch(limpo))


def comentario_pede(texto: str, post: dict) -> bool:
    """QUERO sempre vale; o post tambem pode ter uma palavra propria."""
    if eh_quero(texto):
        return True
    palavra = " ".join(dados.normalizar(post.get("palavra") or "").split())
    return bool(palavra) and " ".join(dados.normalizar(texto or "").split()) == palavra


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


def produtos_do_formulario(titulos: list, fotos: list, links: list, foto_padrao: str = "") -> tuple:
    """Linhas da tela de publicar. Sem foto, o cartao usa a primeira foto do post.
    Devolve (produtos, problemas)."""
    produtos, problemas = [], []
    for numero, (titulo, foto, link) in enumerate(zip(titulos, fotos, links), start=1):
        titulo, foto, link = titulo.strip(), foto.strip(), link.strip()
        if not (titulo or foto or link):
            continue
        foto = foto or foto_padrao
        if not titulo or not link:
            problemas.append(f"Produto {numero}: preencha o nome e o link.")
        elif len(titulo) > 80:
            problemas.append(f"Produto {numero}: o nome passa de 80 letras.")
        elif not link.startswith("https://") or not foto.startswith("https://"):
            problemas.append(f"Produto {numero}: os links precisam começar com https://.")
        else:
            produtos.append({"titulo": titulo, "foto": foto, "link": link})
    if len(produtos) > MAX_PRODUTOS:
        problemas.append(f"São no máximo {MAX_PRODUTOS} produtos por post.")
    return produtos, problemas


def ligar_post(codigo: str, nome: str, produtos: list, palavra: str = "") -> None:
    """Coloca o post na lista do robo (ou atualiza, mantendo a posicao)."""
    posts = dict(ler_config().get("posts") or {})
    posts[codigo] = {"nome": nome.strip()[:80], "produtos": produtos, "palavra": palavra.strip()[:30]}
    salvar_config({"posts": posts})


def reservar_publicacao(token: str) -> bool:
    """Evita publicar duas vezes se o botao for tocado de novo."""
    return dados._cmd(["SET", f"instagram:publicando:{token}", "1", "NX", "EX", "3600"]) == "OK"


def liberar_publicacao(token: str) -> None:
    dados._cmd(["DEL", f"instagram:publicando:{token}"])


def registrar_publicado(registro: dict) -> None:
    lista = dados._ler_json(CHAVE_PUBLICADOS, [])
    lista = lista if isinstance(lista, list) else []
    lista.append({"quando": f"{dados.agora_brasil():%d/%m %H:%M}", **registro})
    dados._gravar_json(CHAVE_PUBLICADOS, lista[-MAX_PUBLICADOS:])


def ler_publicados() -> list:
    lista = dados._ler_json(CHAVE_PUBLICADOS, [])
    return list(reversed(lista)) if isinstance(lista, list) else []


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


def _enviar(destino: dict, mensagem: dict) -> tuple:
    """Devolve (situacao, detalhe). Situacao: "ok" (detalhe = codigo da mensagem),
    "repetir" (tenta na proxima execucao), "parar" (limite de uso ou token) ou
    "erro" (nao adianta tentar de novo). Destino: {"comment_id": ...} ou {"id": ...}."""
    try:
        resp = requests.post(
            f"{ig.BASE_URL}/{ig.INSTAGRAM_USER_ID}/messages",
            headers={"Authorization": f"Bearer {ig.INSTAGRAM_ACCESS_TOKEN}"},
            json={"recipient": destino, "message": mensagem},
            timeout=30,
        )
        corpo = resp.json()
    except (requests.RequestException, ValueError) as erro:
        return "repetir", f"Sem resposta da Meta ({type(erro).__name__})."
    if resp.status_code < 400:
        return "ok", str(corpo.get("message_id") or "")
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
    for codigo, post in (config.get("posts") or {}).items():
        media_id = ids.get(codigo)
        if not media_id:
            nao_achados.append(codigo)
            continue
        for c in _comentarios(media_id):
            if (c.get("id") not in respondidos and comentario_pede(c.get("text"), post)
                    and _dentro_do_prazo(c.get("timestamp"))):
                pendentes.append((codigo, c["id"]))
    return pendentes, nao_achados


def _rodar_comentarios(config: dict, resumo: dict, estado: dict) -> None:
    respondidos = ler_respondidos()
    pendentes, nao_achados = _procurar_pendentes(config, respondidos)
    resumo["esperando"] = len(pendentes)
    if nao_achados:
        resumo["erro"] = "Post não encontrado: " + ", ".join(nao_achados)
    if not config.get("ativo"):
        print(f"Instagram: comentarios desligados, {len(pendentes)} esperando.")
        return
    for n, (post, comentario) in enumerate(pendentes[: int(config.get("max_por_vez") or 0)]):
        if n:
            time.sleep(random.randint(*PAUSA))
        situacao, detalhe = _enviar({"comment_id": comentario}, montar_mensagem(config["posts"][post]))
        if situacao == "repetir":
            print(f"Instagram: tento de novo depois ({detalhe}).")
            continue
        if situacao == "parar":
            resumo["erro"] = detalhe
            _registrar("Robô parou nesta execução", ok=False, erro=detalhe)
            break
        respondidos[comentario] = time.time()
        _salvar_respondidos(respondidos)
        resumo["esperando"] -= 1
        if situacao == "ok":
            resumo["enviadas"] += 1
            if detalhe:
                estado["robo"][detalhe] = time.time()
            _registrar(f"Mensagem enviada (post {post})")
        else:
            _registrar(f"Não enviada (post {post})", ok=False, erro=detalhe)
    print(f"Instagram: {resumo['enviadas']} enviada(s) por comentario, {resumo['esperando']} esperando.")


# ---------------------------------------------------------------- Direct

def _ler_estado_direct() -> dict:
    salvo = dados._ler_json(CHAVE_DIRECT, {})
    salvo = salvo if isinstance(salvo, dict) else {}
    return {"conversas": salvo.get("conversas") or {}, "robo": salvo.get("robo") or {}}


def _salvar_estado_direct(estado: dict) -> None:
    limite = time.time() - DIAS_GUARDAR_CODIGO * 86400
    dados._gravar_json(CHAVE_DIRECT, {
        "conversas": {k: v for k, v in estado["conversas"].items() if v.get("quando", 0) >= limite},
        "robo": {k: v for k, v in estado["robo"].items() if v >= limite},
    })


def _idade_em_horas(carimbo: str) -> float:
    try:
        quando = datetime.strptime(str(carimbo), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return 10 ** 6
    return (datetime.now(timezone.utc) - quando).total_seconds() / 3600


def decidir_direct(mensagens: list, situacao: dict, eh_minha, robo: dict) -> str:
    """O que fazer com a conversa: "" (nada), "boas_vindas", "cartoes" ou "avisar".
    mensagens vem da mais nova para a mais antiga. Sem chamar nada fora daqui."""
    if not mensagens:
        return ""
    ultima = mensagens[0]
    if eh_minha(ultima) or ultima.get("id") == situacao.get("ultima"):
        return ""
    if _idade_em_horas(ultima.get("created_time")) >= HORAS_JANELA_DIRECT:
        return ""
    if any(eh_minha(m) and m.get("id") not in robo for m in mensagens):
        return "avisar"  # a Keiti ja escreveu nessa conversa
    texto = str(ultima.get("message") or "")
    if eh_quero(texto):
        return "avisar" if time.time() - situacao.get("cartoes", 0) < 86400 else "cartoes"
    if _ASSUNTO_PARA_PESSOA.search(dados.normalizar(texto)) or situacao.get("boas_vindas"):
        return "avisar"
    return "boas_vindas"


def _minha_conta() -> dict:
    corpo = _ler_meta("me", {"fields": "id,user_id,username"})
    return {"ids": {str(corpo.get("id")), str(corpo.get("user_id")), str(ig.INSTAGRAM_USER_ID)},
            "username": corpo.get("username")}


def _mensagens_da_conversa(conversa_id: str) -> list:
    corpo = _ler_meta(conversa_id, {"fields": "messages"})
    resumo = corpo.get("messages", {}).get("data", [])
    resumo = sorted(resumo, key=lambda m: str(m.get("created_time")), reverse=True)[:MENSAGENS_OLHADAS]
    return [_ler_meta(m["id"], {"fields": "id,created_time,from,to,message"}) for m in resumo]


def _rodar_direct(config: dict, resumo: dict, estado: dict) -> None:
    ligado = bool(config.get("direct_ativo"))
    conta = _minha_conta()

    def eh_minha(m):
        de = m.get("from") or {}
        return str(de.get("id")) in conta["ids"] or de.get("username") == conta["username"]

    corpo = _ler_meta(f"{ig.INSTAGRAM_USER_ID}/conversations",
                      {"platform": "instagram", "fields": "id,updated_time", "limit": 25})
    posts = list((config.get("posts") or {}).values())
    envios = 0
    for conversa in corpo.get("data", []):
        cid = conversa.get("id")
        if _idade_em_horas(conversa.get("updated_time")) >= HORAS_JANELA_DIRECT:
            continue
        situacao = estado["conversas"].get(cid, {})
        if situacao.get("vista") == conversa.get("updated_time"):
            continue
        mensagens = _mensagens_da_conversa(cid)
        acao = decidir_direct(mensagens, situacao, eh_minha, estado["robo"])
        if acao == "cartoes" and not posts:
            acao = "boas_vindas" if not situacao.get("boas_vindas") else "avisar"
        if acao in ("boas_vindas", "cartoes"):
            resumo["direct_esperando"] += 1
        if not ligado:
            continue
        novo = {**situacao, "vista": conversa.get("updated_time"), "quando": time.time()}
        if acao:
            novo["ultima"] = mensagens[0].get("id")
        if acao == "avisar":
            resumo["direct_avisos"] += 1
            _registrar("Mensagem no Direct precisa de você: abra o Instagram", ok=False)
        elif acao in ("boas_vindas", "cartoes"):
            if envios >= int(config.get("max_por_vez") or 0):
                continue
            if envios:
                time.sleep(random.randint(*PAUSA))
            envios += 1
            mensagem = montar_mensagem(posts[-1]) if acao == "cartoes" else mensagem_boas_vindas()
            situacao_envio, detalhe = _enviar({"id": (mensagens[0].get("from") or {}).get("id")}, mensagem)
            if situacao_envio == "repetir":
                print(f"Instagram: Direct, tento de novo depois ({detalhe}).")
                continue
            if situacao_envio == "parar":
                resumo["erro_direct"] = detalhe
                _registrar("Robô parou nesta execução", ok=False, erro=detalhe)
                break
            resumo["direct_esperando"] -= 1
            if situacao_envio == "ok":
                resumo["direct_enviadas"] += 1
                if detalhe:
                    estado["robo"][detalhe] = time.time()
                novo["boas_vindas" if acao == "boas_vindas" else "cartoes"] = time.time()
                _registrar("Direct: convite do grupo enviado" if acao == "boas_vindas"
                           else "Direct: links enviados")
            else:
                _registrar("Direct: mensagem não enviada", ok=False, erro=detalhe)
        estado["conversas"][cid] = novo


def mensagem_boas_vindas() -> dict:
    return {"attachment": {"type": "template", "payload": {
        "template_type": "button", "text": BOAS_VINDAS,
        "buttons": [{"type": "web_url", "url": GRUPO, "title": "Entrar no grupo"}],
    }}}


def trocar_botao_pronto(ligar: bool) -> None:
    """Botao que aparece para quem abre a conversa com a pagina pela primeira vez."""
    ig._checar_credenciais()
    url = f"{ig.BASE_URL}/me/messenger_profile"
    cabecalho = {"Authorization": f"Bearer {ig.INSTAGRAM_ACCESS_TOKEN}"}
    try:
        if ligar:
            resp = requests.post(url, headers=cabecalho, timeout=30, json={
                "platform": "instagram",
                "ice_breakers": [{"call_to_actions": [{"question": PERGUNTA_PRONTA, "payload": "ENTRAR_NO_GRUPO"}]}],
            })
        else:
            resp = requests.delete(url, headers=cabecalho, timeout=30,
                                   json={"platform": "instagram", "fields": ["ice_breakers"]})
        corpo = resp.json()
    except (requests.RequestException, ValueError) as erro:
        raise ig.InstagramPublishError(f"Sem resposta da Meta ({type(erro).__name__}).") from None
    if resp.status_code >= 400:
        detalhe = corpo.get("error", {})
        raise ig.InstagramPublishError(
            f"Meta recusou (codigo {detalhe.get('code')}): {detalhe.get('message', 'sem detalhe')}")


# ---------------------------------------------------------------- execucao

def rodar() -> dict:
    """Uma execucao. Nunca deixa o erro subir: o robo do WhatsApp roda em seguida."""
    resumo = {"quando": f"{dados.agora_brasil():%d/%m %H:%M}", "ativo": False, "direct_ativo": False,
              "esperando": 0, "enviadas": 0, "erro": "", "direct_esperando": 0, "direct_enviadas": 0,
              "direct_avisos": 0, "erro_direct": ""}
    tem_trava = False
    try:
        tem_trava = dados._cmd(["SET", CHAVE_TRAVA, "1", "NX", "EX", "600"]) == "OK"
        if not tem_trava:
            resumo["erro"] = "Outra execução ainda estava em andamento."
            return resumo
        config = ler_config()
        resumo["ativo"] = bool(config.get("ativo"))
        resumo["direct_ativo"] = bool(config.get("direct_ativo"))
        estado = _ler_estado_direct()
        # Um erro em uma parte (como permissao do Direct) nao atrapalha a outra.
        for parte, campo in ((_rodar_comentarios, "erro"), (_rodar_direct, "erro_direct")):
            try:
                parte(config, resumo, estado)
            except ig.InstagramPublishError as erro:
                resumo[campo] = str(erro)[:300]
                print(f"Instagram: {resumo[campo]}")
        if config.get("ativo") or config.get("direct_ativo"):
            _salvar_estado_direct(estado)
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
