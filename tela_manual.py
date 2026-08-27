"""Pagina de entrada manual, reaproveitada para as plataformas sem busca
automatica funcional: Amazon, Shein, Temu e Mercado Livre (a API de busca
do ML nao expoe preco/nome via app de terceiros - ver mercado_livre.py).
Cola o link, o app tenta preencher nome/preco automaticamente via
og:title/og:image, e a pessoa confere antes de gerar a campanha."""

from threading import Thread

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from produto_manual import buscar_metadados_link
from ui_comum import (
    COR_LARANJA,
    COR_SECUNDARIA,
    COR_TEXTO,
    botao_voltar,
    campo_texto,
    mostrar_popup_campanha,
    rotulo_multilinha,
)
from kivy.uix.button import Button


class TelaManualPlataforma(Screen):
    """Uma instancia desta classe = a pagina de uma plataforma sem API
    de busca. Passe nome_plataforma e, opcionalmente, um aviso extra
    (usado no Mercado Livre pra explicar a ausencia de busca automatica)."""

    def __init__(self, nome_plataforma, aviso="", tela_anterior="principal", **kwargs):
        self.nome_plataforma = nome_plataforma
        self._tela_anterior = tela_anterior
        super().__init__(**kwargs)

        layout = BoxLayout(
            orientation="vertical",
            padding=[dp(18), dp(18), dp(18), dp(18)],
            spacing=dp(8),
        )
        layout.add_widget(botao_voltar(self.voltar))

        layout.add_widget(
            Label(
                text=nome_plataforma.upper(),
                size_hint_y=None,
                height=dp(38),
                font_size=sp(20),
                color=COR_TEXTO,
            )
        )

        if aviso:
            layout.add_widget(
                rotulo_multilinha(aviso, height=dp(56), font_size=sp(13))
            )

        self.campo_link = campo_texto("Cole o link do produto aqui...")
        layout.add_widget(self.campo_link)

        buscar = Button(
            text="🔍 BUSCAR DADOS AUTOMATICAMENTE",
            size_hint_y=None,
            height=dp(52),
            font_size=sp(14),
            background_normal="",
            background_color=(1, 0.80, 0.10, 1),
            color=(0.08, 0.08, 0.08, 1),
        )
        buscar.bind(on_release=self.buscar_dados)
        layout.add_widget(buscar)

        self.status_busca = rotulo_multilinha("", height=dp(40), font_size=sp(13))
        layout.add_widget(self.status_busca)

        self.campo_nome = campo_texto("Nome do produto")
        layout.add_widget(self.campo_nome)

        self.campo_preco = campo_texto("Preco (ex: 79,90)")
        layout.add_widget(self.campo_preco)

        self.campo_comissao = campo_texto("Comissao/observacao (opcional)")
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

        layout.add_widget(Widget())

        self.add_widget(layout)

    def resetar(self):
        self.campo_link.text = ""
        self.campo_nome.text = ""
        self.campo_preco.text = ""
        self.campo_comissao.text = ""
        self.status_busca.text = ""

    def buscar_dados(self, _botao):
        link = self.campo_link.text.strip()
        if not link:
            self.status_busca.text = "Cole um link antes de buscar."
            return

        self.status_busca.text = "Buscando..."
        Thread(target=self._buscar_em_segundo_plano, args=(link,), daemon=True).start()

    def _buscar_em_segundo_plano(self, link):
        dados = buscar_metadados_link(link)
        Clock.schedule_once(lambda _dt: self._preencher_dados(dados), 0)

    def _preencher_dados(self, dados):
        if dados["sucesso"]:
            self.campo_nome.text = dados["nome"]
            if dados["preco_texto"]:
                self.campo_preco.text = dados["preco_texto"]
            self.status_busca.text = "Dados encontrados. Confira antes de continuar."
        else:
            self.status_busca.text = dados["motivo"]

    def criar_campanha(self, _botao):
        nome = self.campo_nome.text.strip()
        link = self.campo_link.text.strip()

        if not nome or not link:
            self.status_busca.text = "Preencha ao menos o nome do produto e o link."
            return

        item = {
            "plataforma": self.nome_plataforma,
            "nome": nome,
            "preco_texto": self.campo_preco.text.strip(),
            "comissao_texto": self.campo_comissao.text.strip(),
            "link": link,
        }
        mostrar_popup_campanha(item)

    def voltar(self, _botao):
        from kivy.app import App

        App.get_running_app().manager.current = self._tela_anterior
