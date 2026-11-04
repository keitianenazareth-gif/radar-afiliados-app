# Tarefa agendada: ofertas do Mercado Livre para a fila do WhatsApp

Roda no notebook da Keiti (app do Claude aberto + Chrome logado no Mercado
Livre, extensão Claude in Chrome conectada). Coloca 3 ofertas do Mercado Livre
e 1 da Amazon na fila da página /whatsapp e, de manhã, 1 ou 2 cupons do ML na
lista de cupons; os lotes do robô mandam no grupo.

**São exatamente 4 ofertas por execução:** cada lote leva 2 da fila, então elas
saem nos 2 lotes seguintes, ainda em promoção. Colocar mais faria a oferta
esperar na fila e vencer.

Pasta do projeto: `C:\Users\keiti\Desktop\radar-afiliados-projeto`

## Passo a passo

1. **Ler as ofertas de duas páginas no Chrome**, sempre rodando o conteúdo de
   `tarefa_ml\extrair_ofertas.js` com a ferramenta de javascript (ele rola a
   página sozinho). A lista traz nome, produto_url, imagem, preco,
   preco_condicao/condicao, preco_antigo, desconto, ganho, ganho_extra, nota,
   vendas, selo e relampago. Se vier vazia ou pedir login, PARAR e avisar a
   Keiti (não tentar fazer login).

   - **Comissão maior:** abrir `https://www.mercadolivre.com.br/afiliados/hub`,
     clicar no filtro com
     `[...document.querySelectorAll('button')].find(b => b.innerText.trim() === 'Ganhos extras').click()`,
     esperar 3 segundos e rodar o extrator.
   - **Ofertaço:** abrir `https://www.mercadolivre.com.br/ofertas` e rodar o
     extrator. Esta página não mostra a comissão (`ganho` vem 0). Para os até 5
     produtos que mais agradarem, abrir a página do produto e ler a comissão
     no topo com
     `(document.body.innerText.replace(/\s+/g, ' ').match(/GANHOS( EXTRAS)? ?(\d+)%/) || [])[0]`.

2. **Escolher 3 do Mercado Livre**, sendo:
   - **2 de comissão maior:** da maior para a menor, `ganho_extra` ou
     `ganho` >= 16%;
   - **1 do Ofertaço:** coisas do dia a dia (mercado, limpeza, casa, beleza,
     pet), com comissão de pelo menos 8%. Pular `relampago: true`, porque o
     relógio pode acabar antes de o lote sair. `OFERTA DO DIA` só na execução
     das 8h, com `"vale_ate_hora": "12:00"` e `"prioridade": true` no arquivo.
     `BLACK FRIDAY` e `OFERTA IMPERDÍVEL` valem em qualquer horário.

   Todos precisam passar nestas regras:
   - desconto real de pelo menos 30% (campo `desconto`, já calculado sobre o
     preço que vale para todo mundo, não sobre o do Pix);
   - nota >= 4,5 e pelo menos 100 vendidos;
   - preço até R$ 300, preferindo até R$ 100 (o grupo compra mais coisa barata);
   - teste da amiga: seria útil e fácil de explicar para uma amiga? Preferir
     casa, cozinha, limpeza, beleza, moda e infantil;
   - variar categorias (não mandar 3 creatinas; no máximo 1 suplemento e 1
     ferramenta por execução);
   - EVITAR: games/consoles, gift cards, celulares/iPhone, eletrodoméstico
     caro, produto adulto, armas, remédio, material hospitalar, hormônios,
     bebida alcoólica, cigarro/vape, peças de carro/moto e equipamento
     profissional.

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
   - Prazo: o `fila_ml.py` coloca 6 horas em toda oferta. Se ela vencer antes de
     sair, o robô descarta. Só escrever `vale_ate_hora` e `prioridade` na
     `OFERTA DO DIA`.

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

   **Amazon (1 por execução):**
   - Abrir `https://www.amazon.com.br/deals` (não precisa de login) e rodar
     `tarefa_ml\extrair_ofertas_amazon.js` (ele rola a página sozinho).
   - Escolher pelo `desconto` (>= 30%), preço até R$ 300 e utilidade para o
     grupo (casa, cozinha, beleza, infantil); evitar livros em excesso,
     eletrônicos caros e os mesmos itens proibidos do passo 2. Preferir o selo
     "Menor preço em 365 dias": "Oferta Exclusiva Prime" pode valer só para
     assinantes.
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
