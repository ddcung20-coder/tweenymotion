#!/usr/bin/env python3
"""claude.ai 아티팩트용 빌드.

아티팩트 안에서는 외부 fetch(Hugging Face, CDN)와 서비스 워커가 막혀 있으므로
ONNX Runtime wasm과 모델을 15MB 미만 조각으로 나눠 페이지 옆에 함께 올린다.
사용법: python3 tools/build-artifact.py <출력 폴더> [RMBG-1.4 int8 .onnx 경로]
"""
import json, os, re, shutil, sys

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1]
RMBG = sys.argv[2] if len(sys.argv) > 2 else None
CHUNK = 14 * 1024 * 1024
RMBG_URL = 'https://huggingface.co/briaai/RMBG-1.4/resolve/main/onnx/model_quantized.onnx'

shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(os.path.join(OUT, 'ort'))
os.makedirs(os.path.join(OUT, 'parts'))

def split(src, name):
    paths = []
    with open(src, 'rb') as f:
        i = 0
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            rel = f'parts/{name}.{i}.wasm'  # .wasm: 아티팩트가 그대로 서비스하는 바이너리 형식
            with open(os.path.join(OUT, rel), 'wb') as o:
                o.write(b)
            paths.append(rel)
            i += 1
    return paths

parts = {
    'models/mobile_sam.encoder.onnx': split(os.path.join(SRC, 'models/mobile_sam.encoder.onnx'), 'sam-encoder'),
    'models/sam_decoder.onnx': split(os.path.join(SRC, 'models/sam_decoder.onnx'), 'sam-decoder'),
}
if RMBG:
    parts[RMBG_URL] = split(RMBG, 'rmbg14-q8')
ort_parts = split(os.path.join(SRC, 'ort/ort-wasm-simd-threaded.asyncify.wasm'), 'ort-wasm')
for f in ['ort.webgpu.bundle.min.mjs', 'ort-wasm-simd-threaded.asyncify.mjs']:
    shutil.copy(os.path.join(SRC, 'ort', f), os.path.join(OUT, 'ort', f))
shutil.copy(os.path.join(SRC, 'engine.worker.js'), os.path.join(OUT, 'engine.worker.js'))

html = open(os.path.join(SRC, 'index.html'), encoding='utf-8').read()
# 아티팩트는 문서 골격을 직접 씌우므로 doctype/html/head/body 태그와 PWA 링크를 뺀다
html = re.sub(r'^<!doctype html>\s*<html[^>]*>\s*<head>\s*<meta charset="utf-8">\s*<meta name="viewport"[^>]*>\s*', '', html)
html = re.sub(r'<link rel="(manifest|icon|apple-touch-icon)"[^>]*>\n', '', html)
html = re.sub(r'<meta name="theme-color"[^>]*>\n', '', html)
html = html.replace('</head>\n<body>\n', '').replace('</body>\n</html>\n', '')
html = html.replace('.app{display:grid;grid-template-rows:auto 1fr auto;height:100dvh;height:100vh}\n@supports(height:100dvh){.app{height:100dvh}}',
                    '.app{display:grid;grid-template-rows:auto 1fr auto;height:100%}')
for a, b in [("const APP_MODE = 'site';", "const APP_MODE = 'artifact';"),
             ('const PARTS = {};', 'const PARTS = ' + json.dumps(parts) + ';'),
             ('const ORT_PARTS = null;', 'const ORT_PARTS = ' + json.dumps(ort_parts) + ';')]:
    assert a in html, a
    html = html.replace(a, b)
open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(html)
total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(OUT) for f in fs)
print(json.dumps({'files': sorted(os.path.relpath(os.path.join(dp, f), OUT) for dp, _, fs in os.walk(OUT) for f in fs), 'totalMB': round(total / 2**20, 1)}, ensure_ascii=False, indent=1))
