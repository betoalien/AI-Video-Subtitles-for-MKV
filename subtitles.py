import subprocess, json, sys

video = sys.argv[1] if len(sys.argv) > 1 else "A Possession in Lincoln County 2026 1080p FoundTV WEB-DL AAC2 0 H 264-BobDobbs.mkv"

# Ver qué pistas de subtítulos hay
info = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "s",
     "-show_entries", "stream=index,codec_name:stream_tags=language,title",
     "-of", "json", video],
    capture_output=True, text=True
)
streams = json.loads(info.stdout).get("streams", [])

if not streams:
    print("No hay pistas de subtítulos (pueden estar 'quemados' en la imagen).")
    sys.exit()

ext_map = {"subrip": "srt", "ass": "ass", "ssa": "ssa", "webvtt": "vtt",
           "hdmv_pgs_subtitle": "sup", "dvd_subtitle": "sub"}

for i, s in enumerate(streams):
    codec = s["codec_name"]
    lang = s.get("tags", {}).get("language", "und")
    ext = ext_map.get(codec, "mks")
    out = f"{video.rsplit('.', 1)[0]}.{lang}.{i}.{ext}"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video,
                    "-map", f"0:s:{i}", "-c", "copy", out])
    print(f"✔ {out}  ({codec}, {lang})")