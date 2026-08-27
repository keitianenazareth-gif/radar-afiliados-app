"""Integracao especifica do Android: pedir permissao de midia, receber
midia compartilhada por outro app (Telegram, etc via menu Compartilhar),
importar da galeria, enviar pro WhatsApp e gerar thumbnail real de
video. Baseado no padrao oficial da lib androidstorage4kivy (projeto
Android-for-Python) - https://github.com/Android-for-Python/androidstorage4kivy
e no exemplo share_receive_example do mesmo projeto.

Tudo aqui so roda de verdade no celular. Fora do Android (testes no PC),
cada funcao publica cai num fallback seguro em vez de quebrar - mas o
comportamento real (permissao, compartilhamento, thumbnail) so pode ser
validado gerando o APK e testando no aparelho."""

from kivy.utils import platform

ANDROID = platform == "android"

if ANDROID:
    from android import mActivity, activity, api_version
    from android.permissions import request_permissions, check_permission, Permission
    from jnius import autoclass, cast
    from androidstorage4kivy import SharedStorage, Chooser, ShareSheet

    Intent = autoclass("android.content.Intent")
    PACOTES_WHATSAPP = ["com.whatsapp", "com.whatsapp.w4b"]


# ---------------------------------------------------------------------------
# Permissoes de midia (imagem/video)
# ---------------------------------------------------------------------------

class PermissoesMidia:
    """Pede as permissoes de leitura de midia necessarias antes de ligar
    o resto da integracao Android. Uso:

        PermissoesMidia(app.iniciar_apos_permissao)

    A callback so e chamada quando a permissao e concedida (ou de
    imediato, fora do Android)."""

    def __init__(self, callback=None):
        self._callback = callback
        self._tentativas = 0
        self._permissoes = []

        if not ANDROID:
            if callback:
                callback()
            return

        if api_version < 33:
            self._permissoes = [Permission.READ_EXTERNAL_STORAGE]
        else:
            self._permissoes = [Permission.READ_MEDIA_IMAGES, Permission.READ_MEDIA_VIDEO]

        self._verificar([], [])

    def _verificar(self, _permissoes, _concedidas):
        from kivy.clock import Clock

        concedido = all(check_permission(p) for p in self._permissoes)
        if concedido:
            if self._callback:
                self._callback()
        elif self._tentativas < 2:
            self._tentativas += 1
            Clock.schedule_once(lambda _dt: request_permissions(self._permissoes, self._verificar))
        # Depois de 2 tentativas negadas, desiste silenciosamente - as
        # telas que dependem de midia vao mostrar erro na hora do uso.


# ---------------------------------------------------------------------------
# Receber midia compartilhada por outro app (Telegram, etc)
# ---------------------------------------------------------------------------

class RecebedorDeCompartilhamento:
    """Escuta o Intent de "Compartilhar" do Android (ACTION_SEND) pra
    imagem/video e entrega o arquivo, ja copiado pra dentro da pasta da
    Biblioteca, via callback(item). So funciona se o app tiver sido
    registrado como alvo de compartilhamento no AndroidManifest -
    ver buildozer.spec (android.manifest.intent_filters) e
    intent_filter_biblioteca.xml."""

    def __init__(self, callback):
        self._callback = callback
        if not ANDROID:
            return

        self._processar(mActivity.getIntent())
        activity.bind(on_new_intent=self._processar)

    def _processar(self, intent):
        if intent is None:
            return

        acao = intent.getAction()
        if acao != Intent.ACTION_SEND:
            return

        tipo_mime = intent.getType() or ""
        if tipo_mime.startswith("image/"):
            tipo = "imagem"
        elif tipo_mime.startswith("video/"):
            tipo = "video"
        else:
            return

        uri = intent.getParcelableExtra(Intent.EXTRA_STREAM)
        if uri is None:
            return

        from threading import Thread

        Thread(target=self._copiar_em_segundo_plano, args=(uri, tipo), daemon=True).start()

    def _copiar_em_segundo_plano(self, uri, tipo):
        from kivy.clock import Clock
        import biblioteca

        try:
            caminho_temporario = SharedStorage().copy_from_shared(uri)
            if not caminho_temporario:
                return
            item = biblioteca.adicionar_item(caminho_temporario, tipo)
        except Exception:
            return

        Clock.schedule_once(lambda _dt: self._callback(item), 0)


# ---------------------------------------------------------------------------
# Importar da galeria
# ---------------------------------------------------------------------------

def importar_da_galeria(tipo, callback):
    """tipo: 'imagem' ou 'video'. Abre o seletor nativo do Android;
    callback(item_ou_None) e chamada quando a pessoa escolhe (ou cancela).
    Fora do Android, chama callback(None) direto."""

    if not ANDROID:
        callback(None)
        return

    mime = "image/*" if tipo == "imagem" else "video/*"

    def ao_escolher(lista_uris):
        if not lista_uris:
            callback(None)
            return

        from threading import Thread

        Thread(target=_importar_em_segundo_plano, args=(lista_uris[0], tipo, callback), daemon=True).start()

    Chooser(ao_escolher).choose_content(mime, multiple=False)


def _importar_em_segundo_plano(uri, tipo, callback):
    from kivy.clock import Clock
    import biblioteca

    try:
        caminho_temporario = SharedStorage().copy_from_shared(uri)
        item = biblioteca.adicionar_item(caminho_temporario, tipo) if caminho_temporario else None
    except Exception:
        item = None

    Clock.schedule_once(lambda _dt: callback(item), 0)


# ---------------------------------------------------------------------------
# Enviar pro WhatsApp
# ---------------------------------------------------------------------------

def enviar_para_whatsapp(caminho_arquivo, ao_concluir):
    """Copia o arquivo privado pra area compartilhada (MediaStore) e
    abre o WhatsApp direto com ele anexado - sem passar pela folha de
    compartilhamento. Tenta o WhatsApp normal e, se nao encontrar,
    o WhatsApp Business. ao_concluir(sucesso, mensagem) e chamada ao final."""

    if not ANDROID:
        ao_concluir(False, "Envio direto so funciona no celular.")
        return

    from threading import Thread

    Thread(target=_enviar_em_segundo_plano, args=(caminho_arquivo, ao_concluir), daemon=True).start()


def _enviar_em_segundo_plano(caminho_arquivo, ao_concluir):
    from kivy.clock import Clock

    try:
        uri_compartilhado = SharedStorage().copy_to_shared(caminho_arquivo)
    except Exception as erro:
        Clock.schedule_once(lambda _dt: ao_concluir(False, f"Erro ao preparar o arquivo: {erro}"), 0)
        return

    if uri_compartilhado is None:
        Clock.schedule_once(lambda _dt: ao_concluir(False, "Nao foi possivel preparar o arquivo pra envio."), 0)
        return

    pacote_encontrado = None
    for pacote in PACOTES_WHATSAPP:
        try:
            mActivity.getPackageManager().getPackageInfo(pacote, 0)
            pacote_encontrado = pacote
            break
        except Exception:
            continue

    if pacote_encontrado is None:
        Clock.schedule_once(lambda _dt: ao_concluir(False, "WhatsApp nao encontrado neste aparelho."), 0)
        return

    try:
        ShareSheet().share_file(uri_compartilhado, app=pacote_encontrado)
        Clock.schedule_once(lambda _dt: ao_concluir(True, ""), 0)
    except Exception as erro:
        Clock.schedule_once(lambda _dt: ao_concluir(False, f"Erro ao abrir o WhatsApp: {erro}"), 0)


# ---------------------------------------------------------------------------
# Thumbnail real de video (primeiro frame)
# ---------------------------------------------------------------------------

def gerar_thumbnail_video(caminho_video, caminho_saida_jpg):
    """Extrai o primeiro frame do video como JPEG, usando a API de midia
    do proprio Android (MediaMetadataRetriever) - sem depender de ffmpeg
    no build. Retorna True se conseguiu, False caso contrario (inclusive
    fora do Android)."""

    if not ANDROID:
        return False

    MediaMetadataRetriever = autoclass("android.media.MediaMetadataRetriever")
    Bitmap = autoclass("android.graphics.Bitmap")
    CompressFormat = autoclass("android.graphics.Bitmap$CompressFormat")
    FileOutputStream = autoclass("java.io.FileOutputStream")

    retriever = MediaMetadataRetriever()
    try:
        retriever.setDataSource(caminho_video)
        bitmap = retriever.getFrameAtTime(0)
        if bitmap is None:
            return False

        saida = FileOutputStream(caminho_saida_jpg)
        bitmap.compress(CompressFormat.JPEG, 85, saida)
        saida.close()
        return True
    except Exception:
        return False
    finally:
        retriever.release()
