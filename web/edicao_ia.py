"""
edicao_ia.py
------------
Fluxos de edicao de video com IA, pra aba "Edicao" do Radar Afiliados.

Usa o Gemini do MESMO jeito que campanhas_ia.py: chamada REST direta
(sem SDK), mesma chave GEMINI_API_KEY (credenciais_locais.py -> variavel
de ambiente) e o mesmo modelo. Cada funcao abaixo corresponde a um dos
6 fluxos de prompt que a Keiti curtiu do carrossel do @erickcastilio.ia,
adaptados pro contexto de video de produto afiliado.

Como encaixa no fluxo do app:

    buscar produto -> gerar video (Creatify) -> revisar/otimizar
    aqui (edicao_ia.py) -> aprovar -> postar

Uso tipico em app_web.py:

    from web.edicao_ia import rodar_fluxo

    resultado = rodar_fluxo(request.form["fluxo"], request.form["texto"])
"""

import time

import requests

# Mesmo padrao de credenciais dos outros modulos: primeiro o arquivo
# local (nunca vai pro Git), depois a variavel de ambiente.
try:
    from credenciais_locais import GEMINI_API_KEY
except ImportError:
    import os

    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Mesmo modelo usado em campanhas_ia.py (camada free do Google AI Studio).
MODELO = "gemini-3.6-flash"
URL_BASE = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODELO}:generateContent"
)


def _chamar_gemini(prompt: str) -> str:
    """Chama o Gemini via REST, igual ao campanhas_ia.py: trata 429
    (limite gratuito), tenta de novo em 500/503 (alta demanda) e
    levanta RuntimeError com mensagem amigavel em qualquer outra falha."""

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "Chave da API do Gemini nao configurada. "
            "Adicione GEMINI_API_KEY em credenciais_locais.py "
            "(ou no Environment do Render)."
        )

    corpo = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            # O gemini-3.x "pensa" antes de responder e esses tokens
            # contam no limite; deixamos folga para nao cortar o texto.
            "maxOutputTokens": 4096,
        },
    }

    ultimo_erro = ""
    for tentativa in range(3):
        try:
            resposta = requests.post(
                f"{URL_BASE}?key={GEMINI_API_KEY}", json=corpo, timeout=40
            )
        except requests.RequestException as erro:
            raise RuntimeError(f"Erro de conexao com o Gemini: {erro}")

        if resposta.status_code == 429:
            raise RuntimeError(
                "Limite gratuito do Gemini atingido no momento. "
                "Aguarde um pouco e tente novamente."
            )
        if resposta.status_code in (500, 503):
            ultimo_erro = f"HTTP {resposta.status_code}"
            time.sleep(2 * (tentativa + 1))
            continue
        if resposta.status_code != 200:
            raise RuntimeError(
                f"Erro do Gemini (HTTP {resposta.status_code}): "
                f"{resposta.text[:200]}"
            )

        dados = resposta.json()
        try:
            partes = dados["candidates"][0]["content"]["parts"]
            texto = "".join(p.get("text", "") for p in partes)
        except (KeyError, IndexError):
            motivo = (
                dados.get("candidates", [{}])[0].get("finishReason")
                if dados.get("candidates")
                else dados.get("promptFeedback", {}).get("blockReason")
            )
            raise RuntimeError(
                f"O Gemini nao retornou texto (motivo: {motivo or 'desconhecido'})."
            )

        if texto.strip():
            return texto.strip()
        ultimo_erro = "resposta vazia"
        time.sleep(1)

    raise RuntimeError(
        f"O Gemini nao respondeu depois de varias tentativas ({ultimo_erro})."
    )


# 1. Blueprint de Edicao ------------------------------------------------

def blueprint_edicao(descricao_material_bruto: str) -> str:
    """
    A IA age como editor senior e transforma a descricao do material
    bruto num roteiro de edicao cronologico, em formato de tabela:
    Timestamp | Acao/Corte | B-roll/Visuais | Audio/SFX | Notas
    """
    prompt = f"""
Voce e um editor de video senior especializado em conteudo curto
para Instagram Reels de produtos afiliados (Mercado Livre, Amazon,
Shopee).

Material bruto disponivel:
{descricao_material_bruto}

Gere um roteiro de edicao cronologico em formato de TABELA markdown,
com as colunas: Timestamp | Acao/Corte | B-roll/Visuais | Audio/SFX | Notas.

O objetivo e um video de ate 30 segundos, com gancho forte nos
primeiros 3 segundos e CTA claro no final (link na bio / comentarios).
"""
    return _chamar_gemini(prompt)


# 2. Engenharia Reversa de Estilo ---------------------------------------

def engenharia_reversa_estilo(descricao_video_referencia: str) -> str:
    """
    A IA analisa a descricao de um video de referencia (que a usuaria
    viu e gostou) e gera um passo a passo para recriar o mesmo estilo
    (ritmo, transicoes, cor, som) no video proprio.
    """
    prompt = f"""
Voce e um especialista em analise de estilo de edicao de video para
redes sociais.

Descricao do video de referencia (estilo que a usuaria quer imitar):
{descricao_video_referencia}

Faca uma engenharia reversa do estilo desse video e entregue um
passo a passo pratico para recriar o MESMO estilo (ritmo de cortes,
tipo de transicoes, paleta de cores/grading, uso de musica/SFX,
tipografia de legenda) aplicado a um video de divulgacao de produto
afiliado. Seja especifico e acionavel, nao generico.
"""
    return _chamar_gemini(prompt)


# 3. Otimizacao do Fluxo do Roteiro --------------------------------------

def otimizar_fluxo_roteiro(roteiro_atual: str) -> str:
    """
    A IA revisa um roteiro existente, identifica pontos fracos de
    ritmo/energia, reescreve o gancho dos primeiros 10s e sugere
    tecnicas de edicao (jump cuts, zooms, legendas, SFX, pattern
    interrupts).
    """
    prompt = f"""
Voce e um estrategista de conteudo de video curto (Reels/TikTok/Shorts).

Roteiro atual:
{roteiro_atual}

1. Identifique os pontos fracos de ritmo/energia do roteiro.
2. Reescreva o gancho (hook) dos primeiros 10 segundos pra ser mais
   forte e prender a atencao imediatamente.
3. Sugira tecnicas de edicao especificas para cada trecho fraco
   (jump cuts, zooms, legendas dinamicas, SFX, pattern interrupts).

Formate a resposta em topicos claros.
"""
    return _chamar_gemini(prompt)


# 4. Triagem de Material Bruto -------------------------------------------

def triagem_material_bruto(descricao_material_bruto: str) -> str:
    """
    A IA separa o material bruto em Ouro (manter), Cortes (remover)
    e Polimento (melhorar com B-roll/legenda/som), com timestamps.
    """
    prompt = f"""
Voce e um editor de video que faz a triagem inicial de material bruto
antes de montar o corte final.

Material bruto disponivel (com timestamps, se houver):
{descricao_material_bruto}

Separe o material em 3 categorias, cada uma com os timestamps
correspondentes:

- OURO (manter como esta, e o melhor material)
- CORTES (remover, nao agrega ou tem problema)
- POLIMENTO (tem potencial mas precisa de B-roll, legenda ou som pra
  melhorar — explique o que adicionar em cada caso)
"""
    return _chamar_gemini(prompt)


# 5. Revisao Final de Polimento ------------------------------------------

def revisao_final_polimento(descricao_video_quase_pronto: str) -> str:
    """
    A IA avalia o video quase pronto como um espectador de primeira
    viagem, da nota de 0 a 10 em varios criterios e aponta as 3
    melhorias de maior impacto.
    """
    prompt = f"""
Voce e um espectador vendo este video pela primeira vez, sem contexto
nenhum. Avalie o video descrito abaixo como se fosse rolar o feed do
Instagram e se deparar com ele.

Descricao do video quase pronto:
{descricao_video_quase_pronto}

De uma nota de 0 a 10 para cada criterio:
- Ritmo
- Audio
- Clareza visual
- Cor
- Narrativa/mensagem

Depois, aponte as 3 melhorias de MAIOR IMPACTO que fariam esse video
performar melhor, em ordem de prioridade.
"""
    return _chamar_gemini(prompt)


# 6. Auditoria de Retencao -----------------------------------------------

def auditoria_retencao(descricao_video_com_timestamps: str) -> str:
    """
    A IA identifica pontos onde a audiencia provavelmente perde
    interesse (com timestamp), sugere correcoes e cria 3 ganchos
    alternativos para os primeiros 10 segundos.
    """
    prompt = f"""
Voce e um especialista em retencao de audiencia em video curto
(Reels/TikTok/Shorts), com foco em produtos afiliados.

Descricao do video, com timestamps:
{descricao_video_com_timestamps}

1. Identifique os pontos exatos (com timestamp) onde a audiencia
   provavelmente perde interesse e explique o motivo.
2. Sugira a correcao especifica para cada ponto.
3. Crie 3 ganchos (hooks) ALTERNATIVOS para os primeiros 10 segundos,
   cada um com uma abordagem diferente (ex: pergunta, choque/curiosidade,
   promessa direta).
"""
    return _chamar_gemini(prompt)


# Dispatcher --------------------------------------------------------------

FLUXOS = {
    "blueprint": blueprint_edicao,
    "engenharia_reversa": engenharia_reversa_estilo,
    "otimizar_roteiro": otimizar_fluxo_roteiro,
    "triagem": triagem_material_bruto,
    "revisao_final": revisao_final_polimento,
    "auditoria_retencao": auditoria_retencao,
}

# Rotulos amigaveis pro seletor da tela (mesma ordem do carrossel).
FLUXOS_ROTULOS = [
    ("blueprint", "1. Blueprint de edicao (roteiro cronologico em tabela)"),
    ("engenharia_reversa", "2. Engenharia reversa de estilo (copiar um video de referencia)"),
    ("otimizar_roteiro", "3. Otimizar o fluxo do roteiro (gancho + ritmo)"),
    ("triagem", "4. Triagem de material bruto (ouro / cortes / polimento)"),
    ("revisao_final", "5. Revisao final de polimento (notas + 3 melhorias)"),
    ("auditoria_retencao", "6. Auditoria de retencao (onde a audiencia cai)"),
]


def rodar_fluxo(nome_fluxo: str, texto_entrada: str) -> str:
    """
    Funcao unica pra chamar da rota do Flask, ex:
        resultado = rodar_fluxo(request.form["fluxo"], request.form["texto"])
    """
    funcao = FLUXOS.get(nome_fluxo)
    if not funcao:
        raise ValueError(
            f"Fluxo '{nome_fluxo}' nao existe. Opcoes: {list(FLUXOS.keys())}"
        )
    return funcao(texto_entrada)


if __name__ == "__main__":
    # Teste rapido pelo terminal:
    #   python edicao_ia.py blueprint "descricao do material aqui"
    import sys

    if len(sys.argv) < 3:
        print("Uso: python edicao_ia.py <fluxo> <texto>")
        print(f"Fluxos disponiveis: {list(FLUXOS.keys())}")
        sys.exit(1)

    fluxo, texto = sys.argv[1], sys.argv[2]
    print(rodar_fluxo(fluxo, texto))
