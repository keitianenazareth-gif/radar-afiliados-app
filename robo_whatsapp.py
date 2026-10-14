"""
robo_whatsapp.py
----------------
Manda um LOTE de ofertas da Shopee no grupo de promocoes do WhatsApp,
sozinho, sem ninguem clicar em nada:

    1. Busca ofertas da Shopee em 3 listas: mais vendidos, maior
       comissao e maiores descontos.
    2. Escolhe as melhores, misturando as 3 listas, sem repetir produto
       enviado nos ultimos 30 dias (historico no Upstash). A cada
       horario busca em categorias e paginas diferentes, pra variar.
    3. Gera o link de afiliado curto com a marcacao "whatsapp" (subId),
       pra saber no relatorio da Shopee o que vendeu pelo grupo.
    4. Envia cada oferta no grupo (foto + texto + link) pela Evolution
       API, com uma pausa entre uma mensagem e outra.

O WhatsApp e' conectado por um NUMERO EXCLUSIVO (chip separado), nunca o
numero pessoal: conexao nao oficial pode levar a banimento do numero.

Uso (no notebook, pra testar):
    python robo_whatsapp.py --teste          -> mostra as mensagens, NAO envia
    python robo_whatsapp.py --listar-grupos  -> mostra os grupos e seus IDs
    python robo_whatsapp.py                  -> envia o lote de verdade

No GitHub Actions roda sozinho nos horarios de .github/workflows/robo-whatsapp.yml

Variaveis de ambiente / Secrets do GitHub:
    SHOPEE_APP_ID, SHOPEE_SECRET                      (ja existem)
    UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN  (ja existem)
    WHATSAPP_API_URL     endereco da Evolution API (ex.: https://meu-whatsapp.onrender.com)
    WHATSAPP_API_KEY     chave (apikey) da Evolution API
    WHATSAPP_INSTANCIA   nome da instancia conectada ao chip (ex.: clubedoquero)
    WHATSAPP_GRUPO_ID    ID do grupo (termina em @g.us) - ver --listar-grupos
Opcionais:
    WHATSAPP_POR_LOTE    quantas ofertas por horario (padrao 3)
    WHATSAPP_PAUSA_MIN / WHATSAPP_PAUSA_MAX  segundos entre mensagens (padrao 40 / 90)
"""

from __future__ import annotations

import json
import os
import random
import sys
import time

import requests

from shopee import _consultar_api, gerar_link_curto, numero

CHAVE_HISTORICO = "robo_whatsapp:historico"
DIAS_SEM_REPETIR = 30  # um produto so pode voltar depois de 30 dias

# Categorias que o robo alterna a cada horario (busca por palavra-chave).
# "" = vitrine geral da Shopee. Pode editar a vontade.
CATEGORIAS = [
    "", "casa", "cozinha", "beleza", "maquiagem", "skincare", "moda feminina",
    "roupa fitness", "academia", "pet", "infantil", "brinquedo", "eletronicos",
    "celular acessorios", "organizacao", "decoracao", "cama mesa banho",
    "limpeza", "ferramentas", "papelaria", "moda masculina", "calcados",
    "bolsas", "relogio", "saude bem estar", "viagem", "carro acessorios",
]
CATEGORIAS_POR_LOTE = 3
PAGINAS = [1, 1, 2, 2, 3]  # sorteia a pagina (a 1 tem mais chance)

# sortType da API de afiliados: 2 = mais vendidos, 4 = menor preco,
# 5 = maior comissao. Nao existe ordenacao por desconto: a lista de
# descontos junta tudo que foi buscado e ordena pelo desconto.
DESCONTO_MINIMO = 20  # %

# Filtro de qualidade minima pra nao mandar produto ruim no grupo.
VENDAS_MINIMAS = 100
NOTA_MINIMA = 4.5  # estrelas (so vale quando a Shopee informa)

CAMPOS_EXTRAS = "shopId productLink ratingStar"


def _env(nome: str, padrao: str = "") -> str:
    return os.environ.get(nome, padrao).strip()


# ---------------------------------------------------------------- historico

def _upstash_cmd(cmd: list):
    url = _env("UPSTASH_REDIS_REST_URL").rstrip("/")
    token = _env("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        raise RuntimeError("Upstash nao configurado (UPSTASH_REDIS_REST_URL/TOKEN).")
    resp = requests.post(
        url, headers={"Authorization": f"Bearer {token}"}, json=cmd, timeout=15
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Upstash erro HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json().get("result")


def _carregar_historico() -> dict:
    """{itemId: data do envio (timestamp)}. Aceita o formato antigo (lista)."""
    bruto = _upstash_cmd(["GET", CHAVE_HISTORICO])
    if not bruto:
        return {}
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError:
        return {}
    if isinstance(dados, list):
        agora = time.time()
        return {str(i): agora for i in dados}
    return {str(k): float(v) for k, v in dados.items()}


def _salvar_historico(hist: dict) -> None:
    limite = time.time() - DIAS_SEM_REPETIR * 86400
    recentes = {k: v for k, v in hist.items() if v >= limite}
    _upstash_cmd(["SET", CHAVE_HISTORICO, json.dumps(recentes)])


# ---------------------------------------------------------------- ofertas

def _buscar_lista(sort_type: int, termo: str = "", pagina: int = 1) -> list:
    try:
        return _consultar_api(termo, sort_type, False, CAMPOS_EXTRAS, pagina)
    except RuntimeError as erro:
        # Se a Shopee nao aceitar algum campo extra, busca sem eles.
        if any(c in str(erro) for c in CAMPOS_EXTRAS.split()):
            return _consultar_api(termo, sort_type, False, "", pagina)
        raise


def _categorias_da_vez() -> list:
    """Cada horario pega um grupo diferente de categorias, em rodizio."""
    rodada = int(time.time() // 3600)  # muda a cada hora
    inicio = (rodada * CATEGORIAS_POR_LOTE) % len(CATEGORIAS)
    return [CATEGORIAS[(inicio + i) % len(CATEGORIAS)] for i in range(CATEGORIAS_POR_LOTE)]


def _juntar(listas: list) -> list:
    vistos, saida = set(), []
    for lista in listas:
        for p in lista:
            k = str(p.get("itemId"))
            if k not in vistos:
                vistos.add(k)
                saida.append(p)
    return saida


def _passa_no_filtro(p: dict) -> bool:
    if not p.get("imageUrl") or not (p.get("offerLink") or p.get("productLink")):
        return False
    if numero(p.get("sales")) < VENDAS_MINIMAS:
        return False
    nota = numero(p.get("ratingStar"))
    if nota and nota < NOTA_MINIMA:
        return False
    return True


def escolher_ofertas(quantidade: int, historico) -> list:
    """Busca em categorias e paginas variadas e mistura as 3 listas
    (uma de cada vez) ate completar o lote."""
    categorias = _categorias_da_vez()
    print("Categorias desta rodada: " + ", ".join(c or "vitrine geral" for c in categorias))
    buscas = {2: [], 5: [], 4: []}
    for termo in categorias:
        for sort_type in buscas:
            try:
                buscas[sort_type].append(
                    _buscar_lista(sort_type, termo, random.choice(PAGINAS)))
            except RuntimeError as erro:
                print(f"  Aviso: busca '{termo or 'geral'}' falhou ({erro}).")
    vendidos = [p for p in _juntar(buscas[2]) if _passa_no_filtro(p)]
    comissao = [p for p in _juntar(buscas[5]) if _passa_no_filtro(p)]
    baratos = [p for p in _juntar(buscas[4]) if _passa_no_filtro(p)]

    todos = {}
    for p in vendidos + comissao + baratos:
        todos.setdefault(str(p.get("itemId")), p)
    descontos = [p for p in todos.values()
                 if numero(p.get("priceDiscountRate")) >= DESCONTO_MINIMO]

    vendidos.sort(key=lambda p: numero(p.get("sales")), reverse=True)
    comissao.sort(key=lambda p: numero(p.get("commission")), reverse=True)
    descontos.sort(key=lambda p: numero(p.get("priceDiscountRate")), reverse=True)
    filas = [
        ("mais vendidos", vendidos),
        ("maior comissao", comissao),
        ("maiores descontos", descontos),
    ]

    limite = time.time() - DIAS_SEM_REPETIR * 86400
    ids_usados = {str(k) for k, v in dict(historico).items() if v >= limite}
    escolhidos = []
    while len(escolhidos) < quantidade and any(f for _, f in filas):
        for nome, fila in filas:
            while fila:
                p = fila.pop(0)
                item_id = str(p.get("itemId"))
                if item_id in ids_usados:
                    continue
                ids_usados.add(item_id)
                p["_lista"] = nome
                escolhidos.append(p)
                break
            if len(escolhidos) >= quantidade:
                break
    return escolhidos


def link_afiliado(p: dict) -> str:
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


def _moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _vendas_texto(vendas: float) -> str:
    v = int(vendas)
    if v >= 1000:
        return f"+{v // 1000} mil vendidos"
    return f"+{v} vendidos"


def montar_mensagem(p: dict, link: str) -> str:
    nome = str(p.get("productName") or "Oferta").strip()
    if len(nome) > 90:
        nome = nome[:87].rstrip() + "..."
    preco = numero(p.get("priceMin"))
    desconto = numero(p.get("priceDiscountRate"))

    linhas = [f"🔥 *{nome}*", ""]
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

    linhas += ["", f"👉 {link}", "", "_Preço e estoque podem mudar a qualquer momento._"]
    return "\n".join(linhas)


# ---------------------------------------------------------------- WhatsApp

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


def enviar_oferta(grupo_id: str, imagem_url: str, texto: str) -> None:
    instancia = _env("WHATSAPP_INSTANCIA")
    try:
        _evolution("POST", f"/message/sendMedia/{instancia}", {
            "number": grupo_id,
            "mediatype": "image",
            "mimetype": "image/jpeg",
            "media": imagem_url,
            "fileName": "oferta.jpg",
            "caption": texto,
        })
    except RuntimeError as erro:
        # Se a foto falhar, manda pelo menos o texto com o link.
        print(f"  Aviso: envio com foto falhou ({erro}); mandando so o texto.")
        _evolution("POST", f"/message/sendText/{instancia}", {
            "number": grupo_id,
            "text": texto,
        })


def listar_grupos() -> None:
    instancia = _env("WHATSAPP_INSTANCIA")
    grupos = _evolution("GET", f"/group/fetchAllGroups/{instancia}?getParticipants=false")
    if not grupos:
        print("Nenhum grupo encontrado. O chip ja esta em algum grupo?")
        return
    print("Grupos deste numero (copie o ID do grupo de promocoes para o Secret WHATSAPP_GRUPO_ID):")
    for g in grupos:
        print(f"  {g.get('subject')}  ->  {g.get('id')}")


# ---------------------------------------------------------------- principal

def rodar(teste: bool = False) -> None:
    if not teste:
        faltando = [n for n in ("WHATSAPP_API_URL", "WHATSAPP_API_KEY",
                                "WHATSAPP_INSTANCIA", "WHATSAPP_GRUPO_ID") if not _env(n)]
        if faltando:
            print("WhatsApp ainda nao configurado (falta: " + ", ".join(faltando) +
                  "). Nada foi enviado.")
            return

    quantidade = int(_env("WHATSAPP_POR_LOTE", "3") or 3)
    pausa_min = int(_env("WHATSAPP_PAUSA_MIN", "40") or 40)
    pausa_max = max(pausa_min, int(_env("WHATSAPP_PAUSA_MAX", "90") or 90))

    try:
        historico = _carregar_historico()
    except (RuntimeError, requests.RequestException) as erro:
        print(f"Aviso: sem historico ({erro}). Pode repetir produto.")
        historico = {}

    ofertas = escolher_ofertas(quantidade, historico)
    if not ofertas:
        print("Nenhuma oferta nova agora. Nada foi enviado.")
        if os.environ.get("GITHUB_ACTIONS"):
            print("::warning title=Sem ofertas::Nenhuma oferta passou nos filtros.")
        return

    grupo = _env("WHATSAPP_GRUPO_ID")
    enviados = 0
    for n, p in enumerate(ofertas, start=1):
        link = link_afiliado(p)
        texto = montar_mensagem(p, link)
        print(f"\n--- Oferta {n}/{len(ofertas)} ({p['_lista']}) ---\n{texto}")
        if teste:
            if os.environ.get("GITHUB_ACTIONS"):
                # Aparece como aviso na pagina da execucao (aba Actions).
                msg = texto.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
                print(f"::notice title=Oferta {n} ({p['_lista']})::{msg}")
            continue
        if n > 1:
            pausa = random.randint(pausa_min, pausa_max)
            print(f"  (esperando {pausa}s antes de enviar)")
            time.sleep(pausa)
        try:
            enviar_oferta(grupo, str(p.get("imageUrl")), texto)
        except (RuntimeError, requests.RequestException) as erro:
            print(f"  ERRO ao enviar: {erro}")
            continue
        enviados += 1
        historico[str(p.get("itemId"))] = time.time()
        print("  Enviada!")

    if teste:
        print("\nModo teste: nada foi enviado.")
        return

    if enviados:
        try:
            _salvar_historico(historico)
        except (RuntimeError, requests.RequestException) as erro:
            print(f"Aviso: nao salvei o historico ({erro}).")

    print(f"\nConcluido: {enviados} de {len(ofertas)} ofertas enviadas.")
    if enviados == 0:
        sys.exit(1)


if __name__ == "__main__":
    args = sys.argv[1:]
    try:
        if "--listar-grupos" in args:
            listar_grupos()
        else:
            rodar(teste="--teste" in args)
    except (RuntimeError, requests.RequestException) as erro:
        print(f"ERRO: {erro}")
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::error title=Robo WhatsApp::{str(erro)[:500]}")
        sys.exit(1)
