[app]
title = Radar Afiliados
package.name = radarafiliados
package.domain = org.keiti.radar

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,xml

version = 1.0

requirements = python3,kivy,requests,certifi,androidstorage4kivy

orientation = portrait
fullscreen = 0

# INTERNET: buscar produtos nas APIs.
# READ_EXTERNAL_STORAGE / READ_MEDIA_IMAGES / READ_MEDIA_VIDEO: importar
# midia da galeria pra Biblioteca (a permissao certa depende da versao do
# Android do aparelho - ver android_integracao.PermissoesMidia).
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,READ_MEDIA_IMAGES,READ_MEDIA_VIDEO

# Registra o app como alvo de "Compartilhar" do Android (ex: Telegram ->
# Compartilhar -> Radar Afiliados) pra imagem/video - ver
# android_integracao.RecebedorDeCompartilhamento.
android.manifest.intent_filters = intent_filter_biblioteca.xml

# <queries>, necessario desde o Android 11 pra o app conseguir checar se
# o WhatsApp (normal ou Business) esta instalado antes de abrir o envio
# direto - ver android_integracao.enviar_para_whatsapp.
android.extra_manifest_xml = extra_manifest.xml

android.api = 34
android.minapi = 21
android.archs = arm64-v8a
android.accept_sdk_license = True

log_level = 2

[buildozer]
warn_on_root = 1
