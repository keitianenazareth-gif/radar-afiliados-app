// Equivalente web do popup "Criar campanha com IA" do app (ui_comum.py).
// Espera um <div id="modal-campanha"> com a estrutura do snippet
// modal_campanha.html incluido em toda pagina que usa gerarCampanha().

function abrirModalCampanha() {
    document.getElementById("modal-campanha").classList.add("aberto");
}

function fecharModalCampanha() {
    document.getElementById("modal-campanha").classList.remove("aberto");
}

function gerarCampanha(item) {
    document.getElementById("modal-campanha-titulo").textContent =
        (item.plataforma || "") + " - " + (item.nome || "");
    document.getElementById("modal-campanha-corpo").textContent = "Gerando campanha...";
    abrirModalCampanha();

    fetch("/api/campanha", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(item),
    })
        .then((resposta) => resposta.json())
        .then((dados) => {
            document.getElementById("modal-campanha-corpo").textContent =
                dados.sucesso ? dados.texto : dados.erro;
        })
        .catch((erro) => {
            document.getElementById("modal-campanha-corpo").textContent =
                "Erro ao gerar campanha: " + erro;
        });
}

// Busca generica usada pelas paginas de plataforma (Shopee, Visao Geral).
// url: endpoint da API. corpo: objeto enviado como JSON.
// aoReceber: callback(listaDeItens) chamada com o resultado.
function buscarProdutos(url, corpo, elementoStatus, aoReceber) {
    elementoStatus.textContent = "Buscando produtos...";

    fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpo),
    })
        .then((resposta) => resposta.json())
        .then((dados) => {
            if (dados.erro) {
                elementoStatus.textContent = "Nao foi possivel concluir a busca: " + dados.erro;
                aoReceber([]);
                return;
            }
            elementoStatus.textContent = dados.itens.length + " produtos encontrados";
            aoReceber(dados.itens);
        })
        .catch((erro) => {
            elementoStatus.textContent = "Nao foi possivel concluir a busca: " + erro;
            aoReceber([]);
        });
}
