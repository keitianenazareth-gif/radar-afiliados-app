"""
stories_dia.py
--------------
Kit de stories do dia para o Instagram: escolhe ofertas da Shopee com foto de
ambiente (foto de fundo branco nao serve para este estilo), monta a arte no
estilo aprovado pela Keiti (foto na tela, nome com seta, preco em amarelo e
moldura "link aqui") e guarda no Cloudinary. Ela posta pelo celular e cola o
link na figurinha: a API da Meta nao permite figurinha de link.

O kit fica no Upstash (chave instagram:stories_dia). Nada e' publicado aqui.
"""

import io
import math
import os
import random
import tempfile
from datetime import datetime

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import robo_whatsapp as rw
import whatsapp_dados as dados
from shopee import numero
from web import galeria

CHAVE = "instagram:stories_dia"
QUANTIDADE = 4
TERMOS = [
    "organizador", "cozinha", "decoracao casa", "banheiro", "quarto", "cama mesa banho",
    "utensilios domesticos", "iluminacao", "lavanderia", "achadinhos casa", "jardim", "beleza",
]
DESCONTO_MINIMO = 40
NOTA_MINIMA = 4.6
VENDAS_MINIMAS = 1000

W, H = 1080, 1920
BRANCO, ESC, ROSA, AMARELO = (255, 255, 255), (20, 14, 10), (236, 32, 118), (255, 214, 10)
_FONTES = os.path.join(os.path.dirname(__file__), "static", "fonts")


def _fonte(nome: str, tamanho: int):
    return ImageFont.truetype(os.path.join(_FONTES, nome), tamanho)


ALTA, FORTE, TEXTO = "BebasNeue-Regular.ttf", "Poppins-SemiBold.ttf", "Poppins-Medium.ttf"


class StoriesError(Exception):
    pass


# ---------------------------------------------------------------- dados

def ler_kit() -> dict:
    return dados._ler_json(CHAVE, {}) or {}


def _salvar_kit(kit: dict) -> None:
    dados._gravar_json(CHAVE, kit)


# ---------------------------------------------------------------- escolha

def fundo_branco(foto: Image.Image) -> bool:
    """Foto de estudio (fundo branco) em vez de ambiente: olha as bordas."""
    p = foto.convert("L").resize((100, 100))
    borda = [p.getpixel((x, y)) for x in range(100) for y in (0, 1, 98, 99)]
    borda += [p.getpixel((x, y)) for y in range(100) for x in (0, 1, 98, 99)]
    claros = sum(1 for v in borda if v >= 235)
    return claros / len(borda) >= 0.45


def _baixar_foto(url: str) -> Image.Image:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content)).convert("RGB")


def escolher_ofertas(quantidade: int = QUANTIDADE, evitar: set | None = None) -> list:
    """Ofertas boas da Shopee com foto de ambiente, uma de cada tipo."""
    evitar = set(evitar or ())
    bloqueadas = dados.ler_config().get("palavras_bloqueadas") or []
    termos = random.sample(TERMOS, len(TERMOS))
    candidatos, vistos = [], set()
    for termo in termos[:6]:
        for ordem in (2, 5):
            try:
                lista = rw._buscar_lista(ordem, termo, random.choice((1, 2)))
            except RuntimeError:
                continue
            for p in lista:
                k = str(p.get("itemId"))
                if k in vistos or k in evitar or not rw._passa_no_filtro(p, bloqueadas):
                    continue
                if (numero(p.get("priceDiscountRate")) < DESCONTO_MINIMO
                        or numero(p.get("ratingStar")) < NOTA_MINIMA
                        or numero(p.get("sales")) < VENDAS_MINIMAS):
                    continue
                vistos.add(k)
                candidatos.append(p)
    candidatos.sort(key=lambda p: numero(p.get("priceDiscountRate")) * 2
                    + min(numero(p.get("sales")), 20000) / 400, reverse=True)

    escolhidos, tipos = [], set()
    for p in candidatos:
        if len(escolhidos) >= quantidade:
            break
        tipo = dados.tipo_do_produto(p.get("productName", ""))
        if tipo in tipos:
            continue
        try:
            foto = _baixar_foto(p["imageUrl"])
        except (requests.RequestException, OSError):
            continue
        if fundo_branco(foto):
            continue
        tipos.add(tipo)
        escolhidos.append((p, foto))
    return escolhidos


# ---------------------------------------------------------------- arte

def _texto(t, xy, s, fonte, cor=BRANCO, sombra=7):
    cam = Image.new("L", t.size, 0)
    ImageDraw.Draw(cam).text(xy, s, font=fonte, fill=200, anchor="mm")
    t.paste(Image.new("RGB", t.size, ESC), mask=cam.filter(ImageFilter.GaussianBlur(sombra)))
    ImageDraw.Draw(t).text(xy, s, font=fonte, fill=cor, anchor="mm")


def _seta(t, ini, fim):
    (x0, y0), (x1, y1) = ini, fim
    cx, cy = x0 - 40, (y0 + y1) / 2 + 30
    pts = [((1 - s) ** 2 * x0 + 2 * (1 - s) * s * cx + s * s * x1,
            (1 - s) ** 2 * y0 + 2 * (1 - s) * s * cy + s * s * y1)
           for s in (k / 40 for k in range(41))]
    cam = Image.new("L", t.size, 0)
    ImageDraw.Draw(cam).line(pts, fill=200, width=10, joint="curve")
    t.paste(Image.new("RGB", t.size, ESC), mask=cam.filter(ImageFilter.GaussianBlur(5)))
    d = ImageDraw.Draw(t)
    d.line(pts, fill=BRANCO, width=6, joint="curve")
    (ax, ay), (bx, by) = pts[-6], pts[-1]
    ang = math.atan2(by - ay, bx - ax)
    for lado in (-1, 1):
        a = ang + math.pi + lado * 0.5
        d.line((bx, by, bx + 34 * math.cos(a), by + 34 * math.sin(a)), fill=BRANCO, width=6)


def _preco(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _mil(vendas: float) -> str:
    return f"+{int(vendas // 1000)} mil vendidos" if vendas >= 1000 else f"+{int(vendas)} vendidos"


def montar_arte(foto: Image.Image, nome: str, preco: float, desconto: float,
                nota: float, vendas: float, data: str) -> Image.Image:
    """Arte 1080x1920 no estilo aprovado (versao 3)."""
    quadrada = foto.resize((W, W), Image.LANCZOS)
    t = quadrada.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(45))
    t.paste(quadrada, (0, 230))
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    for y in range(300):
        d.line((0, y, W, y), fill=int(150 * (1 - y / 300)))
    for y in range(1150, H):
        d.line((0, y, W, y), fill=min(215, int((y - 1150) * 0.5)))
    t.paste(Image.new("RGB", (W, H), ESC), mask=m)

    _texto(t, (W // 2, 120), "achadinho do dia", _fonte(FORTE, 46))
    tam = 72
    while ImageDraw.Draw(t).textlength(nome, font=_fonte(TEXTO, tam)) > 860 and tam > 40:
        tam -= 4
    _texto(t, (W // 2, 330), nome, _fonte(TEXTO, tam))
    _seta(t, (W // 2 - 60, 395), (W // 2 + 40, 760))
    d = ImageDraw.Draw(t)
    d.rounded_rectangle((770, 1140, 1020, 1230), 45, fill=ROSA)
    d.text((895, 1185), f"-{int(desconto)}% OFF", font=_fonte(FORTE, 40), fill=BRANCO, anchor="mm")
    _texto(t, (W // 2, 1380), "a partir de", _fonte(TEXTO, 40))
    _texto(t, (W // 2, 1480), f"R$ {_preco(preco)}", _fonte(ALTA, 170), AMARELO)
    linha = f"nota {nota:.1f}".replace(".", ",") + f" · {_mil(vendas)}"
    _texto(t, (W // 2, 1590), linha, _fonte(TEXTO, 36))
    d = ImageDraw.Draw(t)
    d.rounded_rectangle((170, 1650, 910, 1780), 65, outline=BRANCO, width=5)
    d.text((W // 2, 1715), "link aqui", font=_fonte(FORTE, 38), fill=BRANCO, anchor="mm")
    _texto(t, (W // 2, 1832), f"preço visto em {data} na Shopee, pode mudar · link de afiliada",
           _fonte(TEXTO, 25), sombra=3)
    _texto(t, (W // 2, 1880), "@clube.doquero", _fonte(FORTE, 30), sombra=3)
    return t


_PALAVRAS_FORA = {"kit", "peça", "peças", "pcs", "pçs", "unidade", "unidades", "store", "loja", "oficial", "original"}


def nome_da_arte(nome: str, limite: int = 26) -> str:
    """Nome curto para escrever na arte: palavras inteiras, sem numeros e sem
    termos de anuncio ("kit", "1/2 peças", nome da loja)."""
    palavras = []
    for p in str(nome).replace("|", " ").replace(",", " ").replace(":", " ").split():
        if any(ch.isdigit() for ch in p) or "/" in p or p.lower() in _PALAVRAS_FORA:
            continue
        if len(" ".join(palavras + [p])) > limite:
            break
        palavras.append(p)
    while palavras and palavras[-1].lower() in {"de", "da", "do", "e", "com", "para", "em", "a", "o"}:
        palavras.pop()
    return " ".join(palavras).lower() or str(nome)[:limite].lower()


# ---------------------------------------------------------------- kit

def gerar_kit(nomes_curtos=None) -> dict:
    """Escolhe as ofertas, monta as artes, sobe no Cloudinary e guarda o kit.
    nomes_curtos: funcao que encurta a lista de nomes (Gemini); opcional."""
    agora = dados.agora_brasil()
    anterior = ler_kit()
    evitar = {str(i.get("item_id")) for i in anterior.get("itens", [])}
    escolhidos = escolher_ofertas(evitar=evitar)
    if not escolhidos:
        raise StoriesError("Não achei ofertas com foto de ambiente agora. Tente de novo daqui a pouco.")

    nomes = [str(p.get("productName") or "") for p, _ in escolhidos]
    curtos = nomes
    if nomes_curtos:
        try:
            curtos = nomes_curtos(nomes) or nomes
        except Exception:  # noqa: BLE001 - sem IA fica o nome original
            curtos = nomes

    itens = []
    for (p, foto), curto in zip(escolhidos, curtos):
        nome = nome_da_arte(curto or p.get("productName") or "")
        arte = montar_arte(foto, nome, numero(p.get("priceMin")), numero(p.get("priceDiscountRate")),
                           numero(p.get("ratingStar")), numero(p.get("sales")), f"{agora:%d/%m}")
        caminho = os.path.join(tempfile.gettempdir(), f"story-{p.get('itemId')}.jpg")
        arte.save(caminho, quality=92)
        try:
            enviado = galeria._upload_cloudinary(caminho, "imagem")
        finally:
            os.remove(caminho)
        link = rw.link_afiliado_shopee(p) or str(p.get("offerLink") or "")
        itens.append({
            "item_id": str(p.get("itemId")), "nome": nome,
            "nome_completo": str(p.get("productName") or ""),
            "preco": _preco(numero(p.get("priceMin"))), "desconto": int(numero(p.get("priceDiscountRate"))),
            "link": link, "arte": enviado.get("secure_url", ""),
        })
    kit = {"data": f"{agora:%Y-%m-%d}", "gerado": f"{agora:%d/%m %H:%M}", "itens": itens}
    _salvar_kit(kit)
    return kit


def kit_e_de_hoje(kit: dict) -> bool:
    return kit.get("data") == f"{dados.agora_brasil():%Y-%m-%d}"
