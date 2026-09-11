"""Galeria (web): guarda os videos/imagens gerados pelo app numa nuvem
duravel - o Render (plano free) apaga o disco local a cada
reinicio/deploy, entao guardar so localmente faria a Galeria sumir
sozinha (mesmo problema que resolvemos pro token do Kairogen).

  - Arquivo (video/imagem)  -> Cloudinary (25GB gratis), upload
    assinado via REST, sem precisar do SDK deles.
  - Metadados (id, tipo, url, nome, data, destinos de postagem) ->
    Upstash Redis (o MESMO cofrinho ja usado por web/kairogen_auth.py),
    guardados como uma lista JSON.

Variaveis de ambiente necessarias (Render -> Environment):
    UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN   (ja configurados)
    CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET

NAO confundir com o biblioteca.py da raiz do projeto: aquele e' do app
Android (Kivy) e guarda tudo localmente no celular, o que faz sentido
la (disco do celular nao some). Este arquivo e' so pra versao web.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid

import requests

_CHAVE_ITENS = "galeria:itens"
_CHAVE_DESTINOS = "galeria:destinos"
DESTINOS_PADRAO = ["Instagram", "Pinterest", "Shopee"]
PASTA_CLOUDINARY = "radar-afiliados"


class GaleriaError(RuntimeError):
    """Falha ao salvar/ler a Galeria - mensagem amigavel."""


# --------------------------------------------------------------------------
# Upstash (metadados / indice)
# --------------------------------------------------------------------------
def _upstash_cfg():
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
    if not url or not token:
        raise GaleriaError(
            "Upstash nao configurado (faltam UPSTASH_REDIS_REST_URL / "
            "UPSTASH_REDIS_REST_TOKEN no Environment)."
        )
    return url, token


def _upstash_cmd(cmd: list):
    url, token = _upstash_cfg()
    try:
        resp = requests.post(
            url, headers={"Authorization": f"Bearer {token}"}, json=cmd, timeout=15
        )
    except requests.RequestException as erro:
        raise GaleriaError(f"Upstash inacessivel: {erro}") from erro
    if resp.status_code != 200:
        raise GaleriaError(f"Upstash erro HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json().get("result")


def _ler_bruto(chave):
    bruto = _upstash_cmd(["GET", chave])
    if not bruto:
        return None
    try:
        return json.loads(bruto)
    except json.JSONDecodeError:
        return None


def _salvar(chave, valores):
    _upstash_cmd(["SET", chave, json.dumps(valores)])


# --------------------------------------------------------------------------
# Cloudinary (arquivo)
# --------------------------------------------------------------------------
def _cloudinary_cfg():
    cloud = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
    key = os.environ.get("CLOUDINARY_API_KEY", "").strip()
    secret = os.environ.get("CLOUDINARY_API_SECRET", "").strip()
    if not (cloud and key and secret):
        raise GaleriaError(
            "Cloudinary nao configurado (faltam CLOUDINARY_CLOUD_NAME / "
            "CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET no Environment)."
        )
    return cloud, key, secret


def _assinatura_cloudinary(parametros: dict, api_secret: str) -> str:
    """Algoritmo oficial do Cloudinary pra upload assinado: ordena os
    parametros (exceto file/cloud_name/resource_type/api_key/signature)
    por nome, junta em 'chave=valor' com '&', cola o api_secret no
    final (sem separador) e tira o SHA-1."""
    string_para_assinar = "&".join(f"{k}={v}" for k, v in sorted(parametros.items()))
    return hashlib.sha1((string_para_assinar + api_secret).encode("utf-8")).hexdigest()


def _upload_cloudinary(caminho_arquivo: str, tipo: str) -> dict:
    cloud, key, secret = _cloudinary_cfg()
    parametros = {"timestamp": int(time.time()), "folder": PASTA_CLOUDINARY}
    assinatura = _assinatura_cloudinary(parametros, secret)

    resource_type = "video" if tipo == "video" else "image"
    url_upload = f"https://api.cloudinary.com/v1_1/{cloud}/{resource_type}/upload"

    try:
        with open(caminho_arquivo, "rb") as arquivo:
            resp = requests.post(
                url_upload,
                data={**parametros, "api_key": key, "signature": assinatura},
                files={"file": arquivo},
                timeout=120,
            )
    except (requests.RequestException, OSError) as erro:
        raise GaleriaError(f"Erro ao enviar pro Cloudinary: {erro}") from erro

    corpo = resp.json() if resp.content else {}
    if resp.status_code != 200:
        msg = corpo.get("error", {}).get("message") or f"HTTP {resp.status_code}"
        raise GaleriaError(f"Cloudinary recusou o upload: {msg}")
    return corpo


def _apagar_cloudinary(public_id: str, tipo: str) -> None:
    """Apaga o arquivo no Cloudinary. Falha aqui NAO deve travar a
    remocao do item na Galeria - so avisamos no console do servidor."""
    try:
        cloud, key, secret = _cloudinary_cfg()
    except GaleriaError:
        return
    parametros = {"timestamp": int(time.time()), "public_id": public_id}
    assinatura = _assinatura_cloudinary(parametros, secret)
    resource_type = "video" if tipo == "video" else "image"
    url_destroy = f"https://api.cloudinary.com/v1_1/{cloud}/{resource_type}/destroy"
    try:
        requests.post(
            url_destroy,
            data={**parametros, "api_key": key, "signature": assinatura},
            timeout=30,
        )
    except requests.RequestException as erro:
        print(f"[galeria] aviso: nao consegui apagar {public_id} no Cloudinary: {erro}")


def _thumbnail_de(resultado_upload: dict, tipo: str):
    if tipo == "imagem":
        return resultado_upload.get("secure_url")
    # video: o Cloudinary gera uma miniatura jpg sozinho - basta trocar
    # a extensao do arquivo na URL (transformacao automatica deles).
    url = resultado_upload.get("secure_url") or ""
    if url.lower().endswith(".mp4"):
        return url[: -len(".mp4")] + ".jpg"
    return None


# --------------------------------------------------------------------------
# API publica (mesmo formato do biblioteca.py, pra facilitar o template)
# --------------------------------------------------------------------------
def listar_itens():
    """Mais recentes primeiro."""
    itens = _ler_bruto(_CHAVE_ITENS) or []
    return sorted(itens, key=lambda item: item.get("data_adicionado", 0), reverse=True)


def listar_destinos():
    destinos = _ler_bruto(_CHAVE_DESTINOS)
    if destinos is None:
        destinos = list(DESTINOS_PADRAO)
        _salvar(_CHAVE_DESTINOS, destinos)
    return destinos


def adicionar_destino(nome):
    nome = (nome or "").strip()
    if not nome:
        return listar_destinos()
    destinos = listar_destinos()
    if nome not in destinos:
        destinos.append(nome)
        _salvar(_CHAVE_DESTINOS, destinos)
    return destinos


def remover_destino(nome):
    destinos = [d for d in listar_destinos() if d != nome]
    _salvar(_CHAVE_DESTINOS, destinos)

    itens = listar_itens()
    for item in itens:
        if nome in item.get("destinos", []):
            item["destinos"].remove(nome)
    _salvar(_CHAVE_ITENS, itens)
    return destinos


def adicionar_item(caminho_arquivo, tipo, nome_original=None):
    """Sobe o arquivo pro Cloudinary e registra no indice (Upstash).
    tipo: 'video' ou 'imagem'. Devolve o item criado."""
    resultado = _upload_cloudinary(caminho_arquivo, tipo)
    item = {
        "id": uuid.uuid4().hex,
        "tipo": tipo,
        "url": resultado.get("secure_url"),
        "thumbnail_url": _thumbnail_de(resultado, tipo),
        "public_id": resultado.get("public_id"),
        "nome_original": nome_original or os.path.basename(caminho_arquivo),
        "data_adicionado": time.time(),
        "destinos": [],
    }
    itens = listar_itens()
    itens.append(item)
    _salvar(_CHAVE_ITENS, itens)
    return item


def remover_item(item_id):
    itens = listar_itens()
    restante = []
    for item in itens:
        if item["id"] == item_id:
            if item.get("public_id"):
                _apagar_cloudinary(item["public_id"], item.get("tipo", "imagem"))
        else:
            restante.append(item)
    _salvar(_CHAVE_ITENS, restante)


def alternar_destino(item_id, destino):
    itens = listar_itens()
    for item in itens:
        if item["id"] == item_id:
            destinos_item = item.setdefault("destinos", [])
            if destino in destinos_item:
                destinos_item.remove(destino)
            else:
                destinos_item.append(destino)
            break
    _salvar(_CHAVE_ITENS, itens)
