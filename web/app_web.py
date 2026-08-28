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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

import biblioteca
import produto_manual
from shopee import buscar_produtos, numero

app = Flask(__name__)

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
    "mercado-livre": ("Mercado Livre", AVISO_ML),
    "amazon": ("Amazon", ""),
    "shein": ("Shein", ""),
    "temu": ("Temu", ""),
}


def _texto_preco(dados):
    preco = dados.get("preco")
    if isinstance(preco, (int, float)):
        return f"{preco:.2f}"
    return str(dados.get("preco_texto") or preco or "")


def _encontrar_item_biblioteca(item_id):
    for item in biblioteca.listar_itens():
        if item["id"] == item_id:
            return item
    return None


# ---------------------------------------------------------------------------
# Paginas
# ---------------------------------------------------------------------------

@app.route("/")
def principal():
    plataformas_manuais = [(slug, nome) for slug, (nome, _aviso) in PLATAFORMAS_MANUAIS.items()]
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
    nome_plataforma, aviso = dados
    return render_template("manual.html", nome_plataforma=nome_plataforma, aviso=aviso)


@app.route("/biblioteca")
def biblioteca_pagina():
    return render_template(
        "biblioteca.html",
        itens=biblioteca.listar_itens(),
        destinos=biblioteca.listar_destinos(),
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


@app.route("/api/campanha/video", methods=["POST"])
def api_campanha_video():
    """Gera um video curto (mp4) de divulgacao: foto do produto +
    texto na tela + narracao. Sincrono - pode levar ~30-60s."""
    dados = request.get_json(force=True)

    if not dados.get("nome"):
        return jsonify({"sucesso": False, "erro": "Produto sem nome."})

    try:
        from campanhas_ia import gerar_roteiro_video

        from web.video_campanha import montar_video

        roteiro = gerar_roteiro_video(
            plataforma=dados.get("plataforma", ""),
            produto=dados.get("nome", ""),
            preco=_texto_preco(dados),
            comissao=dados.get("comissao_texto", ""),
            vendas=str(dados.get("vendas", "") or ""),
            link=dados.get("link", ""),
        )
        caminho_mp4, motor_tts = montar_video(dados, roteiro)
    except RuntimeError as erro:
        return jsonify({"sucesso": False, "erro": str(erro)})
    except Exception as erro:  # noqa: BLE001
        return jsonify({"sucesso": False, "erro": f"Erro ao gerar video: {erro}"})

    nome_arquivo = os.path.basename(caminho_mp4)
    return jsonify(
        {
            "sucesso": True,
            "video_url": url_for("static", filename=f"videos/{nome_arquivo}"),
            "narracao": motor_tts,
            "roteiro": roteiro,
        }
    )


# ---------------------------------------------------------------------------
# Biblioteca
# ---------------------------------------------------------------------------

@app.route("/biblioteca/importar", methods=["POST"])
def biblioteca_importar():
    tipo = request.form.get("tipo", "imagem")
    arquivo = request.files.get("arquivo")

    if arquivo and arquivo.filename:
        nome_seguro = secure_filename(arquivo.filename)
        caminho_temp = os.path.join(tempfile.gettempdir(), nome_seguro)
        arquivo.save(caminho_temp)
        biblioteca.adicionar_item(caminho_temp, tipo)
        os.remove(caminho_temp)

    return redirect(url_for("biblioteca_pagina"))


@app.route("/biblioteca/excluir/<item_id>", methods=["POST"])
def biblioteca_excluir(item_id):
    biblioteca.remover_item(item_id)
    return redirect(url_for("biblioteca_pagina"))


@app.route("/biblioteca/destino/alternar", methods=["POST"])
def biblioteca_alternar_destino():
    biblioteca.alternar_destino(request.form["item_id"], request.form["destino"])
    return redirect(url_for("biblioteca_pagina"))


@app.route("/biblioteca/destino/adicionar", methods=["POST"])
def biblioteca_adicionar_destino():
    biblioteca.adicionar_destino(request.form.get("nome", ""))
    return redirect(url_for("biblioteca_pagina"))


@app.route("/biblioteca/destino/remover", methods=["POST"])
def biblioteca_remover_destino():
    biblioteca.remover_destino(request.form.get("nome", ""))
    return redirect(url_for("biblioteca_pagina"))


@app.route("/biblioteca/midia/<item_id>")
def biblioteca_midia(item_id):
    item = _encontrar_item_biblioteca(item_id)
    if item is None:
        return "Midia nao encontrada.", 404
    return send_file(biblioteca.caminho_completo(item))


if __name__ == "__main__":
    # threaded=True: a geracao de video (dezenas de segundos) nao trava
    # o resto do site enquanto roda.
    #
    # debug fica LIGADO por padrao (uso local). Ao expor o site para fora
    # (ngrok etc.), rode com  FLASK_DEBUG=0  -> desliga o debugger do
    # Werkzeug, que permite execucao de codigo remoto se ficar acessivel.
    debug = os.environ.get("FLASK_DEBUG", "1") != "0"
    app.run(debug=debug, port=5000, threaded=True)
