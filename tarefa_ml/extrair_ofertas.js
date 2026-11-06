// Le os cards de produto do Mercado Livre e devolve uma lista com nome, link do
// produto, foto, precos, desconto, comissao, selo, nota e vendas. Serve para a
// Central de Afiliados (/afiliados/hub) e para a pagina de Ofertas (/ofertas),
// que nao mostra a comissao (ganho vem 0: ver INSTRUCOES.md).
// Rodado pela tarefa agendada (ver INSTRUCOES.md) com o javascript do Chrome.
(async () => {
  // As paginas carregam mais produtos conforme rola.
  for (const y of [1200, 2400, 3600, 0]) {
    window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 1200));
  }
  const valor = el => {
    if (!el) return 0;
    const inteiro = el.querySelector('.andes-money-amount__fraction')?.innerText.replace(/\D/g, '') || '0';
    const centavos = el.querySelector('.andes-money-amount__cents')?.innerText.replace(/\D/g, '') || '0';
    return Number(inteiro) + Number(centavos) / 100;
  };
  const numeroBR = (inteiro, centavos) =>
    Number(String(inteiro).replace(/\D/g, '')) + Number(centavos || 0) / 100;

  return [...document.querySelectorAll('.poly-card')].map(card => {
    const a = card.querySelector('a[href*="mercadolivre.com.br"]');
    const texto = card.innerText.replace(/\s+/g, ' ');
    const ganho = texto.match(/GANHOS( EXTRAS)? ?(\d+)%/);
    const vendas = texto.match(/\+(\d+)(mil|M)? vendidos/);
    const selo = texto.match(/^ ?(OFERTA DO DIA|OFERTA IMPERDÍVEL|BLACK FRIDAY|MAIS VENDIDO|MAIS BUSCADO)/);
    // Oferta relampago: o card comeca com o relogio ("0 4 0 : 5 0 ...").
    const relampago = /^ ?\d \d/.test(texto);
    const nota = texto.match(/(\d\.\d) \| \+/);
    // Quando o preco grande e' so no Pix/credito, o card mostra tambem
    // "ou R$ X em outros meios" ou "ou R$ X em 8x": esse e' o preco que vale
    // para todo mundo.
    const outros = texto.match(/ou R\$ ([\d.]+)(?: , (\d+))? em (?:outros meios|\d+x)/);
    const condicao = texto.match(/OFF (no Pix|no Crédito disponível)/);
    const precoDestaque = valor(card.querySelector('.poly-price__current .andes-money-amount'));
    const preco = outros ? numeroBR(outros[1], outros[2]) : precoDestaque;
    const precoAntigo = valor(card.querySelector('.andes-money-amount--previous'));
    return {
      nome: a?.innerText.trim(),
      produto_url: a?.href.split('?')[0].split('#')[0],
      imagem: card.querySelector('img')?.src || '',
      preco,
      preco_condicao: condicao ? precoDestaque : 0,
      condicao: condicao ? condicao[1] : '',
      preco_antigo: precoAntigo,
      // Desconto real: compara com o preco de todo mundo, nao com o do Pix.
      desconto: precoAntigo > preco ? Math.round((1 - preco / precoAntigo) * 100) : 0,
      ganho: ganho ? Number(ganho[2]) : 0,
      ganho_extra: !!(ganho && ganho[1]),
      nota: nota ? Number(nota[1]) : 0,
      vendas: vendas ? Number(vendas[1]) * ({ mil: 1000, M: 1000000 }[vendas[2]] || 1) : 0,
      selo: selo ? selo[1] : '',
      relampago,
      // O card avisa que tem cupom; a condicao so aparece na pagina do produto.
      com_cupom: /com Cupom/i.test(texto),
    };
  }).filter(o => o.nome && o.produto_url && o.preco > 0);
})()
