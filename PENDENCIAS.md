# Pendências do Radar Afiliados (atualizado em 03/11/2026)

Lista do que falta fazer no notebook, em ordem. Mesma lista do projeto "radar"
no claude.ai (doc `claude/whatsapp-robo-status.md`). Ao concluir um item,
marque aqui com [x] e faça commit.

## Situação atual
- Robô do WhatsApp (`robo_whatsapp.py`): horários 9, 12, 14, 16, 19 e 21h.
  Commit 500f8ba (02/11): não repete produto parecido (código, foto e nome) e,
  se o GitHub atrasar, manda o lote do último horário até 3h depois.
- Servidor Evolution API no Railway (projeto "sublime-spirit"), instância `promocoes`.
  O chip agora está no WhatsApp Business: conferir em "Aparelhos conectados" se o
  servidor continua conectado; se não, parear de novo.
- Página de controle: https://radar-afiliados-web.onrender.com/whatsapp
  ("Enviar agora" roda no Render, que já tem as chaves do WhatsApp).
- Instagram: @clube.doquero ("Achadinhos e Promoções | Cupons"), link do grupo na bio.

## Fazer no notebook
- [ ] 1. Secrets do GitHub (Settings > Secrets and variables > Actions): WHATSAPP_API_URL
      (domínio do Railway), WHATSAPP_API_KEY (AUTHENTICATION_API_KEY do Railway; nunca
      colar no chat) e WHATSAPP_INSTANCIA = promocoes. Sem isso o robô agendado não envia
      (logs de 02/11: faltam essas 3 chaves).
- [ ] 2. Rodar o robô no Railway com agendamento pontual (o cron do GitHub atrasa de 3 a 7h).
- [ ] 3. Mensagens mais chamativas (prompt abaixo).
- [ ] 4. Mensagem diária "compartilhe o grupo" no último lote (21h), com o link de convite,
      texto variando; ligar/desligar e editar na página /whatsapp. Exemplos:
      "💸 Gostou das ofertas de hoje? Manda o link pra aquela amiga que ama uma promoção: <link>"
      "🛍️ Quanto mais gente no grupo, mais cupons exclusivos a gente consegue! Compartilha: <link>"
      "👯 Sabe quem também ia amar esses achadinhos? Chama ela: <link>"
- [ ] 5. Verificar o dispositivo no app do Claude (para usar o navegador do app).
- [ ] 6. Tarefa agendada pelo navegador para Mercado Livre, Amazon (SiteStripe) e Shein:
      escolher ofertas, gerar link de afiliada e colocar na fila. Amazon sem preço na mensagem.
      - [x] Mercado Livre (03/11): tarefa "Ofertas do Mercado Livre para o grupo" no app do
        Claude, 8h e 13h. Passo a passo em `tarefa_ml/INSTRUCOES.md`; `fila_ml.py` põe na fila.
        Precisa do notebook ligado, app do Claude aberto e Chrome logado no ML.
      - [ ] Amazon e Shein.
- [ ] 7. Fila aceitar só o link do ML (o robô busca nome, preço e foto sozinho).
- [ ] 8. Escutar os grupos de promoção em que o chip entrou: links de produto (Shopee vira
      link da Keiti pela API; ML/Amazon/Shein vão para a fila) e cupons (Gemini identifica).
- [ ] 9. Cupons automáticos da Shopee (campanhas da API de afiliados).
      - [x] Mercado Livre (03/11): a tarefa das 8h lê a página Cupons (`tarefa_ml/extrair_cupons.js`)
        e cadastra 1 ou 2 cupons gerais, com link de afiliada de um produto onde o cupom vale.
        O ML não gera link de afiliada da página de cupons nem tem código: a pessoa ativa no app.
- [ ] 10. Robô do Instagram para ganhar seguidores (começar consertando `robo-automatico.yml`,
       que falha desde 14/10): postar nos melhores horários, relatório semanal, temas do
       momento, hashtags, responder comentários/DMs, funil "comenta QUERO" (DM só para quem
       falou primeiro, em até 24h), sugerir collabs. NÃO: seguir/deixar de seguir em massa,
       comentar em perfis alheios, DM para quem nunca falou com a conta.
- [ ] 11. Resumo diário para o Canal de transmissão do Instagram: a API não posta no canal,
       então o robô monta a mensagem (3 melhores ofertas, 1 cupom, convite do grupo) e manda
       para a Keiti colar.

## Decisões
- Não mandar mensagem individual para participantes de outros grupos (nem pelo chip nem
  pelo número pessoal): risco de banimento e LGPD. Crescer por convite de quem já está no
  grupo, Instagram, parcerias com admins e lista de transmissão do número pessoal.
- Ação "Traga suas amigas": premiar quem trouxer mais amigas em 15 dias (sem sorteio,
  que em geral precisa de autorização do governo).

## Prompt do item 3 (mensagens mais chamativas)
No `robo_whatsapp.py`, melhorar `mensagem_shopee`, `mensagem_fila` e `mensagem_cupom`:
1. Gancho no topo sorteado de uma lista editável ("😱 PREÇO DE ERRO?", "⚡ CORRE QUE ACABA",
   "🏆 O MAIS VENDIDO DA SEMANA", "💸 ACHADINHO BARATO", "🔥 OFERTA DO DIA"), escolhido
   pelo produto quando fizer sentido; sem repetir seguido no mesmo lote.
2. Nome curto (até ~8 palavras) reescrito pelo Gemini, sem inventar; se falhar, usa o atual.
3. Preço com desconto: "~R$ 89,90~ por *R$ 49,90* (44% OFF)"; na Shopee, só com percentual,
   manter "A partir de *R$ X* · até Y% OFF".
4. Prova social abaixo do preço: "⭐ 4,9 · 🛒 +10 mil vendidos".
5. Chamada antes do link: "Garanta o seu 👇" (variar).
6. Cupom: "🎟️ CUPOM LIBERADO!" / *descrição* na Loja / Código: *CODIGO* / ⏰ Só até DD/MM /
   Ativar cupom 👇 / link.
7. Amazon sem preço (regra do programa de associados).
8. Manter o RODAPE e o link de afiliado exatamente como estão.
Mostrar 3 exemplos de cada tipo no modo teste antes do commit.
