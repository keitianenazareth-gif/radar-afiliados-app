# Tarefa agendada: ofertas do Mercado Livre para a fila do WhatsApp

Roda no notebook da Keiti (app do Claude aberto + Chrome logado no Mercado
Livre, extensão Claude in Chrome conectada). Coloca de 3 a 5 ofertas do
Mercado Livre na fila da página /whatsapp; os lotes do robô mandam no grupo.

Pasta do projeto: `C:\Users\keiti\Desktop\radar-afiliados-projeto`

## Passo a passo

1. **Ler as ofertas.** No Chrome, abrir
   `https://www.mercadolivre.com.br/afiliados/hub` (filtro padrão, "Mais
   vendidos" também serve) e rodar, com a ferramenta de javascript, o conteúdo
   de `tarefa_ml\extrair_ofertas.js`. Ele devolve uma lista com nome,
   produto_url, imagem, preco, preco_condicao/condicao, preco_antigo, ganho,
   ganho_extra, nota e vendas. Se a lista vier vazia ou pedir login, PARAR e
   avisar a Keiti (não tentar fazer login).

2. **Escolher de 3 a 5**, nesta ordem de preferência:
   - comissão: `ganho_extra` primeiro, depois `ganho` >= 12%;
   - desconto real de pelo menos 30% (`preco_antigo` x `preco`);
   - nota >= 4,5 e muitas vendas;
   - preço até R$ 300 (o grupo compra mais coisa barata);
   - variar categorias (não mandar 3 creatinas);
   - EVITAR: games/consoles, gift cards, celulares/iPhone, eletrodoméstico
     caro, produto adulto, armas, remédio, cigarro/vape.

3. **Gerar os links oficiais.** Abrir
   `https://www.mercadolivre.com.br/afiliados/linkbuilder`, colar os
   `produto_url` escolhidos no campo de URLs (um por linha: Shift+Enter
   entre eles), conferir que a etiqueta é `souzakeitiane20230813160040` e
   clicar em **Gerar**. Ler os links com javascript:
   `[...document.querySelectorAll('textarea')].map(t => t.value)` — o
   segundo item tem os `https://meli.la/...` na MESMA ordem das URLs.
   Se aparecer CAPTCHA, PARAR e avisar a Keiti (não resolver CAPTCHA).

4. **Montar o arquivo** `tarefa_ml\ofertas_ml.json` (fica fora do git):

   ```json
   [
     {"link": "https://meli.la/...", "nome": "nome curto, até ~10 palavras",
      "preco": "R$ 68,90", "preco_antigo": "R$ 239,90",
      "imagem": "https://http2.mlstatic.com/...webp",
      "observacao": "💳 R$ 48,90 com crédito disponível\n⭐ 4,9 | 🛒 +750 mil vendidos"}
   ]
   ```

   - `preco` é o preço que vale para todo mundo; quando `condicao` vier
     preenchida, ponha o `preco_condicao` na observação ("💸 ... no Pix" ou
     "💳 ... com crédito disponível").
   - Não inventar nada: nome, preços e foto vêm só do passo 1.

5. **Conferir e mandar para a fila:**

   ```
   .\.venv312\Scripts\python.exe fila_ml.py tarefa_ml\ofertas_ml.json --teste
   .\.venv312\Scripts\python.exe fila_ml.py tarefa_ml\ofertas_ml.json
   ```

   O primeiro só mostra as mensagens; o segundo coloca na fila (o site
   recusa sozinho produto repetido ou com palavra bloqueada).

6. **Resumo final** curto: quais entraram na fila, quais foram pulados e por quê.

## Regras

- Nunca digitar senha, resolver CAPTCHA ou mexer em configurações da conta.
- Nunca enviar mensagem direto no WhatsApp: só colocar na fila.
- Fechar as abas que abriu ao terminar.
