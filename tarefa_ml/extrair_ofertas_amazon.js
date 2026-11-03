// Le as ofertas da pagina https://www.amazon.com.br/deals (nao precisa de
// login) e devolve asin, nome, selo ("Oferta Exclusiva Prime", "Menor preço
// em 365 dias"...), desconto e preco. Desconto e preco servem SO para
// escolher: a mensagem da Amazon nao pode mostrar preco (regra do programa
// de associados). Rodado pela tarefa agendada (ver INSTRUCOES.md).
(async () => {
  // A pagina carrega os cards aos poucos: rola um pouco antes de ler.
  for (const y of [1500, 3000, 4500, 0]) {
    window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 1500));
  }
  const porAsin = {};
  for (const a of document.querySelectorAll('a[href*="/dp/"]')) {
    const asin = (a.href.match(/\/dp\/([A-Z0-9]{10})/) || [])[1];
    if (!asin || porAsin[asin]) continue;
    porAsin[asin] = a.closest('[data-asin], [data-testid], li, [class*="card"]') || a.parentElement;
  }
  return Object.entries(porAsin).map(([asin, card]) => {
    const texto = card.innerText.replace(/\s+/g, ' ').trim();
    const partes = texto.match(/^(.*?) (\d+)% off (.*?) R\$/);
    return {
      asin,
      nome: partes ? partes[1].trim() : '',
      desconto: partes ? Number(partes[2]) : 0,
      selo: partes ? partes[3].trim() : '',
      preco: Number(((texto.match(/R\$ ?([\d.]+,\d{2})/) || [])[1] || '0').replace(/\./g, '').replace(',', '.')),
      link: `https://www.amazon.com.br/dp/${asin}`,
    };
  }).filter(o => o.nome && o.desconto > 0);
})()
