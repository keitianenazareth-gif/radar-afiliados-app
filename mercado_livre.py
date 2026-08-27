import os
import json
import requests

try:
    from kivy.app import App
except ImportError:
    App = None

# Mesmo padrao de credenciais do shopee.py: primeiro tenta o arquivo
# local (gerado pelo GitHub Actions, nunca commitado), depois cai
# para variavel de ambiente.
try:
    from credenciais_locais import ML_ACCESS_TOKEN
except ImportError:
    ML_ACCESS_TOKEN = os.environ.get("ML_ACCESS_TOKEN", "")

try:
    from credenciais_locais import ML_REFRESH_TOKEN
except ImportError:
    ML_REFRESH_TOKEN = os.environ.get("ML_REFRESH_TOKEN", "")

try:
    from credenciais_locais import ML_CLIENT_ID
except ImportError:
    ML_CLIENT_ID = os.environ.get("ML_CLIENT_ID", "")

try:
    from credenciais_locais import ML_CLIENT_SECRET
except ImportError:
    ML_CLIENT_SECRET = os.environ.get("ML_CLIENT_SECRET", "")

URL_BUSCA = "https://api.mercadolibre.com/products/search"
URL_TOKEN = "https://api.mercadolibre.com/oauth/token"
NOME_ARQUIVO_TOKENS = "tokens_ml.json"

# Tokens em memoria (comecam com os valores do credenciais_locais.py e
# sao substituidos pelo conteudo de tokens_ml.json, se existir, na
# primeira busca).
_tokens = {
    "access_token": ML_ACCESS_TOKEN,
    "refresh_token": ML_REFRESH_TOKEN,
}
_tokens_carregados = False


class ErroMercadoLivre(RuntimeError):
    pass


def _caminho_arquivo_tokens():
    """No celular, salva em user_data_dir (unica pasta gravavel garantida
    pelo Android). Fora do app (testes no PC), salva na pasta do projeto."""
    if App is not None:
        app = App.get_running_app()
        if app is not None:
            return os.path.join(app.user_data_dir, NOME_ARQUIVO_TOKENS)
    return NOME_ARQUIVO_TOKENS


def _carregar_tokens():
    global _tokens_carregados
    if _tokens_carregados:
        return
    _tokens_carregados = True

    caminho = _caminho_arquivo_tokens()
    if not os.path.exists(caminho):
        return

    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except (ValueError, OSError):
        return

    if dados.get("access_token"):
        _tokens["access_token"] = dados["access_token"]
    if dados.get("refresh_token"):
        _tokens["refresh_token"] = dados["refresh_token"]


def _salvar_tokens(access_token, refresh_token):
    _tokens["access_token"] = access_token
    _tokens["refresh_token"] = refresh_token

    try:
        with open(_caminho_arquivo_tokens(), "w", encoding="utf-8") as arquivo:
            json.dump(
                {"access_token": access_token, "refresh_token": refresh_token},
                arquivo,
            )
    except OSError:
        pass


def _renovar_token():
    """Usa o refresh_token para pedir um access_token novo. Retorna True
    se conseguiu renovar (e ja salva os tokens novos)."""
    refresh_token = _tokens.get("refresh_token")
    if not refresh_token or not ML_CLIENT_ID or not ML_CLIENT_SECRET:
        return False

    payload = {
        "grant_type": "refresh_token",
        "client_id": ML_CLIENT_ID,
        "client_secret": ML_CLIENT_SECRET,
        "refresh_token": refresh_token,
    }

    try:
        resposta = requests.post(URL_TOKEN, data=payload, timeout=15)
    except requests.RequestException:
        return False

    if resposta.status_code != 200:
        return False

    dados = resposta.json()
    novo_access = dados.get("access_token")
    if not novo_access:
        return False

    # O Mercado Livre rotaciona o refresh_token a cada uso.
    novo_refresh = dados.get("refresh_token") or refresh_token
    _salvar_tokens(novo_access, novo_refresh)
    return True


def _requisicao_ml(url, parametros):
    """GET autenticado na API do ML. Se a resposta vier 401 (token
    expirado/invalido), tenta renovar o token uma vez e refaz a chamada."""
    _carregar_tokens()

    if not _tokens.get("access_token"):
        raise ErroMercadoLivre(
            "Token do Mercado Livre nao configurado. "
            "Defina ML_ACCESS_TOKEN em credenciais_locais.py."
        )

    for tentativa in range(2):
        cabecalhos = {"Authorization": f"Bearer {_tokens['access_token']}"}

        try:
            resposta = requests.get(
                url, params=parametros, headers=cabecalhos, timeout=15
            )
        except requests.RequestException as erro:
            raise ErroMercadoLivre(
                f"Falha de conexao com o Mercado Livre: {erro}"
            )

        if resposta.status_code == 401 and tentativa == 0:
            if _renovar_token():
                continue
            raise ErroMercadoLivre(
                "O token do Mercado Livre expirou e nao foi possivel "
                "renova-lo automaticamente. Gere um novo token."
            )

        if resposta.status_code != 200:
            raise ErroMercadoLivre(
                f"Erro do Mercado Livre (HTTP {resposta.status_code})."
            )

        return resposta.json()

    raise ErroMercadoLivre("Nao foi possivel concluir a busca no Mercado Livre.")


def _buscar_bruto(termo, limite):
    parametros = {
        "status": "active",
        "site_id": "MLB",
        "q": termo or "ofertas",
    }

    dados = _requisicao_ml(URL_BUSCA, parametros)
    resultados = dados.get("results") or []

    produtos = []
    for item in resultados[:limite]:
        preco = float(item.get("price") or 0)
        original = float(item.get("original_price") or 0)
        vendidos = int(item.get("sold_quantity") or 0)

        desconto = 0
        if original > 0 and preco > 0:
            desconto = round(((original - preco) / original) * 100, 1)

        nota = round(min(vendidos / 50, 60) + min(desconto, 40), 1)

        produtos.append({
            "titulo": str(item.get("title") or "Produto sem nome"),
            "preco": preco,
            "desconto": desconto,
            "vendas": vendidos,
            "nota": nota,
            "link": str(item.get("permalink") or ""),
        })

    return produtos


def buscar_produtos_ml(termo="ofertas", limite=15):
    """Retorna produtos do Mercado Livre com nota de oportunidade,
    no mesmo formato usado pela Visao Geral do Radar Afiliados."""
    produtos = _buscar_bruto(termo, limite)
    return [
        {
            "plataforma": "Mercado Livre",
            "nome": produto["titulo"],
            "preco": produto["preco"],
            "desconto": produto["desconto"],
            "vendas": produto["vendas"],
            "comissao_texto": "Não informado",
            "nota": produto["nota"],
            "link": produto["link"],
        }
        for produto in produtos
    ]
