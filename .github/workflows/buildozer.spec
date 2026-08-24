[app]
title = Radar Afiliados
package.name = radarafiliados
package.domain = org.keiti.radar

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0

requirements = python3,kivy,requests,certifi

orientation = portrait
fullscreen = 0

# Permissao de internet, necessaria para buscar produtos nas APIs
android.permissions = INTERNET

android.api = 34
android.minapi = 21
android.archs = arm64-v8a
android.accept_sdk_license = True

log_level = 2

[buildozer]
warn_on_root = 1
