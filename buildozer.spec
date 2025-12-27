[app]
title = Control de Cigarros
package.name = controldecigarros
package.domain = org.sergio
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1.0

requirements = python3,kivy,sqlite3

orientation = portrait
android.minapi = 26
android.api = 33

android.permissions =
android.archs = arm64-v8a,armeabi-v7a

android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
