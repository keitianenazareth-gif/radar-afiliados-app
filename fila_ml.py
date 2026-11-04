"""Coloca ofertas do Mercado Livre na fila do robo do WhatsApp.

Usado pela tarefa agendada do Claude: ela escolhe as ofertas no Chrome,
gera o link oficial de afiliada (meli.la) e grava um arquivo JSON assim:

    [
      {"link": "https://meli.la/...", "nome": "...", "preco": "R$ 49,90",
       "preco_antigo": "R$ 89,90", "imagem": "https://...jpg",
       "observacao": "⭐ 4,8 | 🛒 +5 mil vendidos"},
      {"link": "https://meli.la/...", "nome": "Oferta do dia", "preco": "R$ 11,99",
       "vale_ate_hora": "12:00", "prioridade": true},
      {"tipo": "cupom", "descricao": "30% OFF em Casa",
       "detalhes": "Compra mínima R$ 40 · desconto até R$ 20",
       "validade": "2026-12-31", "link": "https://meli.la/..."}
    ]

Itens com "tipo": "cupom" vao para a lista de cupons (saem uma vez so).
Toda oferta vale por VALIDADE_HORAS; "vale_ate_hora" troca por um horario de
hoje. Se vencer antes do lote, o robo descarta em vez de mandar preco velho.

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
from datetime import datetime, timedelta, timezone

import requests

try:
    from credenciais_locais import WEB_USUARIO, WEB_SENHA
except ImportError:
    WEB_USUARIO = os.environ.get("WEB_USUARIO", "")
    WEB_SENHA = os.environ.get("WEB_SENHA", "")

RADAR_URL = os.environ.get("RADAR_URL", "https://radar-afiliados-web.onrender.com")
VALIDADE_HORAS = 6
FUSO = timezone(timedelta(hours=-3))  # Brasilia; o Windows nao traz a base de fusos
CAMPOS = ("link", "nome", "preco", "preco_antigo", "imagem", "observacao")
CAMPOS_CUPOM = ("link", "descricao", "detalhes", "validade", "como_ativar")
# Os cupons do Mercado Livre nao tem codigo: a pessoa ativa no app. O link
# e' de afiliada para um produto em que o cupom vale.
COMO_ATIVAR_ML = "Ative no app do Mercado Livre em *Cupons* e aproveite neste produto 👇"


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


def _dados_cupom(cupom: dict) -> dict:
    dados = {campo: str(cupom.get(campo) or "").strip() for campo in CAMPOS_CUPOM}
    dados["como_ativar"] = dados["como_ativar"] or COMO_ATIVAR_ML
    return dados


def prazo_da_oferta(oferta: dict, agora: datetime | None = None) -> datetime:
    """Quando a oferta vence: o "vale_ate_hora" de hoje ou VALIDADE_HORAS."""
    agora = agora or datetime.now(FUSO)
    hora = str(oferta.get("vale_ate_hora") or "").strip()
    if hora:
        horas, minutos = hora.split(":")
        return agora.replace(hour=int(horas), minute=int(minutos), second=0, microsecond=0)
    return agora + timedelta(hours=VALIDADE_HORAS)


def enviar_para_fila(sessao: requests.Session, oferta: dict) -> dict:
    if oferta.get("tipo") == "cupom":
        caminho, dados = "/whatsapp/cupons/adicionar", _dados_cupom(oferta)
    else:
        caminho = "/whatsapp/fila/adicionar"
        dados = {campo: str(oferta.get(campo) or "").strip() for campo in CAMPOS}
        prazo = prazo_da_oferta(oferta)
        dados.update({"vale_ate": str(prazo.timestamp()),
                      "vale_ate_texto": prazo.strftime("%d/%m %H:%M"),
                      "prioridade": "1" if oferta.get("prioridade") else ""})
    # "loja": "Amazon" para ofertas da Amazon (o site poe a tag e tira o preco).
    dados.update({"loja": oferta.get("loja") or "Mercado Livre", "formato": "json"})
    resposta = sessao.post(f"{RADAR_URL}{caminho}", data=dados, timeout=60)
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
        from robo_whatsapp import mensagem_cupom, mensagem_fila

        for oferta in ofertas:
            loja = oferta.get("loja") or "Mercado Livre"
            if oferta.get("tipo") == "cupom":
                print(mensagem_cupom({**_dados_cupom(oferta), "loja": loja}))
            elif loja == "Amazon":
                from whatsapp_dados import aplicar_tag_amazon

                tag = os.environ.get("AMAZON_TAG", "2410890e-20")
                print(mensagem_fila({**oferta, "loja": loja, "preco": "", "preco_antigo": "",
                                     "link": aplicar_tag_amazon(oferta["link"], tag)}))
            else:
                print(mensagem_fila({**oferta, "loja": loja}))
            if oferta.get("tipo") != "cupom":
                print(f"[vale até {prazo_da_oferta(oferta).strftime('%d/%m %H:%M')}"
                      f"{', sai primeiro' if oferta.get('prioridade') else ''}]")
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

    print(f"Resumo: {contagem['adicionado']} na fila/cupons, {contagem['repetido']} repetidos, "
          f"{contagem['bloqueado']} com palavra bloqueada, {contagem['erro']} com erro.")
    return 0 if contagem["erro"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
