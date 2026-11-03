// Le os cupons da pagina https://www.mercadolivre.com.br/cupons (Chrome
// logado) a partir dos dados que a propria pagina carrega, e devolve uma
// lista com titulo, onde vale, compra minima, limite, validade e alguns
// produtos de exemplo. Rodado pela tarefa agendada (ver INSTRUCOES.md).
(() => {
  const el = document.getElementById('__NORDIC_RENDERING_CTX__');
  if (!el) return { erro: 'Dados dos cupons nao encontrados (a pagina mudou ou pediu login).' };
  const texto = el.textContent;
  const json = texto.slice(texto.indexOf('{'));
  let ctx;
  try {
    ctx = JSON.parse(json);
  } catch (e) {
    // Depois do JSON vem mais codigo; o erro diz onde o JSON termina.
    const fim = Number((e.message.match(/position (\d+)/) || [])[1]);
    ctx = JSON.parse(json.slice(0, fim));
  }

  const cupons = [];
  const varrer = (o, nivel = 0) => {
    if (!o || typeof o !== 'object' || nivel > 12) return;
    if (Array.isArray(o.rawCoupons)) cupons.push(...o.rawCoupons);
    for (const v of Object.values(o)) varrer(v, nivel + 1);
  };
  varrer(ctx);

  // Validade vem em UTC (ex.: 2027-01-01T02:59Z = 31/12 23:59 em Brasilia).
  const diaBrasil = iso => {
    if (!iso) return '';
    const d = new Date(new Date(iso).getTime() - 3 * 3600 * 1000);
    return isNaN(d) ? '' : d.toISOString().slice(0, 10);
  };
  const reais = txt => Number(String(txt || '').replace(/[^\d,]/g, '').replace(',', '.')) || 0;

  const vistos = new Set();
  return cupons.map(c => ({
    campanha: c.campaign_id,
    titulo: (c.title?.text || '').replace(/\s+/g, ' ').trim(),
    onde: c.initial_subtitle?.text || '',
    tipo: c.activation_type,          // EU_QUERO = qualquer um ativa; AUTOMATIC = de uma loja
    compra_minima: reais(c.amount?.min_amount),
    limite: reais(c.amount?.cap_amount),
    validade: diaBrasil(c.future_coupon_info?.expiration_date),
    aviso: c.expiration_date?.text || '',   // "Vence 31 de dezembro", "Está esgotando!"
    exemplos: (c.items || []).map(i => i.alt_text).filter(Boolean).slice(0, 4),
  })).filter(c => {
    if (!c.titulo || vistos.has(c.campanha)) return false;
    vistos.add(c.campanha);
    return true;
  });
})()
