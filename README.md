# Radar Afiliados - App

## Como gerar o APK (grátis, via GitHub Actions)

1. Crie um repositório no GitHub (pode ser privado) e suba todos esses arquivos.
2. Vá na aba **Actions** do repositório.
3. Clique no workflow **"Gerar APK - Radar Afiliados"** → **"Run workflow"**.
4. Aguarde de 10 a 20 minutos (a primeira vez demora mais).
5. Quando terminar, abra a execução (run) concluída → role até **Artifacts**
   → baixe **radar-afiliados-apk.zip** → descompacte → o `.apk` está lá dentro.
6. Transfira o `.apk` pro celular (ou baixe direto pelo navegador do celular)
   e instale (é preciso permitir "instalar apps de fontes desconhecidas").

## Credenciais

Cadastre no repositório (`Settings` → `Secrets and variables` → `Actions`
→ `New repository secret`) estes secrets:

- `SHOPEE_APP_ID`
- `SHOPEE_SECRET`
- `ML_ACCESS_TOKEN` (opcional — deixe em branco se ainda não tiver)
- `ML_REFRESH_TOKEN` (opcional — necessário para o app renovar sozinho o
  token do Mercado Livre quando expirar)
- `ML_CLIENT_ID` e `ML_CLIENT_SECRET` (opcionais — também necessários
  para a renovação automática do token do Mercado Livre)
- `GEMINI_API_KEY` (grátis em aistudio.google.com/apikey — necessária para o botão "Criar campanha com IA")

O workflow cria automaticamente um arquivo `credenciais_locais.py`
com esses valores só durante a compilação, e ele nunca é salvo no
Git — fica só dentro do APK final, no seu celular.

**Nunca** edite `credenciais_locais.py.exemplo` com valores reais e
suba pro GitHub — ele é só um modelo.
