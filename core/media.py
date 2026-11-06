"""ffmpeg/ffprobe: detection, track selection and extraction."""
import json, os, shutil, subprocess, tempfile, sys

TEXT_CODECS = {"subrip": "srt", "srt": "srt", "ass": "ass", "ssa": "ass",
               "webvtt": "srt", "mov_text": "srt", "text": "srt"}
IMAGE_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}

_NOWIN = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def ffmpeg_available() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def probe_subtitles(video: str) -> list[dict]:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "s",
         "-show_entries", "stream=index,codec_name:stream_tags=language,title"
         ":stream_disposition=forced,hearing_impaired,default",
         "-of", "json", video],
        capture_output=True, text=True, encoding="utf-8", errors="replace", **_NOWIN)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "ffprobe failed")
    streams = json.loads(r.stdout or "{}").get("streams", [])
    for i, s in enumerate(streams):
        s["sub_index"] = i  # relative index for -map 0:s:i
    return streams


def _is_plain(s: dict) -> bool:
    disp = s.get("disposition", {})
    title = (s.get("tags", {}).get("title") or "").lower()
    if disp.get("forced") or disp.get("hearing_impaired"):
        return False
    return not any(k in title for k in ("sdh", "forced", "forzad", "cc", "commentary", "signs"))


def pick_track(streams: list[dict]) -> dict:
    """First 'normal' English TEXT track; else first English text track; else first text track."""
    text = [s for s in streams if s.get("codec_name") in TEXT_CODECS]
    if not text:
        if any(s.get("codec_name") in IMAGE_CODECS for s in streams):
            raise RuntimeError("Only IMAGE subtitles found (PGS/VobSub). Not supported in this version.")
        raise RuntimeError("The MKV has no text subtitle tracks.")
    eng = [s for s in text if (s.get("tags", {}).get("language") or "").lower() in ("eng", "en")]
    for group in ([s for s in eng if _is_plain(s)], eng, [s for s in text if _is_plain(s)], text):
        if group:
            return group[0]


def extract(video: str, stream: dict) -> tuple[str, str]:
    """Extracts the track to a temp file. Returns (path, format 'srt'|'ass')."""
    fmt = TEXT_CODECS[stream["codec_name"]]
    out = os.path.join(tempfile.mkdtemp(prefix="vsub_"), f"track.{fmt}")
    codec = "copy" if stream["codec_name"] in ("subrip", "srt", "ass", "ssa") else "srt"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video,
                        "-map", f"0:s:{stream['sub_index']}", "-c:s", codec, out],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", **_NOWIN)
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(r.stderr.strip() or "ffmpeg could not extract the subtitle")
    return out, fmt
