"""Gera um video vertical curto (15-30s) de divulgacao a partir de:

  - a foto do produto (Shopee API / link manual)
  - o roteiro estruturado do Gemini (campanhas_ia.gerar_roteiro_video)
  - narracao em audio (web.tts.sintetizar)

Uso:
    from web.video_campanha import montar_video
    caminho_mp4 = montar_video(produto, roteiro)

'produto' e' o mesmo dicionario que o front manda para /api/campanha
(nome, preco/preco_texto, plataforma, imagem/imageUrl, link).
'roteiro' e' o dict devolvido por gerar_roteiro_video.
"""

import io
import os
import re
import uuid

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from moviepy import AudioFileClip, CompositeVideoClip, ImageClip, concatenate_videoclips
from moviepy import vfx

from web.tts import sintetizar

# 1080x1920 (9:16), padrao de Reels / Shopee Video / TikTok.
# Em servidor com pouca RAM (ex.: Render free), definir VIDEO_LARGURA=720
# e VIDEO_ALTURA=1280 para gastar menos memoria no encode.
LARGURA = int(os.environ.get("VIDEO_LARGURA", "1080"))
ALTURA = int(os.environ.get("VIDEO_ALTURA", "1920"))
FPS = 24
FADE = 0.25                  # fade curto entre cenas (transicao simples)
DUR_MIN, DUR_MAX = 15.0, 30.0
PRESET = os.environ.get("VIDEO_PRESET", "ultrafast")  # libx264
KEN_BURNS = False            # zoom lento por cena; encarece MUITO o render

PASTA_SAIDA = os.path.join(os.path.dirname(__file__), "static", "videos")

_CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# Fontes
# ---------------------------------------------------------------------------

def _fonte(tamanho, negrito=True):
    candidatos = (
        ["arialbd.ttf", "seguisb.ttf", "segoeuib.ttf"]
        if negrito
        else ["arial.ttf", "segoeui.ttf"]
    )
    for nome in candidatos:
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Imagem do produto
# ---------------------------------------------------------------------------

def _baixar_imagem(produto):
    url = (
        produto.get("imagem")
        or produto.get("imageUrl")
        or produto.get("image")
        or ""
    ).strip()
    if not url:
        return None
    try:
        resp = requests.get(url, headers=_CABECALHOS, timeout=15)
        if resp.status_code != 200:
            return None
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except (requests.RequestException, OSError):
        return None


def _cobrir(img, larg, alt):
    """Redimensiona cobrindo larg x alt (crop central), estilo CSS cover."""
    escala = max(larg / img.width, alt / img.height)
    nova = img.resize(
        (max(1, round(img.width * escala)), max(1, round(img.height * escala))),
        Image.LANCZOS,
    )
    esq = (nova.width - larg) // 2
    topo = (nova.height - alt) // 2
    return nova.crop((esq, topo, esq + larg, topo + alt))


def _fundo(img_produto):
    """Fundo da tela: foto do produto borrada e escurecida, ou gradiente."""
    if img_produto is not None:
        fundo = _cobrir(img_produto, LARGURA, ALTURA).filter(
            ImageFilter.GaussianBlur(40)
        )
        escuro = Image.new("RGB", (LARGURA, ALTURA), (0, 0, 0))
        return Image.blend(fundo, escuro, 0.55)

    base = Image.new("RGB", (LARGURA, ALTURA), (24, 24, 40))
    top = np.linspace(30, 12, ALTURA).astype("uint8")
    arr = np.stack(
        [np.tile(c[:, None], (1, LARGURA)) for c in (top, top // 2, top + 20)],
        axis=-1,
    )
    return Image.fromarray(arr, "RGB")


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

def _quebrar(draw, texto, fonte, larg_max):
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = (atual + " " + palavra).strip()
        if draw.textlength(teste, font=fonte) <= larg_max or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _bloco_texto(draw, texto, fonte, larg_max, y, cor=(255, 255, 255), centro=True):
    linhas = _quebrar(draw, texto, fonte, larg_max)
    altura_linha = int(fonte.size * 1.25)
    for linha in linhas:
        larg = draw.textlength(linha, font=fonte)
        x = (LARGURA - larg) / 2 if centro else (LARGURA - larg_max) / 2
        # sombra para leitura sobre qualquer fundo
        draw.text((x + 3, y + 3), linha, font=fonte, fill=(0, 0, 0))
        draw.text((x, y), linha, font=fonte, fill=cor)
        y += altura_linha
    return y


def _texto_preco(produto):
    preco = produto.get("preco")
    if isinstance(preco, (int, float)) and preco > 0:
        return f"R$ {preco:.2f}".replace(".", ",")
    bruto = str(produto.get("preco_texto") or produto.get("priceMin") or "").strip()
    if not bruto:
        return ""
    if bruto.replace(".", "").replace(",", "").isdigit():
        try:
            return f"R$ {float(bruto.replace(',', '.')):.2f}".replace(".", ",")
        except ValueError:
            pass
    return bruto if bruto.upper().startswith("R$") else f"R$ {bruto}"


def _badge_preco(draw, texto, y):
    if not texto:
        return
    fonte = _fonte(64)
    larg = draw.textlength(texto, font=fonte)
    pad_x, pad_y = 40, 22
    x0 = (LARGURA - larg) / 2 - pad_x
    x1 = (LARGURA + larg) / 2 + pad_x
    draw.rounded_rectangle(
        [x0, y, x1, y + fonte.size + 2 * pad_y], radius=28, fill=(255, 78, 0)
    )
    draw.text(
        ((LARGURA - larg) / 2, y + pad_y - 4), texto, font=fonte, fill=(255, 255, 255)
    )


# ---------------------------------------------------------------------------
# Composicao de uma cena (frame estatico, PNG -> array)
# ---------------------------------------------------------------------------

def _frame_cena(fundo, img_produto, titulo, texto_cena, preco, mostrar_titulo):
    quadro = fundo.copy()

    # foto do produto em destaque, contida numa area central
    if img_produto is not None:
        area_l, area_a = int(LARGURA * 0.82), int(ALTURA * 0.46)
        prod = img_produto.copy()
        prod.thumbnail((area_l, area_a), Image.LANCZOS)
        px = (LARGURA - prod.width) // 2
        py = int(ALTURA * 0.20)
        moldura = Image.new("RGB", (prod.width + 24, prod.height + 24), (255, 255, 255))
        quadro.paste(moldura, (px - 12, py - 12))
        quadro.paste(prod, (px, py))

    draw = ImageDraw.Draw(quadro)
    larg_max = int(LARGURA * 0.86)

    if mostrar_titulo and titulo:
        _bloco_texto(draw, titulo.upper(), _fonte(76), larg_max, int(ALTURA * 0.055))

    _badge_preco(draw, preco, int(ALTURA * 0.70))

    if texto_cena:
        _bloco_texto(
            draw, texto_cena, _fonte(66), larg_max, int(ALTURA * 0.80),
            cor=(255, 255, 255),
        )

    return np.array(quadro)


# ---------------------------------------------------------------------------
# Ken Burns (zoom lento)
# ---------------------------------------------------------------------------

def _ken_burns(clip, dur, aproximar=True):
    z0, z1 = (1.0, 1.08) if aproximar else (1.08, 1.0)

    def escala(t):
        return z0 + (z1 - z0) * (t / dur if dur else 0)

    ampliado = clip.resized(escala).with_position(("center", "center"))
    return CompositeVideoClip([ampliado], size=(LARGURA, ALTURA)).with_duration(dur)


# ---------------------------------------------------------------------------
# Montagem
# ---------------------------------------------------------------------------

def _slug(texto, limite=40):
    base = re.sub(r"[^a-z0-9]+", "-", (texto or "video").lower()).strip("-")
    return (base[:limite] or "video")


def _duracoes(cenas, dur_audio):
    """Distribui a duracao total (casada com o audio) entre as cenas,
    proporcional aos 'segundos' sugeridos pelo Gemini."""
    alvo = min(DUR_MAX, max(DUR_MIN, dur_audio + 1.0))
    pesos = [max(0.1, float(c.get("segundos", 4))) for c in cenas]
    soma = sum(pesos)
    return [alvo * p / soma for p in pesos]


def montar_video(produto, roteiro):
    os.makedirs(PASTA_SAIDA, exist_ok=True)

    cenas = roteiro.get("cenas") or []
    if not cenas:
        raise RuntimeError("Roteiro sem cenas.")

    nome_id = f"{_slug(produto.get('nome'))}-{uuid.uuid4().hex[:8]}"
    caminho_audio_base = os.path.join(PASTA_SAIDA, f"_narr-{nome_id}")
    caminho_mp4 = os.path.join(PASTA_SAIDA, f"{nome_id}.mp4")

    # 1) narracao
    caminho_audio, motor_tts = sintetizar(roteiro["narracao"], caminho_audio_base + ".wav")
    narracao = AudioFileClip(caminho_audio)

    # 2) imagem + fundo
    img_produto = _baixar_imagem(produto)
    fundo = _fundo(img_produto)
    preco = _texto_preco(produto)

    # 3) cenas -> clipes
    duracoes = _duracoes(cenas, narracao.duration)
    clipes = []
    for i, (cena, dur) in enumerate(zip(cenas, duracoes)):
        frame = _frame_cena(
            fundo, img_produto, roteiro.get("titulo", ""),
            cena.get("texto_tela", ""), preco, mostrar_titulo=(i == 0),
        )
        clipe = ImageClip(frame).with_duration(dur)
        if KEN_BURNS:
            clipe = _ken_burns(clipe, dur, aproximar=(i % 2 == 0))
        # fade rapido no inicio/fim de cada cena. 'chain' (em vez de
        # 'compose') e' ~6x mais rapido de renderizar.
        clipe = clipe.with_effects([vfx.FadeIn(FADE), vfx.FadeOut(FADE)])
        clipes.append(clipe)

    video = concatenate_videoclips(clipes, method="chain")

    # 4) audio: narracao comeca em ~0.3s; video nao passa de DUR_MAX
    video = video.with_duration(min(video.duration, DUR_MAX))
    narracao = narracao.with_start(0.3)
    video = video.with_audio(narracao)

    # 5) exporta
    video.write_videofile(
        caminho_mp4,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset=PRESET,
        threads=os.cpu_count() or 2,
        logger=None,
    )

    for c in clipes:
        c.close()
    video.close()
    narracao.close()
    try:
        os.remove(caminho_audio)
    except OSError:
        pass

    return caminho_mp4, motor_tts
