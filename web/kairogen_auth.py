"""Autenticacao do Kairogen para uso no backend (headless).

O Kairogen nao entrega uma "chave de API" fixa. Ele usa OAuth:

  - refresh_token : credencial de longa duracao. Serve para pedir
                    access_tokens novos. MUDA a cada uso (rotacao) e o
                    antigo e' revogado - se reusar, o Kairogen derruba tudo.
  - access_token  : dura ~8h. E' o que vai no header das chamadas reais:
                    Authorization: Bearer <access_token>

Este modulo guarda os tokens num "cofrinho" e troca o refresh_token por
um access_token novo quando o atual vence, regravando o refresh_token
rotacionado no cofrinho.

--------------------------------------------------------------------
COMO USAR NO CODIGO
--------------------------------------------------------------------
    from web.kairogen_auth import get_access_token
    import requests
    tok = get_access_token()                       # renova sozinho
    requests.get(url, headers={"Authorization": f"Bearer {tok}"})

--------------------------------------------------------------------
ONDE FICA O COFRINHO (token store)
--------------------------------------------------------------------
Se UPSTASH_REDIS_REST_URL e UPSTASH_REDIS_REST_TOKEN estiverem no
ambiente  ->  usa o Upstash Redis (duravel, sobrevive a restart do
Render no plano free). E' o modo recomendado em producao.

Senao  ->  usa um arquivo JSON local:
    KAIROGEN_TOKEN_STORE (se definido)  ou
    <raiz do projeto>/kairogen_tokens.json
Bom para rodar/testar no Windows. No Render free o arquivo some a
cada deploy, por isso o Upstash.

--------------------------------------------------------------------
PRIMEIRA CARGA (semente)
--------------------------------------------------------------------
Se o cofrinho ainda estiver vazio, o modulo semeia com:
    KAIROGEN_REFRESH_TOKEN   (obrigatorio na 1a vez)
    KAIROGEN_ACCESS_TOKEN    (opcional)
Depois disso a fonte da verdade passa a ser o cofrinho; a variavel
KAIROGEN_REFRESH_TOKEN vira so um plano B de emergencia.

Variaveis auxiliares (tem default, normalmente nao precisa mexer):
    KAIROGEN_CLIENT_ID   (default: dyn-r3Sodr7P0yX5NYLy)
    KAIROGEN_TOKEN_URL   (default: https://api.kairogen.ai/oauth/token)
    KAIROGEN_STORE_KEY   (default: kairogen:tokens)
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import requests

_DEFAULT_CLIENT_ID = "dyn-r3Sodr7P0yX5NYLy"
_DEFAULT_TOKEN_URL = "https://api.kairogen.ai/oauth/token"
_SKEW = 90  # segundos de folga antes do vencimento do access_token
_lock = threading.Lock()


class KairogenAuthError(RuntimeError):
    """Falha que exige acao humana (refazer o device flow e resemear)."""


# --------------------------------------------------------------------------
# Configuracao
# --------------------------------------------------------------------------
def _client_id() -> str:
    return os.environ.get("KAIROGEN_CLIENT_ID") or _DEFAULT_CLIENT_ID


def _token_url() -> str:
    return os.environ.get("KAIROGEN_TOKEN_URL") or _DEFAULT_TOKEN_URL


def _store_key() -> str:
    return os.environ.get("KAIROGEN_STORE_KEY") or "kairogen:tokens"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# Cofrinho: Upstash Redis (REST) ou arquivo local
# --------------------------------------------------------------------------
def _upstash_cfg():
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
    if url and token:
        return url, token
    return None


def _upstash_cmd(cmd: list):
    url, token = _upstash_cfg()
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=cmd,
            timeout=15,
        )
    except requests.RequestException as e:
        raise KairogenAuthError(f"Upstash inacessivel: {e}") from e
    if r.status_code != 200:
        raise KairogenAuthError(f"Upstash erro HTTP {r.status_code}: {r.text[:200]}")
    return r.json().get("result")


def _store_file() -> Path:
    p = os.environ.get("KAIROGEN_TOKEN_STORE")
    return Path(p) if p else _project_root() / "kairogen_tokens.json"


def _store_read() -> dict | None:
    if _upstash_cfg():
        raw = _upstash_cmd(["GET", _store_key()])
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
        return None
    caminho = _store_file()
    if caminho.exists():
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _store_write(dados: dict) -> None:
    if _upstash_cfg():
        _upstash_cmd(["SET", _store_key(), json.dumps(dados)])
        return
    caminho = _store_file()
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = caminho.with_suffix(".tmp")
        tmp.write_text(json.dumps(dados, indent=2), encoding="utf-8")
        tmp.replace(caminho)
    except OSError as e:
        print(f"[kairogen_auth] aviso: nao consegui gravar {caminho}: {e}")


# --------------------------------------------------------------------------
# Logica de token
# --------------------------------------------------------------------------
def _seed_from_env() -> dict:
    rt = os.environ.get("KAIROGEN_REFRESH_TOKEN", "").strip()
    if not rt:
        raise KairogenAuthError(
            "Cofrinho vazio e sem KAIROGEN_REFRESH_TOKEN no ambiente. "
            "Rode o device flow de novo e semeie o refresh_token."
        )
    return {
        "refresh_token": rt,
        "access_token": os.environ.get("KAIROGEN_ACCESS_TOKEN", "").strip(),
        "access_expires_at": 0,
        "scope": "",
    }


def _refresh(store: dict) -> dict:
    resp = requests.post(
        _token_url(),
        data={
            "grant_type": "refresh_token",
            "refresh_token": store["refresh_token"],
            "client_id": _client_id(),
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    corpo = resp.json() if resp.content else {}
    if resp.status_code != 200 or "access_token" not in corpo:
        erro = corpo.get("error") or corpo.get("code") or f"HTTP {resp.status_code}"
        if erro in ("invalid_grant", "VALIDATION_ERROR"):
            raise KairogenAuthError(
                f"O Kairogen recusou o refresh_token ({erro}). Foi revogado ou "
                "reusado. Refaca o device flow e resemeie o cofrinho."
            )
        raise KairogenAuthError(f"Falha ao renovar token: {erro} - {corpo}")

    novo = {
        "refresh_token": corpo.get("refresh_token", store["refresh_token"]),
        "access_token": corpo["access_token"],
        "access_expires_at": int(time.time()) + int(corpo.get("expires_in", 28800)),
        "scope": corpo.get("scope", store.get("scope", "")),
    }
    _store_write(novo)  # grava ANTES de devolver: nao perde o refresh rotacionado
    return novo


def get_access_token(force: bool = False) -> str:
    """Devolve um access_token valido, renovando pelo refresh se preciso."""
    with _lock:
        store = _store_read()
        if store is None:
            store = _seed_from_env()
            _store_write(store)
        agora = int(time.time())
        if (
            not force
            and store.get("access_token")
            and int(store.get("access_expires_at", 0)) - _SKEW > agora
        ):
            return store["access_token"]
        return _refresh(store)["access_token"]


def auth_header() -> dict:
    """Atalho: {'Authorization': 'Bearer <token>'} pronto para o requests."""
    return {"Authorization": f"Bearer {get_access_token()}"}


if __name__ == "__main__":
    # Teste manual:  python -m web.kairogen_auth
    t = get_access_token()
    print("access_token OK, primeiros 12 chars:", t[:12], "...")
    r = requests.get(
        "https://api.kairogen.ai/oauth/userinfo",
        headers={"Authorization": f"Bearer {t}"},
        timeout=20,
    )
    print("userinfo:", r.status_code, r.json())
