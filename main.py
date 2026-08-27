from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager

import android_integracao
from tela_principal import TelaPrincipal
from tela_shopee import TelaShopee
from tela_manual import TelaManualPlataforma
from tela_geral import TelaGeral
from tela_biblioteca import TelaBiblioteca

Window.clearcolor = (0.025, 0.03, 0.04, 1)

AVISO_ML = (
    "Busca automatica indisponivel: a API do Mercado Livre nao "
    "libera preco/nome de anuncio para apps de terceiros no momento. "
    "Cole o link do produto abaixo."
)


class RadarAfiliadosApp(App):
    def build(self):
        self.manager = ScreenManager()
        self.manager.add_widget(TelaPrincipal(name="principal"))
        self.manager.add_widget(TelaShopee(name="shopee"))
        self.manager.add_widget(
            TelaManualPlataforma("Mercado Livre", aviso=AVISO_ML, name="mercado_livre")
        )
        self.manager.add_widget(TelaManualPlataforma("Amazon", name="amazon"))
        self.manager.add_widget(TelaManualPlataforma("Shein", name="shein"))
        self.manager.add_widget(TelaManualPlataforma("Temu", name="temu"))
        self.manager.add_widget(TelaGeral(name="geral"))
        self.manager.add_widget(TelaBiblioteca(name="biblioteca"))
        return self.manager

    def on_start(self):
        self._segurar_referencia_permissao = android_integracao.PermissoesMidia(
            self._apos_permissao_midia
        )

    def _apos_permissao_midia(self):
        self._segurar_referencia_permissao = None
        tela_biblioteca = self.manager.get_screen("biblioteca")
        self._recebedor_compartilhamento = android_integracao.RecebedorDeCompartilhamento(
            tela_biblioteca.midia_recebida
        )


if __name__ == "__main__":
    RadarAfiliadosApp().run()
