"""Visao Geral: melhores oportunidades entre as plataformas com busca
automatica funcional. Hoje isso e' so a Shopee - o Mercado Livre nao
entra aqui porque a API de busca por palavra-chave nao expoe preco/nome
de anuncio pra apps de terceiros (ver mercado_livre.py)."""

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
    COR_LARANJA,
    COR_SECUNDARIA,
    COR_TEXTO,
    TelaComLista,
    mostrar_popup_campanha,
    rotulo_multilinha,
)


class TelaGeral(TelaComLista):
    def __init__(self, **kwargs):
        super().__init__("⭐ VISÃO GERAL", **kwargs)

    def iniciar_busca(self):
        self.status.text = "Buscando as melhores oportunidades..."
        self.mostrar_aguarde()
        Thread(target=self._buscar_em_segundo_plano, daemon=True).start()

    def _buscar_em_segundo_plano(self):
        try:
            produtos = buscar_produtos("5", "", limite=20)
            itens = [
                {
                    "plataforma": "Shopee",
                    "nome": str(produto.get("productName") or "Produto"),
                    "preco": numero(produto.get("priceMin")),
                    "comissao_texto": f"R$ {numero(produto.get('commission')):.2f}",
                    "vendas": int(numero(produto.get("sales"))),
                    "nota": produto.get("nota") or 0,
                    "link": str(produto.get("offerLink") or ""),
                }
                for produto in produtos
            ]
            itens.sort(key=lambda item: item["nota"], reverse=True)
            Clock.schedule_once(lambda _dt: self._mostrar_itens(itens[:20]), 0)
        except Exception as erro:
            Clock.schedule_once(lambda _dt: self.mostrar_erro(str(erro)), 0)

    def _mostrar_itens(self, itens):
        self.lista.clear_widgets()
        self.status.text = (
            f"{len(itens)} oportunidades encontradas "
            "(Mercado Livre indisponivel no momento - limitacao da API)"
        )

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
            self.lista.add_widget(self._criar_card(item))

    def _criar_card(self, item):
        card = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(290),
            padding=[dp(15), dp(12), dp(15), dp(12)],
            spacing=dp(6),
        )

        card.add_widget(
            Label(
                text=item["plataforma"].upper(),
                size_hint_y=None,
                height=dp(28),
                font_size=sp(15),
                color=COR_LARANJA,
            )
        )

        card.add_widget(
            rotulo_multilinha(item["nome"], height=dp(64), font_size=sp(16), valign="middle", color=COR_TEXTO)
        )

        linhas = [
            f"Preco: R$ {item['preco']:.2f}",
            f"Comissao: {item['comissao_texto']}",
            f"Vendas: {item['vendas']:,}".replace(",", "."),
            f"Nota: {item['nota']:.1f} / 100",
        ]
        card.add_widget(rotulo_multilinha("\n".join(linhas), height=dp(110)))

        link = item.get("link") or ""
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
        campanha.bind(on_release=lambda _b, it=item: mostrar_popup_campanha(it))
        card.add_widget(campanha)

        return card
