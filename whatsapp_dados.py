"""
whatsapp_dados.py
-----------------
Tudo que o robo do WhatsApp guarda, num lugar so (Upstash), para que a
pagina /whatsapp do Radar web (no celular) e o robo (GitHub Actions)
enxerguem as mesmas coisas:

    whatsapp:config     ajustes (ligado/pausado, horarios, tamanho do lote...)
    whatsapp:fila       ofertas de outras lojas coladas pela Keiti
    whatsapp:cupons     cupons cadastrados
    whatsapp:historico  produtos da Shopee ja enviados {itemId: quando}
    whatsapp:log        ultimos envios (pra aparecer no historico da pagina)
    whatsapp:ultimo_lote  "AAAA-MM-DD HH" do ultimo lote automatico
"""

from __future__ import annotations

import json
import os
import time
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

CHAVE_CONFIG = "whatsapp:config"
CHAVE_FILA = "whatsapp:fila"
CHAVE_CUPONS = "whatsapp:cupons"
CHAVE_HISTORICO = "whatsapp:historico"
CHAVE_LOG = "whatsapp:log"
CHAVE_ULTIMO_LOTE = "whatsapp:ultimo_lote"
CHAVE_TRAVA = "whatsapp:trava"
# Historico da 1a versao do robo (lista simples) - lido uma vez e migrado.
CHAVE_HISTORICO_ANTIGA = "robo_whatsapp:historico"

DIAS_SEM_REPETIR = 30
MAX_LOG = 60

LOJAS = ["Mercado Livre", "Amazon", "Shopee", "Shein", "Temu", "Magalu", "Outra"]

CATEGORIAS_PADRAO = [
    "", "casa", "cozinha", "beleza", "maquiagem", "skincare", "moda feminina",
    "roupa fitness", "academia", "pet", "infantil", "brinquedo", "eletronicos",
    "celular acessorios", "organizacao", "decoracao", "cama mesa banho",
    "limpeza", "ferramentas", "papelaria", "moda masculina", "calcados",
    "bolsas", "relogio", "viagem", "carro acessorios",
]

PALAVRAS_BLOQUEADAS_PADRAO = [
    "suplemento", "emagrec", "insulina", "diabete", "remedio", "medicamento",
    "capsula", "cha seca", "queima gordura", "termogenico", "detox",
    "sexual", "erotic", "faca tatica", "cigarro", "vape",
]


def tem_palavra_bloqueada(texto: str, palavras: list) -> str:
    """Devolve a palavra proibida encontrada (comeco de palavra, sem
    acento/maiuscula), ou "" se nao tiver nenhuma."""
    import re

    alvo = normalizar(texto)
    for palavra in palavras or []:
        p = normalizar(palavra).strip()
        if p and re.search(r"(?<![a-z0-9])" + re.escape(p), alvo):
            return palavra
    return ""

CONFIG_PADRAO = {
    "ativo": True,
    "horarios": [9, 12, 19],
    "por_lote": 3,           # produtos por lote (fila + Shopee)
    "fila_por_lote": 1,      # quantos desses vem da fila de outras lojas
    "cupons_por_lote": 1,
    "amazon_tag": "",
    "palavras_bloqueadas": PALAVRAS_BLOQUEADAS_PADRAO,
    "categorias": CATEGORIAS_PADRAO,
}

try:
    from zoneinfo import ZoneInfo

    FUSO = ZoneInfo("America/Sao_Paulo")
except Exception:  # noqa: BLE001 - sem base de fusos: Brasilia = UTC-3
    FUSO = timezone(timedelta(hours=-3))


def agora_brasil() -> datetime:
    return datetime.now(FUSO)


def normalizar(texto: str) -> str:
    """minusculas e sem acento - pra comparar palavras proibidas."""
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).lower()


# ---------------------------------------------------------------- Upstash

def _cmd(cmd: list):
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
    if not url or not token:
        raise RuntimeError("Upstash nao configurado (UPSTASH_REDIS_REST_URL/TOKEN).")
    try:
        resp = requests.post(
            url, headers={"Authorization": f"Bearer {token}"}, json=cmd, timeout=15
        )
    except requests.RequestException as erro:
        raise RuntimeError(f"Upstash inacessivel: {erro}") from erro
    if resp.status_code != 200:
        raise RuntimeError(f"Upstash erro HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json().get("result")


def _ler_json(chave: str, padrao):
    bruto = _cmd(["GET", chave])
    if not bruto:
        return padrao
    try:
        return json.loads(bruto)
    except json.JSONDecodeError:
        return padrao


def _gravar_json(chave: str, valor) -> None:
    _cmd(["SET", chave, json.dumps(valor, ensure_ascii=False)])


def pegar_trava(segundos: int = 900) -> bool:
    """Evita dois lotes ao mesmo tempo (horario automatico + 'Enviar agora')."""
    return _cmd(["SET", CHAVE_TRAVA, "1", "NX", "EX", str(segundos)]) == "OK"


def soltar_trava() -> None:
    try:
        _cmd(["DEL", CHAVE_TRAVA])
    except RuntimeError:
        pass


# ---------------------------------------------------------------- config

def ler_config() -> dict:
    salvo = _ler_json(CHAVE_CONFIG, {})
    config = dict(CONFIG_PADRAO)
    if isinstance(salvo, dict):
        config.update({k: v for k, v in salvo.items() if k in CONFIG_PADRAO})
    return config


def salvar_config(novos: dict) -> dict:
    config = ler_config()
    config.update({k: v for k, v in novos.items() if k in CONFIG_PADRAO})
    _gravar_json(CHAVE_CONFIG, config)
    return config


# ---------------------------------------------------------------- fila

def aplicar_tag_amazon(link: str, tag: str) -> str:
    """Coloca a tag de afiliada num link normal da Amazon. Links curtos
    (amzn.to) ficam como estao - esses ja saem com a tag do SiteStripe."""
    tag = (tag or "").strip()
    try:
        partes = urlsplit(link)
    except ValueError:
        return link
    if not tag or "amazon." not in partes.netloc.lower():
        return link
    parametros = [(k, v) for k, v in parse_qsl(partes.query) if k.lower() != "tag"]
    parametros.append(("tag", tag))
    return urlunsplit(partes._replace(query=urlencode(parametros)))


def listar_fila() -> list:
    fila = _ler_json(CHAVE_FILA, [])
    return fila if isinstance(fila, list) else []


def adicionar_na_fila(loja: str, link: str, nome: str, preco: str = "",
                      imagem: str = "", observacao: str = "") -> dict:
    item = {
        "id": uuid.uuid4().hex[:8],
        "loja": loja or "Outra",
        "link": link.strip(),
        "nome": nome.strip(),
        "preco": preco.strip(),
        "imagem": imagem.strip(),
        "observacao": observacao.strip(),
        "criado_em": time.time(),
    }
    fila = listar_fila()
    fila.append(item)
    _gravar_json(CHAVE_FILA, fila)
    return item


def remover_da_fila(item_id: str) -> None:
    _gravar_json(CHAVE_FILA, [i for i in listar_fila() if i.get("id") != item_id])


def mover_na_fila(item_id: str, direcao: int) -> None:
    fila = listar_fila()
    pos = next((n for n, i in enumerate(fila) if i.get("id") == item_id), None)
    if pos is None:
        return
    novo = max(0, min(len(fila) - 1, pos + direcao))
    fila.insert(novo, fila.pop(pos))
    _gravar_json(CHAVE_FILA, fila)


# ---------------------------------------------------------------- cupons

def listar_cupons() -> list:
    cupons = _ler_json(CHAVE_CUPONS, [])
    return cupons if isinstance(cupons, list) else []


def cupom_valido(cupom: dict, hoje: str | None = None) -> bool:
    hoje = hoje or agora_brasil().strftime("%Y-%m-%d")
    validade = cupom.get("validade") or ""
    return not validade or validade >= hoje


def adicionar_cupom(loja: str, codigo: str, descricao: str, link: str,
                    validade: str = "") -> dict:
    cupom = {
        "id": uuid.uuid4().hex[:8],
        "loja": loja or "Outra",
        "codigo": codigo.strip(),
        "descricao": descricao.strip(),
        "link": link.strip(),
        "validade": validade.strip(),  # AAAA-MM-DD (vazio = sem validade)
        "ultimo_envio": "",            # AAAA-MM-DD
        "criado_em": time.time(),
    }
    cupons = listar_cupons()
    cupons.append(cupom)
    _gravar_json(CHAVE_CUPONS, cupons)
    return cupom


def remover_cupom(cupom_id: str) -> None:
    _gravar_json(CHAVE_CUPONS, [c for c in listar_cupons() if c.get("id") != cupom_id])


def marcar_cupom_enviado(cupom_id: str) -> None:
    hoje = agora_brasil().strftime("%Y-%m-%d")
    cupons = listar_cupons()
    for c in cupons:
        if c.get("id") == cupom_id:
            c["ultimo_envio"] = hoje
    # Aproveita pra tirar os vencidos.
    _gravar_json(CHAVE_CUPONS, [c for c in cupons if cupom_valido(c, hoje)])


# ---------------------------------------------------------------- historico Shopee

def ler_historico() -> dict:
    dados = _ler_json(CHAVE_HISTORICO, None)
    if dados is None:
        antigo = _ler_json(CHAVE_HISTORICO_ANTIGA, {})
        agora = time.time()
        if isinstance(antigo, list):
            return {str(i): agora for i in antigo}
        return {str(k): float(v) for k, v in (antigo or {}).items()}
    return {str(k): float(v) for k, v in dados.items()}


def ids_recentes(historico: dict) -> set:
    limite = time.time() - DIAS_SEM_REPETIR * 86400
    return {k for k, v in historico.items() if v >= limite}


def salvar_historico(historico: dict) -> None:
    limite = time.time() - DIAS_SEM_REPETIR * 86400
    _gravar_json(CHAVE_HISTORICO, {k: v for k, v in historico.items() if v >= limite})


def pular_produto_shopee(item_id: str) -> None:
    """'Pular' na previa: trata como se ja tivesse sido enviado."""
    historico = ler_historico()
    historico[str(item_id)] = time.time()
    salvar_historico(historico)


# ---------------------------------------------------------------- log

def registrar(tipo: str, titulo: str, link: str = "", ok: bool = True,
              erro: str = "", origem: str = "") -> None:
    try:
        log = _ler_json(CHAVE_LOG, [])
        if not isinstance(log, list):
            log = []
        log.append({
            "quando": agora_brasil().strftime("%d/%m %H:%M"),
            "tipo": tipo,
            "titulo": titulo[:120],
            "link": link,
            "ok": ok,
            "erro": erro[:300],
            "origem": origem,
        })
        _gravar_json(CHAVE_LOG, log[-MAX_LOG:])
    except RuntimeError as falha:
        print(f"Aviso: nao registrei no historico ({falha}).")


def ler_log() -> list:
    log = _ler_json(CHAVE_LOG, [])
    return list(reversed(log)) if isinstance(log, list) else []


def ler_ultimo_lote() -> str:
    return str(_cmd(["GET", CHAVE_ULTIMO_LOTE]) or "")


def marcar_ultimo_lote(marca: str) -> None:
    _cmd(["SET", CHAVE_ULTIMO_LOTE, marca])
