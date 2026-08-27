"""Widgets e helpers compartilhados entre as telas do Radar Afiliados:
cores, campo de texto padrao, botao voltar, tela-base com lista rolavel,
e o popup de "Criar campanha com IA" usado por todas as paginas de
plataforma (busca automatica e entrada manual)."""

from threading import Thread

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

COR_FUNDO_CARD = (0.11, 0.12, 0.16, 1)
COR_LARANJA = (1, 0.30, 0.03, 1)
COR_AMARELO = (1, 0.80, 0.10, 1)
COR_TEXTO = (1, 1, 1, 1)
COR_SECUNDARIA = (0.70, 0.72, 0.78, 1)
COR_CAMPO = (0.08, 0.10, 0.13, 1)


def botao_voltar(callback):
    botao = Button(
        text="< VOLTAR",
        size_hint_y=None,
        height=dp(52),
        font_size=sp(16),
        background_normal="",
        background_color=COR_FUNDO_CARD,
        color=COR_TEXTO,
    )
    botao.bind(on_release=callback)
    return botao


def campo_texto(hint_text, **kwargs):
    padrao = dict(
        multiline=False,
        size_hint_y=None,
        height=dp(56),
        font_size=sp(15),
        background_normal="",
        background_active="",
        background_color=COR_CAMPO,
        foreground_color=COR_TEXTO,
        hint_text_color=(0.55, 0.58, 0.64, 1),
        cursor_color=COR_LARANJA,
        padding=[dp(12), dp(15)],
    )
    padrao.update(kwargs)
    return TextInput(hint_text=hint_text, **padrao)


def rotulo_multilinha(texto="", **kwargs):
    """Label que quebra linha e cresce com o conteudo (bom pra listas
    de texto tipo 'Preco: ...\\nDesconto: ...')."""
    padrao = dict(
        size_hint_y=None,
        font_size=sp(14),
        halign="left",
        valign="top",
        color=COR_SECUNDARIA,
    )
    padrao.update(kwargs)
    label = Label(text=texto, **padrao)
    label.bind(size=lambda inst, tam: setattr(inst, "text_size", (tam[0], None)))
    return label


class TelaComLista(Screen):
    """Base para paginas com: botao voltar, titulo, status e uma lista
    rolavel de cards. Subclasses populam self.lista e podem sobrescrever
    montar_corpo_extra() pra inserir widgets entre o status e a lista
    (caixa de busca, botoes de filtro, etc)."""

    def __init__(self, titulo_tela, tela_anterior="principal", **kwargs):
        super().__init__(**kwargs)
        self._tela_anterior = tela_anterior

        layout = BoxLayout(
            orientation="vertical",
            padding=[dp(18), dp(18), dp(18), dp(18)],
            spacing=dp(10),
        )
        layout.add_widget(botao_voltar(self.voltar))

        self.titulo = Label(
            text=titulo_tela,
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

        self.montar_corpo_extra(layout)

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

    def montar_corpo_extra(self, layout):
        pass

    def mostrar_aguarde(self, mensagem="Aguarde alguns segundos..."):
        self.lista.clear_widgets()
        self.lista.add_widget(
            Label(
                text=mensagem,
                size_hint_y=None,
                height=dp(90),
                font_size=sp(17),
                color=COR_SECUNDARIA,
            )
        )

    def mostrar_erro(self, mensagem):
        self.status.text = "Nao foi possivel concluir a busca."
        self.lista.clear_widgets()
        self.lista.add_widget(
            rotulo_multilinha(mensagem, height=dp(180), font_size=sp(15), color=COR_TEXTO)
        )

    def voltar(self, _botao):
        App.get_running_app().manager.current = self._tela_anterior


def _texto_preco(item):
    preco = item.get("preco")
    if isinstance(preco, (int, float)):
        return f"{preco:.2f}"
    return str(item.get("preco_texto") or preco or "")


def mostrar_popup_campanha(item):
    """Gera e mostra a campanha de IA num popup, a partir de um dict com
    nome/preco/comissao_texto/vendas/link/plataforma. Usado tanto pelo
    botao de campanha direto no card (busca automatica) quanto pelo
    formulario manual (Amazon/Shein/Temu/Mercado Livre)."""

    conteudo = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))

    cabecalho = rotulo_multilinha(
        f"{item.get('plataforma', '')} - {item.get('nome', '')}",
        size_hint_y=None,
        height=dp(50),
        color=COR_SECUNDARIA,
    )
    conteudo.add_widget(cabecalho)

    resultado = rotulo_multilinha("Gerando campanha...", color=COR_TEXTO)
    resultado.bind(texture_size=lambda inst, tam: setattr(inst, "height", tam[1]))

    scroll = ScrollView(do_scroll_x=False)
    caixa_scroll = BoxLayout(orientation="vertical", size_hint_y=None)
    caixa_scroll.bind(minimum_height=caixa_scroll.setter("height"))
    caixa_scroll.add_widget(resultado)
    scroll.add_widget(caixa_scroll)
    conteudo.add_widget(scroll)

    fechar = Button(
        text="FECHAR",
        size_hint_y=None,
        height=dp(48),
        background_normal="",
        background_color=COR_FUNDO_CARD,
        color=COR_TEXTO,
    )
    conteudo.add_widget(fechar)

    popup = Popup(
        title="Criar campanha com IA",
        content=conteudo,
        size_hint=(0.92, 0.85),
    )
    fechar.bind(on_release=popup.dismiss)
    popup.open()

    def gerar_em_segundo_plano():
        try:
            from campanhas_ia import gerar_campanha

            texto = gerar_campanha(
                plataforma=item.get("plataforma", ""),
                produto=item.get("nome", ""),
                preco=_texto_preco(item),
                comissao=item.get("comissao_texto", ""),
                vendas=str(item.get("vendas", "") or ""),
                link=item.get("link", ""),
                observacoes=(
                    "Crie conteudo natural para afiliada. "
                    "Nao invente informacoes."
                ),
            )
        except ImportError:
            texto = (
                "O arquivo campanhas_ia.py nao foi encontrado "
                "nesta pasta do projeto."
            )
        except RuntimeError as erro:
            texto = str(erro)
        except Exception as erro:
            texto = f"Erro ao gerar campanha: {erro}"

        Clock.schedule_once(lambda _dt: setattr(resultado, "text", texto), 0)

    Thread(target=gerar_em_segundo_plano, daemon=True).start()
