# Background Eraser

브라우저에서 바로 배경을 지우는 독립 앱입니다. 사진은 기기 밖으로 나가지 않고, 모델을 한 번 받으면 오프라인에서도 작동합니다.

## 기능
- **AI 모델** ("AI 엔진" 탭에서 선택)
  - BiRefNet Lite: 추천, 범용 고품질 (MIT, fp16 115MB / fp32 224MB)
  - BiRefNet: 최고 품질, GPU가 있는 PC용 (MIT, fp16 490MB)
  - RMBG-1.4: 빠름, 저사양 기기용 (비상업 라이선스, int8 44MB)
  - MODNet: 인물 전용 초경량 (Apache-2.0, 26MB, 항상 CPU에서 실행)
- **품질 파이프라인**: 좌우 반전 앙상블(TTA) → 가이디드 필터로 원본 해상도 경계 보정 → Blur-Fusion 전경색 추정으로 배경색 번짐 제거
- **AI 선택 브러시**: "AI 남기기"로 남길 물체 위를 칠하면 AI(MobileSAM)가 윤곽을 찾아 나머지를 모두 지우고, "AI 빼기"로 칠한 물체는 통째로 지웁니다. 경계의 머리카락 같은 세부는 누끼 모델 결과를 살려 합칩니다. 이 모델(43MB)은 앱에 들어 있어 처음부터 오프라인으로 작동합니다.
- **편집**: 경계 선명도·이동·부드럽게, 잡티 제거, 구멍 메우기, 복원/지우기 브러시(경도 조절), 되돌리기, 원본 비교, 확대·이동
- **배경**: 투명, 단색, 원본 흐림, 사진, 바닥 그림자
- **저장**: PNG/WebP/JPG, 피사체에 맞춰 자르기, 크기 조절, 클립보드 복사, 여러 장 일괄 처리 후 ZIP 저장

## 배포
HTTPS로 서비스되는 정적 호스팅(GitHub Pages, Netlify, Cloudflare Pages 등)에 이 폴더를 그대로 올리면 됩니다. 빌드 과정은 없습니다.

- 처음 방문할 때 서비스 워커(`sw.js`)가 앱 파일과 ONNX Runtime을 저장합니다.
- 선택한 모델은 Hugging Face에서 한 번 내려받아 브라우저의 Cache Storage에 보관합니다.
- 그 뒤로는 인터넷 없이 작동합니다. 홈 화면에 앱(PWA)으로 추가할 수도 있습니다.
- 완전한 오프라인 환경이라면, 미리 받아 둔 모델 파일을 모델 카드의 ".onnx 파일로 불러오기" 버튼으로 넣으면 됩니다.
- `file://`로 직접 열면 작동하지 않습니다. HTTPS나 `localhost`로 열어 주세요.

## 구성
| 파일 | 역할 |
| --- | --- |
| `index.html` | 화면, 편집·합성, 저장 |
| `engine.worker.js` | 모델 추론(WebGPU/WASM)과 경계·색 보정 |
| `sw.js` | 오프라인 캐시, CPU 멀티스레드 추론용 cross-origin isolation |
| `ort/` | ONNX Runtime Web 1.31.1 (MIT) |
| `models/` | MobileSAM 이미지 인코더 + SAM 마스크 디코더 (Apache-2.0, `@geti-ui/smart-tools` 1.7.1에서 가져옴) |
| `tools/build-artifact.py` | claude.ai 아티팩트용 빌드 (외부 다운로드가 막힌 환경이라 런타임·모델을 조각 파일로 함께 올림) |
