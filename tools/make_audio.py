"""依 audio/讀稿.md 產生語音檔與 audio/manifest.json。

用法（在 repo 根目錄）：
  pip install edge-tts
  python tools/make_audio.py                  # 只重產內容有變的段落
  python tools/make_audio.py --only parking-1 # 只產指定段落（可多個）
  python tools/make_audio.py --sample         # 用同一段產幾種聲音的試聽檔到 audio/_sample/
  python tools/make_audio.py --check          # 不產檔，只檢查讀稿、manifest、網頁按鈕是否一致

規則：
- 讀稿每段 `## 段落ID`，段內以「（按鈕位置…）」開頭的行是註解，不念。
- manifest 的值 = 讀稿內容＋聲音＋語速的雜湊；任何一項改了，該段才會重產。
- 網頁只為 manifest 裡有的段落顯示「▶ 聽」按鈕。
"""
import argparse, asyncio, hashlib, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "audio" / "讀稿.md"
MANIFEST = ROOT / "audio" / "manifest.json"
HTML = ROOT / "index.html"

VOICE = "zh-TW-HsiaoChenNeural"   # 選定聲音後改這裡
RATE = "-5%"                       # 長輩聽，預設略慢；網頁另有「念慢一點」0.85 倍
SAMPLE_VOICES = ["zh-TW-HsiaoChenNeural", "zh-TW-HsiaoYuNeural", "zh-TW-YunJheNeural"]
SAMPLE_ID = "parking-1"


def load_segments():
    text = SCRIPT.read_text(encoding="utf-8")
    segs = {}
    for sid, body in re.findall(r"^## (\S+)\n(.*?)(?=^## |\Z)", text, re.S | re.M):
        lines = [l.strip() for l in body.splitlines()]
        lines = [l for l in lines if l and l != "---" and not l.startswith("（按鈕位置")]
        segs[sid] = "\n".join(lines)
    if not segs:
        sys.exit("讀稿裡找不到任何 ## 段落")
    return segs


def digest(text, voice, rate):
    return hashlib.sha256(f"{voice}|{rate}|{text}".encode("utf-8")).hexdigest()[:10]


async def synth(text, voice, rate, out):
    import edge_tts
    out.parent.mkdir(parents=True, exist_ok=True)
    await edge_tts.Communicate(text, voice, rate=rate).save(str(out))
    if out.stat().st_size < 1000:
        raise RuntimeError(f"{out.name} 檔案太小，產生失敗")


def check(segs, manifest):
    page_ids = set(re.findall(r'data-audio="([\w-]+)"', HTML.read_text(encoding="utf-8")))
    problems = []
    if page_ids != set(segs):
        problems.append(f"網頁按鈕與讀稿不一致：只在網頁 {sorted(page_ids - set(segs))}；只在讀稿 {sorted(set(segs) - page_ids)}")
    for sid, text in segs.items():
        if manifest.get(sid) != digest(text, VOICE, RATE):
            problems.append(f"{sid}：讀稿已改但音檔未重產")
        if not (ROOT / "audio" / f"{sid}.mp3").exists():
            problems.append(f"{sid}：缺音檔")
    for sid in set(manifest) - set(segs):
        problems.append(f"manifest 多出 {sid}（讀稿已刪）")
    for p in problems:
        print("FAIL", p)
    print(f"結果：{len(problems)} 個問題，共 {len(segs)} 段")
    return not problems


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    segs = load_segments()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}

    if a.check:
        sys.exit(0 if check(segs, manifest) else 1)

    if a.sample:
        for v in SAMPLE_VOICES:
            out = ROOT / "audio" / "_sample" / f"{SAMPLE_ID}_{v}.mp3"
            await synth(segs[SAMPLE_ID], v, RATE, out)
            print("試聽檔", out.relative_to(ROOT))
        return

    targets = a.only or list(segs)
    for sid in targets:
        if sid not in segs:
            sys.exit(f"讀稿裡沒有 {sid}")
        h = digest(segs[sid], VOICE, RATE)
        out = ROOT / "audio" / f"{sid}.mp3"
        if not a.only and manifest.get(sid) == h and out.exists():
            continue
        await synth(segs[sid], VOICE, RATE, out)
        manifest[sid] = h
        print("產生", out.name)

    for sid in list(manifest):
        if sid not in segs:
            del manifest[sid]
            (ROOT / "audio" / f"{sid}.mp3").unlink(missing_ok=True)
            print("移除", sid)
    MANIFEST.write_text(json.dumps(dict(sorted(manifest.items())), ensure_ascii=False, indent=1), encoding="utf-8")
    check(segs, manifest)


if __name__ == "__main__":
    asyncio.run(main())
