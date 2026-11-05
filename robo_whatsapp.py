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
      (nem o mesmo produto vendido por outra loja: compara codigo, foto e
      nome) e pulando produtos com palavras proibidas.

Os links da Shopee saem como link curto de afiliada com a marcacao
(subId) "whatsapp". As fotos saem com a marca d'agua @clube.doquero
(marca_dagua.py; MARCA_DAGUA=0 desliga). Envio pela Evolution API, com pausa entre mensagens.
Os ajustes (ligado/pausado, horarios, quantidades, palavras proibidas,
tag da Amazon) ficam no Upstash e sao editados pela pagina /whatsapp.

O WhatsApp e' conectado por um NUMERO EXCLUSIVO (chip separado), nunca o
numero pessoal: conexao nao oficial pode levar a banimento do numero.

Uso (no notebook, pra testar):
    python robo_whatsapp.py --teste          -> mostra o lote, NAO envia
    python robo_whatsapp.py --listar-grupos  -> mostra os grupos e seus IDs
    python robo_whatsapp.py --agora          -> envia um lote ja (ignora horario)
    python robo_whatsapp.py                  -> envia se for hora de uma rodada

No Railway roda a cada 10 minutos e, nos horarios de rodada da pagina /whatsapp,
manda a rodada inteira de uma vez: a fila misturada com a Shopee. Se faltar
oferta boa, a rodada sai menor e fica um aviso no registro de envios.

Variaveis de ambiente / Secrets do GitHub / Environment do Render:
    SHOPEE_APP_ID, SHOPEE_SECRET, UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN
    WHATSAPP_API_URL     endereco da Evolution API
    WHATSAPP_API_KEY     chave (apikey) da Evolution API
    WHATSAPP_INSTANCIA   nome da instancia conectada ao chip
    WHATSAPP_GRUPO_ID    (opcional) ID do grupo - o normal e' escolher o grupo
                         na pagina /whatsapp, que salva no Upstash
Opcionais: WHATSAPP_PAUSA_MIN / WHATSAPP_PAUSA_MAX (segundos, padrao 40 / 90), so para o "Enviar agora"
"""

from __future__ import annotations

import os
import random
import re
import sys
import time

import requests

import whatsapp_dados as dados
from shopee import _consultar_api, gerar_link_curto, numero

VARIAVEIS_WHATSAPP = ("WHATSAPP_API_URL", "WHATSAPP_API_KEY", "WHATSAPP_INSTANCIA")

# Filtro de qualidade minima pra nao mandar produto ruim no grupo.
VENDAS_MINIMAS = 100
NOTA_MINIMA = 4.5      # estrelas (so vale quando a Shopee informa)
DESCONTO_MINIMO = 30   # % (o mesmo do Mercado Livre e da Amazon)
PRECO_MAXIMO = 100     # R$ (o grupo compra mais coisa barata)
PRECO_MINIMO = 5       # R$ (abaixo disso costuma ser so a variacao mais barata do anuncio)
# Se o GitHub atrasar, o lote ainda sai ate esse tanto de horas depois do horario.
CATEGORIAS_POR_LOTE = 5
PAUSA_RODADA = (10, 20)  # segundos entre as mensagens de uma rodada
PAGINAS = [1, 1, 2, 2, 3]  # sorteia a pagina (a 1 tem mais chance)
CAMPOS_EXTRAS = "shopId productLink ratingStar"


def _env(nome: str, padrao: str = "") -> str:
    return os.environ.get(nome, padrao).strip()


def _aviso_actions(nivel: str, titulo: str, texto: str) -> None:
    """No GitHub Actions, aparece como aviso na pagina da execucao."""
    if os.environ.get("GITHUB_ACTIONS"):
        msg = texto.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::{nivel} title={titulo}::{msg}")


def conexao_configurada() -> list:
    """Variaveis de conexao com a Evolution API que ainda faltam."""
    return [n for n in VARIAVEIS_WHATSAPP if not _env(n)]


def grupo_destino() -> str:
    """Grupo escolhido na pagina /whatsapp; o Secret WHATSAPP_GRUPO_ID so
    vale se nenhum grupo tiver sido escolhido la."""
    try:
        escolhido = (dados.ler_config().get("grupo_id") or "").strip()
    except RuntimeError:
        escolhido = ""
    return escolhido or _env("WHATSAPP_GRUPO_ID")


def whatsapp_configurado() -> list:
    """Lista o que ainda falta para o robo conseguir enviar."""
    faltando = conexao_configurada()
    if not grupo_destino():
        faltando.append("grupo (escolha na pagina /whatsapp)")
    return faltando


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
    if numero(p.get("priceDiscountRate")) < DESCONTO_MINIMO:
        return False
    if not PRECO_MINIMO <= numero(p.get("priceMin")) <= PRECO_MAXIMO:
        return False
    nota = numero(p.get("ratingStar"))
    if nota and nota < NOTA_MINIMA:
        return False
    if dados.tem_palavra_bloqueada(p.get("productName", ""), palavras_bloqueadas):
        return False
    return True


# ---------------------------------------------------------------- produto parecido
# O mesmo produto aparece em varias lojas da Shopee, cada uma com um codigo
# diferente. Pra nao mandar "a mesma garrafinha" duas vezes, comparamos
# tambem a FOTO e o NOME (palavras principais).

palavras_do_nome = dados.palavras_do_nome
nome_parecido = dados.nome_parecido


def chave_foto(url: str) -> str:
    """Identificador da foto (o fim do endereco, sem tamanho/extensao)."""
    fim = str(url or "").rstrip("/").split("/")[-1]
    fim = fim.split("?")[0].split("_tn")[0].split(".")[0]
    return f"img:{fim}" if len(fim) >= 8 else ""


def chave_nome(nome: str) -> str:
    palavras = palavras_do_nome(nome)
    return "nome:" + " ".join(sorted(palavras)) if palavras else ""


def nomes_recentes(usados: set) -> list:
    return [frozenset(k[5:].split()) for k in usados if k.startswith("nome:")]


def _proxima_lista(nomes: list) -> int:
    """Qual lista usar agora: a seguinte a da ultima oferta da Shopee enviada.
    Como sai 1 oferta por vez, sem isso a primeira lista ganharia sempre."""
    for registro in dados.ler_log():
        achou = re.match(r"Shopee \((.+?)\):", str(registro.get("titulo") or ""))
        if achou and registro.get("ok") and achou.group(1) in nomes:
            return (nomes.index(achou.group(1)) + 1) % len(nomes)
    return 0


def escolher_ofertas_shopee(quantidade: int, ja_usados: set, config: dict) -> list:
    """Busca em categorias e paginas variadas e mistura as 3 listas
    (uma de cada vez, em rodizio) ate completar a quantidade."""
    if quantidade <= 0:
        return []
    bloqueadas = config.get("palavras_bloqueadas") or []
    categorias = _categorias_da_vez(config.get("categorias") or [""])
    print("Categorias desta rodada: " + ", ".join(c or "vitrine geral" for c in categorias))

    buscas = {2: [], 5: [], 4: []}
    for termo in categorias:
        for sort_type in buscas:
            # A Shopee as vezes devolve "System Error" numa busca: tenta mais uma vez.
            for tentativa in (1, 2):
                try:
                    buscas[sort_type].append(
                        _buscar_lista(sort_type, termo, random.choice(PAGINAS)))
                    break
                except RuntimeError as erro:
                    if tentativa == 2:
                        print(f"  Aviso: busca '{termo or 'geral'}' falhou ({erro}).")
                    else:
                        time.sleep(2)

    vendidos = [p for p in _juntar(buscas[2]) if _passa_no_filtro(p, bloqueadas)]
    comissao = [p for p in _juntar(buscas[5]) if _passa_no_filtro(p, bloqueadas)]
    baratos = [p for p in _juntar(buscas[4]) if _passa_no_filtro(p, bloqueadas)]
    descontos = _juntar([vendidos, comissao, baratos])

    vendidos.sort(key=lambda p: numero(p.get("sales")), reverse=True)
    comissao.sort(key=lambda p: numero(p.get("commission")), reverse=True)
    descontos.sort(key=lambda p: numero(p.get("priceDiscountRate")), reverse=True)
    filas = [
        ("mais vendidos", vendidos),
        ("maior comissão", comissao),
        ("maiores descontos", descontos),
    ]
    inicio = _proxima_lista([nome for nome, _ in filas])
    filas = filas[inicio:] + filas[:inicio]

    escolhidos, usados = [], set(ja_usados)
    nomes_usados = nomes_recentes(usados)
    # Nada do mesmo tipo de algo que ja saiu hoje ou que esta na fila.
    tipos_usados = dados.tipos_de_hoje() | dados.tipos_na_fila()
    pulados = 0
    while len(escolhidos) < quantidade and any(f for _, f in filas):
        for nome, fila in filas:
            while fila:
                p = fila.pop(0)
                item_id = str(p.get("itemId"))
                if item_id in usados:
                    continue
                foto = chave_foto(p.get("imageUrl"))
                palavras = palavras_do_nome(p.get("productName", ""))
                tipo = dados.tipo_do_produto(p.get("productName", ""))
                if ((foto and foto in usados) or nome_parecido(palavras, nomes_usados)
                        or tipo in tipos_usados):
                    usados.add(item_id)
                    pulados += 1
                    continue
                usados.add(item_id)
                if foto:
                    usados.add(foto)
                nomes_usados.append(palavras)
                tipos_usados.add(tipo)
                p["_lista"] = nome
                escolhidos.append(p)
                break
            if len(escolhidos) >= quantidade:
                break
    if pulados:
        print(f"  {pulados} produto(s) parecido(s) com outros ja enviados foram pulados.")
    return escolhidos


def link_afiliado_shopee(p: dict) -> str:
    """Link curto com subIds 'whatsapp' e a hora do envio (ex.: 'h20'), para
    o relatorio da Shopee mostrar qual horario vende mais; se falhar, usa o
    link normal."""
    origem = p.get("productLink")
    if not origem and p.get("shopId") and p.get("itemId"):
        origem = f"https://shopee.com.br/product/{p['shopId']}/{p['itemId']}"
    if origem:
        try:
            hora = f"h{dados.agora_brasil().hour:02d}"
            return gerar_link_curto(origem, ["whatsapp", hora])
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


def nome_curto_local(nome: str, max_palavras: int = 9) -> str:
    """Plano B quando o Gemini nao encurta: fica com o 1o pedaco do nome
    (antes de ' - ', ' | ', ', ' ou '(') se ele tiver 3+ palavras, e corta
    em ate ~9 palavras, sem deixar preposicao solta no fim."""
    nome = " ".join(str(nome or "Oferta").split())
    primeiro = re.split(r"\s[-|–]\s|,\s|\s\(", nome)[0]
    if len(primeiro.split()) >= 3:
        nome = primeiro
    palavras = nome.split()[:max_palavras]
    while len(palavras) > 3 and palavras[-1].lower() in {
            "de", "da", "do", "das", "dos", "para", "pra", "com", "e", "em", "a", "o"}:
        palavras.pop()
    return " ".join(palavras)


class Estilo:
    """Ganchos (1a linha) e chamadas (antes do link) de um lote. Escolhe o
    gancho pelo produto quando da e nao repete gancho no mesmo lote."""

    def __init__(self, config: dict | None = None):
        config = config or {}
        self.ganchos = list(config.get("ganchos") or dados.GANCHOS_PADRAO)
        self.chamadas = list(config.get("chamadas") or dados.CHAMADAS_PADRAO)
        self.usados: set = set()

    def gancho(self, desconto: float = 0, vendas: float = 0, preco: float = 0) -> str:
        livres = [g for g in self.ganchos if g not in self.usados] or self.ganchos
        regras = [("BAIXOU", desconto >= 60), ("MAIS VENDIDO", vendas >= 10000),
                  ("BARATO", 0 < preco <= 30)]
        escolhido = ""
        for palavra, vale in regras:
            if vale:
                escolhido = next((g for g in livres if palavra in g.upper()), "")
                if escolhido:
                    break
        if not escolhido:
            # Sem regra: sorteia entre os que nao dependem de regra (se
            # acabaram no lote, repete um deles - nunca usa "BAIXOU DEMAIS"
            # num produto que nao tem desconto pra isso).
            def _comum(g):
                return not any(p in g.upper() for p, _ in regras)

            comuns = ([g for g in livres if _comum(g)]
                      or [g for g in self.ganchos if _comum(g)] or livres)
            escolhido = random.choice(comuns)
        self.usados.add(escolhido)
        return escolhido

    def chamada(self) -> str:
        return random.choice(self.chamadas)


def _topo(estilo: Estilo, nome: str, **sinais) -> list:
    return [f"*{estilo.gancho(**sinais)}*", "", f"*{_encurtar(nome_curto_local(nome, 12))}*"]


def _na_loja(loja: str) -> str:
    return f"no {loja}" if loja == "Mercado Livre" else f"na {loja}"


def _prova_social(nota: float, vendas: float) -> str:
    extras = []
    if nota:
        extras.append(f"⭐ {nota:.1f}".replace(".", ","))
    if vendas:
        extras.append(f"🛒 {_vendas_texto(vendas)}")
    return " · ".join(extras)


def _final(estilo: Estilo, link: str) -> list:
    return ["", estilo.chamada(), f"{link}", "", RODAPE]


def mensagem_shopee(p: dict, link: str, estilo: Estilo | None = None,
                    nome: str = "") -> str:
    estilo = estilo or Estilo()
    preco = numero(p.get("priceMin"))
    desconto = numero(p.get("priceDiscountRate"))
    vendas = numero(p.get("sales"))

    linhas = _topo(estilo, nome or p.get("productName"),
                   desconto=desconto, vendas=vendas, preco=preco)
    # A Shopee informa o MAIOR desconto entre as variacoes e o MENOR preco,
    # que podem ser de variacoes diferentes - por isso nao calculamos "De R$".
    if preco > 0 and desconto >= 5:
        linhas.append(f"A partir de *{_moeda(preco)}* · até {desconto:g}% OFF")
    elif preco > 0:
        linhas.append(f"A partir de *{_moeda(preco)}*")
    social = _prova_social(numero(p.get("ratingStar")), vendas)
    if social:
        linhas.append(social)
    linhas.append("🏬 Shopee")
    return "\n".join(linhas + _final(estilo, link))


def _valor_do_texto(texto: str) -> float:
    """'R$ 1.234,56' -> 1234.56 (0 se nao der pra ler)."""
    limpo = re.sub(r"[^0-9,.]", "", str(texto or ""))
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return 0.0


def _vendas_da_observacao(texto: str) -> float:
    """'... 🛒 +750 mil vendidos' -> 750000 (usado para escolher o gancho)."""
    achado = re.search(r"\+(\d+)\s*(mil)?\s*vendidos", str(texto or ""))
    if not achado:
        return 0
    return int(achado.group(1)) * (1000 if achado.group(2) else 1)


def mensagem_fila(item: dict, estilo: Estilo | None = None, nome: str = "") -> str:
    estilo = estilo or Estilo()
    preco = str(item.get("preco") or "").strip()
    valor = _valor_do_texto(preco)
    antigo = _valor_do_texto(item.get("preco_antigo"))
    desconto = round((1 - valor / antigo) * 100) if valor > 0 and antigo > valor else 0
    observacao = str(item.get("observacao") or "").replace(" | ", " · ")

    linhas = _topo(estilo, nome or item.get("nome"), desconto=desconto,
                   vendas=_vendas_da_observacao(observacao), preco=valor)
    if desconto:
        linhas.append(f"~{_moeda(antigo)}~ por *{_moeda(valor)}* ({desconto}% OFF)")
    elif preco:
        if not preco.upper().startswith("R$"):
            preco = "R$ " + preco
        linhas.append(f"Por *{preco}*")
    if observacao:
        linhas.append(observacao)
    linhas.append(f"🏬 {item.get('loja') or 'Oferta'}")
    return "\n".join(linhas + _final(estilo, item.get("link")))


def mensagem_cupom(cupom: dict, estilo: Estilo | None = None) -> str:
    loja = str(cupom.get("loja") or "").strip()
    linhas = ["🎟️ *CUPOM LIBERADO!*", ""]
    descricao = str(cupom.get("descricao") or "").strip()
    if descricao:
        linhas.append(f"*{descricao}* {_na_loja(loja)}" if loja else f"*{descricao}*")
    elif loja:
        linhas.append(f"*{loja}*")
    if cupom.get("detalhes"):
        linhas.append(str(cupom["detalhes"]))
    if cupom.get("codigo"):
        linhas.append(f"Código: *{cupom['codigo']}*")
    validade = cupom.get("validade")
    if validade:
        try:
            _ano, mes, dia = validade.split("-")
            linhas.append(f"⏰ Só até {dia}/{mes}")
        except ValueError:
            pass
    if cupom.get("como_ativar"):
        # Cupom sem codigo (ex.: Mercado Livre, que se ativa no app).
        linhas += ["", str(cupom["como_ativar"])]
    elif cupom.get("link"):
        linhas += ["", "Ativar cupom 👇"]
    if cupom.get("link"):
        linhas.append(str(cupom["link"]))
    linhas += ["", "_Cupons podem esgotar antes do prazo._"]
    return "\n".join(linhas)


# ================================================================ montar o lote

def _misturar(fila: list, shopee: list) -> list:
    """Espalha as duas listas por igual, sem mudar a ordem dentro de cada uma."""
    com_posicao = [((i + 0.5) / len(fila), m) for i, m in enumerate(fila)]
    com_posicao += [((i + 0.5) / len(shopee), m) for i, m in enumerate(shopee)]
    return [m for _, m in sorted(com_posicao, key=lambda par: par[0])]


def montar_lote(config: dict, gerar_links: bool = True, quantidade: int = 0,
                com_cupom: bool = True) -> list:
    """Devolve a lista de mensagens do proximo lote, cada uma como
    {tipo, titulo, texto, imagem, link, ref}. Nao envia nada. Com "quantidade"
    (rodada), usa a fila toda que couber e completa com a Shopee; sem ela
    (botao "Enviar agora"), segue os ajustes por_lote e fila_por_lote."""
    lote = []
    hoje = dados.agora_brasil().strftime("%Y-%m-%d")
    estilo = Estilo(config)

    # 1) Cupom: o mais antigo que ainda nao saiu hoje.
    qtd_cupons = int(config.get("cupons_por_lote") or 0) if com_cupom else 0
    if qtd_cupons > 0:
        cupons = [c for c in dados.listar_cupons()
                  if dados.cupom_valido(c, hoje) and c.get("ultimo_envio") != hoje]
        cupons.sort(key=lambda c: not c.get("prioridade"))  # "Usar na rodada" sai primeiro
        for c in cupons[:qtd_cupons]:
            lote.append({
                "tipo": "cupom",
                "titulo": f"Cupom {c.get('loja')}: {c.get('codigo') or c.get('descricao')}",
                "texto": mensagem_cupom(c, estilo), "imagem": "", "link": c.get("link", ""),
                "ref": c.get("id"), "codigo": c.get("codigo", ""),
            })

    por_lote = quantidade or max(0, int(config.get("por_lote") or 0))

    # 2) Fila de outras lojas: sem as vencidas e com as prioritarias na frente.
    na_fila = dados.fila_para_envio()
    # Do mesmo tipo de algo que ja saiu hoje fica de fora (e vence, se tiver prazo).
    tipos_hoje = dados.tipos_de_hoje()
    na_fila = [i for i in na_fila
               if dados.tipo_do_produto(str(i.get("nome") or "")) not in tipos_hoje]
    if quantidade:
        # Dois do mesmo tipo tambem nao saem juntos na mesma rodada.
        da_fila, tipos_rodada = [], set()
        for item in na_fila:
            tipo = dados.tipo_do_produto(str(item.get("nome") or ""))
            if tipo and tipo in tipos_rodada:
                continue
            tipos_rodada.add(tipo)
            da_fila.append(item)
        da_fila = da_fila[:quantidade]
    else:
        da_fila = na_fila[: min(por_lote, int(config.get("fila_por_lote") or 0))]

    # 3) Completa com Shopee.
    faltam = por_lote - len(da_fila)
    da_shopee = []
    if faltam > 0:
        historico = dados.ler_historico()
        da_shopee = escolher_ofertas_shopee(faltam, dados.ids_recentes(historico), config)

    # Nome curto pelo Gemini: uma chamada so para o lote todo (se falhar,
    # ficam os nomes originais). O titulo do historico usa o nome original,
    # que e' o que o robo compara para nao repetir produto.
    nomes = [str(i.get("nome") or "") for i in da_fila]
    nomes += [str(p.get("productName") or "") for p in da_shopee]
    curtos = nomes
    if nomes and config.get("nome_curto_ia", True):
        from campanhas_ia import encurtar_nomes

        curtos = encurtar_nomes(nomes)

    msgs_fila, msgs_shopee = [], []
    for item, curto in zip(da_fila, curtos):
        msgs_fila.append({
            "tipo": "fila", "titulo": f"{item.get('loja')}: {item.get('nome')}",
            "texto": mensagem_fila(item, estilo, curto), "imagem": item.get("imagem", ""),
            "link": item.get("link", ""), "ref": item.get("id"),
            "nome": str(item.get("nome") or ""),
        })
    for p, curto in zip(da_shopee, curtos[len(da_fila):]):
        link = link_afiliado_shopee(p) if gerar_links else str(p.get("offerLink") or "")
        msgs_shopee.append({
            "tipo": "shopee", "lista": p["_lista"],
            "titulo": f"Shopee ({p['_lista']}): {p.get('productName')}",
            "texto": mensagem_shopee(p, link, estilo, curto),
            "imagem": str(p.get("imageUrl") or ""),
            "link": link, "ref": str(p.get("itemId")),
            "nome": str(p.get("productName") or ""),
        })
    return lote + (_misturar(msgs_fila, msgs_shopee) if quantidade else msgs_fila + msgs_shopee)


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
    # linkPreview: o WhatsApp mostra a foto/titulo do link (usado na Amazon,
    # que vai sem foto anexada).
    _evolution("POST", f"/message/sendText/{_env('WHATSAPP_INSTANCIA')}",
               {"number": grupo_id, "text": texto, "linkPreview": True})


def _foto_com_marca(url: str) -> str:
    """Baixa a foto e devolve em base64 com a marca d'agua @clube.doquero.
    Se algo falhar (ou a marca estiver desligada), devolve o link original,
    pra nunca deixar de mandar a oferta por causa da marca."""
    try:
        import marca_dagua
        if not marca_dagua.ligada():
            return url
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return marca_dagua.jpeg_base64(resp.content)
    except Exception as erro:  # noqa: BLE001 - a marca e' opcional
        print(f"  Aviso: nao consegui colocar a marca d'agua ({erro}); mandando a foto original.")
        return url


def enviar_mensagem(grupo_id: str, msg: dict) -> None:
    instancia = _env("WHATSAPP_INSTANCIA")
    enviado = False
    if msg.get("imagem"):
        try:
            _evolution("POST", f"/message/sendMedia/{instancia}", {
                "number": grupo_id,
                "mediatype": "image",
                "mimetype": "image/jpeg",
                "media": _foto_com_marca(msg["imagem"]),
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
    return [{"nome": g.get("subject"), "id": g.get("id")} for g in (grupos or [])
            if isinstance(g, dict) and str(g.get("id", "")).endswith("@g.us")]


def enviar_teste(texto: str = "") -> None:
    """Manda uma mensagem simples no grupo escolhido, so pra conferir."""
    grupo = grupo_destino()
    if not grupo:
        raise RuntimeError("Nenhum grupo escolhido ainda.")
    _enviar_texto(grupo, texto or "✅ Teste do robô do Radar Afiliados: conexão funcionando!")


def _depois_de_enviar(msg: dict) -> None:
    """Tira da fila / marca cupom / guarda no historico da Shopee."""
    if msg["tipo"] == "fila":
        dados.remover_da_fila(msg["ref"])
    elif msg["tipo"] == "cupom":
        dados.marcar_cupom_enviado(msg["ref"])
    if msg["tipo"] in ("shopee", "fila"):
        # Guarda o codigo, a foto e o nome, pra nao repetir o mesmo
        # produto nem quando ele vier de outra loja.
        historico = dados.ler_historico()
        agora = time.time()
        chaves = [chave_foto(msg.get("imagem")), chave_nome(msg.get("nome", ""))]
        if msg["tipo"] == "shopee":
            chaves.append(str(msg["ref"]))
        for chave in chaves:
            if chave:
                historico[chave] = agora
        dados.salvar_historico(historico)


def enviar_lote(origem: str = "automatico", quantidade: int = 0) -> int:
    """Monta e envia um lote. Devolve quantas mensagens foram enviadas."""
    faltando = whatsapp_configurado()
    if faltando:
        raise RuntimeError("WhatsApp ainda nao configurado (falta: " + ", ".join(faltando) + ").")
    if not dados.pegar_trava():
        raise RuntimeError("Ja tem um lote sendo enviado agora. Tente de novo em alguns minutos.")

    try:
        config = dados.ler_config()
        # Oferta vencida nao vai para o grupo: quem abre o link tem que achar
        # o preco da mensagem.
        for vencida in dados.limpar_fila_vencida():
            print(f"Oferta vencida, nao enviada: {vencida.get('nome')}")
            dados.registrar("aviso", f"Oferta vencida, não enviada: {vencida.get('nome')}",
                            vencida.get("link", ""), ok=False, origem=origem)
        lote = montar_lote(config, quantidade=quantidade)
        if not lote:
            print("Nada para enviar agora (sem ofertas novas, fila e cupons vazios).")
            dados.registrar("aviso", "Lote vazio: nenhuma oferta nova encontrada",
                            ok=False, origem=origem)
            return 0

        ofertas = sum(1 for m in lote if m["tipo"] != "cupom")
        if quantidade and ofertas < quantidade:
            aviso = f"Rodada menor: {ofertas} de {quantidade} ofertas (faltou oferta nova que passe nas regras)"
            print(aviso)
            dados.registrar("aviso", aviso, ok=False, origem=origem)

        if quantidade:
            pausa_min, pausa_max = PAUSA_RODADA
        else:
            pausa_min = int(_env("WHATSAPP_PAUSA_MIN", "40") or 40)
            pausa_max = max(pausa_min, int(_env("WHATSAPP_PAUSA_MAX", "90") or 90))
        grupo = grupo_destino()
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
    """Chamado a cada 10 minutos pelo Railway: se for hora de uma rodada,
    manda ela inteira, uma vez so."""
    config = dados.ler_config()
    agora = dados.agora_brasil()
    if not config.get("ativo"):
        print("Robo pausado na pagina /whatsapp. Nada enviado.")
        return
    rodada = dados.rodada_atual(config, agora)
    if not rodada:
        print(f"Agora sao {agora:%H:%M} (Brasilia): fora das rodadas {config.get('rodadas')}. Nada a fazer.")
        return
    if dados.ler_ultimo_lote() == rodada["marca"]:
        print(f"A rodada das {rodada['hora']} ja foi enviada.")
        return
    faltando = whatsapp_configurado()
    if faltando:
        print("WhatsApp ainda nao configurado (falta: " + ", ".join(faltando) + "). Nada enviado.")
        _aviso_actions("warning", "WhatsApp nao configurado", "Falta: " + ", ".join(faltando))
        return
    dados.marcar_ultimo_lote(rodada["marca"])
    enviados = enviar_lote("automatico", int(config.get("ofertas_por_rodada") or 0))
    if enviados == 0:
        _aviso_actions("warning", "Lote vazio", "Nenhuma mensagem foi enviada neste horario.")


def rodar_teste() -> None:
    config = dados.ler_config()
    print(f"Robo {'LIGADO' if config.get('ativo') else 'PAUSADO'} | rodadas {config.get('rodadas')}")
    lote = montar_lote(config, quantidade=int(config.get("ofertas_por_rodada") or 0))
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
            print("Grupos deste numero (ou escolha o grupo na pagina /whatsapp):")
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
            try:
                import robo_instagram

                robo_instagram.rodar()
            except Exception as erro:  # noqa: BLE001 - o WhatsApp sai mesmo se o Instagram falhar
                print(f"Instagram: {type(erro).__name__}")
            rodar_agendado()
    except (RuntimeError, requests.RequestException) as erro:
        print(f"ERRO: {erro}")
        _aviso_actions("error", "Robo WhatsApp", str(erro)[:500])
        sys.exit(1)
