# FFXIV 글로벌 한글 폰트 패치 (고해상도판)

구 글로벌 클라이언트 한글 폰트 패치 시 영문 및 일본어 등 각종 폰트가 열화되는 문제를 해결한 새 한글 폰트 패치입니다.

<!-- 일반 사용자용 -->

## 설치

1. 구 한글 채팅 패치를 사용 중인 경우 `C:\Program Files (x86)\SquareEnix\FINAL FANTASY XIV - A Realm Reborn\game`에서 `dinput8.dll`과 `data` 폴더를 삭제합니다.
2. `FFXIVGlobalKr` 폴더 안의 `dinput8.dll`과 `koreanfont` 폴더를 게임 설치 경로(기본적으로 `C:\Program Files (x86)\SquareEnix\FINAL FANTASY XIV - A Realm Reborn\game`)에 복사해 넣으시면 됩니다. (Steam판은 `steamapps\common\FINAL FANTASY XIV Online\game`)
   ```
   FINAL FANTASY XIV - A Realm Reborn\game\
     ffxiv_dx11.exe
     dinput8.dll
     koreanfont\000000.win32.dat
     koreanfont\files.txt
   ```
3. 게임을 재실행합니다. 정상적으로 실행될 경우 폰트 열화 현상이 사라지고 한글 채팅이 보이게 되며, `koreanfont\loader.log`에 `ready: 30 font files ...` 문구가 기록됩니다.

삭제할 때는 `dinput8.dll`과 `koreanfont` 폴더를 지우면 됩니다.

## 기존 패치에서 열화가 생기던 이유

기존 `dinput8.dll`은 실행할 때마다 다음 작업을 합니다.

- 게임의 `AXIS_12/14/18.fdt`에 `KrnAXIS_120/140/180`의 한글 글리프를 합칩니다.
- `font5/6/7.tex`를 `font_krn_1/2/3.tex`로 덮어씁니다.
- **`AXIS_36.fdt`를 한글이 합쳐진 18pt 폰트로 통째로 덮어씁니다.**

고해상도 UI는 AXIS_36 글리프로 글자를 그립니다. 그런데 AXIS_36 자리에 18pt 폰트가 들어가 있으니 한글뿐 아니라 영어, 일본어까지 18pt 글리프를 두 배로 늘려 그리게 되고, 그래서 글자가 흐려졌습니다.

## 변경점

- AXIS_36은 게임의 원래 36pt 글리프를 그대로 쓰고, 한글은 9.6, 12, 14, 18, 36pt 크기마다 그 크기에 맞는 글리프를 넣습니다.
  - **12/14/18/36pt:** 한국 서버와 똑같이 보이도록 한국 클라이언트 글리프(`KrnAXIS_120/140/180/360`)를 그대로 씁니다.
  - **9.6pt와 옛한글 자모 43자:** 한국 클라이언트에도 없어서 Source Han Sans K로 렌더링합니다.
  - Source Han Sans로 렌더링할 때는 Medium을 쓰고, 한국 클라이언트 글리프와 비슷해 보이도록 가로로 늘리고(12pt 1.11배, 18·36pt 1.04배) 위치를 옮겨 평균 잉크 영역을 맞춥니다.
- 한글 범위는 기존 패치와 같습니다. 완성형 11,172자에 호환 자모(ㄱ~ㆎ) 94자를 더했습니다.
- `font1~7.tex`를 2048×2048 8bit(B8G8R8A8)로 키웠습니다.
  - 게임의 기존 글리프는 좌상단 1024² 영역에 원래 좌표 그대로 두었고, 한글은 남는 공간에 배치했습니다.
  - 8bit라서 기존 4bit보다 안티앨리어싱이 부드럽습니다.
- AXIS_18과 AXIS_36은 문자 목록과 순서가 같도록 맞췄습니다. 게임이 AXIS_18의 글리프 순서를 기준으로 AXIS_36 글리프를 고르기 때문에 반드시 일치해야 합니다.
- 게임 파일은 수정하지 않습니다.
  - 새 `dinput8.dll`은 게임이 `000000.win32.index`/`index2`를 열 때 수정된 사본을 대신 열게 합니다. 사본에서는 폰트 30개 항목만 `koreanfont\000000.win32.dat`을 가리킵니다.
  - 사본은 실행할 때마다 실제 인덱스로 새로 만들기 때문에 게임이 패치돼도 어긋나지 않습니다.

## 게임 내에서 폰트 업데이트가 이뤄지는 경우

로더는 게임이 업데이트돼도 정상적으로 동작합니다. 하지만 폰트 데이터는 빌드한 시점의 게임 폰트로 생성됩니다. 따라서 게임 패치로 인해 원본 폰트 파일이 변경되면 그 패치로 인해 새로 추가된 기호 등 일부 문자가 보이지 않을 수 있습니다. 이 경우 새 버전을 받거나 아래 방법으로 리빌드하면 정상적인 사용이 가능합니다. 게임 폴더에서 폰트 항목을 찾지 못하면 로더는 아무것도 바꾸지 않고, 그 내용은 `loader.log`에서 확인 가능합니다.

## 크레딧

본 프로젝트는 원본을 참조 및 바탕으로 한 새 폰트 로더 및 빌드 툴입니다.

- 원본: dlunch님 ([글로벌 클라이언트 한글채팅 패치](https://www.inven.co.kr/board/ff14/4338/4398))
- 한글 글리프: FINAL FANTASY XIV 한국 클라이언트 폰트 (© SQUARE ENIX / Actoz Soft)
- 대체 렌더링 폰트: Source Han Sans K (© Adobe, SIL Open Font License 1.1)
- 참고 자료: [FFXIV-FontChanger](https://github.com/Soreepeong/FFXIV-FontChanger), [xivres](https://github.com/Soreepeong/xivres) (Soreepeong, Apache-2.0) — 폰트 및 sqpack 형식 참고

## 라이선스

`modify/tools`와 `modify/loader`의 코드는 [MIT 라이선스](LICENSE)를 따릅니다.
배포 파일(`000000.win32.dat`)에 들어 있는 게임 폰트와 한국 클라이언트 글리프는 SQUARE ENIX / Actoz Soft의 저작물이며 MIT 라이선스 대상이 아닙니다.

## 고지

- FINAL FANTASY XIV는 SQUARE ENIX의 등록상표입니다. 이 프로젝트는 비공식이며 SQUARE ENIX와 관련이 없습니다.
- 외부 프로그램 사용은 게임 이용약관에 위배될 수 있으며, 사용에 따른 책임은 사용자에게 있습니다.

<!-- 빌드용 -->

## 리빌드

### 준비물

- 글로벌 서버 클라이언트
- Python 3
- [Source Han Sans](https://github.com/adobe-fonts/source-han-sans/releases)의 한국어 OTF(`SourceHanSansK-Medium.otf` 등)를 `font/OTF/Korean/`에 넣기

### 한국 클라이언트 폰트 준비

빌드할 PC에 `modify/krn` 폴더가 없는 경우 본 준비 작업이 필요합니다. 한국 클라이언트가 설치된 PC에서 Python만 있으면 실행할 수 있습니다(추가 패키지 필요 없음).

```
cd modify/tools
python export_krn.py "한국 클라이언트 설치 폴더"
```

- 결과는 `modify/krn`에 저장됩니다(`--out`으로 변경 가능). `KrnAXIS_120/140/180/360.fdt`와 이 폰트들이 쓰는 `font_krn_*.tex`가 들어갑니다.
- 다른 PC에서 폰트를 받아온 경우 그 폴더 및 파일을 빌드할 PC의 `modify/krn`에 복사합니다.
- 경로는 설치 폴더, `game` 폴더, 그 하위 폴더 중 어느 것을 줘도 됩니다. 글로벌 클라이언트에는 빈 자리표시자만 있어서, 글로벌 클라이언트를 지정하면 그 이유를 알려주고 멈춥니다.

### 빌드

```
cd modify/tools
pip install -r requirements.txt
python build_all.py            # 설치된 게임에서 폰트를 읽어 modify/FFXIVGlobalKr/koreanfont 생성
```

한국 서버 글리프는 `modify/krn`에서 불러옵니다. 폴더가 없으면 모든 크기를 Source Han Sans K로 렌더링합니다. 어느 소스를 썼는지는 빌드 로그 첫 줄에 표시됩니다.

- `--game <경로>`: 게임 폴더(`...\game`)가 기본 위치가 아닐 때 지정합니다.
- `--krn-dir <폴더>`: 한국 서버 폰트 폴더를 직접 지정합니다.
- `--krn-game <한국 클라이언트 경로>`: 같은 PC에 한국 클라이언트가 있으면 꺼내는 단계 없이 바로 읽습니다.
- `--no-krn`: 모든 한글 글리프를 Source Han Sans K로 렌더링합니다. 한국 클라이언트 에셋을 배포본에 넣지 않습니다.
- `--format b4g4r4a4`: 바닐라와 같은 4bit 포맷으로 만듭니다. 텍스처 VRAM이 112MB에서 56MB로 줄어듭니다(바닐라는 14MB).
- 빌드할 때 바닐라 글리프와 커닝이 그대로인지, 글리프끼리 겹치지 않는지, AXIS_18/36 목록이 같은지를 자동으로 검사합니다. 검사가 끝나면 `modify/preview.png`도 만듭니다.

| 파일 | 역할 |
|---|---|
| `modify/tools/build_font.py` | 게임 폰트를 읽고 한글을 렌더링해 병합합니다. 크기별 굵기·가로 배율·위치는 `KOREAN_FONTS`에 있고, 굵기만 바꿀 때는 `--weight AXIS_36=Regular`처럼 지정합니다. |
| `modify/tools/export_krn.py` | 한국 클라이언트에서 한국 서버 폰트를 꺼냅니다(표준 라이브러리만 사용). |
| `modify/tools/verify_build.py` | 빌드 결과를 검사하고 미리보기를 만듭니다. |
| `modify/tools/make_dat.py` | 결과물을 로더용 `.dat`과 `files.txt`로 묶습니다. |
| `modify/loader/dinput8.c` | 로더 소스입니다. |

로더 빌드에는 [Zig](https://ziglang.org/download/)(0.17.0으로 확인)를 씁니다.

```
cd modify/loader
zig cc -target x86_64-windows-gnu -shared -O2 -s -o dinput8.dll dinput8.c
```
