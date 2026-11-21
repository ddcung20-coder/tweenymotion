#!/usr/bin/env python3
"""단일 HTML 파일 빌드: 더블클릭으로 열어 쓰는 background-eraser.html 을 만든다.

엔진 워커를 페이지 안에 넣고, ONNX Runtime·AI 선택 모델은 CDN(jsDelivr, 실패 시 unpkg)에서,
배경 제거 모델은 Hugging Face에서 처음 한 번 받아 브라우저 저장소(IndexedDB)에 보관한다.
사용법: python3 tools/build-standalone.py [출력 경로]
"""
import base64, os, re, sys

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SRC, 'background-eraser.html')

html = open(os.path.join(SRC, 'index.html'), encoding='utf-8').read()
worker = open(os.path.join(SRC, 'engine.worker.js'), encoding='utf-8').read()
assert '</script' not in worker
# file://에서는 모듈 워커가 막혀 클래식 워커로 띄우므로 import.meta 를 쓰지 않게 바꾼다
HERE = "const here = (rel) => { try { return new URL(rel, import.meta.url).href; } catch (e) { return null; } };"
assert HERE in worker
worker = worker.replace(HERE, 'const here = () => null;')
assert 'import.meta' not in worker
icon = base64.b64encode(open(os.path.join(SRC, 'icon.svg'), 'rb').read()).decode()

html = re.sub(r'<link rel="manifest"[^>]*>\n', '', html)
html = re.sub(r'<link rel="apple-touch-icon"[^>]*>\n', '', html)
html = re.sub(r'<link rel="icon"[^>]*>', f'<link rel="icon" href="data:image/svg+xml;base64,{icon}" type="image/svg+xml">', html)
a = "const APP_MODE = 'site';"
assert a in html
html = html.replace(a, "const APP_MODE = 'standalone';")
html = html.replace('<script type="module">', '<script type="text/plain" id="engine-src">\n' + worker + '</script>\n<script type="module">', 1)
open(OUT, 'w', encoding='utf-8').write(html)
print(OUT, round(os.path.getsize(OUT) / 1024), 'KB')
