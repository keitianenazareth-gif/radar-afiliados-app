// Le os cards de produto da Central de Afiliados do Mercado Livre
// (https://www.mercadolivre.com.br/afiliados/hub) e devolve uma lista com
// nome, link do produto, foto, precos, comissao, nota e vendas.
// Rodado pela tarefa agendada (ver INSTRUCOES.md) com o javascript do Chrome.
(() => {
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
    const vendas = texto.match(/\+(\d+)(mil)? vendidos/);
    const nota = texto.match(/(\d\.\d) \| \+/);
    // Quando o preco grande e' so no Pix/credito, o card mostra tambem
    // "ou R$ X em outros meios": esse e' o preco que vale para todo mundo.
    const outros = texto.match(/ou R\$ ([\d.]+)(?: , (\d+))? em outros meios/);
    const condicao = texto.match(/OFF (no Pix|no Crédito disponível)/);
    const precoDestaque = valor(card.querySelector('.poly-price__current .andes-money-amount'));
    return {
      nome: a?.innerText.trim(),
      produto_url: a?.href.split('?')[0].split('#')[0],
      imagem: card.querySelector('img')?.src || '',
      preco: outros ? numeroBR(outros[1], outros[2]) : precoDestaque,
      preco_condicao: condicao ? precoDestaque : 0,
      condicao: condicao ? condicao[1] : '',
      preco_antigo: valor(card.querySelector('.andes-money-amount--previous')),
      ganho: ganho ? Number(ganho[2]) : 0,
      ganho_extra: !!(ganho && ganho[1]),
      nota: nota ? Number(nota[1]) : 0,
      vendas: vendas ? Number(vendas[1]) * (vendas[2] ? 1000 : 1) : 0,
    };
  }).filter(o => o.nome && o.produto_url && o.preco > 0);
})()
