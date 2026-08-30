# CLAUDE.md — Radar Afiliados

Contexto do projeto para o Claude. Fale sempre em **português (Brasil)**.
Preferências gerais sobre mim e meu jeito de trabalhar estão em `C:\Users\keiti\.claude\CLAUDE.md`.
Resumo do essencial: sou **analista administrativa, não programadora** — explique o plano
antes de implementar, trabalhe em passos pequenos, diagnostique a causa antes de consertar,
e me dê comandos prontos para Windows/PowerShell.

## O que é o projeto

App para pesquisar produtos de programas de afiliados e gerar material de divulgação:

- **Plataformas de busca:** Shopee, Mercado Livre, Amazon, Shein, Temu.
- **Biblioteca:** coleção de mídias (imagens/vídeos), com importação da galeria do celular
  e recebimento via "Compartilhar" do Android.
- **Campanha com IA:** roteiro gerado pelo **Gemini** (`campanhas_ia.py`), narração em áudio
  via **TTS** (`web/tts.py`, `edge-tts`) e **vídeo curto** de 15–30s montado a partir das
  fotos do produto (`web/video_campanha.py`, `moviepy`).
- **Envio para WhatsApp** (normal ou Business) a partir do app Android.

## Duas frentes, mesmo código

### 1. App Android (Kivy)
- Interface: `main.py` + `tela_*.py` + `ui_comum.py`.
- APK gerado **de graça pelo GitHub Actions** — workflow `.github/workflows/build-apk.yml`
  ("Gerar APK - Radar Afiliados"). Dispara no push para `main` ou manualmente
  (Actions → Run workflow). Leva ~10–20 min. Baixar em: run concluída → **Artifacts** →
  `radar-afiliados-apk`.
- O workflow monta o `credenciais_locais.py` na hora da compilação a partir dos **Secrets**
  do repositório. Config de build: `buildozer.spec` (arm64-v8a, android.api 34, minapi 21).

### 2. Versão web (Flask)
- Pasta `web/` — `web/app_web.py` (rotas), templates em `web/templates/`, estáticos em
  `web/static/`. Vídeos gerados vão para `web/static/videos/` (ignorado pelo Git).
- Rodar local:
  ```
  pip install -r web/requirements.txt
  python web/app_web.py
  ```
  Abre em `http://localhost:5000`. Precisa do `credenciais_locais.py` preenchido na raiz.
- Hospedada no **Render** (`render.yaml`, blueprint) → `https://radar-afiliados-web.onrender.com`.
  - Start: `gunicorn web.app_web:app --workers 1 --threads 4 --timeout 300 --bind 0.0.0.0:$PORT`
  - Health check: `/healthz`. Plano **free** (vídeo pode dar OOM; subir para "standard" ou
    reduzir `VIDEO_LARGURA`/`VIDEO_ALTURA` se apertar).
  - Credenciais vão na aba **Environment** do serviço no painel do Render, nunca no Git.
- Login básico da web: `WEB_USUARIO` / `WEB_SENHA` (senha vazia = acesso livre). Precisa
  responder com header `WWW-Authenticate` para o navegador abrir a caixa de login.
- Compartilhar a versão local para revisão externa: **ngrok** apontando para a porta 5000.

## Ambiente Python

- **Python 3.12** (`.python-version` = 3.12.10). Python 3.14 **não** funciona com Kivy.
- Venv local: `.venv312\`. Rodar o app: `.\.venv312\Scripts\python.exe main.py`
  (ou o atalho `Executar App.bat`).

## Credenciais — regras

- Valores reais ficam **só** em `credenciais_locais.py` (raiz, no `.gitignore`),
  em `tokens_ml.json`, nos **Secrets do GitHub** e no **Environment do Render**.
- `credenciais_locais.py.exemplo` é **modelo** — nunca preencher com valores reais.
- Chaves usadas: `SHOPEE_APP_ID`, `SHOPEE_SECRET`, `GEMINI_API_KEY`,
  `ML_ACCESS_TOKEN`, `ML_REFRESH_TOKEN`, `ML_CLIENT_ID`, `ML_CLIENT_SECRET`.
- **Mercado Livre (OAuth):** o `access_token` expira; o app renova sozinho usando o
  `refresh_token` + `ML_CLIENT_ID`/`ML_CLIENT_SECRET` e salva os novos tokens em
  `tokens_ml.json` para persistir entre usos. Gerar token inicial: `gerar_token_ml.py`
  (usa o `code` do fluxo OAuth com `redirect_uri` do ngrok).
- Se eu colar uma chave real no chat: me avise, guarde no arquivo certo, e nunca commite.
  Se já vazou publicamente, me diga para revogar e gerar outra.
- Atualizar secret do repo: `gh secret set NOME_DO_SECRET`.

## Git

- Repositório: `github.com/keitianenazareth-gif/radar-afiliados-app` (remote `origin`, branch `main`).
- Push para `main` dispara o build do APK — considere isso antes de subir mudança quebrada.
- Quando eu pedir para subir: rode `add`/`commit`/`push` e me confirme o **hash** e que
  chegou no `origin/main`.

## Convenções de UI (Kivy)

- Todo `height`, `font_size`, `spacing` e `padding` usa `dp()` / `sp()` de `kivy.metrics`
  (`from kivy.metrics import dp, sp`) — para adaptar ao tamanho da tela do celular.
- Permissões de mídia dependem da versão do Android — ver
  `android_integracao.PermissoesMidia`.

## Mapa de arquivos

| Arquivo | Função |
|---|---|
| `main.py` | Entrada do app Kivy, registro das telas |
| `tela_principal.py` | Tela inicial com os botões de cada plataforma |
| `tela_shopee.py` / `tela_geral.py` / `tela_manual.py` | Telas de resultados e produto manual |
| `tela_biblioteca.py` / `biblioteca.py` | Biblioteca de mídias |
| `shopee.py` / `mercado_livre.py` | Integrações com as APIs |
| `campanhas_ia.py` | Geração de roteiro/campanha com Gemini |
| `android_integracao.py` | Permissões, compartilhamento, envio ao WhatsApp |
| `ui_comum.py` | Componentes de interface reaproveitados |
| `web/app_web.py` | Servidor Flask da versão web |
| `web/video_campanha.py` / `web/tts.py` | Geração de vídeo e narração |
| `buildozer.spec` / `.github/workflows/build-apk.yml` | Build do APK |
| `render.yaml` | Deploy da versão web no Render |
