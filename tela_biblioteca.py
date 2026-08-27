"""Biblioteca: video e imagens salvos no app, cada um com os destinos de
postagem marcados. Importa da galeria ou recebe compartilhamento de
outros apps (Telegram etc - ver android_integracao.py), e manda
qualquer item direto pro WhatsApp."""

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label

import android_integracao
import biblioteca
from ui_comum import (
    COR_AMARELO,
    COR_FUNDO_CARD,
    COR_LARANJA,
    COR_SECUNDARIA,
    COR_TEXTO,
    TelaComLista,
    campo_texto,
    rotulo_multilinha,
)


class TelaBiblioteca(TelaComLista):
    def __init__(self, **kwargs):
        super().__init__("📚 BIBLIOTECA", **kwargs)

    def montar_corpo_extra(self, layout):
        linha_importar = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(8)
        )
        botao_imagem = Button(
            text="🖼️ IMPORTAR IMAGEM",
            font_size=sp(13),
            background_normal="",
            background_color=COR_FUNDO_CARD,
            color=COR_TEXTO,
        )
        botao_imagem.bind(on_release=lambda _b: self.importar("imagem"))
        linha_importar.add_widget(botao_imagem)

        botao_video = Button(
            text="🎬 IMPORTAR VIDEO",
            font_size=sp(13),
            background_normal="",
            background_color=COR_FUNDO_CARD,
            color=COR_TEXTO,
        )
        botao_video.bind(on_release=lambda _b: self.importar("video"))
        linha_importar.add_widget(botao_video)
        layout.add_widget(linha_importar)

        linha_destino = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(8)
        )
        self.campo_novo_destino = campo_texto("Novo destino (ex: TikTok)...", height=dp(52))
        linha_destino.add_widget(self.campo_novo_destino)

        botao_add_destino = Button(
            text="+",
            size_hint_x=None,
            width=dp(52),
            background_normal="",
            background_color=COR_AMARELO,
            color=(0.08, 0.08, 0.08, 1),
        )
        botao_add_destino.bind(on_release=self.adicionar_destino)
        linha_destino.add_widget(botao_add_destino)
        layout.add_widget(linha_destino)

    def on_pre_enter(self):
        self.atualizar_lista()

    def importar(self, tipo):
        self.status.text = "Abrindo galeria..."
        android_integracao.importar_da_galeria(tipo, self._apos_importar)

    def _apos_importar(self, item):
        if item is None:
            self.status.text = "Importacao cancelada ou indisponivel (so funciona no celular)."
            return
        self.status.text = "Item importado."
        self.atualizar_lista()

    def adicionar_destino(self, _botao):
        nome = self.campo_novo_destino.text.strip()
        if not nome:
            return
        biblioteca.adicionar_destino(nome)
        self.campo_novo_destino.text = ""
        self.atualizar_lista()

    def midia_recebida(self, item):
        self.status.text = "Nova midia recebida por compartilhamento."
        self.atualizar_lista()

    def atualizar_lista(self):
        itens = biblioteca.listar_itens()
        self.status.text = f"{len(itens)} itens na biblioteca"
        self.lista.clear_widgets()

        if not itens:
            self.lista.add_widget(
                Label(
                    text="Nenhuma midia ainda.\nImporte da galeria ou compartilhe pro app.",
                    size_hint_y=None,
                    height=dp(100),
                    font_size=sp(15),
                    halign="center",
                    color=COR_SECUNDARIA,
                )
            )
            return

        for item in itens:
            self.lista.add_widget(self._criar_card(item))

    def _criar_card(self, item):
        destinos = biblioteca.listar_destinos()
        altura = dp(300) + dp(40) * ((len(destinos) + 2) // 3)

        card = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=altura,
            padding=[dp(15), dp(12), dp(15), dp(12)],
            spacing=dp(6),
        )

        card.add_widget(self._preview(item))

        card.add_widget(
            rotulo_multilinha(
                item.get("nome_original", ""),
                height=dp(30),
                font_size=sp(13),
                color=COR_SECUNDARIA,
            )
        )

        card.add_widget(Label(text="Postar em:", size_hint_y=None, height=dp(24), font_size=sp(12), color=COR_SECUNDARIA, halign="left"))

        grade_destinos = self._grade_destinos(item, destinos)
        card.add_widget(grade_destinos)

        linha_acoes = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8))

        whatsapp = Button(
            text="📤 ENVIAR WHATSAPP",
            font_size=sp(13),
            background_normal="",
            background_color=(0.14, 0.62, 0.31, 1),
            color=COR_TEXTO,
        )
        whatsapp.bind(on_release=lambda _b, it=item: self._enviar_whatsapp(it))
        linha_acoes.add_widget(whatsapp)

        excluir = Button(
            text="EXCLUIR",
            font_size=sp(13),
            size_hint_x=None,
            width=dp(90),
            background_normal="",
            background_color=COR_FUNDO_CARD,
            color=COR_TEXTO,
        )
        excluir.bind(on_release=lambda _b, it=item: self._excluir(it))
        linha_acoes.add_widget(excluir)

        card.add_widget(linha_acoes)

        return card

    def _preview(self, item):
        if item["tipo"] == "imagem":
            return Image(source=biblioteca.caminho_completo(item), size_hint_y=None, height=dp(160))

        caminho_thumb = biblioteca.caminho_thumbnail(item)
        if caminho_thumb:
            return Image(source=caminho_thumb, size_hint_y=None, height=dp(160))

        return Label(
            text="🎬 VIDEO",
            size_hint_y=None,
            height=dp(160),
            font_size=sp(22),
            color=COR_SECUNDARIA,
        )

    def _grade_destinos(self, item, destinos):
        linhas = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        linhas.height = dp(40) * ((len(destinos) + 2) // 3) if destinos else dp(30)

        if not destinos:
            linhas.add_widget(Label(text="Nenhum destino cadastrado ainda.", size_hint_y=None, height=dp(30), font_size=sp(12), color=COR_SECUNDARIA))
            return linhas

        for inicio in range(0, len(destinos), 3):
            linha = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(6))
            for destino in destinos[inicio:inicio + 3]:
                ativo = destino in item.get("destinos", [])
                botao = Button(
                    text=destino,
                    font_size=sp(12),
                    background_normal="",
                    background_color=COR_LARANJA if ativo else COR_FUNDO_CARD,
                    color=COR_TEXTO,
                )
                botao.bind(
                    on_release=lambda _b, it=item, d=destino: self._alternar_destino(it, d)
                )
                linha.add_widget(botao)
            linhas.add_widget(linha)

        return linhas

    def _alternar_destino(self, item, destino):
        biblioteca.alternar_destino(item["id"], destino)
        self.atualizar_lista()

    def _excluir(self, item):
        biblioteca.remover_item(item["id"])
        self.atualizar_lista()

    def _enviar_whatsapp(self, item):
        self.status.text = "Abrindo WhatsApp..."
        caminho = biblioteca.caminho_completo(item)
        android_integracao.enviar_para_whatsapp(caminho, self._apos_enviar_whatsapp)

    def _apos_enviar_whatsapp(self, sucesso, mensagem):
        self.status.text = "Enviado." if sucesso else mensagem
