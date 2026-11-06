"""Versao web do Radar Afiliados - roda localmente com Flask, usando os
mesmos modulos e as mesmas credenciais (credenciais_locais.py) do app
Android. Nao substitui o app; e' so mais uma forma de acessar, pelo
navegador do notebook.

Rodar: python web/app_web.py  ->  http://localhost:5000
"""

import hmac
import os
import re
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import (
    Flask,
    Response,
    flash,
    get_flashed_messages,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
import requests
from werkzeug.utils import secure_filename

import produto_manual
from shopee import buscar_produtos, numero

app = Flask(__name__)
# 100MB: a Keiti sobe pela Galeria os videos que grava no celular.
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
# So pra mensagens de status (flash) apos postar no Instagram pela Galeria -
# nao guarda nada sensivel, nao tem sessao/login por cookie (o login e'
# HTTP Basic, refeito a cada request).
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "radar-afiliados-flash-nao-sensivel")
# Sem isso, o navegador pode guardar app.js/estilo.css em cache por horas
# e a Keiti continuar vendo a tela antiga mesmo depois de um deploy novo
# (foi o que aconteceu com o prompt do video nao aparecendo editavel).
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


def _url_publica(caminho_relativo):
    """Monta uma URL publica e completa (https) a partir de um caminho
    tipo /static/... - necessario pro Kairogen conseguir BAIXAR a foto
    (ele nao enxerga localhost nem caminho relativo). Sem ProxyFix
    configurado, request.host_url viria como 'http://' mesmo no Render
    (que fica atras de um proxy https), entao usamos o dominio fixo
    conhecido - da pra trocar via variavel de ambiente se precisar
    (ex.: testando local com ngrok)."""
    base = os.environ.get("BASE_URL_PUBLICA", "https://radar-afiliados-web.onrender.com")
    return base.rstrip("/") + caminho_relativo

# ---------------------------------------------------------------------------
# Login (HTTP Basic). Usuario/senha vem de credenciais_locais.py ou de
# variaveis de ambiente. Se a senha ficar vazia, o login fica DESLIGADO
# (uso local). Preencha ao expor o site para fora (ngrok etc.).
# ---------------------------------------------------------------------------

try:
    from credenciais_locais import WEB_USUARIO as _WEB_USUARIO
except ImportError:
    _WEB_USUARIO = ""
try:
    from credenciais_locais import WEB_SENHA as _WEB_SENHA
except ImportError:
    _WEB_SENHA = ""

WEB_USUARIO = os.environ.get("WEB_USUARIO") or _WEB_USUARIO or "revisor"
WEB_SENHA = os.environ.get("WEB_SENHA") or _WEB_SENHA or ""


@app.before_request
def _exigir_login():
    # /healthz fica sempre aberta: e' o que o Render usa para saber que
    # o servico esta no ar (se pedisse login, o Render veria 401 e nao
    # rotearia trafego para o app).
    if request.path == "/healthz":
        return None
    if not WEB_SENHA:
        return None  # login desligado
    cred = request.authorization
    if (
        cred
        and cred.type == "basic"
        and hmac.compare_digest(cred.username or "", WEB_USUARIO)
        and hmac.compare_digest(cred.password or "", WEB_SENHA)
    ):
        return None
    return Response(
        "Acesso restrito.",
        401,
        {"WWW-Authenticate": 'Basic realm="Radar Afiliados"'},
    )

AVISO_ML = (
    "Busca automatica indisponivel: a API do Mercado Livre nao libera "
    "preco/nome de anuncio para apps de terceiros no momento. Cole o "
    "link do produto abaixo."
)

PLATAFORMAS_MANUAIS = {
    # slug: (nome, aviso, link do site - pra abrir e escolher o produto)
    "mercado-livre": ("Mercado Livre", AVISO_ML, "https://www.mercadolivre.com.br"),
    "amazon": ("Amazon", "", "https://www.amazon.com.br"),
    "shein": ("Shein", "", "https://www.shein.com.br"),
    "temu": ("Temu", "", "https://www.temu.com"),
}


def _texto_preco(dados):
    preco = dados.get("preco")
    if isinstance(preco, (int, float)):
        return f"{preco:.2f}"
    return str(dados.get("preco_texto") or preco or "")


def _resumo_robos():
    """Numeros de hoje para o Inicio e a tela de Robos. Se o banco falhar, mostra zerado com aviso."""
    import robo_instagram as ri
    import whatsapp_dados as wd

    resumo = {"whatsapp_ligado": False, "proxima": "", "enviadas": 0, "meta": 0, "por_rodada": 0,
              "fila": 0, "cupons": 0, "ig_ligado": False, "direct_ligado": False, "ig_esperando": 0,
              "ig_quando": "", "ig_erro": ""}
    try:
        agora = wd.agora_brasil()
        config = wd.ler_config()
        hoje = agora.strftime("%d/%m")
        resumo.update(
            whatsapp_ligado=bool(config.get("ativo")),
            proxima=wd.proxima_rodada(config, agora),
            por_rodada=int(config.get("ofertas_por_rodada") or 0),
            meta=len(config.get("rodadas") or []) * int(config.get("ofertas_por_rodada") or 0),
            enviadas=sum(1 for e in wd.ler_log() if e.get("ok") and e.get("tipo") in ("shopee", "fila")
                         and str(e.get("quando", "")).startswith(hoje)),
            fila=len(wd.listar_fila()),
            cupons=sum(1 for c in wd.listar_cupons() if wd.cupom_valido(c)),
        )
        ig_config, execucao = ri.ler_config(), ri.ler_execucao()
        resumo.update(
            ig_ligado=bool(ig_config.get("ativo")),
            direct_ligado=bool(ig_config.get("direct_ativo")),
            ig_esperando=int(execucao.get("esperando") or 0),
            ig_quando=str(execucao.get("quando") or "")[-5:],
            ig_erro=execucao.get("erro") or "",
        )
    except RuntimeError as erro:
        return resumo, str(erro)
    return resumo, ""


# ---------------------------------------------------------------------------
# Paginas
# ---------------------------------------------------------------------------

@app.route("/healthz")
def healthz():
    return "ok", 200


@app.route("/")
def principal():
    plataformas_manuais = [
        (slug, nome) for slug, (nome, _aviso, _link) in PLATAFORMAS_MANUAIS.items()
    ]
    resumo, erro_dados = _resumo_robos()
    return render_template("principal.html", plataformas_manuais=plataformas_manuais,
                           resumo=resumo, erro_dados=erro_dados)


@app.route("/robos")
def robos():
    resumo, erro_dados = _resumo_robos()
    return render_template("robos.html", resumo=resumo, erro_dados=erro_dados)


@app.route("/shopee")
def shopee():
    return render_template("shopee.html")


@app.route("/geral")
def geral():
    return render_template("geral.html")


@app.route("/plataforma/<slug>")
def plataforma(slug):
    dados = PLATAFORMAS_MANUAIS.get(slug)
    if dados is None:
        return "Plataforma desconhecida.", 404
    nome_plataforma, aviso, link_site = dados
    return render_template(
        "manual.html", nome_plataforma=nome_plataforma, aviso=aviso, link_site=link_site
    )


@app.route("/galeria")
def galeria_pagina():
    from web import galeria

    try:
        itens = galeria.listar_itens()
        destinos = galeria.listar_destinos()
        erro_galeria = None
    except galeria.GaleriaError as erro:
        itens, destinos, erro_galeria = [], [], str(erro)

    return render_template(
        "galeria.html", itens=itens, destinos=destinos, erro_galeria=erro_galeria
    )


@app.route("/edicao", methods=["GET", "POST"])
def edicao():
    """Aba "Edicao": caixa de texto + seletor com os 6 fluxos de IA
    (edicao_ia.rodar_fluxo), mais um jeito de ANEXAR um video (da Galeria
    ou do celular) so pra Keiti ver do lado enquanto escreve o texto - o
    video em si nao e' mandado pra IA, so fica de referencia visual na
    tela (ver o <script> no fim de edicao.html)."""
    from web import galeria
    from web.edicao_ia import FLUXOS_ROTULOS, rodar_fluxo

    try:
        videos_galeria = [i for i in galeria.listar_itens() if i.get("tipo") == "video"]
    except galeria.GaleriaError:
        videos_galeria = []

    resultado = None
    erro = None
    fluxo_escolhido = ""
    texto_enviado = ""

    if request.method == "POST":
        fluxo_escolhido = request.form.get("fluxo", "")
        texto_enviado = request.form.get("texto", "").strip()
        if not texto_enviado:
            erro = "Escreva o texto (roteiro, descricao do material, etc.) antes de enviar."
        else:
            try:
                resultado = rodar_fluxo(fluxo_escolhido, texto_enviado)
            except ValueError as e:
                erro = str(e)
            except RuntimeError as e:
                erro = str(e)
            except Exception as e:  # noqa: BLE001
                erro = f"Erro ao rodar o fluxo: {e}"

    return render_template(
        "edicao.html",
        fluxos=FLUXOS_ROTULOS,
        fluxo_escolhido=fluxo_escolhido,
        texto_enviado=texto_enviado,
        resultado=resultado,
        erro=erro,
        videos_galeria=videos_galeria,
    )


# ---------------------------------------------------------------------------
# API (buscas e campanha) - respostas em JSON, consumidas via fetch() no JS
# ---------------------------------------------------------------------------

@app.route("/api/shopee/buscar", methods=["POST"])
def api_shopee_buscar():
    dados = request.get_json(force=True)
    opcao = str(dados.get("opcao", ""))
    termo = dados.get("termo", "")

    try:
        produtos = buscar_produtos(opcao, termo, limite=10)
    except Exception as erro:
        return jsonify({"erro": str(erro)})

    return jsonify({"itens": produtos})


@app.route("/api/geral/buscar", methods=["POST"])
def api_geral_buscar():
    try:
        produtos = buscar_produtos("5", "", limite=20)
    except Exception as erro:
        return jsonify({"erro": str(erro)})

    itens = [
        {
            "plataforma": "Shopee",
            "nome": str(produto.get("productName") or "Produto"),
            "preco": numero(produto.get("priceMin")),
            "comissao_texto": f"R$ {numero(produto.get('commission')):.2f}",
            "vendas": int(numero(produto.get("sales"))),
            "nota": produto.get("nota") or 0,
            "link": str(produto.get("offerLink") or ""),
            "imagem": str(produto.get("imageUrl") or ""),
        }
        for produto in produtos
    ]
    itens.sort(key=lambda item: item["nota"], reverse=True)
    return jsonify({"itens": itens[:20]})


@app.route("/api/manual/buscar-dados", methods=["POST"])
def api_manual_buscar_dados():
    dados = request.get_json(force=True)
    resultado = produto_manual.buscar_metadados_link(dados.get("link", ""))
    return jsonify(resultado)


@app.route("/api/campanha", methods=["POST"])
def api_campanha():
    dados = request.get_json(force=True)

    try:
        from campanhas_ia import gerar_campanha

        texto = gerar_campanha(
            plataforma=dados.get("plataforma", ""),
            produto=dados.get("nome", ""),
            preco=_texto_preco(dados),
            comissao=dados.get("comissao_texto", ""),
            vendas=str(dados.get("vendas", "") or ""),
            link=dados.get("link", ""),
            observacoes=(
                "Crie conteudo natural para afiliada. Nao invente informacoes."
            ),
        )
    except ImportError:
        return jsonify({"sucesso": False, "erro": "O arquivo campanhas_ia.py nao foi encontrado."})
    except RuntimeError as erro:
        return jsonify({"sucesso": False, "erro": str(erro)})
    except Exception as erro:
        return jsonify({"sucesso": False, "erro": f"Erro ao gerar campanha: {erro}"})

    return jsonify({"sucesso": True, "texto": texto})


def _produto_com_foto_manual(dados):
    """Se a Keiti enviou uma foto propria (upload do celular), essa URL
    substitui a foto raspada da plataforma - vale pros 3 modos."""
    produto = dict(dados)
    foto_manual = (dados.get("foto_manual_url") or "").strip()
    if foto_manual:
        produto["imagem"] = foto_manual
    return produto


@app.route("/api/campanha/video/prompt", methods=["POST"])
def api_campanha_video_prompt():
    """So gera o roteiro (Gemini) + o prompt do modo "Vídeo por IA" -
    NAO chama o Kairogen, entao nao gasta credito nenhum. Serve pra
    Keiti revisar/editar o prompt antes de confirmar a geracao paga
    (ver /api/campanha/video, campo "prompt_video")."""
    dados = request.get_json(force=True)

    if not dados.get("nome"):
        return jsonify({"sucesso": False, "erro": "Produto sem nome."})

    try:
        from campanhas_ia import gerar_roteiro_video

        from web.video_campanha import montar_prompt_video_ia

        roteiro = gerar_roteiro_video(
            plataforma=dados.get("plataforma", ""),
            produto=dados.get("nome", ""),
            preco=_texto_preco(dados),
            comissao=dados.get("comissao_texto", ""),
            vendas=str(dados.get("vendas", "") or ""),
            link=dados.get("link", ""),
        )
        prompt = montar_prompt_video_ia(roteiro)
    except RuntimeError as erro:
        return jsonify({"sucesso": False, "erro": str(erro)})
    except Exception as erro:  # noqa: BLE001
        return jsonify({"sucesso": False, "erro": f"Erro ao gerar o prompt: {erro}"})

    return jsonify({"sucesso": True, "roteiro": roteiro, "prompt": prompt})


@app.route("/api/campanha/foto", methods=["POST"])
def api_campanha_foto():
    """Recebe uma foto enviada manualmente (ex.: tirada/escolhida no
    celular) pra usar no lugar da foto raspada da plataforma. Devolve
    uma URL PUBLICA (obrigatorio: o Kairogen precisa baixar a imagem
    pela internet, nao enxerga arquivo local nem localhost)."""
    arquivo = request.files.get("foto")
    if not arquivo or not arquivo.filename:
        return jsonify({"sucesso": False, "erro": "Nenhuma foto enviada."})

    extensao = os.path.splitext(arquivo.filename)[1].lower()
    if extensao not in (".jpg", ".jpeg", ".png", ".webp"):
        return jsonify(
            {"sucesso": False, "erro": "Formato nao aceito. Use JPG, PNG ou WEBP."}
        )

    pasta = os.path.join(os.path.dirname(__file__), "static", "uploads")
    os.makedirs(pasta, exist_ok=True)
    nome_arquivo = f"{uuid.uuid4().hex[:16]}{extensao}"
    arquivo.save(os.path.join(pasta, nome_arquivo))

    url = _url_publica(url_for("static", filename=f"uploads/{nome_arquivo}"))
    return jsonify({"sucesso": True, "url": url})


@app.route("/api/campanha/video", methods=["POST"])
def api_campanha_video():
    """Gera um video curto (mp4) de divulgacao: foto do produto +
    texto na tela + narracao. Sincrono - pode levar ~30-60s (ou alguns
    minutos no modo "video" com IA).

    dados["modo_video"] escolhe o modo:
        (ausente/"padrao") -> fundo borrado, como sempre foi
        "fundo"            -> fundo gerado por IA (Kairogen, barato)
        "video"            -> video de IA animando a foto real do
                               produto (Kairogen, ate ~50 creditos)

    dados["foto_manual_url"]: se veio de /api/campanha/foto, usa essa
    foto no lugar da foto raspada da plataforma (vale pros 3 modos).

    dados["roteiro"] + dados["prompt_video"] (opcionais, so modo
    "video"): quando a tela ja mostrou o prompt pra Keiti revisar
    (via /api/campanha/video/prompt) e ela confirmou, manda os dois de
    volta aqui - evita gerar um roteiro/narracao diferente do que ela
    viu na hora de confirmar."""
    dados = request.get_json(force=True)

    if not dados.get("nome"):
        return jsonify({"sucesso": False, "erro": "Produto sem nome."})

    modo_ia = dados.get("modo_video") or None
    if modo_ia not in (None, "fundo", "video", "personagem"):
        modo_ia = None

    personagem_url = None
    if modo_ia == "personagem":
        from web.kairogen_media import PERSONAGENS

        personagem_url = PERSONAGENS.get((dados.get("personagem") or "maya").lower())
        if not personagem_url:
            return jsonify({"sucesso": False, "erro": "Personagem inválida."})

    produto = _produto_com_foto_manual(dados)
    roteiro_pronto = dados.get("roteiro")
    prompt_video = (dados.get("prompt_video") or "").strip() or None

    try:
        from web.video_campanha import montar_video

        if roteiro_pronto and roteiro_pronto.get("cenas") and roteiro_pronto.get("narracao"):
            roteiro = roteiro_pronto
        else:
            from campanhas_ia import gerar_roteiro_video

            roteiro = gerar_roteiro_video(
                plataforma=dados.get("plataforma", ""),
                produto=dados.get("nome", ""),
                preco=_texto_preco(dados),
                comissao=dados.get("comissao_texto", ""),
                vendas=str(dados.get("vendas", "") or ""),
                link=dados.get("link", ""),
            )
        caminho_mp4, motor_tts = montar_video(
            produto, roteiro, modo_ia=modo_ia, prompt_video=prompt_video,
            personagem_url=personagem_url,
            animar_personagem=bool(dados.get("animar_personagem")),
        )
    except RuntimeError as erro:
        return jsonify({"sucesso": False, "erro": str(erro)})
    except Exception as erro:  # noqa: BLE001
        return jsonify({"sucesso": False, "erro": f"Erro ao gerar video: {erro}"})

    nome_arquivo = os.path.basename(caminho_mp4)

    # Salva na Galeria automaticamente (Cloudinary+Upstash - sobrevive a
    # reinicio do Render). Best-effort: se falhar, o video gerado ainda
    # e' devolvido normalmente (da pra baixar), so avisamos na tela.
    # A URL do Cloudinary (galeria_url) e' a que o Instagram consegue
    # baixar de verdade - a video_url local (/static/videos/...) nao
    # funciona pro Instagram, so pro preview/download aqui no site.
    aviso_galeria = None
    galeria_url = None
    try:
        from web import galeria

        item_galeria = galeria.adicionar_item(
            caminho_mp4, "video", nome_original=dados.get("nome")
        )
        galeria_url = item_galeria.get("url")
    except Exception as erro:  # noqa: BLE001
        aviso_galeria = f"Vídeo pronto, mas não consegui salvar na Galeria: {erro}"

    return jsonify(
        {
            "sucesso": True,
            "video_url": url_for("static", filename=f"videos/{nome_arquivo}"),
            "galeria_url": galeria_url,
            "narracao": motor_tts,
            "roteiro": roteiro,
            "aviso_galeria": aviso_galeria,
        }
    )


# ---------------------------------------------------------------------------
# Galeria (fotos/videos gerados ou importados - guardados no Cloudinary,
# indice no Upstash. Ver web/galeria.py pro motivo de nao usar disco local)
# ---------------------------------------------------------------------------

@app.route("/galeria/importar", methods=["POST"])
def galeria_importar():
    from web import galeria

    tipo = request.form.get("tipo", "imagem")
    arquivo = request.files.get("arquivo")

    if arquivo and arquivo.filename:
        nome_seguro = secure_filename(arquivo.filename)
        caminho_temp = os.path.join(tempfile.gettempdir(), nome_seguro)
        arquivo.save(caminho_temp)
        try:
            galeria.adicionar_item(caminho_temp, tipo, nome_original=nome_seguro)
        finally:
            os.remove(caminho_temp)

    return redirect(url_for("galeria_pagina"))


@app.route("/galeria/excluir/<item_id>", methods=["POST"])
def galeria_excluir(item_id):
    from web import galeria

    galeria.remover_item(item_id)
    return redirect(url_for("galeria_pagina"))


@app.route("/galeria/destino/alternar", methods=["POST"])
def galeria_alternar_destino():
    from web import galeria

    galeria.alternar_destino(request.form["item_id"], request.form["destino"])
    return redirect(url_for("galeria_pagina"))


@app.route("/galeria/destino/adicionar", methods=["POST"])
def galeria_adicionar_destino():
    from web import galeria

    galeria.adicionar_destino(request.form.get("nome", ""))
    return redirect(url_for("galeria_pagina"))


@app.route("/galeria/destino/remover", methods=["POST"])
def galeria_remover_destino():
    from web import galeria

    galeria.remover_destino(request.form.get("nome", ""))
    return redirect(url_for("galeria_pagina"))


@app.route("/api/instagram/status")
def instagram_status():
    """So leitura: mostra qual conta o token publica. Nao posta nada."""
    from web.instagram_publish import InstagramPublishError, status_conta

    try:
        return jsonify({"ok": True, **status_conta()})
    except InstagramPublishError as erro:
        return jsonify({"ok": False, "erro": str(erro)})


def _midias_escolhidas(ids):
    """Itens da Galeria na ordem escolhida."""
    from web import galeria

    por_id = {item["id"]: item for item in galeria.listar_itens()}
    return [por_id[i] for i in ids if i in por_id]


def _form_publicar(fonte=None):
    """Valores da tela: do formulario, ou vazios ao abrir."""
    fonte = fonte or {}
    return {
        "modo": fonte.get("modo") or "produtos",
        "nome": fonte.get("nome", ""),
        "legenda": fonte.get("legenda", ""),
        "palavra": fonte.get("palavra", ""),
        "produtos": fonte.get("produtos") or [],
        "ids": fonte.get("ids") or [],
    }


def _pagina_publicar(form, problemas=None):
    from web import galeria

    import robo_instagram as ri

    itens, erro_galeria, publicados, robo_ligado = [], "", [], False
    try:
        itens = galeria.listar_itens()
    except galeria.GaleriaError as erro:
        erro_galeria = str(erro)
    try:
        publicados = ri.ler_publicados()[:5]
        robo_ligado = bool(ri.ler_config().get("ativo"))
    except RuntimeError as erro:
        erro_galeria = erro_galeria or str(erro)
    return render_template(
        "instagram_publicar.html", form=form, itens=itens, erro_galeria=erro_galeria,
        publicados=publicados, problemas=problemas or [], robo_ligado=robo_ligado,
        max_produtos=ri.MAX_PRODUTOS,
    )


def _salvar_arquivos_enviados():
    """Sobe para a Galeria os arquivos enviados na hora. Devolve os ids."""
    from web import galeria

    ids = []
    for arquivo in request.files.getlist("arquivos"):
        if not arquivo or not arquivo.filename:
            continue
        nome = secure_filename(arquivo.filename) or "arquivo"
        tipo = "video" if (arquivo.mimetype or "").startswith("video/") else "imagem"
        caminho = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4().hex}-{nome}")
        arquivo.save(caminho)
        try:
            ids.append(galeria.adicionar_item(caminho, tipo, nome_original=nome)["id"])
        finally:
            os.remove(caminho)
    return ids


def _completar_produtos(titulos, fotos, links):
    """Se faltou nome ou foto, tenta pegar do link. Nunca falha."""
    for n, link in enumerate(links):
        if link.strip() and not (titulos[n].strip() and fotos[n].strip()):
            info = produto_manual.buscar_metadados_link(link.strip())
            titulos[n] = titulos[n].strip() or info.get("nome", "")[:80]
            fotos[n] = fotos[n].strip() or info.get("imagem", "")


@app.route("/instagram-publicar", methods=["GET", "POST"])
def instagram_publicar():
    import json

    if request.method == "GET":
        escolhido = request.args.get("item", "")
        return _pagina_publicar(_form_publicar({"ids": [escolhido] if escolhido else []}))

    if request.form.get("editar"):  # voltou da conferencia
        try:
            produtos = json.loads(request.form.get("produtos_json") or "[]")
        except ValueError:
            produtos = []
        return _pagina_publicar(_form_publicar({
            **request.form.to_dict(), "produtos": produtos,
            "ids": request.form.get("ids", "").split(",") if request.form.get("ids") else [],
        }))

    import robo_instagram as ri
    from web import galeria
    from web.instagram_publish import MAX_ITENS_CARROSSEL, url_para_foto

    modo = "diferente" if request.form.get("modo") == "diferente" else "produtos"
    ids = [i for i in request.form.get("ordem", "").split(",") if i] or request.form.getlist("midia")
    problemas = []
    try:
        ids += _salvar_arquivos_enviados()
        midias = _midias_escolhidas(ids)
    except galeria.GaleriaError as erro:
        midias, problemas = [], [str(erro)]
    if not problemas and not 1 <= len(midias) <= MAX_ITENS_CARROSSEL:
        problemas.append(f"Escolha de 1 a {MAX_ITENS_CARROSSEL} fotos ou vídeos.")

    titulos = request.form.getlist("produto_titulo")
    fotos = request.form.getlist("produto_foto")
    links = request.form.getlist("produto_link")
    _completar_produtos(titulos, fotos, links)
    foto_padrao = ""
    if midias:
        foto_padrao = (url_para_foto(midias[0]["url"]) if midias[0].get("tipo") != "video"
                       else midias[0].get("thumbnail_url") or "")
    produtos, erros = ri.produtos_do_formulario(titulos, fotos, links, foto_padrao)
    problemas += erros
    if modo == "produtos" and not produtos and not erros:
        problemas.append("Coloque pelo menos 1 produto, ou escolha Criar diferente.")

    legenda = request.form.get("legenda", "").strip()
    if len(legenda) > 2200:
        problemas.append("A legenda passa de 2.200 letras.")

    form = {"modo": modo, "nome": request.form.get("nome", "").strip(), "legenda": legenda,
            "palavra": request.form.get("palavra", "").strip(), "ids": [m["id"] for m in midias]}
    if problemas:
        rascunho = [{"titulo": t, "foto": f, "link": l} for t, f, l in zip(titulos, fotos, links)
                    if t.strip() or f.strip() or l.strip()]
        return _pagina_publicar(_form_publicar({**form, "produtos": rascunho}), problemas)

    return render_template(
        "instagram_conferir.html", form=form, midias=midias, produtos=produtos,
        produtos_json=json.dumps(produtos, ensure_ascii=False), token=uuid.uuid4().hex,
        sem_quero=bool(produtos) and "quero" not in legenda.lower(),
    )


@app.route("/instagram-publicar/confirmar", methods=["POST"])
def instagram_publicar_confirmar():
    import json

    import robo_instagram as ri
    from web import galeria
    from web.instagram_publish import InstagramPublishError, dados_da_midia, publicar_midias

    token = request.form.get("token", "")
    try:
        produtos = json.loads(request.form.get("produtos_json") or "[]")
        midias = _midias_escolhidas(request.form.get("ids", "").split(","))
        if not token or not midias:
            flash("⚠️ Não encontrei o que publicar. Monte o post de novo.")
            return redirect(url_for("instagram_publicar"))
        if not ri.reservar_publicacao(token):
            flash("⚠️ Este post já foi enviado. Confira a lista abaixo antes de montar outro.")
            return redirect(url_for("instagram_publicar"))
    except (ValueError, RuntimeError, galeria.GaleriaError) as erro:
        flash(f"⚠️ Não consegui publicar: {erro}")
        return redirect(url_for("instagram_publicar"))

    legenda = request.form.get("legenda", "")
    nome = request.form.get("nome", "") or legenda[:40] or "Post"
    try:
        media_id = publicar_midias(midias, legenda)
    except InstagramPublishError as erro:
        ri.liberar_publicacao(token)
        flash(f"⚠️ O post não foi publicado: {erro}")
        return redirect(url_for("instagram_publicar"))
    except Exception as erro:  # noqa: BLE001
        # Pode ter saido mesmo assim: nao libera, para nao publicar em dobro.
        flash(f"⚠️ Falha sem resposta clara ({type(erro).__name__}). Confira no Instagram "
              "se o post saiu antes de tentar de novo.")
        return redirect(url_for("instagram_publicar"))

    registro = {"nome": nome[:80], "permalink": "", "produtos": len(produtos), "ligado": False}
    try:
        info = dados_da_midia(media_id)
        registro["permalink"] = info["permalink"]
        if produtos and info["shortcode"]:
            ri.ligar_post(info["shortcode"], nome, produtos, request.form.get("palavra", ""))
            registro["ligado"] = True
    except (InstagramPublishError, RuntimeError, requests.RequestException, ValueError) as erro:
        registro["erro"] = str(erro)[:200]
    try:
        ri.registrar_publicado(registro)
    except RuntimeError:
        pass

    if registro["ligado"]:
        flash(f"✅ Publicado, e o robô do QUERO já cuida deste post ({len(produtos)} produtos).")
    elif produtos:
        flash("⚠️ Publicado, mas não consegui ligar ao robô do QUERO. Cadastre o post em Robôs > Instagram.")
    else:
        flash("✅ Publicado.")
    return redirect(url_for("instagram_publicar"))


# ---------------------------------------------------------------------------
# WhatsApp - controle do robo de ofertas no grupo (robo_whatsapp.py).
# Ajustes, fila, cupons e historico ficam no Upstash (whatsapp_dados.py):
# o robo agendado no GitHub Actions le daqui antes de cada envio.
# ---------------------------------------------------------------------------

_DOMINIOS_LOJA = [
    ("mercadolivre", "Mercado Livre"), ("mercadolibre", "Mercado Livre"),
    ("meli.la", "Mercado Livre"), ("amazon.", "Amazon"), ("amzn.", "Amazon"),
    ("shopee", "Shopee"), ("shein", "Shein"), ("temu", "Temu"),
    ("magazineluiza", "Magalu"), ("magalu", "Magalu"),
]


def _loja_do_link(link):
    link = (link or "").lower()
    return next((loja for trecho, loja in _DOMINIOS_LOJA if trecho in link), "Outra")


def _pagina_whatsapp(lote=None, erro_lote=None, grupos=None):
    import robo_whatsapp
    import whatsapp_dados as wd

    contexto = {
        "faltando": robo_whatsapp.whatsapp_configurado(),
        "faltando_conexao": robo_whatsapp.conexao_configurada(),
        "grupos": grupos,
        "lojas": wd.LOJAS,
        "lote": lote,
        "erro_lote": erro_lote,
        "hoje": wd.agora_brasil().strftime("%Y-%m-%d"),
        "horas": list(range(6, 24)),
        "erro_dados": None,
    }
    try:
        contexto.update(
            config=wd.ler_config(),
            fila=wd.listar_fila(),
            cupons=wd.listar_cupons(),
            log=wd.ler_log()[:30],
        )
    except RuntimeError as erro:
        contexto.update(config=dict(wd.CONFIG_PADRAO), fila=[], cupons=[], log=[],
                        erro_dados=str(erro))
    return render_template("whatsapp.html", **contexto)


@app.route("/whatsapp")
def whatsapp():
    return _pagina_whatsapp()


@app.route("/whatsapp/previa", methods=["POST"])
def whatsapp_previa():
    import robo_whatsapp
    import whatsapp_dados as wd

    try:
        lote = robo_whatsapp.montar_lote(wd.ler_config(), gerar_links=False)
        return _pagina_whatsapp(lote=lote)
    except Exception as erro:  # noqa: BLE001
        return _pagina_whatsapp(lote=[], erro_lote=str(erro))


@app.route("/whatsapp/pular/<item_id>", methods=["POST"])
def whatsapp_pular(item_id):
    import whatsapp_dados as wd

    wd.pular_produto_shopee(item_id)
    flash("Produto pulado: ele não será enviado nos próximos 30 dias.")
    return redirect(url_for("whatsapp") + "#previa")


@app.route("/whatsapp/ligar", methods=["POST"])
def whatsapp_ligar():
    import whatsapp_dados as wd

    ativo = request.form.get("ativo") == "1"
    wd.salvar_config({"ativo": ativo})
    flash("✅ Robô ligado." if ativo else "⏸️ Robô pausado: nada será enviado até você ligar de novo.")
    return redirect(url_for("whatsapp"))


@app.route("/whatsapp/grupos", methods=["POST"])
def whatsapp_grupos():
    """Busca os grupos do chip na Evolution API pra Keiti escolher."""
    import robo_whatsapp

    faltando = robo_whatsapp.conexao_configurada()
    if faltando:
        flash("Falta configurar no Render: " + ", ".join(faltando) + ".")
        return redirect(url_for("whatsapp") + "#grupo")
    try:
        grupos = robo_whatsapp.listar_grupos()
    except Exception as erro:  # noqa: BLE001
        flash(f"Não consegui buscar os grupos: {erro}")
        return redirect(url_for("whatsapp") + "#grupo")
    if not grupos:
        flash("Nenhum grupo encontrado no chip. Confira se o chip está no grupo "
              "e se a instância está conectada.")
    return _pagina_whatsapp(grupos=grupos)


@app.route("/whatsapp/grupo/escolher", methods=["POST"])
def whatsapp_grupo_escolher():
    import whatsapp_dados as wd

    grupo_id = request.form.get("grupo_id", "").strip()
    nome = request.form.get("grupo_nome", "").strip()
    if not grupo_id.endswith("@g.us"):
        flash("Grupo inválido.")
        return redirect(url_for("whatsapp") + "#grupo")
    try:
        wd.salvar_config({"grupo_id": grupo_id, "grupo_nome": nome})
        flash(f"✅ Grupo escolhido: {nome or grupo_id}. Agora toque em ENVIAR TESTE.")
    except RuntimeError as erro:
        flash(f"Não consegui salvar o grupo: {erro}")
    return redirect(url_for("whatsapp") + "#grupo")


@app.route("/whatsapp/grupo/teste", methods=["POST"])
def whatsapp_grupo_teste():
    import robo_whatsapp

    faltando = robo_whatsapp.whatsapp_configurado()
    if faltando:
        flash("Ainda falta: " + ", ".join(faltando) + ".")
        return redirect(url_for("whatsapp") + "#grupo")
    try:
        robo_whatsapp.enviar_teste()
        flash("✅ Mensagem de teste enviada! Confira no grupo.")
    except Exception as erro:  # noqa: BLE001
        flash(f"O teste falhou: {erro}")
    return redirect(url_for("whatsapp") + "#grupo")


@app.route("/whatsapp/enviar-agora", methods=["POST"])
def whatsapp_enviar_agora():
    import threading

    import robo_whatsapp

    faltando = robo_whatsapp.whatsapp_configurado()
    if faltando:
        flash("O WhatsApp ainda não está conectado (falta: " + ", ".join(faltando) + ").")
        return redirect(url_for("whatsapp"))

    def _rodar():
        try:
            robo_whatsapp.enviar_lote("enviar agora (site)")
        except Exception as erro:  # noqa: BLE001
            import whatsapp_dados as wd

            wd.registrar("erro", "Falha ao enviar o lote", ok=False, erro=str(erro),
                         origem="enviar agora (site)")

    threading.Thread(target=_rodar, daemon=True).start()
    flash("🚀 Enviando o lote agora. Tem uma pausa entre as mensagens, então leva "
          "alguns minutos. Atualize a página para ver no histórico.")
    return redirect(url_for("whatsapp"))


@app.route("/whatsapp/fila/adicionar", methods=["POST"])
def whatsapp_fila_adicionar():
    import whatsapp_dados as wd

    # O fila_ml.py (tarefa agendada do Mercado Livre) manda formato=json e
    # recebe a resposta em JSON em vez de voltar para a pagina.
    em_json = request.form.get("formato") == "json"

    def _responder(ok: bool, mensagem: str, situacao: str):
        if em_json:
            return jsonify({"ok": ok, "situacao": situacao, "mensagem": mensagem})
        flash(mensagem)
        return redirect(url_for("ofertas") + "#fila")

    link = request.form.get("link", "").strip()
    if not link.startswith("http"):
        return _responder(False, "Cole o link completo do produto (começando com https://).",
                          "erro")

    loja = request.form.get("loja") or "auto"
    if loja == "auto":
        loja = _loja_do_link(link)
    nome = request.form.get("nome", "").strip()
    preco = request.form.get("preco", "").strip()
    preco_antigo = request.form.get("preco_antigo", "").strip()
    imagem = request.form.get("imagem", "").strip()

    if loja == "Amazon" and em_json:
        # Regra do programa de associados: preco/foto copiados do site nao
        # podem ir na mensagem (o WhatsApp mostra a previa do link sozinho).
        preco = preco_antigo = imagem = ""
    elif not nome or not imagem or not preco:
        info = produto_manual.buscar_metadados_link(link)
        nome = nome or info.get("nome", "")
        imagem = imagem or info.get("imagem", "")
        preco = preco or info.get("preco_texto", "")

    if not nome:
        return _responder(False, "Não consegui pegar o nome do produto sozinho (a loja "
                          "bloqueou). Cole o link de novo e preencha o nome (e o preço, "
                          "se quiser).", "erro")

    if em_json:
        proibida = wd.tem_palavra_bloqueada(
            nome, wd.ler_config().get("palavras_bloqueadas") or [])
        if proibida:
            return _responder(False, f"Palavra bloqueada ({proibida}): {nome[:60]}",
                              "bloqueado")

    repetido = wd.produto_repetido(nome)
    if repetido == "fila":
        return _responder(False, f"Esse produto já está na fila: {nome[:60]}", "repetido")
    if repetido == "enviado" and em_json:
        return _responder(False, f"Esse produto saiu há pouco no grupo: {nome[:60]}",
                          "repetido")
    if em_json:
        tipo = wd.tipo_repetido(nome)
        if tipo:
            return _responder(False, f"Já tem produto desse tipo hoje ({tipo}): {nome[:60]}",
                              "repetido")

    if loja == "Amazon":
        link = wd.aplicar_tag_amazon(link, wd.ler_config().get("amazon_tag", ""))

    # Prazo vem so da tarefa agendada (fila_ml.py); colado na pagina nao vence.
    try:
        vale_ate = float(request.form.get("vale_ate") or 0)
    except ValueError:
        vale_ate = 0
    wd.adicionar_na_fila(loja, link, nome, preco, imagem,
                         request.form.get("observacao", ""), preco_antigo,
                         vale_ate=vale_ate,
                         vale_ate_texto=request.form.get("vale_ate_texto", "").strip(),
                         prioridade=request.form.get("prioridade") == "1",
                         cupom=request.form.get("cupom", ""))
    return _responder(True, f"✅ Adicionado na fila: {nome[:60]}", "adicionado")


@app.route("/whatsapp/fila/remover/<item_id>", methods=["POST"])
def whatsapp_fila_remover(item_id):
    import whatsapp_dados as wd

    wd.remover_da_fila(item_id)
    return redirect(url_for("ofertas") + "#fila")


@app.route("/whatsapp/fila/mover/<item_id>/<direcao>", methods=["POST"])
def whatsapp_fila_mover(item_id, direcao):
    import whatsapp_dados as wd

    wd.mover_na_fila(item_id, -1 if direcao == "cima" else 1)
    return redirect(url_for("ofertas") + "#fila")


@app.route("/whatsapp/cupons/adicionar", methods=["POST"])
def whatsapp_cupons_adicionar():
    import whatsapp_dados as wd

    # O fila_ml.py (tarefa agendada) manda formato=json: recebe JSON, o
    # cupom e' checado contra repetidos e sai uma vez so.
    em_json = request.form.get("formato") == "json"

    def _responder(ok: bool, mensagem: str, situacao: str):
        if em_json:
            return jsonify({"ok": ok, "situacao": situacao, "mensagem": mensagem})
        flash(mensagem)
        return redirect(url_for("cupons"))

    codigo = request.form.get("codigo", "").strip()
    descricao = request.form.get("descricao", "").strip()
    link = request.form.get("link", "").strip()
    if not (codigo or link):
        return _responder(False, "Preencha pelo menos o código do cupom ou o link.", "erro")
    loja = request.form.get("loja") or "Outra"
    if em_json and wd.produto_repetido(descricao or codigo, cupom=True):
        return _responder(False, f"Cupom já cadastrado ou enviado há pouco: {descricao or codigo}",
                          "repetido")
    if loja == "Amazon" and link:
        link = wd.aplicar_tag_amazon(link, wd.ler_config().get("amazon_tag", ""))
    wd.adicionar_cupom(loja, codigo, descricao, link, request.form.get("validade", ""),
                       request.form.get("detalhes", ""), request.form.get("como_ativar", ""),
                       uma_vez=em_json, desconto=request.form.get("desconto", ""),
                       desconto_tipo=request.form.get("desconto_tipo", "%"),
                       minimo=request.form.get("minimo", ""), limite=request.form.get("limite", ""))
    if em_json:
        return _responder(True, f"✅ Cupom cadastrado: {descricao or codigo}", "adicionado")
    return _responder(True, "✅ Cupom cadastrado. Ele sai na primeira rodada do dia (1x por dia, "
                      "até vencer). Para soltar antes, use \"Usar na rodada\".", "adicionado")


@app.route("/whatsapp/cupons/remover/<cupom_id>", methods=["POST"])
def whatsapp_cupons_remover(cupom_id):
    import whatsapp_dados as wd

    wd.remover_cupom(cupom_id)
    return redirect(url_for("cupons"))


def _inteiro(valor, padrao, minimo, maximo):
    try:
        return max(minimo, min(maximo, int(valor)))
    except (TypeError, ValueError):
        return padrao


@app.route("/whatsapp/ajustes", methods=["POST"])
def whatsapp_ajustes():
    import whatsapp_dados as wd

    rodadas = _horarios(request.form.get("rodadas"))

    por_lote = _inteiro(request.form.get("por_lote"), 3, 1, 10)

    def _linhas(campo):
        return [l.strip() for l in request.form.get(campo, "").splitlines() if l.strip()]

    categorias = _linhas("categorias")
    if request.form.get("incluir_geral"):
        categorias = [""] + [c for c in categorias if c]

    wd.salvar_config({
        "rodadas": rodadas,
        "ofertas_por_rodada": _inteiro(request.form.get("ofertas_por_rodada"), 20, 1, 30),
        "por_lote": por_lote,
        "fila_por_lote": _inteiro(request.form.get("fila_por_lote"), 1, 0, por_lote),
        "cupons_por_lote": _inteiro(request.form.get("cupons_por_lote"), 1, 0, 3),
        "amazon_tag": request.form.get("amazon_tag", "").strip(),
        "palavras_bloqueadas": _linhas("palavras_bloqueadas"),
        "categorias": categorias or wd.CATEGORIAS_PADRAO,
        "ganchos": _linhas("ganchos") or wd.GANCHOS_PADRAO,
        "chamadas": _linhas("chamadas") or wd.CHAMADAS_PADRAO,
        "nome_curto_ia": bool(request.form.get("nome_curto_ia")),
    })
    if not rodadas:
        flash("⚠️ Ajustes salvos, mas sem horário de rodada válido: o robô não vai enviar sozinho.")
    else:
        flash("✅ Ajustes salvos.")
    return redirect(url_for("whatsapp") + "#ajustes")


def _horarios(texto):
    """Horarios separados por virgula ou espaco; o que nao for hora valida fica de fora."""
    return sorted({h for h in re.split(r"[,;\s]+", texto or "")
                   if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", h)})


# ------------------------------------------------------------ cupons

@app.route("/cupons")
def cupons():
    import whatsapp_dados as wd

    hoje, lista, erro_dados = wd.agora_brasil().strftime("%Y-%m-%d"), [], ""
    try:
        lista = wd.listar_cupons()
    except RuntimeError as erro:
        erro_dados = str(erro)
    # Validos primeiro, os que vencem antes em cima; vencidos no fim.
    lista = sorted(lista, key=lambda c: (bool(c.get("validade") and c["validade"] < hoje),
                                         not c.get("validade"), c.get("validade") or ""))
    return render_template(
        "cupons.html", cupons=lista, lojas=wd.LOJAS, hoje=hoje, erro_dados=erro_dados,
        validos=sum(1 for c in lista if wd.cupom_valido(c, hoje)),
        conferidos=sum(1 for c in lista if c.get("conferido") and wd.cupom_valido(c, hoje)),
    )


@app.route("/cupons/<cupom_id>/conferir", methods=["POST"])
def cupom_conferir(cupom_id):
    import whatsapp_dados as wd

    wd.atualizar_cupom(cupom_id, conferido=request.form.get("conferido") == "1")
    return redirect(url_for("cupons"))


@app.route("/cupons/<cupom_id>/usar", methods=["POST"])
def cupom_usar(cupom_id):
    import whatsapp_dados as wd

    wd.atualizar_cupom(cupom_id, prioridade=True)
    flash("✅ Este cupom sai na próxima rodada.")
    return redirect(url_for("cupons"))


# ------------------------------------------------------------ ofertas

@app.route("/ofertas")
def ofertas():
    import robo_whatsapp
    import whatsapp_dados as wd

    erro_dados, fila = "", []
    config = dict(wd.CONFIG_PADRAO)
    try:
        config, fila = wd.ler_config(), wd.listar_fila()
    except RuntimeError as erro:
        erro_dados = str(erro)
    categorias = [c for c in (config.get("categorias") or []) if c][:12]
    return render_template(
        "ofertas.html", config=config, fila=fila, erro_dados=erro_dados, lojas=wd.LOJAS,
        categorias=categorias, faltando=robo_whatsapp.whatsapp_configurado(),
        proxima=wd.proxima_rodada(config, wd.agora_brasil()),
    )


@app.route("/ofertas/ritmo", methods=["POST"])
def ofertas_ritmo():
    import whatsapp_dados as wd

    rodadas = _horarios(request.form.get("rodadas"))
    if not rodadas:
        flash("⚠️ Nada foi salvo: coloque pelo menos um horário, como 07:00.")
        return redirect(url_for("ofertas"))
    wd.salvar_config({"rodadas": rodadas,
                      "ofertas_por_rodada": _inteiro(request.form.get("ofertas_por_rodada"), 20, 1, 30)})
    flash("✅ Ritmo salvo.")
    return redirect(url_for("ofertas"))


@app.route("/api/ofertas/adicionar-shopee", methods=["POST"])
def api_ofertas_adicionar_shopee():
    """O + do garimpo: poe o produto na fila, com link de afiliado."""
    import robo_whatsapp
    import whatsapp_dados as wd

    produto = request.get_json(force=True) or {}
    nome = str(produto.get("productName") or "").strip()
    if not nome:
        return jsonify({"ok": False, "mensagem": "Produto sem nome: não adicionei."})
    try:
        if wd.produto_repetido(nome) == "fila":
            return jsonify({"ok": False, "mensagem": f"Já está na fila: {nome[:60]}"})
        link = robo_whatsapp.link_afiliado_shopee(produto)
        if not link:
            return jsonify({"ok": False, "mensagem": "A Shopee não devolveu o link deste produto."})
        preco = numero(produto.get("priceMin"))
        wd.adicionar_na_fila("Shopee", link, nome, f"{preco:.2f}".replace(".", ",") if preco else "",
                             str(produto.get("imageUrl") or ""))
    except RuntimeError as erro:
        return jsonify({"ok": False, "mensagem": f"Não consegui salvar: {erro}"})
    return jsonify({"ok": True, "mensagem": f"Na fila: {nome[:60]}"})


@app.route("/api/ofertas/converter", methods=["POST"])
def api_ofertas_converter():
    from shopee import gerar_link_curto

    dados = request.get_json(force=True) or {}
    itens = []
    for link in [l.strip() for l in str(dados.get("links") or "").splitlines() if l.strip()][:20]:
        if not link.startswith("https://"):
            itens.append({"link": link, "situacao": "⚠️ Não é um link https: ignorado"})
        elif "shopee" not in link.lower():
            itens.append({"link": link, "situacao": "Outra loja: ficou como estava"})
        else:
            try:
                itens.append({"link": gerar_link_curto(link, ["radar"]), "situacao": "✅ Shopee: seu link"})
            except (RuntimeError, requests.RequestException) as erro:
                itens.append({"link": link, "situacao": f"⚠️ Não converti: {str(erro)[:80]}"})
    return jsonify({"itens": itens})


# ------------------------------------------------------------ robo do Instagram

@app.route("/instagram-robo")
def instagram_robo():
    import robo_instagram as ri

    erro_dados = ""
    config, log, execucao = {}, [], {}
    try:
        config, log, execucao = ri.ler_config(), ri.ler_log(), ri.ler_execucao()
    except RuntimeError as erro:
        erro_dados = str(erro)
    return render_template("instagram_robo.html", config=config, log=log, execucao=execucao,
                           erro_dados=erro_dados)


@app.route("/instagram-robo/ligar", methods=["POST"])
def instagram_robo_ligar():
    import robo_instagram as ri

    ativo = request.form.get("ativo") == "1"
    ri.salvar_config({"ativo": ativo})
    flash("✅ Robô ligado: ele responde na próxima conferida, em até 10 minutos." if ativo
          else "⏸️ Robô desligado: nenhuma mensagem será enviada.")
    return redirect(url_for("instagram_robo"))


@app.route("/instagram-robo/direct", methods=["POST"])
def instagram_robo_direct():
    import robo_instagram as ri

    ativo = request.form.get("ativo") == "1"
    ri.salvar_config({"direct_ativo": ativo})
    flash("✅ Resposta do Direct ligada: começa na próxima conferida, em até 10 minutos." if ativo
          else "⏸️ Resposta do Direct desligada.")
    return redirect(url_for("instagram_robo"))


@app.route("/instagram-robo/botao-pronto", methods=["POST"])
def instagram_robo_botao_pronto():
    import robo_instagram as ri
    from web.instagram_publish import InstagramPublishError

    ligar = request.form.get("ligar") == "1"
    try:
        ri.trocar_botao_pronto(ligar)
        flash("✅ Botão pronto ativado no Direct." if ligar else "✅ Botão pronto removido do Direct.")
    except InstagramPublishError as erro:
        flash(f"⚠️ Não consegui mudar o botão: {erro}")
    return redirect(url_for("instagram_robo"))


@app.route("/instagram-robo/post", methods=["POST"])
def instagram_robo_post():
    import robo_instagram as ri

    codigo = ri.codigo_do_post(request.form.get("post", ""))
    produtos, problemas = ri.ler_produtos(request.form.get("produtos", ""))
    if not codigo:
        problemas.insert(0, "Não reconheci o link do post.")
    if problemas:
        flash("⚠️ Nada foi salvo. " + " ".join(problemas))
        return redirect(url_for("instagram_robo"))
    ri.ligar_post(codigo, request.form.get("nome", ""), produtos, request.form.get("palavra", ""))
    flash("✅ Post salvo.")
    return redirect(url_for("instagram_robo"))


@app.route("/instagram-robo/post/<codigo>/remover", methods=["POST"])
def instagram_robo_remover(codigo):
    import robo_instagram as ri

    posts = dict(ri.ler_config().get("posts") or {})
    posts.pop(codigo, None)
    ri.salvar_config({"posts": posts})
    flash("✅ O robô não responde mais nesse post.")
    return redirect(url_for("instagram_robo"))


if __name__ == "__main__":
    # threaded=True: a geracao de video (dezenas de segundos) nao trava
    # o resto do site enquanto roda.
    #
    # debug fica LIGADO por padrao (uso local). Ao expor o site para fora
    # (ngrok etc.), rode com  FLASK_DEBUG=0  -> desliga o debugger do
    # Werkzeug, que permite execucao de codigo remoto se ficar acessivel.
    debug = os.environ.get("FLASK_DEBUG", "1") != "0"
    app.run(debug=debug, port=5000, threaded=True)
