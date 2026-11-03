"""
marca_dagua.py
--------------
Coloca a marca d'agua "@clube.doquero" nas fotos e videos que os robos
publicam (WhatsApp e Instagram).

A marca e' uma "pilula" escura semitransparente com o @ em branco: no
canto inferior direito das fotos e no alto, a esquerda, dos videos. Nao impede copia, mas quem repostar leva a marca
junto (e faz propaganda do Clube do Quero).

Ajustes por variavel de ambiente (opcionais):
    MARCA_DAGUA_TEXTO   texto da marca (padrao "@clube.doquero")
    MARCA_DAGUA         "0" desliga a marca em tudo
"""

from __future__ import annotations

import base64
import io
import os

from PIL import Image, ImageDraw, ImageFont

TEXTO_PADRAO = "@clube.doquero"
_PASTA = os.path.dirname(os.path.abspath(__file__))
_FONTE = os.path.join(_PASTA, "web", "static", "fonts", "Roboto-Bold.ttf")


def ligada() -> bool:
    return os.environ.get("MARCA_DAGUA", "1") != "0"


def texto_marca() -> str:
    return (os.environ.get("MARCA_DAGUA_TEXTO") or TEXTO_PADRAO).strip()


def _fonte(tamanho: int):
    for nome in (_FONTE, "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def camada(largura: int, altura: int, texto: str | None = None,
           posicao: str = "inferior_direito") -> Image.Image:
    """Imagem transparente (RGBA) do tamanho pedido, so com a marca.
    posicao "inferior_direito" (fotos) ou "superior_esquerdo" (videos de
    Reels/Shopee Video, onde o canto de baixo fica coberto pelos botoes
    e pela legenda do aplicativo)."""
    texto = texto or texto_marca()
    base = min(largura, altura)
    tamanho = max(14, int(base * 0.045))
    fonte = _fonte(tamanho)
    rascunho = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    x0, y0, x1, y1 = rascunho.textbbox((0, 0), texto, font=fonte)
    larg_txt, alt_txt = x1 - x0, y1 - y0
    pad_x, pad_y = int(tamanho * 0.6), int(tamanho * 0.35)
    margem = int(base * 0.035)
    larg_pilula = larg_txt + 2 * pad_x
    alt_pilula = alt_txt + 2 * pad_y
    if posicao == "superior_esquerdo":
        px, py = margem, int(altura * 0.09)
    else:
        px = largura - margem - larg_pilula
        py = altura - margem - alt_pilula

    img = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (px, py, px + larg_pilula, py + alt_pilula),
        radius=alt_pilula // 2, fill=(0, 0, 0, 110),
    )
    draw.text((px + pad_x - x0, py + pad_y - y0), texto, font=fonte,
              fill=(255, 255, 255, 215))
    return img


def aplicar(img: Image.Image, texto: str | None = None) -> Image.Image:
    """Devolve uma copia da foto com a marca d'agua."""
    rgba = img.convert("RGBA")
    rgba.alpha_composite(camada(rgba.width, rgba.height, texto))
    return rgba.convert("RGB")


def aplicar_em_bytes(conteudo: bytes, texto: str | None = None) -> bytes:
    """Bytes de uma foto qualquer -> bytes JPEG com a marca d'agua."""
    img = Image.open(io.BytesIO(conteudo))
    img.load()
    saida = io.BytesIO()
    aplicar(img, texto).save(saida, format="JPEG", quality=90)
    return saida.getvalue()


def jpeg_base64(conteudo: bytes, texto: str | None = None) -> str:
    return base64.b64encode(aplicar_em_bytes(conteudo, texto)).decode("ascii")
