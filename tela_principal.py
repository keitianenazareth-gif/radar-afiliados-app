"""Hub inicial: um card de navegacao por plataforma, mais o atalho pra
Visao Geral."""

from kivy.app import App
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from ui_comum import COR_AMARELO, COR_FUNDO_CARD, COR_SECUNDARIA, COR_TEXTO


class TelaPrincipal(Screen):
    PLATAFORMAS = [
        ("shopee", "SHOPEE", "Busca automatica e campanhas com IA"),
        ("mercado_livre", "MERCADO LIVRE", "Cole o link do produto"),
        ("amazon", "AMAZON", "Cole o link do produto"),
        ("shein", "SHEIN", "Cole o link do produto"),
        ("temu", "TEMU", "Cole o link do produto"),
        ("biblioteca", "📚 BIBLIOTECA", "Videos e imagens salvos pra postar"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = BoxLayout(
            orientation="vertical",
            padding=[dp(18), dp(18), dp(18), dp(16)],
            spacing=dp(10),
        )

        layout.add_widget(
            Label(
                text="RADAR AFILIADOS",
                size_hint_y=None,
                height=dp(42),
                font_size=sp(24),
                color=COR_TEXTO,
            )
        )
        layout.add_widget(
            Label(
                text="Escolha uma plataforma para comecar",
                size_hint_y=None,
                height=dp(28),
                font_size=sp(13),
                color=COR_SECUNDARIA,
            )
        )

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

        for tela, nome, descricao in self.PLATAFORMAS:
            layout.add_widget(self._card_plataforma(tela, nome, descricao))

        layout.add_widget(Widget())
        self.add_widget(layout)

    def _card_plataforma(self, tela, nome, descricao):
        botao = Button(
            text=f"{nome}\n{descricao}",
            size_hint_y=None,
            height=dp(88),
            font_size=sp(17),
            halign="left",
            valign="middle",
            background_normal="",
            background_color=COR_FUNDO_CARD,
            color=COR_TEXTO,
        )
        botao.bind(
            size=lambda inst, tam: setattr(inst, "text_size", (tam[0] - dp(30), tam[1]))
        )
        botao.bind(on_release=lambda _b, t=tela: self.abrir_plataforma(t))
        return botao

    def abrir_plataforma(self, nome_tela):
        app = App.get_running_app()
        tela = app.manager.get_screen(nome_tela)
        if hasattr(tela, "resetar"):
            tela.resetar()
        app.manager.current = nome_tela

    def abrir_geral(self, _botao):
        app = App.get_running_app()
        app.manager.get_screen("geral").iniciar_busca()
        app.manager.current = "geral"
