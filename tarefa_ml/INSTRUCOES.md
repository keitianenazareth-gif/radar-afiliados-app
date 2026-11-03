# Tarefa agendada: ofertas do Mercado Livre para a fila do WhatsApp

Roda no notebook da Keiti (app do Claude aberto + Chrome logado no Mercado
Livre, extensão Claude in Chrome conectada). Coloca de 3 a 5 ofertas do
Mercado Livre e 1 ou 2 da Amazon na fila da página /whatsapp e, de manhã,
1 ou 2 cupons do ML na lista de cupons; os lotes do robô mandam no grupo.

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

   **Cupons (só na execução da manhã, antes das 12h):**
   - Abrir `https://www.mercadolivre.com.br/cupons` e rodar
     `tarefa_ml\extrair_cupons.js`. NÃO clicar em "Aplicar" nem em nada da
     página (isso mexe na conta da Keiti).
   - Escolher **1 ou 2** cupons: `tipo` = `EU_QUERO` e `onde` = "Em produtos
     selecionados" (valem para todo mundo); compra mínima até R$ 100;
     validade de pelo menos 2 dias (ou aviso "Está esgotando!", que dá
     urgência); preferir casa, mercado, beleza, moda e limpeza; evitar
     maquininhas, peças de carro e cupons de uma loja só (`AUTOMATIC`).
   - Para cada cupom, pegar o 1º nome de `exemplos`, abrir
     `https://lista.mercadolivre.com.br/<nome-com-hifens>` e copiar o link do
     produto com o mesmo nome (`/p/MLB...`, `/up/MLBU...` ou
     `produto.mercadolivre.com.br/MLB-...`). Esse produto entra no MESMO
     Gerador de links do passo 3 (junto com as ofertas, na ordem).
   - No arquivo, o cupom vai assim (o site recusa cupom repetido e cada um
     sai uma vez só):

   ```json
   {"tipo": "cupom", "descricao": "40% OFF em Veja",
    "detalhes": "Compra mínima R$ 20 · desconto até R$ 30 · ⚠️ Está esgotando!",
    "validade": "2026-11-11", "link": "https://meli.la/..."}
   ```

   (`⚠️ Está esgotando!` só quando o `aviso` disser isso; `validade` vem
   pronta do extrair_cupons.js.)

   **Amazon (1 ou 2 por execução):**
   - Abrir `https://www.amazon.com.br/deals` (não precisa de login) e rodar
     `tarefa_ml\extrair_ofertas_amazon.js` (ele rola a página sozinho).
   - Escolher pelo `desconto` (>= 30%), preço até R$ 300 e utilidade para o
     grupo (casa, cozinha, beleza, infantil); evitar livros em excesso,
     eletrônicos caros e os mesmos itens proibidos do passo 2.
   - O link é o `link` do extrator (`https://www.amazon.com.br/dp/ASIN`): o
     site coloca a tag de associada sozinho. NÃO usar o Gerador do ML.
   - No arquivo, **sem preço e sem foto** (regra do programa de associados):

   ```json
   {"loja": "Amazon", "link": "https://www.amazon.com.br/dp/B075TGQVHT",
    "nome": "Chaleira Elétrica Inox Agratto 1,8 Litro 220V",
    "observacao": "⚡ Oferta Exclusiva Prime"}
   ```

   (`observacao` = o `selo` do extrator com um emoji; nome curto, sem inventar.)

5. **Conferir e mandar para a fila:**

   ```
   .\.venv312\Scripts\python.exe fila_ml.py tarefa_ml\ofertas_ml.json --teste
   .\.venv312\Scripts\python.exe fila_ml.py tarefa_ml\ofertas_ml.json
   ```

   O primeiro só mostra as mensagens; o segundo coloca na fila (o site
   recusa sozinho produto repetido ou com palavra bloqueada).

6. **Resumo final** curto: quais ofertas e cupons entraram, quais foram
   pulados e por quê.

## Regras

- Nunca digitar senha, resolver CAPTCHA ou mexer em configurações da conta.
- Nunca enviar mensagem direto no WhatsApp: só colocar na fila.
- Fechar as abas que abriu ao terminar.
