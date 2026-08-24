from threading import Thread
import webbrowser

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from shopee import buscar_produtos, numero
from mercado_livre import buscar_produtos_ml
from produto_manual import buscar_metadados_link


Window.clearcolor = (0.025, 0.03, 0.04, 1)

COR_FUNDO_CARD = (0.11, 0.12, 0.16, 1)
COR_LARANJA = (1, 0.30, 0.03, 1)
COR_AMARELO = (1, 0.80, 0.10, 1)
COR_TEXTO = (1, 1, 1, 1)
COR_SECUNDARIA = (0.70, 0.72, 0.78, 1)


class TelaPrincipal(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = BoxLayout(
            orientation="vertical",
            padding=[dp(18), dp(18), dp(18), dp(16)],
            spacing=dp(10),
        )

        titulo = Label(
            text="RADAR AFILIADOS",
            size_hint_y=None,
            height=dp(42),
            font_size=sp(24),
            color=COR_TEXTO,
        )
        layout.add_widget(titulo)

        subtitulo = Label(
            text="Encontre produtos com maior potencial de divulgacao",
            size_hint_y=None,
            height=dp(28),
            font_size=sp(13),
            color=COR_SECUNDARIA,
        )
        layout.add_widget(subtitulo)

        # Botao de destaque para a Visao Geral (todas as plataformas)
        geral = Button(
            text="⭐ VISÃO GERAL\nMelhores oportunidades de todas as plataformas",
            size_hint_y=None,
            height=dp(100),
            font_size=sp(17),
            halign="left",
            valign="middle",
            background_normal="",
            background_color=COR_AMARELO,
            color=(0.08, 0.08, 0.08, 1),
        )
        geral.bind(
            size=lambda inst, tam: setattr(inst, "text_size", (tam[0] - dp(30), tam[1]))
        )
        geral.bind(on_release=self.abrir_geral)
        layout.add_widget(geral)

        manual = Button(
            text="➕ ADICIONAR PRODUTO\nAmazon, Shein, Temu (cole o link)",
            size_hint_y=None,
            height=dp(90),
            font_size=sp(16),
            halign="left",
            valign="middle",
            background_normal="",
            background_color=(0.16, 0.18, 0.24, 1),
            color=COR_TEXTO,
        )
        manual.bind(
            size=lambda inst, tam: setattr(inst, "text_size", (tam[0] - dp(30), tam[1]))
        )
        manual.bind(on_release=self.abrir_manual)
        layout.add_widget(manual)

        shopee = Label(
            text="SHOPEE",
            size_hint_y=None,
            height=dp(70),
            font_size=sp(42),
            color=COR_LARANJA,
        )
        layout.add_widget(shopee)

        self.pesquisa = TextInput(
            hint_text="Digite um produto para pesquisar...",
            multiline=False,
            size_hint_y=None,
            height=dp(66),
            font_size=sp(18),
            background_normal="",
            background_active="",
            background_color=(0.08, 0.10, 0.13, 1),
            foreground_color=COR_TEXTO,
            hint_text_color=(0.55, 0.58, 0.64, 1),
            cursor_color=COR_LARANJA,
            padding=[dp(15), dp(18)],
        )
        layout.add_widget(self.pesquisa)

        self._adicionar_botao(
            layout,
            "Produtos virais\nEncontre produtos com alto volume de vendas",
            "1",
        )
        self._adicionar_botao(
            layout,
            "Maior comissao extra\nProdutos com melhor retorno por venda",
            "2",
        )
        self._adicionar_botao(
            layout,
            "Promocoes\nOfertas e descontos em destaque",
            "3",
        )
        self._adicionar_botao(
            layout,
            "Procurar produto\nPesquise uma categoria especifica",
            "4",
        )
        self._adicionar_botao(
            layout,
            "Melhores oportunidades (Shopee)\nRanking dos produtos mais promissores",
            "5",
        )

        layout.add_widget(Widget())
        self.add_widget(layout)

    def _adicionar_botao(self, layout, texto, opcao):
        botao = Button(
            text=texto,
            size_hint_y=None,
            height=dp(88),
            font_size=sp(16),
            halign="left",
            valign="middle",
            background_normal="",
            background_color=COR_FUNDO_CARD,
            color=COR_TEXTO,
        )
        botao.bind(
            size=lambda inst, tam: setattr(inst, "text_size", (tam[0] - dp(30), tam[1]))
        )
        botao.bind(on_release=lambda _botao, op=opcao: self.abrir_resultados(op))
        layout.add_widget(botao)

    def abrir_resultados(self, opcao):
        termo = ""
        if opcao == "4":
            termo = self.pesquisa.text.strip()
            if not termo:
                self.pesquisa.hint_text = "Digite o produto antes de pesquisar"
                return

        app = App.get_running_app()
        app.tela_resultados.iniciar_busca(opcao, termo)
        app.manager.current = "resultados"

    def abrir_geral(self, _botao):
        app = App.get_running_app()
        app.tela_geral.iniciar_busca()
        app.manager.current = "geral"

    def abrir_manual(self, _botao):
        app = App.get_running_app()
        app.tela_manual.resetar()
        app.manager.current = "manual"


class TelaResultados(Screen):
    TITULOS = {
        "1": "PRODUTOS VIRAIS",
        "2": "MAIOR COMISSAO EXTRA",
        "3": "PROMOCOES",
        "4": "PROCURAR PRODUTO",
        "5": "MELHORES OPORTUNIDADES",
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = BoxLayout(
            orientation="vertical",
            padding=[dp(18), dp(18), dp(18), dp(18)],
            spacing=dp(10),
        )

        voltar = Button(
            text="< VOLTAR",
            size_hint_y=None,
            height=dp(52),
            font_size=sp(16),
            background_normal="",
            background_color=COR_FUNDO_CARD,
            color=COR_TEXTO,
        )
        voltar.bind(on_release=self.voltar)
        layout.add_widget(voltar)

        self.titulo = Label(
            text="RESULTADOS",
            size_hint_y=None,
            height=dp(42),
            font_size=sp(21),
            color=COR_TEXTO,
        )
        layout.add_widget(self.titulo)

        self.status = Label(
            text="",
            size_hint_y=None,
            height=dp(28),
            font_size=sp(13),
            color=COR_SECUNDARIA,
        )
        layout.add_widget(self.status)

        self.scroll = ScrollView(do_scroll_x=False)
        self.lista = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(12),
            padding=[dp(0), dp(6), dp(0), dp(10)],
        )
        self.lista.bind(minimum_height=self.lista.setter("height"))
        self.scroll.add_widget(self.lista)
        layout.add_widget(self.scroll)

        self.add_widget(layout)

    def iniciar_busca(self, opcao, termo=""):
        self.titulo.text = self.TITULOS.get(opcao, "RESULTADOS")
        self.status.text = "Buscando produtos..."
        self.lista.clear_widgets()
        self.lista.add_widget(
            Label(
                text="Aguarde alguns segundos...",
                size_hint_y=None,
                height=dp(90),
                font_size=sp(17),
                color=COR_SECUNDARIA,
            )
        )

        Thread(
            target=self._buscar_em_segundo_plano,
            args=(opcao, termo),
            daemon=True,
        ).start()

    def _buscar_em_segundo_plano(self, opcao, termo):
        try:
            produtos = buscar_produtos(opcao, termo, limite=10)
            Clock.schedule_once(
                lambda _dt: self.mostrar_produtos(produtos, opcao),
                0,
            )
        except Exception as erro:
            mensagem = str(erro)
            Clock.schedule_once(
                lambda _dt: self.mostrar_erro(mensagem),
                0,
            )

    def mostrar_erro(self, mensagem):
        self.status.text = "Nao foi possivel concluir a busca."
        self.lista.clear_widgets()
        label = Label(
            text=mensagem,
            size_hint_y=None,
            height=dp(180),
            font_size=sp(15),
            halign="left",
            valign="top",
            color=COR_TEXTO,
        )
        label.bind(size=lambda inst, tam: setattr(inst, "text_size", (tam[0], None)))
        self.lista.add_widget(label)

    def mostrar_produtos(self, produtos, opcao):
        self.lista.clear_widgets()
        self.status.text = f"{len(produtos)} produtos encontrados"

        if not produtos:
            self.lista.add_widget(
                Label(
                    text="Nenhum produto encontrado.",
                    size_hint_y=None,
                    height=dp(100),
                    font_size=sp(16),
                    color=COR_SECUNDARIA,
                )
            )
            return

        for produto in produtos:
            self.lista.add_widget(self.criar_card(produto, opcao))

    def criar_card(self, produto, opcao):
        card = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(360) if opcao == "5" else dp(300),
            padding=[dp(15), dp(12), dp(15), dp(12)],
            spacing=dp(6),
        )

        topo = Label(
            text=f"TOP {produto.get('posicao', '')}",
            size_hint_y=None,
            height=dp(30),
            font_size=sp(18),
            color=COR_LARANJA,
        )
        card.add_widget(topo)

        nome = Label(
            text=str(produto.get("productName") or "Produto sem nome"),
            size_hint_y=None,
            height=dp(64),
            font_size=sp(16),
            halign="left",
            valign="middle",
            color=COR_TEXTO,
        )
        nome.bind(size=lambda inst, tam: setattr(inst, "text_size", (tam[0], None)))
        card.add_widget(nome)

        preco = numero(produto.get("priceMin"))
        desconto = numero(produto.get("priceDiscountRate"))
        vendas = int(numero(produto.get("sales")))
        comissao_total = numero(produto.get("commissionRate")) * 100
        comissao_extra = numero(produto.get("sellerCommissionRate")) * 100
        valor_comissao = numero(produto.get("commission"))

        linhas = [
            f"Preco: R$ {preco:.2f}",
            f"Desconto: {desconto:g}%",
            f"Vendas: {vendas:,}".replace(",", "."),
            f"Comissao total: {comissao_total:.1f}%",
            f"Comissao extra: {comissao_extra:.1f}%",
            f"Valor da comissao: R$ {valor_comissao:.2f}",
        ]

        if opcao == "5":
            linhas.append(f"Nota: {produto.get('nota', 0)} / 100")
            linhas.append(f"Classificacao: {produto.get('classificacao', '')}")
            motivos = produto.get("motivos") or []
            if motivos:
                linhas.append("Motivos: " + " | ".join(motivos))

        info = Label(
            text="\n".join(linhas),
            size_hint_y=None,
            height=dp(185) if opcao == "5" else dp(135),
            font_size=sp(14),
            halign="left",
            valign="top",
            color=COR_SECUNDARIA,
        )
        info.bind(size=lambda inst, tam: setattr(inst, "text_size", (tam[0], None)))
        card.add_widget(info)

        abrir = Button(
            text="ABRIR PRODUTO",
            size_hint_y=None,
            height=dp(48),
            font_size=sp(15),
            background_normal="",
            background_color=COR_LARANJA,
            color=COR_TEXTO,
        )
        link = produto.get("offerLink") or ""
        abrir.bind(on_release=lambda _btn, url=link: self.abrir_link(url))
        card.add_widget(abrir)

        return card

    def abrir_link(self, link):
        if link:
            webbrowser.open(link)

    def voltar(self, _botao):
        App.get_running_app().manager.current = "principal"


class TelaGeral(Screen):
    """Tela unificada: melhores oportunidades de todas as plataformas
    conectadas (Shopee + Mercado Livre), ordenadas por nota."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = BoxLayout(
            orientation="vertical",
            padding=[dp(18), dp(18), dp(18), dp(18)],
            spacing=dp(10),
        )

        voltar = Button(
            text="< VOLTAR",
            size_hint_y=None,
            height=dp(52),
            font_size=sp(16),
            background_normal="",
            background_color=COR_FUNDO_CARD,
            color=COR_TEXTO,
        )
        voltar.bind(on_release=self.voltar)
        layout.add_widget(voltar)

        titulo = Label(
            text="⭐ VISÃO GERAL",
            size_hint_y=None,
            height=dp(42),
            font_size=sp(22),
            color=COR_AMARELO,
        )
        layout.add_widget(titulo)

        self.status = Label(
            text="",
            size_hint_y=None,
            height=dp(28),
            font_size=sp(13),
            color=COR_SECUNDARIA,
        )
        layout.add_widget(self.status)

        self.scroll = ScrollView(do_scroll_x=False)
        self.lista = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(12),
            padding=[dp(0), dp(6), dp(0), dp(10)],
        )
        self.lista.bind(minimum_height=self.lista.setter("height"))
        self.scroll.add_widget(self.lista)
        layout.add_widget(self.scroll)

        self.add_widget(layout)

    def iniciar_busca(self):
        self.status.text = "Buscando nas plataformas conectadas..."
        self.lista.clear_widgets()
        self.lista.add_widget(
            Label(
                text="Aguarde alguns segundos...",
                size_hint_y=None,
                height=dp(90),
                font_size=sp(17),
                color=COR_SECUNDARIA,
            )
        )

        Thread(
            target=self._buscar_em_segundo_plano,
            daemon=True,
        ).start()

    def _buscar_em_segundo_plano(self):
        itens = []

        try:
            produtos_shopee = buscar_produtos("5", "", limite=15)
            for produto in produtos_shopee:
                itens.append({
                    "plataforma": "Shopee",
                    "nome": str(produto.get("productName") or "Produto"),
                    "preco": numero(produto.get("priceMin")),
                    "comissao_texto": f"R$ {numero(produto.get('commission')):.2f}",
                    "vendas": int(numero(produto.get("sales"))),
                    "nota": produto.get("nota") or 0,
                    "link": str(produto.get("offerLink") or ""),
                })
        except Exception:
            pass

        try:
            itens.extend(buscar_produtos_ml(limite=15))
        except Exception:
            pass

        itens.sort(key=lambda item: item["nota"], reverse=True)
        itens = itens[:20]

        Clock.schedule_once(
            lambda _dt: self.mostrar_itens(itens),
            0,
        )

    def mostrar_itens(self, itens):
        self.lista.clear_widgets()
        self.status.text = f"{len(itens)} oportunidades encontradas"

        if not itens:
            self.lista.add_widget(
                Label(
                    text="Nenhum produto encontrado.\nVerifique suas credenciais.",
                    size_hint_y=None,
                    height=dp(100),
                    font_size=sp(16),
                    color=COR_SECUNDARIA,
                )
            )
            return

        for item in itens:
            self.lista.add_widget(self.criar_card(item))

    def criar_card(self, item):
        card = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(290),
            padding=[dp(15), dp(12), dp(15), dp(12)],
            spacing=dp(6),
        )

        cor_selo = COR_LARANJA if item["plataforma"] == "Shopee" else COR_AMARELO

        selo = Label(
            text=item["plataforma"].upper(),
            size_hint_y=None,
            height=dp(28),
            font_size=sp(15),
            color=cor_selo,
        )
        card.add_widget(selo)

        nome = Label(
            text=item["nome"],
            size_hint_y=None,
            height=dp(64),
            font_size=sp(16),
            halign="left",
            valign="middle",
            color=COR_TEXTO,
        )
        nome.bind(size=lambda inst, tam: setattr(inst, "text_size", (tam[0], None)))
        card.add_widget(nome)

        linhas = [
            f"Preco: R$ {item['preco']:.2f}",
            f"Comissao: {item['comissao_texto']}",
            f"Vendas: {item['vendas']:,}".replace(",", "."),
            f"Nota: {item['nota']:.1f} / 100",
        ]

        info = Label(
            text="\n".join(linhas),
            size_hint_y=None,
            height=dp(110),
            font_size=sp(14),
            halign="left",
            valign="top",
            color=COR_SECUNDARIA,
        )
        info.bind(size=lambda inst, tam: setattr(inst, "text_size", (tam[0], None)))
        card.add_widget(info)

        abrir = Button(
            text="ABRIR PRODUTO",
            size_hint_y=None,
            height=dp(48),
            font_size=sp(15),
            background_normal="",
            background_color=cor_selo,
            color=(0.08, 0.08, 0.08, 1),
        )
        link = item.get("link") or ""
        abrir.bind(on_release=lambda _btn, url=link: self.abrir_link(url))
        card.add_widget(abrir)

        campanha = Button(
            text="✨ CRIAR CAMPANHA COM IA",
            size_hint_y=None,
            height=dp(48),
            font_size=sp(14),
            background_normal="",
            background_color=COR_LARANJA,
            color=COR_TEXTO,
        )
        campanha.bind(
            on_release=lambda _btn, it=item: self.criar_campanha_item(it)
        )
        card.add_widget(campanha)

        return card

    def criar_campanha_item(self, item):
        app = App.get_running_app()
        tela = app.tela_manual
        tela.resetar()
        tela.campo_link.text = item.get("link", "")
        tela.campo_nome.text = item.get("nome", "")
        tela.campo_preco.text = f"{item.get('preco', 0):.2f}"
        tela.campo_comissao.text = item.get("comissao_texto", "")
        tela.definir_plataforma_externa(item.get("plataforma", ""))
        app.manager.current = "manual"
        tela.criar_campanha(None)

    def abrir_link(self, link):
        if link:
            webbrowser.open(link)

    def voltar(self, _botao):
        App.get_running_app().manager.current = "principal"


class TelaManual(Screen):
    """Tela para produtos de plataformas sem API (Amazon, Shein, Temu):
    voce cola o link, o app tenta preencher nome/imagem automaticamente,
    e voce completa/confirma antes de gerar a campanha."""

    PLATAFORMAS = ["Amazon", "Shein", "Temu"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.plataforma_atual = self.PLATAFORMAS[0]
        self.imagem_url = ""

        layout = BoxLayout(
            orientation="vertical",
            padding=[dp(18), dp(18), dp(18), dp(18)],
            spacing=dp(8),
        )

        voltar = Button(
            text="< VOLTAR",
            size_hint_y=None,
            height=dp(52),
            font_size=sp(16),
            background_normal="",
            background_color=COR_FUNDO_CARD,
            color=COR_TEXTO,
        )
        voltar.bind(on_release=self.voltar)
        layout.add_widget(voltar)

        titulo = Label(
            text="➕ ADICIONAR PRODUTO",
            size_hint_y=None,
            height=dp(38),
            font_size=sp(20),
            color=COR_TEXTO,
        )
        layout.add_widget(titulo)

        # Seletor de plataforma (3 botoes lado a lado)
        linha_plataformas = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(56),
            spacing=dp(8),
        )
        self.botoes_plataforma = {}
        for nome_plat in self.PLATAFORMAS:
            botao = Button(
                text=nome_plat,
                background_normal="",
                background_color=(
                    COR_LARANJA if nome_plat == self.plataforma_atual
                    else COR_FUNDO_CARD
                ),
                color=COR_TEXTO,
            )
            botao.bind(
                on_release=lambda _b, p=nome_plat: self.selecionar_plataforma(p)
            )
            self.botoes_plataforma[nome_plat] = botao
            linha_plataformas.add_widget(botao)
        layout.add_widget(linha_plataformas)

        self.campo_link = TextInput(
            hint_text="Cole o link do produto aqui...",
            multiline=False,
            size_hint_y=None,
            height=dp(56),
            font_size=sp(15),
            background_normal="",
            background_color=(0.08, 0.10, 0.13, 1),
            foreground_color=COR_TEXTO,
            hint_text_color=(0.55, 0.58, 0.64, 1),
            cursor_color=COR_LARANJA,
            padding=[dp(12), dp(15)],
        )
        layout.add_widget(self.campo_link)

        buscar = Button(
            text="🔍 BUSCAR DADOS AUTOMATICAMENTE",
            size_hint_y=None,
            height=dp(52),
            font_size=sp(14),
            background_normal="",
            background_color=COR_AMARELO,
            color=(0.08, 0.08, 0.08, 1),
        )
        buscar.bind(on_release=self.buscar_dados)
        layout.add_widget(buscar)

        self.status_busca = Label(
            text="",
            size_hint_y=None,
            height=dp(40),
            font_size=sp(13),
            halign="left",
            valign="top",
            color=COR_SECUNDARIA,
        )
        self.status_busca.bind(
            size=lambda inst, tam: setattr(inst, "text_size", (tam[0], None))
        )
        layout.add_widget(self.status_busca)

        self.campo_nome = TextInput(
            hint_text="Nome do produto",
            multiline=False,
            size_hint_y=None,
            height=dp(56),
            font_size=sp(15),
            background_normal="",
            background_color=(0.08, 0.10, 0.13, 1),
            foreground_color=COR_TEXTO,
            hint_text_color=(0.55, 0.58, 0.64, 1),
            cursor_color=COR_LARANJA,
            padding=[dp(12), dp(15)],
        )
        layout.add_widget(self.campo_nome)

        self.campo_preco = TextInput(
            hint_text="Preco (ex: 79,90)",
            multiline=False,
            size_hint_y=None,
            height=dp(56),
            font_size=sp(15),
            input_filter=None,
            background_normal="",
            background_color=(0.08, 0.10, 0.13, 1),
            foreground_color=COR_TEXTO,
            hint_text_color=(0.55, 0.58, 0.64, 1),
            cursor_color=COR_LARANJA,
            padding=[dp(12), dp(15)],
        )
        layout.add_widget(self.campo_preco)

        self.campo_comissao = TextInput(
            hint_text="Comissao/observacao (opcional)",
            multiline=False,
            size_hint_y=None,
            height=dp(56),
            font_size=sp(15),
            background_normal="",
            background_color=(0.08, 0.10, 0.13, 1),
            foreground_color=COR_TEXTO,
            hint_text_color=(0.55, 0.58, 0.64, 1),
            cursor_color=COR_LARANJA,
            padding=[dp(12), dp(15)],
        )
        layout.add_widget(self.campo_comissao)

        criar = Button(
            text="✨ CRIAR CAMPANHA COM IA",
            size_hint_y=None,
            height=dp(56),
            font_size=sp(15),
            background_normal="",
            background_color=COR_LARANJA,
            color=COR_TEXTO,
        )
        criar.bind(on_release=self.criar_campanha)
        layout.add_widget(criar)

        self.resultado_campanha = Label(
            text="",
            size_hint_y=None,
            font_size=sp(14),
            halign="left",
            valign="top",
            color=COR_TEXTO,
        )
        self.resultado_campanha.bind(
            size=lambda inst, tam: setattr(inst, "text_size", (tam[0], None)),
            texture_size=lambda inst, tam: setattr(inst, "height", tam[1]),
        )

        scroll = ScrollView(do_scroll_x=False)
        conteudo_scroll = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
        )
        conteudo_scroll.bind(
            minimum_height=conteudo_scroll.setter("height")
        )
        conteudo_scroll.add_widget(self.resultado_campanha)
        scroll.add_widget(conteudo_scroll)
        layout.add_widget(scroll)

        self.add_widget(layout)

    def resetar(self):
        self.campo_link.text = ""
        self.campo_nome.text = ""
        self.campo_preco.text = ""
        self.campo_comissao.text = ""
        self.status_busca.text = ""
        self.resultado_campanha.text = ""

    def selecionar_plataforma(self, nome_plat):
        self.plataforma_atual = nome_plat
        for nome, botao in self.botoes_plataforma.items():
            botao.background_color = (
                COR_LARANJA if nome == nome_plat else COR_FUNDO_CARD
            )

    def definir_plataforma_externa(self, nome_plat):
        """Usado quando a campanha vem de fora dos 3 botoes fixos
        (ex: Shopee/Mercado Livre vindos da Visao Geral)."""
        self.plataforma_atual = nome_plat
        for botao in self.botoes_plataforma.values():
            botao.background_color = COR_FUNDO_CARD

    def buscar_dados(self, _botao):
        link = self.campo_link.text.strip()
        if not link:
            self.status_busca.text = "Cole um link antes de buscar."
            return

        self.status_busca.text = "Buscando..."
        Thread(
            target=self._buscar_em_segundo_plano,
            args=(link,),
            daemon=True,
        ).start()

    def _buscar_em_segundo_plano(self, link):
        dados = buscar_metadados_link(link)
        Clock.schedule_once(
            lambda _dt: self._preencher_dados(dados),
            0,
        )

    def _preencher_dados(self, dados):
        if dados["sucesso"]:
            self.campo_nome.text = dados["nome"]
            if dados["preco_texto"]:
                self.campo_preco.text = dados["preco_texto"]
            self.status_busca.text = "✅ Dados encontrados. Confira antes de continuar."
        else:
            self.status_busca.text = f"⚠️ {dados['motivo']}"

    def criar_campanha(self, _botao):
        nome = self.campo_nome.text.strip()
        preco = self.campo_preco.text.strip()
        link = self.campo_link.text.strip()

        if not nome or not link:
            self.resultado_campanha.text = (
                "Preencha ao menos o nome do produto e o link."
            )
            return

        self.resultado_campanha.text = "Gerando campanha..."

        Thread(
            target=self._gerar_campanha_em_segundo_plano,
            args=(nome, preco, link),
            daemon=True,
        ).start()

    def _gerar_campanha_em_segundo_plano(self, nome, preco, link):
        try:
            from campanhas_ia import gerar_campanha

            texto = gerar_campanha(
                plataforma=self.plataforma_atual,
                produto=nome,
                preco=preco,
                comissao=self.campo_comissao.text.strip(),
                vendas="",
                link=link,
                observacoes=(
                    "Crie conteudo natural para afiliada. "
                    "Nao invente informacoes."
                ),
            )
        except ImportError:
            texto = (
                "⚠️ O arquivo campanhas_ia.py nao foi encontrado "
                "nesta pasta do projeto."
            )
        except RuntimeError as erro:
            texto = f"⚠️ {erro}"
        except Exception as erro:
            texto = f"Erro ao gerar campanha: {erro}"

        Clock.schedule_once(
            lambda _dt: setattr(self.resultado_campanha, "text", texto),
            0,
        )

    def voltar(self, _botao):
        App.get_running_app().manager.current = "principal"


class RadarAfiliadosApp(App):
    def build(self):
        self.manager = ScreenManager()
        principal = TelaPrincipal(name="principal")
        self.tela_resultados = TelaResultados(name="resultados")
        self.tela_geral = TelaGeral(name="geral")
        self.tela_manual = TelaManual(name="manual")
        self.manager.add_widget(principal)
        self.manager.add_widget(self.tela_resultados)
        self.manager.add_widget(self.tela_geral)
        self.manager.add_widget(self.tela_manual)
        return self.manager


if __name__ == "__main__":
    RadarAfiliadosApp().run()
