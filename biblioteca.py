"""Camada de dados da Biblioteca: indice de midias (video/imagem) salvas
no app, cada uma com os destinos de postagem marcados (Instagram,
Pinterest, Shopee, ou qualquer nome que a pessoa cadastrar). Sem
dependencia de Android - roda igual no celular e no PC."""

import json
import os
import shutil
import time
import uuid

try:
    from kivy.app import App
except ImportError:
    App = None

NOME_ARQUIVO_INDICE = "biblioteca.json"
NOME_ARQUIVO_DESTINOS = "destinos.json"
NOME_PASTA_MIDIAS = "biblioteca_midias"

DESTINOS_PADRAO = ["Instagram", "Pinterest", "Shopee"]


def _pasta_dados():
    """No celular, usa user_data_dir (unica pasta gravavel garantida no
    Android). Fora do app (testes no PC), usa a pasta do projeto."""
    if App is not None:
        app = App.get_running_app()
        if app is not None:
            return app.user_data_dir
    return os.path.dirname(os.path.abspath(__file__))


def _caminho_indice():
    return os.path.join(_pasta_dados(), NOME_ARQUIVO_INDICE)


def _caminho_destinos():
    return os.path.join(_pasta_dados(), NOME_ARQUIVO_DESTINOS)


def _pasta_midias():
    pasta = os.path.join(_pasta_dados(), NOME_PASTA_MIDIAS)
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _ler_json(caminho, padrao):
    if not os.path.exists(caminho):
        return padrao
    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (ValueError, OSError):
        return padrao


def _salvar_json(caminho, dados):
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)


def listar_itens():
    """Mais recentes primeiro."""
    itens = _ler_json(_caminho_indice(), [])
    return sorted(itens, key=lambda item: item.get("data_adicionado", 0), reverse=True)


def listar_destinos():
    destinos = _ler_json(_caminho_destinos(), None)
    if destinos is None:
        destinos = list(DESTINOS_PADRAO)
        _salvar_json(_caminho_destinos(), destinos)
    return destinos


def adicionar_destino(nome):
    nome = nome.strip()
    if not nome:
        return listar_destinos()
    destinos = listar_destinos()
    if nome not in destinos:
        destinos.append(nome)
        _salvar_json(_caminho_destinos(), destinos)
    return destinos


def remover_destino(nome):
    destinos = [d for d in listar_destinos() if d != nome]
    _salvar_json(_caminho_destinos(), destinos)

    itens = _ler_json(_caminho_indice(), [])
    for item in itens:
        if nome in item.get("destinos", []):
            item["destinos"].remove(nome)
    _salvar_json(_caminho_indice(), itens)
    return destinos


def caminho_completo(item):
    return os.path.join(_pasta_midias(), item["arquivo"])


def caminho_thumbnail(item):
    if not item.get("thumbnail"):
        return None
    return os.path.join(_pasta_midias(), item["thumbnail"])


def adicionar_item(caminho_origem, tipo):
    """Copia o arquivo de origem pra dentro da pasta da Biblioteca e
    registra a entrada no indice. tipo: 'video' ou 'imagem'."""
    extensao = os.path.splitext(caminho_origem)[1].lower()
    nome_arquivo = f"{uuid.uuid4().hex}{extensao}"
    destino = os.path.join(_pasta_midias(), nome_arquivo)
    shutil.copyfile(caminho_origem, destino)

    thumbnail = None
    if tipo == "video":
        nome_thumb = f"{os.path.splitext(nome_arquivo)[0]}_thumb.jpg"
        caminho_thumb = os.path.join(_pasta_midias(), nome_thumb)
        import android_integracao

        if android_integracao.gerar_thumbnail_video(destino, caminho_thumb):
            thumbnail = nome_thumb

    item = {
        "id": uuid.uuid4().hex,
        "tipo": tipo,
        "arquivo": nome_arquivo,
        "thumbnail": thumbnail,
        "nome_original": os.path.basename(caminho_origem),
        "data_adicionado": time.time(),
        "destinos": [],
    }

    itens = _ler_json(_caminho_indice(), [])
    itens.append(item)
    _salvar_json(_caminho_indice(), itens)
    return item


def remover_item(item_id):
    itens = _ler_json(_caminho_indice(), [])
    restante = []
    for item in itens:
        if item["id"] == item_id:
            for caminho in (caminho_completo(item), caminho_thumbnail(item)):
                if caminho and os.path.exists(caminho):
                    try:
                        os.remove(caminho)
                    except OSError:
                        pass
        else:
            restante.append(item)
    _salvar_json(_caminho_indice(), restante)


def alternar_destino(item_id, destino):
    itens = _ler_json(_caminho_indice(), [])
    for item in itens:
        if item["id"] == item_id:
            destinos_item = item.setdefault("destinos", [])
            if destino in destinos_item:
                destinos_item.remove(destino)
            else:
                destinos_item.append(destino)
            break
    _salvar_json(_caminho_indice(), itens)
