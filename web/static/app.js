// Equivalente web do popup "Criar campanha com IA" do app (ui_comum.py).
// Espera um <div id="modal-campanha"> com a estrutura do snippet
// _modal_campanha.html incluido em toda pagina que usa gerarCampanha().

// Guarda o produto da campanha aberta no momento, para o gerador de video.
let campanhaAtual = null;
// URL local (/static/videos/...) do ultimo video gerado - so pra
// preview/download aqui no site (o Instagram/WhatsApp nao enxergam).
let videoUrlAtual = null;
// URL publica do video na Galeria (Cloudinary) - essa sim o Instagram e
// o WhatsApp conseguem abrir. Fica null se o salvamento na Galeria falhar.
let videoUrlPublica = null;
// URL publica da foto enviada manualmente (celular), se houver - substitui
// a foto da plataforma nos 3 modos de video.
let fotoManualUrl = null;
// Roteiro/prompt do modo "Vídeo por IA": o 1o clique em GERAR so busca e
// mostra o prompt (gratis); o 2o confirma e gera de verdade (gasta credito).
let roteiroVideoIA = null;

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
    const posVideo = document.getElementById("pos-video-area");
    const statusIg = document.getElementById("instagram-status");
    const fotoInput = document.getElementById("foto-manual-input");
    const fotoStatus = document.getElementById("foto-manual-status");
    const legenda = document.getElementById("legenda-postagem");
    if (status) status.textContent = "";
    if (saida) saida.innerHTML = "";
    if (botao) botao.disabled = false;
    if (posVideo) posVideo.style.display = "none";
    if (statusIg) statusIg.textContent = "";
    if (fotoInput) fotoInput.value = "";
    if (fotoStatus) fotoStatus.textContent = "";
    if (legenda) legenda.value = "";
    videoUrlAtual = null;
    videoUrlPublica = null;
    fotoManualUrl = null;
    resetarEstadoPromptVideo();
}

function resetarEstadoPromptVideo() {
    roteiroVideoIA = null;
    const areaPrompt = document.getElementById("prompt-video-ia-area");
    if (areaPrompt) areaPrompt.style.display = "none";
    const botao = document.getElementById("botao-gerar-video");
    if (botao) botao.textContent = "🎬 GERAR VIDEO (15-30s)";
    const status = document.getElementById("video-status");
    if (status) status.textContent = "";
}

function enviarFotoManual(evento) {
    const arquivo = evento.target.files && evento.target.files[0];
    const status = document.getElementById("foto-manual-status");
    if (!arquivo) return;

    status.textContent = "Enviando foto...";
    resetarEstadoPromptVideo(); // a foto mudou, o prompt antigo nao vale mais

    const dadosForm = new FormData();
    dadosForm.append("foto", arquivo);

    fetch("/api/campanha/foto", { method: "POST", body: dadosForm })
        .then((resposta) => resposta.json())
        .then((dados) => {
            if (!dados.sucesso) {
                status.textContent = "Nao foi possivel enviar a foto: " + dados.erro;
                fotoManualUrl = null;
                return;
            }
            fotoManualUrl = dados.url;
            status.textContent = "✅ Foto enviada - vai usar essa em vez da foto da plataforma.";
        })
        .catch((erro) => {
            status.textContent = "Erro ao enviar a foto: " + erro;
            fotoManualUrl = null;
        });
}

function copiarDadosCampanha() {
    if (!campanhaAtual) return;

    const partes = ["PRODUTO: " + (campanhaAtual.nome || "")];
    if (campanhaAtual.plataforma) partes.push("Plataforma: " + campanhaAtual.plataforma);
    const preco = campanhaAtual.preco || campanhaAtual.preco_texto || campanhaAtual.priceMin;
    if (preco) partes.push("Preço: " + preco);
    if (campanhaAtual.comissao_texto) partes.push("Comissão: " + campanhaAtual.comissao_texto);
    if (campanhaAtual.vendas) partes.push("Vendas: " + campanhaAtual.vendas);
    if (campanhaAtual.link) partes.push("Link: " + campanhaAtual.link);

    const corpo = document.getElementById("modal-campanha-corpo");
    if (corpo && corpo.innerText && corpo.innerText.trim() && corpo.innerText !== "Gerando campanha...") {
        partes.push("", "--- CAMPANHA GERADA ---", corpo.innerText.trim());
    }
    if (roteiroVideoIA) {
        partes.push(
            "", "--- ROTEIRO DO VÍDEO ---",
            "Título: " + (roteiroVideoIA.titulo || ""),
            "Benefício: " + (roteiroVideoIA.beneficio || ""),
            "Narração: " + (roteiroVideoIA.narracao || "")
        );
    }

    const status = document.getElementById("copiar-dados-status");
    navigator.clipboard
        .writeText(partes.join("\n"))
        .then(() => {
            if (status) status.textContent = "Copiado! Já pode colar no ChatGPT, Gemini, Claude...";
        })
        .catch(() => {
            if (status) status.textContent = "Não deu pra copiar automaticamente - copie manualmente.";
        });
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
    const areaPrompt = document.getElementById("prompt-video-ia-area");
    const campoPrompt = document.getElementById("prompt-video-ia");
    const modoEscolhido = (document.querySelector('input[name="modo-video"]:checked') || {}).value || "padrao";

    // Modo "video": 1o clique so gera/mostra o prompt (GRATIS, nao chama
    // o Kairogen ainda) pra Keiti revisar/editar. So no 2o clique
    // ("CONFIRMAR") e' que gasta credito de verdade.
    if (modoEscolhido === "video" && !roteiroVideoIA) {
        botao.disabled = true;
        status.textContent = "Gerando o roteiro e o prompt do vídeo (grátis, ainda não gasta crédito)...";
        fetch("/api/campanha/video/prompt", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(campanhaAtual),
        })
            .then((resposta) => resposta.json())
            .then((dados) => {
                botao.disabled = false;
                if (!dados.sucesso) {
                    status.textContent = "Não foi possível gerar o prompt: " + dados.erro;
                    return;
                }
                roteiroVideoIA = dados.roteiro;
                campoPrompt.value = dados.prompt;
                areaPrompt.style.display = "block";
                status.textContent = "Revise o prompt acima (pode editar) e clique em Confirmar pra gerar (~19 créditos).";
                botao.textContent = "✅ CONFIRMAR E GERAR (~19 créditos)";
            })
            .catch((erro) => {
                botao.disabled = false;
                status.textContent = "Erro ao gerar o prompt: " + erro;
            });
        return;
    }

    const dadosEnvio = Object.assign({}, campanhaAtual, { modo_video: modoEscolhido });
    if (fotoManualUrl) dadosEnvio.foto_manual_url = fotoManualUrl;
    if (modoEscolhido === "video") {
        dadosEnvio.roteiro = roteiroVideoIA;
        dadosEnvio.prompt_video = campoPrompt.value;
    }

    botao.disabled = true;
    saida.innerHTML = "";
    videoUrlAtual = null;
    videoUrlPublica = null;
    const posVideo = document.getElementById("pos-video-area");
    if (posVideo) posVideo.style.display = "none";
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
            videoUrlPublica = dados.galeria_url || null;
            status.textContent = "Video pronto (narracao: " + dados.narracao + ").";
            if (dados.aviso_galeria) {
                status.textContent += " ⚠️ " + dados.aviso_galeria;
            } else {
                status.textContent += " Salvo na Galeria.";
            }
            saida.innerHTML =
                '<video src="' + dados.video_url + '" controls playsinline ' +
                'style="width:100%;max-width:320px;border-radius:12px;margin-top:8px"></video>' +
                '<a class="botao botao-primario" href="' + dados.video_url +
                '" download style="display:block;margin-top:8px">BAIXAR VIDEO (.mp4)</a>';

            if (posVideo) {
                const legenda = document.getElementById("legenda-postagem");
                const botaoIg = document.getElementById("botao-instagram");
                const botaoWpp = document.getElementById("botao-whatsapp");
                if (legenda) legenda.value = document.getElementById("modal-campanha-corpo").innerText.trim();
                if (!videoUrlPublica) {
                    document.getElementById("instagram-status").textContent =
                        "⚠️ Não salvou na Galeria, então não dá pra postar no Instagram nem compartilhar no WhatsApp por aqui - baixe o vídeo acima e envie manualmente.";
                    if (botaoIg) botaoIg.disabled = true;
                    if (botaoWpp) botaoWpp.disabled = true;
                } else {
                    if (botaoIg) botaoIg.disabled = false;
                    if (botaoWpp) botaoWpp.disabled = false;
                }
                posVideo.style.display = "block";
            }

            // limpa so o estado do prompt (sem apagar a mensagem "Video pronto"
            // que acabou de aparecer) - pronto pra gerar outro do zero, se quiser
            roteiroVideoIA = null;
            if (areaPrompt) areaPrompt.style.display = "none";
            botao.textContent = "🎬 GERAR VIDEO (15-30s)";
        })
        .catch((erro) => {
            botao.disabled = false;
            status.textContent = "Erro ao gerar o video: " + erro;
        });
}

function compartilharVideoWhatsApp() {
    if (!videoUrlPublica) return;
    const legenda = document.getElementById("legenda-postagem").value.trim();
    const texto = (legenda ? legenda + "\n\n" : "") + videoUrlPublica;
    window.open("https://wa.me/?text=" + encodeURIComponent(texto), "_blank");
}

function postarNoInstagram() {
    if (!videoUrlPublica) return;

    const botaoIg = document.getElementById("botao-instagram");
    const statusIg = document.getElementById("instagram-status");
    const legenda = document.getElementById("legenda-postagem").value.trim();

    botaoIg.disabled = true;
    statusIg.textContent = "Publicando no Instagram... o Instagram processa o video antes (pode levar alguns minutos).";

    fetch("/api/instagram/postar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_url: videoUrlPublica, legenda: legenda }),
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
