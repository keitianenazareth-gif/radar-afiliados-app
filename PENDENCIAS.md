# Pendências do Radar Afiliados (atualizado em 03/11/2026)

Lista do que falta fazer no notebook, em ordem. Mesma lista do projeto "radar"
no claude.ai (doc `claude/whatsapp-robo-status.md`). Ao concluir um item,
marque aqui com [x] e faça commit.

## Situação atual
- Robô do WhatsApp (`robo_whatsapp.py`): desde 04/11, 1 oferta a cada 10 min nas faixas 11h30-13h30
  e 19h-21h: 5 Mercado Livre, 5 Shopee e 2 Amazon por faixa (24 por dia, editável em /whatsapp).
  Testar por 1 semana: olhar avisos do WhatsApp e gente saindo do grupo.
  Links da Shopee levam subId da hora (ex.: `h20`): em 2-3 semanas, ver no relatório da
  Shopee quais horários vendem mais e ajustar.
  Commit 500f8ba (02/11): não repete produto parecido (código, foto e nome) e,
  se o GitHub atrasar, manda o lote do último horário até 3h depois.
- Servidor Evolution API no Railway (projeto "sublime-spirit"), instância `promocoes`.
  O chip agora está no WhatsApp Business: conferir em "Aparelhos conectados" se o
  servidor continua conectado; se não, parear de novo.
- Página de controle: https://radar-afiliados-web.onrender.com/whatsapp
  ("Enviar agora" roda no Render, que já tem as chaves do WhatsApp).
- Instagram: @clube.doquero ("Achadinhos e Promoções | Cupons"), link do grupo na bio.

- Marca d'agua @clube.doquero (marca_dagua.py): fotos do robo do WhatsApp (canto
  inferior direito) e videos/Reels gerados por web/video_campanha.py (no alto, a esquerda,
  fora dos botoes do Reels). DESLIGADA por enquanto (decisao da Keiti em 03/11);
  para ligar, MARCA_DAGUA=1 nos Secrets do GitHub e no Environment do Render.
  MARCA_DAGUA_TEXTO troca o texto. Opcao vista: so o @ sem a faixa escura.

## Fazer no notebook
- [x] 1. Secrets do GitHub (03/11): WHATSAPP_API_URL, WHATSAPP_API_KEY e WHATSAPP_INSTANCIA
      cadastrados. O teste listar_grupos deu `rate-overlimit` do WhatsApp; repetir só com folga.
- [x] 2. Robô no Railway (03/11): serviço radar-afiliados-app no projeto sublime-spirit, de hora
      em hora no minuto 2 (cron definido na tela, em Settings). O lote das 20h saiu às 20:06.
      O agendamento do GitHub foi desligado; lá só roda manualmente. Conferir o custo real.
- [x] 3. Mensagens mais chamativas (03/11, commit be0af4d). Ganchos e chamadas editáveis nos
      Ajustes; "PREÇO DE ERRO?" virou "BAIXOU DEMAIS!" a pedido da Keiti. O nome curto por IA
      está ligado, mas a chave do Gemini responde HTTP 402 (pede pagamento): enquanto isso vale
      o encurtamento simples. Conferir o plano da chave no Google AI Studio.
- [ ] 4. Mensagem diária "compartilhe o grupo" no último lote (21h), com o link de convite,
      texto variando; ligar/desligar e editar na página /whatsapp. Exemplos:
      "💸 Gostou das ofertas de hoje? Manda o link pra aquela amiga que ama uma promoção: <link>"
      "🛍️ Quanto mais gente no grupo, mais cupons exclusivos a gente consegue! Compartilha: <link>"
      "👯 Sabe quem também ia amar esses achadinhos? Chama ela: <link>"
- [ ] 5. Verificar o dispositivo no app do Claude (para usar o navegador do app).
- [ ] 6. Tarefa agendada pelo navegador para Mercado Livre, Amazon (SiteStripe) e Shein:
      escolher ofertas, gerar link de afiliada e colocar na fila. Amazon sem preço na mensagem.
      - [x] Mercado Livre (03/11): tarefa "Ofertas do Mercado Livre e Amazon para o grupo" no
        app do Claude, 8h, 14h e 19h. Passo a passo em `tarefa_ml/INSTRUCOES.md`; `fila_ml.py`
        põe na fila. Precisa do notebook ligado, app do Claude aberto e Chrome logado no ML.
      - [x] Amazon (03/11): mesma tarefa, página de ofertas sem login, tag `2410890e-20` nos
        Ajustes; mensagem sem preço e sem foto (regra do programa de associados).
      - [x] Leitores corrigidos (04/11): Amazon lê a página de Black Friday (nome vem da foto);
        ML reconhece "ou R$ X em 8x" e calcula o desconto real. Testados nas páginas reais.
      - [x] Nova seleção do ML (04/11, pedido da Keiti): 2-3 de comissão maior (filtro Ganhos
        extras) + 1-2 do Ofertaço (/ofertas; comissão lida na página do produto). Regras em
        `tarefa_ml/INSTRUCOES.md`. Leitura testada; conferir a primeira execução completa.
      - [x] Oferta não vence na fila (04/11): 4 ofertas por execução (3 ML + 1 Amazon), 2 da fila
        por lote, validade de 6h (Oferta do dia até 12h e sai primeiro); vencida é descartada.
        Conferir o preço na hora do envio ficou de fora: o ML respondeu 403 à página e 401 à API
        sem login. Se quiser retomar, avaliar a API oficial com token.
      - [ ] Shein: a Keiti precisa entrar na conta da Shein no Chrome do notebook; depois
        explorar o painel br.shein.com/affiliate (gerador de links e cupons).
      - [ ] No notebook: abrir a tarefa em Scheduled e clicar "Run now" uma vez para aprovar
        Chrome e PowerShell (senão a execução automática pode parar pedindo permissão).
- [ ] 7. Fila aceitar só o link do ML (o robô busca nome, preço e foto sozinho).
- [ ] 8. Escutar os grupos de promoção em que o chip entrou: links de produto (Shopee vira
      link da Keiti pela API; ML/Amazon/Shein vão para a fila) e cupons (Gemini identifica).
- [ ] 9. Cupons automáticos da Shopee (campanhas da API de afiliados).
      - [x] Mercado Livre (03/11): a tarefa das 8h lê a página Cupons (`tarefa_ml/extrair_cupons.js`)
        e cadastra 1 ou 2 cupons gerais, com link de afiliada de um produto onde o cupom vale.
        O ML não gera link de afiliada da página de cupons nem tem código: a pessoa ativa no app.
- [ ] 10. Robô do Instagram para ganhar seguidores. Situação em 03/11: o agendamento de
       `robo-automatico.yml` foi desligado (só roda manual). Fotos animadas e cenas de IA foram
       reprovadas pela Keiti; o fluxo novo é ela gravar o vídeo, subir na Galeria (/galeria, até
       100MB) e publicar com a legenda aprovada. Token corrigido (endereço graph.instagram.com) e
       conferido em /api/instagram/status; falta testar uma publicação real e renovar o token
       antes de expirar. Voz aprovada: pt-BR-FranciscaNeural. Depois: melhores horários, relatório semanal, temas do
       momento, hashtags, responder comentários/DMs, funil "comenta QUERO" (DM só para quem
       falou primeiro, em até 24h), sugerir collabs. NÃO: seguir/deixar de seguir em massa,
       comentar em perfis alheios, DM para quem nunca falou com a conta.
- [ ] 11. Resumo diário para o Canal de transmissão do Instagram: a API não posta no canal,
       então o robô monta a mensagem (3 melhores ofertas, 1 cupom, convite do grupo) e manda
       para a Keiti colar.

- [ ] 12. Testar o OpenMontage (github.com/calesthio/OpenMontage): sistema de producao de
       video com agentes para o Claude Code. Ver se melhora os videos de campanha e quanto custa
       (alguns pipelines podem usar servicos pagos). Testar so no notebook, sem mexer no robo.
- [ ] 13. Testar o VoiceStudio (github.com/debpalash/voicestudio): narracao/clonagem de voz
       gratuita e local, alternativa ao ElevenLabs. Conferir se tem portugues do Brasil e se o
       notebook aguenta (costuma precisar de placa de video). Nao roda no Render gratuito.
       Comparar com a voz atual (Gemini TTS / edge-tts em web/tts.py).
       Antes de instalar qualquer projeto de terceiros: conferir estrelas, data da ultima
       atualizacao e licenca.

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
