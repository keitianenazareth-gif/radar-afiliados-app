// Equivalente web do popup "Criar campanha com IA" do app (ui_comum.py).
// Espera um <div id="modal-campanha"> com a estrutura do snippet
// _modal_campanha.html incluido em toda pagina que usa gerarCampanha().

// Guarda o produto da campanha aberta no momento, para o gerador de video.
let campanhaAtual = null;
// URL do ultimo video gerado pela Creatify (usada pelo "Postar no Instagram").
let videoUrlAtual = null;

function abrirModalCampanha() {
    document.getElementById("modal-campanha").classList.add("aberto");
}

function fecharModalCampanha() {
    document.getElementById("modal-campanha").classList.remove("aberto");
}

function resetarAreaVideo() {
    const status = document.getElementById("video-status");
    const saida = document.getElementById("video-saida");
    const botao = document.getElementById("botao-gerar-video");
    const botaoIg = document.getElementById("botao-instagram");
    const statusIg = document.getElementById("instagram-status");
    if (status) status.textContent = "";
    if (saida) saida.innerHTML = "";
    if (botao) botao.disabled = false;
    if (botaoIg) botaoIg.style.display = "none";
    if (statusIg) statusIg.textContent = "";
    videoUrlAtual = null;
}

function gerarCampanha(item) {
    campanhaAtual = item;
    document.getElementById("modal-campanha-titulo").textContent =
        (item.plataforma || "") + " - " + (item.nome || "");
    document.getElementById("modal-campanha-corpo").textContent = "Gerando campanha...";
    resetarAreaVideo();
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

function gerarVideoCampanha() {
    if (!campanhaAtual) return;

    const botao = document.getElementById("botao-gerar-video");
    const status = document.getElementById("video-status");
    const saida = document.getElementById("video-saida");

    const modoEscolhido = (document.querySelector('input[name="modo-video"]:checked') || {}).value || "padrao";
    const dadosEnvio = Object.assign({}, campanhaAtual, { modo_video: modoEscolhido });

    botao.disabled = true;
    saida.innerHTML = "";
    videoUrlAtual = null;
    const botaoIg = document.getElementById("botao-instagram");
    if (botaoIg) botaoIg.style.display = "none";
    document.getElementById("instagram-status").textContent = "";
    status.textContent =
        modoEscolhido === "video"
            ? "Gerando video com IA... isso pode levar de 1 a 3 minutos (a IA anima a foto real do produto)."
            : modoEscolhido === "fundo"
            ? "Gerando fundo com IA e montando o video... isso pode levar ate 1-2 minutos."
            : "Gerando video... isso pode levar ate 1 minuto (roteiro + narracao + montagem).";

    fetch("/api/campanha/video", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(dadosEnvio),
    })
        .then((resposta) => resposta.json())
        .then((dados) => {
            botao.disabled = false;
            if (!dados.sucesso) {
                status.textContent = "Nao foi possivel gerar o video: " + dados.erro;
                return;
            }
            videoUrlAtual = dados.video_url;
            status.textContent = "Video pronto (narracao: " + dados.narracao + ").";
            saida.innerHTML =
                '<video src="' + dados.video_url + '" controls playsinline ' +
                'style="width:100%;max-width:320px;border-radius:12px;margin-top:8px"></video>' +
                '<a class="botao botao-primario" href="' + dados.video_url +
                '" download style="display:block;margin-top:8px">BAIXAR VIDEO (.mp4)</a>';
            if (botaoIg) botaoIg.style.display = "block";
        })
        .catch((erro) => {
            botao.disabled = false;
            status.textContent = "Erro ao gerar o video: " + erro;
        });
}

function postarNoInstagram() {
    if (!videoUrlAtual) return;

    const botaoIg = document.getElementById("botao-instagram");
    const statusIg = document.getElementById("instagram-status");
    const legenda = document.getElementById("modal-campanha-corpo").innerText.trim();

    botaoIg.disabled = true;
    statusIg.textContent = "Publicando no Instagram... o Instagram processa o video antes (pode levar alguns minutos).";

    fetch("/api/instagram/postar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_url: videoUrlAtual, legenda: legenda }),
    })
        .then((resposta) => resposta.json())
        .then((dados) => {
            botaoIg.disabled = false;
            statusIg.textContent = dados.sucesso
                ? "Reel publicado! (id: " + dados.media_id + ")"
                : "Nao foi possivel publicar: " + dados.erro;
        })
        .catch((erro) => {
            botaoIg.disabled = false;
            statusIg.textContent = "Erro ao publicar no Instagram: " + erro;
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
