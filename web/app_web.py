"""Versao web do Radar Afiliados - roda localmente com Flask, usando os
mesmos modulos e as mesmas credenciais (credenciais_locais.py) do app
Android. Nao substitui o app; e' so mais uma forma de acessar, pelo
navegador do notebook.

Rodar: python web/app_web.py  ->  http://localhost:5000
"""

import hmac
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename

import produto_manual
from shopee import buscar_produtos, numero

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # 12MB - foto enviada do celular
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
    return render_template("principal.html", plataformas_manuais=plataformas_manuais)


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
    if modo_ia not in (None, "fundo", "video"):
        modo_ia = None

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
            produto, roteiro, modo_ia=modo_ia, prompt_video=prompt_video
        )
    except RuntimeError as erro:
        return jsonify({"sucesso": False, "erro": str(erro)})
    except Exception as erro:  # noqa: BLE001
        return jsonify({"sucesso": False, "erro": f"Erro ao gerar video: {erro}"})

    nome_arquivo = os.path.basename(caminho_mp4)

    # Salva na Galeria automaticamente (Cloudinary+Upstash - sobrevive a
    # reinicio do Render). Best-effort: se falhar, o video gerado ainda
    # e' devolvido normalmente (da pra baixar), so avisamos na tela.
    aviso_galeria = None
    try:
        from web import galeria

        galeria.adicionar_item(caminho_mp4, "video", nome_original=dados.get("nome"))
    except Exception as erro:  # noqa: BLE001
        aviso_galeria = f"Vídeo pronto, mas não consegui salvar na Galeria: {erro}"

    return jsonify(
        {
            "sucesso": True,
            "video_url": url_for("static", filename=f"videos/{nome_arquivo}"),
            "narracao": motor_tts,
            "roteiro": roteiro,
            "aviso_galeria": aviso_galeria,
        }
    )


@app.route("/api/instagram/postar", methods=["POST"])
def api_instagram_postar():
    """Publica o video ja aprovado como Reel no Instagram (@clubedoquero).

    Recebe a URL do video (a que a Creatify devolveu) e a legenda (o texto
    da campanha). Sincrono - o Instagram processa o video antes de publicar
    (segundos a poucos minutos)."""
    dados = request.get_json(force=True)
    video_url = (dados.get("video_url") or "").strip()
    legenda = (dados.get("legenda") or "").strip()

    if not video_url:
        return jsonify({"sucesso": False, "erro": "Sem URL de video para publicar."})

    try:
        from web.instagram_publish import InstagramPublishError, postar_reel

        media_id = postar_reel(video_url, legenda)
    except InstagramPublishError as erro:
        return jsonify({"sucesso": False, "erro": str(erro)})
    except Exception as erro:  # noqa: BLE001
        return jsonify({"sucesso": False, "erro": f"Erro ao publicar no Instagram: {erro}"})

    return jsonify({"sucesso": True, "media_id": media_id})


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


if __name__ == "__main__":
    # threaded=True: a geracao de video (dezenas de segundos) nao trava
    # o resto do site enquanto roda.
    #
    # debug fica LIGADO por padrao (uso local). Ao expor o site para fora
    # (ngrok etc.), rode com  FLASK_DEBUG=0  -> desliga o debugger do
    # Werkzeug, que permite execucao de codigo remoto se ficar acessivel.
    debug = os.environ.get("FLASK_DEBUG", "1") != "0"
    app.run(debug=debug, port=5000, threaded=True)
