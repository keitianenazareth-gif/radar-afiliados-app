"""
robo_whatsapp.py
----------------
Manda LOTES de ofertas no grupo de promocoes do WhatsApp, sozinho.

Cada lote tem:
    - ate 1 cupom cadastrado na pagina /whatsapp (cada cupom sai no
      maximo 1x por dia, ate vencer);
    - ofertas da FILA (links de Mercado Livre, Amazon, Shein... colados
      pela Keiti na pagina /whatsapp), na ordem em que foram colados;
    - o resto completado com ofertas da Shopee escolhidas sozinhas:
      mais vendidos, maior comissao e maiores descontos, em categorias e
      paginas que mudam a cada horario, sem repetir produto por 30 dias
      e pulando produtos com palavras proibidas.

Os links da Shopee saem como link curto de afiliada com a marcacao
(subId) "whatsapp". Envio pela Evolution API, com pausa entre mensagens.
Os ajustes (ligado/pausado, horarios, quantidades, palavras proibidas,
tag da Amazon) ficam no Upstash e sao editados pela pagina /whatsapp.

O WhatsApp e' conectado por um NUMERO EXCLUSIVO (chip separado), nunca o
numero pessoal: conexao nao oficial pode levar a banimento do numero.

Uso (no notebook, pra testar):
    python robo_whatsapp.py --teste          -> mostra o lote, NAO envia
    python robo_whatsapp.py --listar-grupos  -> mostra os grupos e seus IDs
    python robo_whatsapp.py --agora          -> envia um lote ja (ignora horario)
    python robo_whatsapp.py                  -> envia se for um dos horarios

No GitHub Actions roda de hora em hora (.github/workflows/robo-whatsapp.yml)
e so envia nos horarios escolhidos na pagina.

Variaveis de ambiente / Secrets do GitHub / Environment do Render:
    SHOPEE_APP_ID, SHOPEE_SECRET, UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN
    WHATSAPP_API_URL     endereco da Evolution API
    WHATSAPP_API_KEY     chave (apikey) da Evolution API
    WHATSAPP_INSTANCIA   nome da instancia conectada ao chip
    WHATSAPP_GRUPO_ID    ID do grupo (termina em @g.us) - ver --listar-grupos
Opcionais: WHATSAPP_PAUSA_MIN / WHATSAPP_PAUSA_MAX (segundos, padrao 40 / 90)
"""

from __future__ import annotations

import os
import random
import sys
import time

import requests

import whatsapp_dados as dados
from shopee import _consultar_api, gerar_link_curto, numero

VARIAVEIS_WHATSAPP = ("WHATSAPP_API_URL", "WHATSAPP_API_KEY",
                      "WHATSAPP_INSTANCIA", "WHATSAPP_GRUPO_ID")

# Filtro de qualidade minima pra nao mandar produto ruim no grupo.
VENDAS_MINIMAS = 100
NOTA_MINIMA = 4.5      # estrelas (so vale quando a Shopee informa)
DESCONTO_MINIMO = 20   # % pra entrar na lista de "maiores descontos"
CATEGORIAS_POR_LOTE = 3
PAGINAS = [1, 1, 2, 2, 3]  # sorteia a pagina (a 1 tem mais chance)
CAMPOS_EXTRAS = "shopId productLink ratingStar"


def _env(nome: str, padrao: str = "") -> str:
    return os.environ.get(nome, padrao).strip()


def _aviso_actions(nivel: str, titulo: str, texto: str) -> None:
    """No GitHub Actions, aparece como aviso na pagina da execucao."""
    if os.environ.get("GITHUB_ACTIONS"):
        msg = texto.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::{nivel} title={titulo}::{msg}")


def whatsapp_configurado() -> list:
    """Lista as variaveis do WhatsApp que ainda faltam."""
    return [n for n in VARIAVEIS_WHATSAPP if not _env(n)]


# ================================================================ Shopee

def _buscar_lista(sort_type: int, termo: str = "", pagina: int = 1) -> list:
    """sortType da API de afiliados: 2 = mais vendidos, 4 = menor preco,
    5 = maior comissao (nao existe ordenacao por desconto)."""
    try:
        return _consultar_api(termo, sort_type, False, CAMPOS_EXTRAS, pagina)
    except RuntimeError as erro:
        # Se a Shopee nao aceitar algum campo extra, busca sem eles.
        if any(c in str(erro) for c in CAMPOS_EXTRAS.split()):
            return _consultar_api(termo, sort_type, False, "", pagina)
        raise


def _categorias_da_vez(categorias: list) -> list:
    """Cada horario pega um grupo diferente de categorias, em rodizio."""
    categorias = categorias or [""]
    rodada = int(time.time() // 3600)  # muda a cada hora
    inicio = (rodada * CATEGORIAS_POR_LOTE) % len(categorias)
    qtd = min(CATEGORIAS_POR_LOTE, len(categorias))
    return [categorias[(inicio + i) % len(categorias)] for i in range(qtd)]


def _juntar(listas: list) -> list:
    vistos, saida = set(), []
    for lista in listas:
        for p in lista:
            k = str(p.get("itemId"))
            if k not in vistos:
                vistos.add(k)
                saida.append(p)
    return saida


def _passa_no_filtro(p: dict, palavras_bloqueadas: list) -> bool:
    if not p.get("imageUrl") or not (p.get("offerLink") or p.get("productLink")):
        return False
    if numero(p.get("sales")) < VENDAS_MINIMAS:
        return False
    nota = numero(p.get("ratingStar"))
    if nota and nota < NOTA_MINIMA:
        return False
    if dados.tem_palavra_bloqueada(p.get("productName", ""), palavras_bloqueadas):
        return False
    return True


def escolher_ofertas_shopee(quantidade: int, ja_usados: set, config: dict) -> list:
    """Busca em categorias e paginas variadas e mistura as 3 listas
    (uma de cada vez) ate completar a quantidade."""
    if quantidade <= 0:
        return []
    bloqueadas = config.get("palavras_bloqueadas") or []
    categorias = _categorias_da_vez(config.get("categorias") or [""])
    print("Categorias desta rodada: " + ", ".join(c or "vitrine geral" for c in categorias))

    buscas = {2: [], 5: [], 4: []}
    for termo in categorias:
        for sort_type in buscas:
            try:
                buscas[sort_type].append(
                    _buscar_lista(sort_type, termo, random.choice(PAGINAS)))
            except RuntimeError as erro:
                print(f"  Aviso: busca '{termo or 'geral'}' falhou ({erro}).")

    vendidos = [p for p in _juntar(buscas[2]) if _passa_no_filtro(p, bloqueadas)]
    comissao = [p for p in _juntar(buscas[5]) if _passa_no_filtro(p, bloqueadas)]
    baratos = [p for p in _juntar(buscas[4]) if _passa_no_filtro(p, bloqueadas)]
    descontos = [p for p in _juntar([vendidos, comissao, baratos])
                 if numero(p.get("priceDiscountRate")) >= DESCONTO_MINIMO]

    vendidos.sort(key=lambda p: numero(p.get("sales")), reverse=True)
    comissao.sort(key=lambda p: numero(p.get("commission")), reverse=True)
    descontos.sort(key=lambda p: numero(p.get("priceDiscountRate")), reverse=True)
    filas = [
        ("mais vendidos", vendidos),
        ("maior comissão", comissao),
        ("maiores descontos", descontos),
    ]

    escolhidos, usados = [], set(ja_usados)
    while len(escolhidos) < quantidade and any(f for _, f in filas):
        for nome, fila in filas:
            while fila:
                p = fila.pop(0)
                item_id = str(p.get("itemId"))
                if item_id in usados:
                    continue
                usados.add(item_id)
                p["_lista"] = nome
                escolhidos.append(p)
                break
            if len(escolhidos) >= quantidade:
                break
    return escolhidos


def link_afiliado_shopee(p: dict) -> str:
    """Link curto com subId 'whatsapp'; se falhar, usa o link normal."""
    origem = p.get("productLink")
    if not origem and p.get("shopId") and p.get("itemId"):
        origem = f"https://shopee.com.br/product/{p['shopId']}/{p['itemId']}"
    if origem:
        try:
            return gerar_link_curto(origem, ["whatsapp"])
        except (RuntimeError, requests.RequestException) as erro:
            print(f"  Aviso: link curto falhou ({erro}); usando o link normal.")
    return str(p.get("offerLink") or origem or "")


# ================================================================ mensagens

RODAPE = "_Preço e estoque podem mudar a qualquer momento._"


def _moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _vendas_texto(vendas: float) -> str:
    v = int(vendas)
    if v >= 1000:
        return f"+{v // 1000} mil vendidos"
    return f"+{v} vendidos"


def _encurtar(nome: str, limite: int = 90) -> str:
    nome = str(nome or "Oferta").strip()
    return nome if len(nome) <= limite else nome[:limite - 3].rstrip() + "..."


def mensagem_shopee(p: dict, link: str) -> str:
    preco = numero(p.get("priceMin"))
    desconto = numero(p.get("priceDiscountRate"))

    linhas = [f"🔥 *{_encurtar(p.get('productName'))}*", ""]
    # A Shopee informa o MAIOR desconto entre as variacoes e o MENOR preco,
    # que podem ser de variacoes diferentes - por isso nao calculamos "De R$".
    if preco > 0 and desconto >= 5:
        linhas.append(f"A partir de *{_moeda(preco)}* · até {desconto:g}% OFF")
    elif preco > 0:
        linhas.append(f"A partir de *{_moeda(preco)}*")

    extras = []
    nota = numero(p.get("ratingStar"))
    if nota:
        extras.append(f"⭐ {nota:.1f}")
    if numero(p.get("sales")):
        extras.append(f"🛒 {_vendas_texto(numero(p.get('sales')))}")
    if extras:
        linhas.append(" | ".join(extras))
    linhas.append("🏬 Shopee")

    linhas += ["", f"👉 {link}", "", RODAPE]
    return "\n".join(linhas)


def mensagem_fila(item: dict) -> str:
    linhas = [f"🔥 *{_encurtar(item.get('nome'))}*", ""]
    preco = str(item.get("preco") or "").strip()
    if preco:
        if not preco.upper().startswith("R$"):
            preco = "R$ " + preco
        linhas.append(f"Por *{preco}*")
    if item.get("observacao"):
        linhas.append(str(item["observacao"]))
    linhas.append(f"🏬 {item.get('loja') or 'Oferta'}")
    linhas += ["", f"👉 {item.get('link')}", "", RODAPE]
    return "\n".join(linhas)


def mensagem_cupom(cupom: dict) -> str:
    linhas = [f"🎟️ *CUPOM {str(cupom.get('loja') or '').upper()}*", ""]
    if cupom.get("descricao"):
        linhas.append(str(cupom["descricao"]))
    if cupom.get("codigo"):
        linhas.append(f"Código: *{cupom['codigo']}*")
    validade = cupom.get("validade")
    if validade:
        try:
            _ano, mes, dia = validade.split("-")
            linhas.append(f"⏰ Válido até {dia}/{mes}")
        except ValueError:
            pass
    if cupom.get("link"):
        linhas += ["", f"👉 {cupom['link']}"]
    linhas += ["", "_Cupons podem esgotar antes do prazo._"]
    return "\n".join(linhas)


# ================================================================ montar o lote

def montar_lote(config: dict, gerar_links: bool = True) -> list:
    """Devolve a lista de mensagens do proximo lote, cada uma como
    {tipo, titulo, texto, imagem, link, ref}. Nao envia nada."""
    lote = []
    hoje = dados.agora_brasil().strftime("%Y-%m-%d")

    # 1) Cupom: o mais antigo que ainda nao saiu hoje.
    qtd_cupons = int(config.get("cupons_por_lote") or 0)
    if qtd_cupons > 0:
        cupons = [c for c in dados.listar_cupons()
                  if dados.cupom_valido(c, hoje) and c.get("ultimo_envio") != hoje]
        for c in cupons[:qtd_cupons]:
            lote.append({
                "tipo": "cupom",
                "titulo": f"Cupom {c.get('loja')}: {c.get('codigo') or c.get('descricao')}",
                "texto": mensagem_cupom(c), "imagem": "", "link": c.get("link", ""),
                "ref": c.get("id"), "codigo": c.get("codigo", ""),
            })

    por_lote = max(0, int(config.get("por_lote") or 0))

    # 2) Fila de outras lojas, na ordem em que foram coladas.
    da_fila = dados.listar_fila()[: min(por_lote, int(config.get("fila_por_lote") or 0))]
    for item in da_fila:
        lote.append({
            "tipo": "fila", "titulo": f"{item.get('loja')}: {item.get('nome')}",
            "texto": mensagem_fila(item), "imagem": item.get("imagem", ""),
            "link": item.get("link", ""), "ref": item.get("id"),
        })

    # 3) Completa com Shopee.
    faltam = por_lote - len(da_fila)
    if faltam > 0:
        historico = dados.ler_historico()
        for p in escolher_ofertas_shopee(faltam, dados.ids_recentes(historico), config):
            link = link_afiliado_shopee(p) if gerar_links else str(p.get("offerLink") or "")
            lote.append({
                "tipo": "shopee", "lista": p["_lista"],
                "titulo": f"Shopee ({p['_lista']}): {p.get('productName')}",
                "texto": mensagem_shopee(p, link), "imagem": str(p.get("imageUrl") or ""),
                "link": link, "ref": str(p.get("itemId")),
            })
    return lote


# ================================================================ WhatsApp

def _evolution(metodo: str, caminho: str, corpo: dict | None = None):
    base = _env("WHATSAPP_API_URL").rstrip("/")
    chave = _env("WHATSAPP_API_KEY")
    if not base or not chave:
        raise RuntimeError("WhatsApp nao configurado (WHATSAPP_API_URL / WHATSAPP_API_KEY).")
    resp = requests.request(
        metodo, f"{base}{caminho}", headers={"apikey": chave}, json=corpo, timeout=60
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Evolution API erro HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json() if resp.text else {}


def _enviar_texto(grupo_id: str, texto: str) -> None:
    _evolution("POST", f"/message/sendText/{_env('WHATSAPP_INSTANCIA')}",
               {"number": grupo_id, "text": texto})


def enviar_mensagem(grupo_id: str, msg: dict) -> None:
    instancia = _env("WHATSAPP_INSTANCIA")
    enviado = False
    if msg.get("imagem"):
        try:
            _evolution("POST", f"/message/sendMedia/{instancia}", {
                "number": grupo_id,
                "mediatype": "image",
                "mimetype": "image/jpeg",
                "media": msg["imagem"],
                "fileName": "oferta.jpg",
                "caption": msg["texto"],
            })
            enviado = True
        except RuntimeError as erro:
            # Se a foto falhar, manda pelo menos o texto com o link.
            print(f"  Aviso: envio com foto falhou ({erro}); mandando so o texto.")
    if not enviado:
        _enviar_texto(grupo_id, msg["texto"])
    # Cupom: manda o codigo sozinho tambem, pra copiar com um toque.
    if msg.get("tipo") == "cupom" and msg.get("codigo"):
        time.sleep(3)
        _enviar_texto(grupo_id, str(msg["codigo"]))


def listar_grupos() -> list:
    instancia = _env("WHATSAPP_INSTANCIA")
    grupos = _evolution("GET", f"/group/fetchAllGroups/{instancia}?getParticipants=false")
    return [{"nome": g.get("subject"), "id": g.get("id")} for g in (grupos or [])]


def _depois_de_enviar(msg: dict) -> None:
    """Tira da fila / marca cupom / guarda no historico da Shopee."""
    if msg["tipo"] == "fila":
        dados.remover_da_fila(msg["ref"])
    elif msg["tipo"] == "cupom":
        dados.marcar_cupom_enviado(msg["ref"])
    elif msg["tipo"] == "shopee":
        historico = dados.ler_historico()
        historico[msg["ref"]] = time.time()
        dados.salvar_historico(historico)


def enviar_lote(origem: str = "automatico") -> int:
    """Monta e envia um lote. Devolve quantas mensagens foram enviadas."""
    faltando = whatsapp_configurado()
    if faltando:
        raise RuntimeError("WhatsApp ainda nao configurado (falta: " + ", ".join(faltando) + ").")
    if not dados.pegar_trava():
        raise RuntimeError("Ja tem um lote sendo enviado agora. Tente de novo em alguns minutos.")

    try:
        config = dados.ler_config()
        lote = montar_lote(config)
        if not lote:
            print("Nada para enviar agora (sem ofertas novas, fila e cupons vazios).")
            dados.registrar("aviso", "Lote vazio: nenhuma oferta nova encontrada",
                            ok=False, origem=origem)
            return 0

        pausa_min = int(_env("WHATSAPP_PAUSA_MIN", "40") or 40)
        pausa_max = max(pausa_min, int(_env("WHATSAPP_PAUSA_MAX", "90") or 90))
        grupo = _env("WHATSAPP_GRUPO_ID")
        enviados = 0
        for n, msg in enumerate(lote, start=1):
            print(f"\n--- {n}/{len(lote)} {msg['titulo']} ---\n{msg['texto']}")
            if n > 1:
                pausa = random.randint(pausa_min, pausa_max)
                print(f"  (esperando {pausa}s antes de enviar)")
                time.sleep(pausa)
            try:
                enviar_mensagem(grupo, msg)
            except (RuntimeError, requests.RequestException) as erro:
                print(f"  ERRO ao enviar: {erro}")
                dados.registrar(msg["tipo"], msg["titulo"], msg["link"], ok=False,
                                erro=str(erro), origem=origem)
                continue
            enviados += 1
            print("  Enviada!")
            dados.registrar(msg["tipo"], msg["titulo"], msg["link"], origem=origem)
            try:
                _depois_de_enviar(msg)
            except RuntimeError as erro:
                print(f"  Aviso: enviada, mas nao atualizei fila/historico ({erro}).")
        print(f"\nConcluido: {enviados} de {len(lote)} mensagens enviadas.")
        return enviados
    finally:
        dados.soltar_trava()


# ================================================================ principal

def rodar_agendado() -> None:
    """Chamado de hora em hora pelo GitHub Actions: so envia se o robo
    estiver ligado, se for um dos horarios e se esse horario ainda nao
    tiver saido hoje."""
    config = dados.ler_config()
    agora = dados.agora_brasil()
    if not config.get("ativo"):
        print("Robo pausado na pagina /whatsapp. Nada enviado.")
        return
    horarios = [int(h) for h in config.get("horarios") or []]
    if agora.hour not in horarios:
        print(f"Agora sao {agora:%H:%M} (Brasilia). Horarios de envio: {horarios}. Nada a fazer.")
        return
    marca = agora.strftime("%Y-%m-%d %H")
    if dados.ler_ultimo_lote() == marca:
        print("O lote deste horario ja foi enviado.")
        return
    faltando = whatsapp_configurado()
    if faltando:
        print("WhatsApp ainda nao configurado (falta: " + ", ".join(faltando) + "). Nada enviado.")
        _aviso_actions("warning", "WhatsApp nao configurado", "Falta: " + ", ".join(faltando))
        return
    dados.marcar_ultimo_lote(marca)
    enviados = enviar_lote("automatico")
    if enviados == 0:
        _aviso_actions("warning", "Lote vazio", "Nenhuma mensagem foi enviada neste horario.")


def rodar_teste() -> None:
    config = dados.ler_config()
    print(f"Robo {'LIGADO' if config.get('ativo') else 'PAUSADO'} | horarios {config.get('horarios')}")
    lote = montar_lote(config)
    if not lote:
        print("Lote vazio.")
        _aviso_actions("warning", "Lote vazio", "Nenhuma oferta, item da fila ou cupom disponivel.")
    for n, msg in enumerate(lote, start=1):
        print(f"\n--- {n}/{len(lote)} {msg['titulo']} ---\n{msg['texto']}")
        foto = f"\n[foto] {msg['imagem']}" if msg.get("imagem") else ""
        _aviso_actions("notice", f"{n} - {msg['tipo']}", msg["texto"] + foto)
    print("\nModo teste: nada foi enviado.")


if __name__ == "__main__":
    args = sys.argv[1:]
    try:
        if "--listar-grupos" in args:
            grupos = listar_grupos()
            print("Grupos deste numero (copie o ID para o Secret WHATSAPP_GRUPO_ID):")
            for g in grupos:
                print(f"  {g['nome']}  ->  {g['id']}")
                _aviso_actions("notice", g["nome"] or "grupo", g["id"] or "")
            if not grupos:
                print("Nenhum grupo encontrado. O chip ja esta em algum grupo?")
        elif "--teste" in args:
            rodar_teste()
        elif "--agora" in args:
            enviar_lote("manual (Actions)")
        else:
            rodar_agendado()
    except (RuntimeError, requests.RequestException) as erro:
        print(f"ERRO: {erro}")
        _aviso_actions("error", "Robo WhatsApp", str(erro)[:500])
        sys.exit(1)
