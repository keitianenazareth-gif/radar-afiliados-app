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
TOLERANCIA_RODADA_MIN = 20
MAX_LOG = 400  # precisa cobrir o dia todo: os tipos de hoje saem daqui

LOJAS = ["Mercado Livre", "Amazon", "Shopee", "Shein", "Temu", "Magalu", "Outra"]

CATEGORIAS_PADRAO = [
    "casa", "cozinha", "jardim", "beleza", "utensilios domesticos", "plantas", "pet", "banheiro",
    "decoracao", "maquiagem", "organizador", "vaso de planta", "infantil", "lavanderia", "iluminacao",
    "skincare", "achadinhos", "cama mesa banho", "papelaria", "moda feminina", "limpeza", "churrasco",
    "acessorios celular", "viagem", "festa", "ferramentas jardim",
]
# Lista anterior: se ainda for a salva na pagina, passa a valer a nova.
_CATEGORIAS_ANTIGAS = [
    "casa", "cozinha", "beleza", "maquiagem", "skincare", "moda feminina",
    "pet", "infantil", "organizacao", "cama mesa banho", "limpeza",
]

PALAVRAS_BLOQUEADAS_PADRAO = [
    "suplemento", "emagrec", "insulina", "diabete", "remedio", "medicamento",
    "capsula", "cha seca", "queima gordura", "termogenico", "detox",
    "sexual", "erotic", "faca tatica", "cigarro", "vape",
    "creatina", "whey", "pre treino", "pre-treino", "parafusadeira", "furadeira",
    "esmerilhadeira", "chenille", "cachimbo", "palmilha", "pasta sanfonada",
    "calcinha", "tanga", "apito",
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

# Primeira linha das mensagens. O robo escolhe pelo produto quando o gancho
# tem estas palavras: "BAIXOU" (desconto de 60%+), "MAIS VENDIDO" (10 mil+
# vendas), "BARATO" (ate R$ 30); senao sorteia. Nao repete no mesmo lote.
GANCHOS_PADRAO = [
    "😱 BAIXOU DEMAIS!",
    "⚡ CORRE QUE ACABA",
    "🏆 O MAIS VENDIDO DA SEMANA",
    "💸 ACHADINHO BARATO",
    "🔥 OFERTA DO DIA",
]

# Frase logo antes do link (sorteada).
CHAMADAS_PADRAO = [
    "Garanta o seu 👇",
    "Corre pra pegar 👇",
    "Aproveita aqui 👇",
    "Clica e confere 👇",
]

CONFIG_PADRAO = {
    "ativo": True,
    "horarios": [9, 12, 19],  # antigo: o robo agora usa as rodadas abaixo
    # Envio automatico: em cada horario, sai a rodada inteira de uma vez.
    "rodadas": [f"{hora:02d}:00" for hora in range(7, 22)],  # de hora em hora
    "ofertas_por_rodada": 20,
    "por_lote": 3,           # botao "Enviar agora": produtos de uma vez
    "fila_por_lote": 1,      # botao "Enviar agora": quantos vem da fila
    "cupons_por_lote": 1,    # cupons em cada rodada
    "amazon_tag": "",
    "palavras_bloqueadas": PALAVRAS_BLOQUEADAS_PADRAO,
    "categorias": CATEGORIAS_PADRAO,
    "ganchos": GANCHOS_PADRAO,
    "chamadas": CHAMADAS_PADRAO,
    "nome_curto_ia": True,   # Gemini encurta o nome dos produtos
    "grupo_id": "",         # grupo escolhido na pagina /whatsapp (termina em @g.us)
    "grupo_nome": "",
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


def pegar_trava(segundos: int = 1800) -> bool:
    """Evita dois lotes ao mesmo tempo (horario automatico + 'Enviar agora')."""
    return _cmd(["SET", CHAVE_TRAVA, "1", "NX", "EX", str(segundos)]) == "OK"


def soltar_trava() -> None:
    try:
        _cmd(["DEL", CHAVE_TRAVA])
    except RuntimeError:
        pass


# ---------------------------------------------------------------- config

def _minutos(hora: str) -> int:
    horas, minutos = str(hora).split(":")
    return int(horas) * 60 + int(minutos)


def proxima_rodada(config: dict, agora: datetime) -> str:
    """Texto da proxima rodada (ex.: "20:00" ou "amanhã, 07:00"); vazio se nao houver."""
    minuto = agora.hour * 60 + agora.minute
    horas = []
    for hora in config.get("rodadas") or []:
        try:
            horas.append((_minutos(hora), hora))
        except (AttributeError, TypeError, ValueError):
            continue
    if not horas:
        return ""
    horas.sort()
    for inicio, hora in horas:
        if inicio > minuto:
            return hora
    return f"amanhã, {horas[0][1]}"


def rodada_atual(config: dict, agora: datetime) -> dict | None:
    """A rodada que deve sair agora, ou None. O robo acorda a cada 10 minutos:
    a tolerancia cobre uma execucao perdida, sem mandar rodada muito atrasada."""
    minuto = agora.hour * 60 + agora.minute
    validas = []
    for hora in config.get("rodadas") or []:
        try:
            validas.append((_minutos(hora), hora))
        except (AttributeError, TypeError, ValueError):
            continue
    for inicio, hora in sorted(validas, reverse=True):
        if inicio <= minuto:
            if minuto - inicio < TOLERANCIA_RODADA_MIN:
                return {"hora": hora, "marca": f"{agora:%Y-%m-%d} rodada {hora}"}
            return None
    return None


def ler_config() -> dict:
    salvo = _ler_json(CHAVE_CONFIG, {})
    config = dict(CONFIG_PADRAO)
    if isinstance(salvo, dict):
        config.update({k: v for k, v in salvo.items() if k in CONFIG_PADRAO})
        if config.get("categorias") == _CATEGORIAS_ANTIGAS:
            config["categorias"] = CATEGORIAS_PADRAO
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
                      imagem: str = "", observacao: str = "",
                      preco_antigo: str = "", vale_ate: float = 0,
                      vale_ate_texto: str = "", prioridade: bool = False) -> dict:
    item = {
        "id": uuid.uuid4().hex[:8],
        "loja": loja or "Outra",
        "link": link.strip(),
        "nome": nome.strip(),
        "preco": preco.strip(),
        "preco_antigo": preco_antigo.strip(),
        "imagem": imagem.strip(),
        "observacao": observacao.strip(),
        "criado_em": time.time(),
        "vale_ate": vale_ate,  # hora (epoch) em que a oferta vence; 0 = sem prazo
        "vale_ate_texto": vale_ate_texto,  # o mesmo prazo, para mostrar na pagina
        "prioridade": prioridade,  # sai antes das demais (ex.: Oferta do dia)
    }
    fila = listar_fila()
    fila.append(item)
    _gravar_json(CHAVE_FILA, fila)
    return item


def item_vencido(item: dict, agora: float | None = None) -> bool:
    """True se a oferta tem prazo e ele ja passou."""
    try:
        prazo = float(item.get("vale_ate") or 0)
    except (TypeError, ValueError):
        return False
    return prazo > 0 and prazo <= (time.time() if agora is None else agora)


def ordenar_para_envio(fila: list, agora: float | None = None) -> list:
    """Tira as vencidas e poe as prioritarias na frente, mantendo a ordem da
    fila dentro de cada grupo."""
    validas = [i for i in fila if not item_vencido(i, agora)]
    return sorted(validas, key=lambda i: not i.get("prioridade"))


def fila_para_envio() -> list:
    return ordenar_para_envio(listar_fila())


def limpar_fila_vencida() -> list:
    """Remove da fila as ofertas vencidas e devolve quais sairam."""
    fila = listar_fila()
    vencidas = [i for i in fila if item_vencido(i)]
    if vencidas:
        _gravar_json(CHAVE_FILA, [i for i in fila if not item_vencido(i)])
    return vencidas


# ---------------------------------------------------------------- produto parecido
# O mesmo produto aparece com nomes um pouco diferentes ("1kg" e "x 1kg"), em
# varias lojas. Por isso comparamos as palavras principais do nome.

_PALAVRAS_IGNORADAS = {
    "para", "com", "sem", "kit", "pcs", "pecas", "peca", "unidade", "unidades",
    "original", "novo", "nova", "promocao", "oferta", "envio", "imediato",
    "pronta", "entrega", "frete", "gratis", "atacado", "cor", "cores", "tam",
    "tamanho", "unissex", "feminino", "feminina", "masculino", "masculina",
    "das", "dos", "uma", "por", "que", "the", "and", "for",
}
SEMELHANCA_MINIMA = 0.6
# Palavras que abrem o nome, mas nao dizem o que o produto e'.
_NAO_DIZEM_O_TIPO = {"mini", "jogo", "conjunto", "par", "pares", "combo", "caixa",
                     "pack", "refil", "super", "mega"}
# Produtos com nomes diferentes que, para quem le o grupo, sao a mesma coisa.
TIPOS_IGUAIS = {
    "tira-manchas": ("percarbonato", "tira manchas", "tira-manchas", "alvejante", "vanish"),
    "racao": ("racao", "whiskas", "friskies", "pedigree"),
}


def _palavras(nome: str) -> list:
    import re

    texto = re.sub(r"[^a-z0-9 ]", " ", normalizar(nome))
    return [w for w in texto.split()
            if len(w) >= 3 and not w.isdigit() and w not in _PALAVRAS_IGNORADAS]


def palavras_do_nome(nome: str) -> frozenset:
    return frozenset(_palavras(nome)[:8])


def nome_parecido(palavras: frozenset, recentes: list) -> bool:
    if len(palavras) < 2:
        return False
    for outras in recentes:
        if not outras:
            continue
        iguais = len(palavras & outras)
        if iguais / len(palavras | outras) >= SEMELHANCA_MINIMA:
            return True
    return False


def tipo_do_produto(nome: str) -> str:
    """O que o produto e', para nao mandar dois iguais no dia: um grupo de
    TIPOS_IGUAIS ou a primeira palavra que importa ("sanduicheira")."""
    alvo = normalizar(nome)
    for tipo, termos in TIPOS_IGUAIS.items():
        if any(termo in alvo for termo in termos):
            return tipo
    for palavra in _palavras(nome):
        if palavra not in _NAO_DIZEM_O_TIPO:
            return palavra.rstrip("s") or palavra
    return ""


def tipos_de_hoje() -> set:
    """Tipos dos produtos que ja sairam hoje no grupo (cupom nao conta)."""
    hoje = agora_brasil().strftime("%d/%m")
    tipos = {tipo_do_produto(str(r.get("titulo") or "").split(": ", 1)[-1])
             for r in ler_log()
             if r.get("ok") and r.get("tipo") in ("fila", "shopee")
             and str(r.get("quando") or "").startswith(hoje)}
    tipos.discard("")
    return tipos


def tipos_na_fila() -> set:
    tipos = {tipo_do_produto(str(i.get("nome") or "")) for i in listar_fila()}
    tipos.discard("")
    return tipos


def tipo_repetido(nome: str) -> str:
    """O tipo do produto, se ja saiu hoje ou ja esta na fila; senao ""."""
    tipo = tipo_do_produto(nome)
    return tipo if tipo and tipo in (tipos_de_hoje() | tipos_na_fila()) else ""


def produto_repetido(nome: str, cupom: bool = False) -> str:
    """'fila' se um produto de nome igual ou parecido ja esta na fila (ou, com
    cupom=True, um cupom com a mesma descricao ja esta cadastrado),
    'enviado' se saiu recentemente (historico de envios), '' se e' novo."""
    # O historico guarda o titulo cortado em 120 letras, entao compara so o
    # comeco do nome.
    def _comeco(texto) -> str:
        return " ".join(normalizar(texto).split())[:80]

    alvo = _comeco(nome)
    if not alvo:
        return ""
    palavras = palavras_do_nome(nome)

    def _igual(outro) -> bool:
        if _comeco(outro) == alvo:
            return True
        return not cupom and nome_parecido(palavras, [palavras_do_nome(outro)])

    if cupom:
        if any(_igual(c.get("descricao")) for c in listar_cupons()):
            return "fila"
    elif any(_igual(i.get("nome")) for i in listar_fila()):
        return "fila"
    for registro in ler_log():
        if not registro.get("ok"):
            continue
        titulo = str(registro.get("titulo") or "")
        if _igual(titulo.split(": ", 1)[-1]):
            return "enviado"
    if not cupom:
        # O historico lembra os nomes por DIAS_SEM_REPETIR dias; o log, so os ultimos envios.
        recentes = [frozenset(k[5:].split()) for k in ids_recentes(ler_historico())
                    if k.startswith("nome:")]
        if nome_parecido(palavras, recentes):
            return "enviado"
    return ""


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
                    validade: str = "", detalhes: str = "", como_ativar: str = "",
                    uma_vez: bool = False, desconto: str = "", desconto_tipo: str = "%",
                    minimo: str = "", limite: str = "") -> dict:
    cupom = {
        "id": uuid.uuid4().hex[:8],
        "loja": loja or "Outra",
        "codigo": codigo.strip(),
        "descricao": descricao.strip(),
        "link": link.strip(),
        "validade": validade.strip(),  # AAAA-MM-DD (vazio = sem validade)
        "detalhes": detalhes.strip(),  # ex.: "Compra mínima R$ 40 · desconto até R$ 20"
        "como_ativar": como_ativar.strip(),  # usado quando nao tem codigo
        "uma_vez": uma_vez,            # cupons do robo saem 1 vez so
        "desconto": str(desconto).strip(),
        "desconto_tipo": "R$" if desconto_tipo == "R$" else "%",
        "minimo": str(minimo).strip(),
        "limite": str(limite).strip(),
        "conferido": False,            # a Keiti testou o codigo no carrinho
        "prioridade": False,           # sai antes dos outros na proxima rodada
        "ultimo_envio": "",            # AAAA-MM-DD
        "criado_em": time.time(),
    }
    cupons = listar_cupons()
    cupons.append(cupom)
    _gravar_json(CHAVE_CUPONS, cupons)
    return cupom


def atualizar_cupom(cupom_id: str, **campos) -> None:
    cupons = listar_cupons()
    for c in cupons:
        if c.get("id") == cupom_id:
            c.update(campos)
    _gravar_json(CHAVE_CUPONS, cupons)


def remover_cupom(cupom_id: str) -> None:
    _gravar_json(CHAVE_CUPONS, [c for c in listar_cupons() if c.get("id") != cupom_id])


def marcar_cupom_enviado(cupom_id: str) -> None:
    hoje = agora_brasil().strftime("%Y-%m-%d")
    cupons = listar_cupons()
    for c in cupons:
        if c.get("id") == cupom_id:
            c["ultimo_envio"] = hoje
            c["prioridade"] = False
    # Aproveita pra tirar os vencidos e os do robo que ja sairam (uma_vez).
    _gravar_json(CHAVE_CUPONS, [
        c for c in cupons
        if cupom_valido(c, hoje) and not (c.get("uma_vez") and c.get("ultimo_envio"))
    ])


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
