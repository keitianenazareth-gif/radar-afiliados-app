"""Pagina dedicada da Shopee: os 5 modos de busca automatica reunidos
numa unica tela, com botao de criar campanha com IA direto em cada
produto encontrado (sem precisar colar nada manualmente)."""

import webbrowser
from threading import Thread

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from shopee import buscar_produtos, numero
from ui_comum import (
    COR_AMARELO,
    COR_FUNDO_CARD,
    COR_LARANJA,
    COR_SECUNDARIA,
    COR_TEXTO,
    TelaComLista,
    campo_texto,
    mostrar_popup_campanha,
    rotulo_multilinha,
)


class TelaShopee(TelaComLista):
    OPCOES = [
        ("1", "Produtos virais\nEncontre produtos com alto volume de vendas"),
        ("2", "Maior comissao extra\nProdutos com melhor retorno por venda"),
        ("3", "Promocoes\nOfertas e descontos em destaque"),
        ("4", "Procurar produto\nPesquise uma categoria especifica"),
        ("5", "Melhores oportunidades\nRanking dos produtos mais promissores"),
    ]

    def __init__(self, **kwargs):
        self.opcao_atual = "5"
        super().__init__("SHOPEE", **kwargs)

    def montar_corpo_extra(self, layout):
        self.pesquisa = campo_texto("Digite um produto para pesquisar...")
        layout.add_widget(self.pesquisa)

        linha_opcoes = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(8),
        )
        linha_opcoes.bind(minimum_height=linha_opcoes.setter("height"))
        for opcao, texto in self.OPCOES:
            linha_opcoes.add_widget(self._botao_opcao(texto, opcao))
        layout.add_widget(linha_opcoes)

    def _botao_opcao(self, texto, opcao):
        botao = Button(
            text=texto,
            size_hint_y=None,
            height=dp(72),
            font_size=sp(14),
            halign="left",
            valign="middle",
            background_normal="",
            background_color=COR_FUNDO_CARD,
            color=COR_TEXTO,
        )
        botao.bind(
            size=lambda inst, tam: setattr(inst, "text_size", (tam[0] - dp(30), tam[1]))
        )
        botao.bind(on_release=lambda _b, op=opcao: self.buscar(op))
        return botao

    def buscar(self, opcao):
        termo = ""
        if opcao == "4":
            termo = self.pesquisa.text.strip()
            if not termo:
                self.pesquisa.hint_text = "Digite o produto antes de pesquisar"
                return

        self.opcao_atual = opcao
        self.status.text = "Buscando produtos..."
        self.mostrar_aguarde()

        Thread(target=self._buscar_em_segundo_plano, args=(opcao, termo), daemon=True).start()

    def _buscar_em_segundo_plano(self, opcao, termo):
        try:
            produtos = buscar_produtos(opcao, termo, limite=10)
            Clock.schedule_once(lambda _dt: self._mostrar_produtos(produtos), 0)
        except Exception as erro:
            Clock.schedule_once(lambda _dt: self.mostrar_erro(str(erro)), 0)

    def _mostrar_produtos(self, produtos):
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
            self.lista.add_widget(self._criar_card(produto))

    def _criar_card(self, produto):
        opcao = self.opcao_atual
        card = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(420) if opcao == "5" else dp(360),
            padding=[dp(15), dp(12), dp(15), dp(12)],
            spacing=dp(6),
        )

        card.add_widget(
            Label(
                text=f"TOP {produto.get('posicao', '')}",
                size_hint_y=None,
                height=dp(30),
                font_size=sp(18),
                color=COR_LARANJA,
            )
        )

        nome_produto = str(produto.get("productName") or "Produto sem nome")
        nome = rotulo_multilinha(
            nome_produto,
            height=dp(64),
            font_size=sp(16),
            valign="middle",
            color=COR_TEXTO,
        )
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

        card.add_widget(
            rotulo_multilinha(
                "\n".join(linhas),
                height=dp(185) if opcao == "5" else dp(135),
            )
        )

        link = str(produto.get("offerLink") or "")

        abrir = Button(
            text="ABRIR PRODUTO",
            size_hint_y=None,
            height=dp(48),
            font_size=sp(15),
            background_normal="",
            background_color=COR_LARANJA,
            color=COR_TEXTO,
        )
        abrir.bind(on_release=lambda _b, url=link: webbrowser.open(url) if url else None)
        card.add_widget(abrir)

        campanha = Button(
            text="✨ CRIAR CAMPANHA COM IA",
            size_hint_y=None,
            height=dp(48),
            font_size=sp(14),
            background_normal="",
            background_color=COR_AMARELO,
            color=(0.08, 0.08, 0.08, 1),
        )
        item = {
            "plataforma": "Shopee",
            "nome": nome_produto,
            "preco": preco,
            "comissao_texto": f"R$ {valor_comissao:.2f}",
            "vendas": vendas,
            "link": link,
        }
        campanha.bind(on_release=lambda _b, it=item: mostrar_popup_campanha(it))
        card.add_widget(campanha)

        return card
