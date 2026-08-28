"""Narracao (texto -> fala) para o gerador de video.

Motor principal: TTS nativo do Gemini (mesma chave GEMINI_API_KEY do
resto do app). Se falhar (cota, modelo preview fora do ar, etc.), cai
automaticamente para o edge-tts (vozes neurais pt-BR da Microsoft,
gratuito e sem chave).

Uso:
    from web.tts import sintetizar
    caminho_wav, motor = sintetizar("texto da narracao", "saida.wav")
"""

import asyncio
import base64
import os
import time
import wave

import requests

try:
    from credenciais_locais import GEMINI_API_KEY
except ImportError:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Modelo de TTS do Google AI Studio (camada free). E' "preview" - se
# sair do ar, o fallback edge-tts assume.
MODELO_TTS = "gemini-2.5-flash-preview-tts"
URL_TTS = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODELO_TTS}:generateContent"
)
VOZ_GEMINI = "Kore"          # voz feminina neutra
VOZ_EDGE = "pt-BR-FranciscaNeural"


def _pcm_para_wav(pcm_bytes, caminho_wav, taxa=24000):
    """O Gemini devolve PCM 16-bit mono cru; embrulha num .wav."""
    with wave.open(caminho_wav, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(taxa)
        wav.writeframes(pcm_bytes)


def _taxa_do_mime(mime):
    """Extrai 'rate=NNNN' de algo como 'audio/L16;codec=pcm;rate=24000'."""
    for parte in (mime or "").split(";"):
        parte = parte.strip()
        if parte.startswith("rate="):
            try:
                return int(parte.split("=", 1)[1])
            except ValueError:
                pass
    return 24000


def _tts_gemini(texto, caminho_wav):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY nao configurada.")

    corpo = {
        "contents": [{"parts": [{"text": texto}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": VOZ_GEMINI}
                }
            },
        },
    }

    # 503 ("high demand") no TTS preview e' comum. Uma retentativa rapida
    # e, se persistir, deixamos o edge-tts assumir (voz pt-BR muito boa)
    # em vez de segurar a requisicao.
    for tentativa in range(2):
        resposta = requests.post(
            f"{URL_TTS}?key={GEMINI_API_KEY}", json=corpo, timeout=60
        )
        if resposta.status_code != 503:
            break
        time.sleep(2)

    if resposta.status_code != 200:
        raise RuntimeError(
            f"Gemini TTS HTTP {resposta.status_code}: {resposta.text[:160]}"
        )

    try:
        parte = resposta.json()["candidates"][0]["content"]["parts"][0]
        dados = parte["inlineData"]["data"]
        mime = parte["inlineData"].get("mimeType", "")
    except (KeyError, IndexError):
        raise RuntimeError("Gemini TTS nao retornou audio.")

    _pcm_para_wav(base64.b64decode(dados), caminho_wav, _taxa_do_mime(mime))
    return caminho_wav


def _tts_edge(texto, caminho_saida):
    """Fallback: edge-tts gera MP3."""
    import edge_tts

    caminho_mp3 = os.path.splitext(caminho_saida)[0] + ".mp3"

    async def _gerar():
        com = edge_tts.Communicate(texto, VOZ_EDGE)
        await com.save(caminho_mp3)

    asyncio.run(_gerar())
    return caminho_mp3


def sintetizar(texto, caminho_saida):
    """Gera o audio da narracao. Tenta Gemini, cai para edge-tts.

    Retorna (caminho_do_arquivo, nome_do_motor). Levanta RuntimeError
    apenas se TODOS os motores falharem.
    """
    texto = (texto or "").strip()
    if not texto:
        raise RuntimeError("Narracao vazia.")

    erros = []
    try:
        return _tts_gemini(texto, caminho_saida), "gemini"
    except Exception as erro:  # noqa: BLE001 - queremos o fallback
        erros.append(f"gemini: {erro}")

    try:
        return _tts_edge(texto, caminho_saida), "edge-tts"
    except Exception as erro:  # noqa: BLE001
        erros.append(f"edge-tts: {erro}")

    raise RuntimeError("Nenhum motor de narracao funcionou -> " + " | ".join(erros))
