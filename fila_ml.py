"""Coloca ofertas do Mercado Livre na fila do robo do WhatsApp.

Usado pela tarefa agendada do Claude: ela escolhe as ofertas no Chrome,
gera o link oficial de afiliada (meli.la) e grava um arquivo JSON assim:

    [
      {"link": "https://meli.la/...", "nome": "...", "preco": "R$ 49,90",
       "preco_antigo": "R$ 89,90", "imagem": "https://...jpg",
       "observacao": "⭐ 4,8 | 🛒 +5 mil vendidos"}
    ]

Depois roda:
    .\\.venv312\\Scripts\\python.exe fila_ml.py ofertas_ml.json

O programa manda cada oferta para a pagina /whatsapp do Radar web (no
Render), com o usuario e senha do credenciais_locais.py - assim quem roda
nao precisa ver a senha. Produtos ja na fila ou enviados ha pouco sao
pulados pelo proprio site. Use --teste para so mostrar as mensagens.
"""

from __future__ import annotations

import json
import os
import sys
import time

import requests

try:
    from credenciais_locais import WEB_USUARIO, WEB_SENHA
except ImportError:
    WEB_USUARIO = os.environ.get("WEB_USUARIO", "")
    WEB_SENHA = os.environ.get("WEB_SENHA", "")

RADAR_URL = os.environ.get("RADAR_URL", "https://radar-afiliados-web.onrender.com")
CAMPOS = ("link", "nome", "preco", "preco_antigo", "imagem", "observacao")


def ler_ofertas(caminho: str) -> list:
    # utf-8-sig: aceita tambem arquivo salvo pelo PowerShell/Bloco de Notas.
    with open(caminho, encoding="utf-8-sig") as arquivo:
        ofertas = json.load(arquivo)
    if not isinstance(ofertas, list):
        raise ValueError("O arquivo precisa ter uma lista de ofertas.")
    return [o for o in ofertas if isinstance(o, dict) and str(o.get("link", "")).startswith("http")]


def acordar_site(sessao: requests.Session) -> None:
    """O Render gratis dorme; a primeira visita pode levar ~1 minuto."""
    for _ in range(6):
        try:
            if sessao.get(f"{RADAR_URL}/healthz", timeout=30).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(10)
    raise RuntimeError("O site do Radar nao respondeu (Render fora do ar?).")


def enviar_para_fila(sessao: requests.Session, oferta: dict) -> dict:
    dados = {campo: str(oferta.get(campo) or "").strip() for campo in CAMPOS}
    dados.update({"loja": "Mercado Livre", "formato": "json"})
    resposta = sessao.post(f"{RADAR_URL}/whatsapp/fila/adicionar", data=dados, timeout=60)
    if resposta.status_code == 401:
        raise RuntimeError("Login recusado: confira WEB_USUARIO/WEB_SENHA no credenciais_locais.py.")
    try:
        return resposta.json()
    except ValueError:
        return {"ok": False, "situacao": "erro",
                "mensagem": f"Resposta inesperada do site (HTTP {resposta.status_code})."}


def main() -> int:
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not argumentos:
        print(__doc__)
        return 1
    ofertas = ler_ofertas(argumentos[0])
    if not ofertas:
        print("Nenhuma oferta com link no arquivo.")
        return 1

    if "--teste" in sys.argv:
        from robo_whatsapp import mensagem_fila

        for oferta in ofertas:
            print(mensagem_fila({**oferta, "loja": "Mercado Livre"}))
            print("-" * 40)
        return 0

    if not WEB_SENHA:
        print("Falta WEB_SENHA no credenciais_locais.py.")
        return 1

    sessao = requests.Session()
    sessao.auth = (WEB_USUARIO, WEB_SENHA)
    acordar_site(sessao)

    contagem = {"adicionado": 0, "repetido": 0, "bloqueado": 0, "erro": 0}
    for oferta in ofertas:
        resultado = enviar_para_fila(sessao, oferta)
        situacao = resultado.get("situacao", "erro")
        contagem[situacao] = contagem.get(situacao, 0) + 1
        print(f"[{situacao}] {resultado.get('mensagem')}")

    print(f"Resumo: {contagem['adicionado']} na fila, {contagem['repetido']} repetidos, "
          f"{contagem['bloqueado']} com palavra bloqueada, {contagem['erro']} com erro.")
    return 0 if contagem["erro"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
