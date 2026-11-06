"""Video Subtitles Translator — GUI.
MKV → extracts the first English text track → detects language → translates (NVIDIA / Ollama) → saves next to the MKV."""
import os, sys, threading, subprocess, shutil, platform
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT, ".env"))

from core import media, languages                     # noqa: E402
from core.subformat import Subtitle                   # noqa: E402
from core.translator import Translator                # noqa: E402
from core.languages import detect_language            # noqa: E402

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Video Subtitles Translator")
        self.geometry("720x560"); self.minsize(620, 500)
        self.video_path = self.video_dir = None
        self.sub = self.sub_fmt = self.source = None
        self.targets = []
        self._build()
        self.after(200, self.check_ffmpeg)

    # ---------- UI
    def _build(self):
        pad = {"padx": 16, "pady": (10, 0)}
        ctk.CTkLabel(self, text="Video Subtitles Translator", font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w", padx=16, pady=(16, 4))

        row = ctk.CTkFrame(self, fg_color="transparent"); row.pack(fill="x", **pad)
        self.btn_open = ctk.CTkButton(row, text="Select MKV…", width=170, command=self.choose_file)
        self.btn_open.pack(side="left")
        self.lbl_file = ctk.CTkLabel(row, text="No file selected", anchor="w", text_color="gray70")
        self.lbl_file.pack(side="left", padx=12, fill="x", expand=True)

        self.lbl_lang = ctk.CTkLabel(self, text="LANGUAGE: —", font=ctk.CTkFont(size=16, weight="bold"), anchor="w")
        self.lbl_lang.pack(fill="x", **pad)
        self.lbl_track = ctk.CTkLabel(self, text="", anchor="w", text_color="gray70")
        self.lbl_track.pack(fill="x", padx=16)

        row2 = ctk.CTkFrame(self, fg_color="transparent"); row2.pack(fill="x", **pad)
        ctk.CTkLabel(row2, text="Translate to:").pack(side="left")
        self.cmb = ctk.CTkComboBox(row2, values=["—"], width=260, state="disabled")
        self.cmb.pack(side="left", padx=10)
        self.btn_go = ctk.CTkButton(row2, text="PROCEED", width=140, state="disabled",
                                    font=ctk.CTkFont(weight="bold"), command=self.proceed)
        self.btn_go.pack(side="right")

        self.bar = ctk.CTkProgressBar(self); self.bar.set(0); self.bar.pack(fill="x", **pad)
        self.lbl_prog = ctk.CTkLabel(self, text="", anchor="w"); self.lbl_prog.pack(fill="x", padx=16)
        self.logbox = ctk.CTkTextbox(self, height=220); self.logbox.pack(fill="both", expand=True, padx=16, pady=(6, 16))
        self.logbox.configure(state="disabled")

    def log(self, msg):
        def _w():
            self.logbox.configure(state="normal"); self.logbox.insert("end", msg + "\n")
            self.logbox.see("end"); self.logbox.configure(state="disabled")
        self.after(0, _w)

    def ui(self, fn, *a, **k):
        self.after(0, lambda: fn(*a, **k))

    # ---------- ffmpeg
    def check_ffmpeg(self):
        if media.ffmpeg_available():
            self.log("✔ ffmpeg detected"); return
        sysname = platform.system()
        cmd = {"Windows": ["winget", "install", "-e", "--id", "Gyan.FFmpeg"],
               "Darwin": ["brew", "install", "ffmpeg"]}.get(sysname)
        if cmd and shutil.which(cmd[0]) and messagebox.askyesno(
                "ffmpeg not found", f"ffmpeg is required.\nInstall it now with:\n{' '.join(cmd)}?"):
            self.log("Installing ffmpeg…")
            subprocess.run(cmd)
            messagebox.showinfo("ffmpeg", "Installation finished. Restart the application to continue.")
        else:
            messagebox.showwarning("ffmpeg not found",
                "Install ffmpeg and restart:\n• Windows: winget install Gyan.FFmpeg\n• macOS: brew install ffmpeg\n"
                "• Linux: sudo apt install ffmpeg  (or dnf/pacman)")
        self.btn_open.configure(state="disabled")
        self.log("✖ ffmpeg not available")

    # ---------- step 1: choose MKV (auto-extract and detect)
    def choose_file(self):
        path = filedialog.askopenfilename(title="Select the video",
                                          filetypes=[("Matroska", "*.mkv"), ("Video", "*.mkv *.mp4 *.m4v"), ("All files", "*.*")])
        if not path:
            return
        self.video_path = os.path.abspath(path)
        self.video_dir = os.path.dirname(self.video_path)
        self.lbl_file.configure(text=os.path.basename(path), text_color="white")
        self.cmb.configure(state="disabled"); self.btn_go.configure(state="disabled")
        self.lbl_lang.configure(text="LANGUAGE: analyzing…"); self.lbl_track.configure(text="")
        self.bar.set(0); self.lbl_prog.configure(text="")
        threading.Thread(target=self._analyze, daemon=True).start()

    def _analyze(self):
        try:
            streams = media.probe_subtitles(self.video_path)
            st = media.pick_track(streams)
            self.log(f"Subtitle tracks: {len(streams)} · using #{st['sub_index']} ({st['codec_name']})")
            path, self.sub_fmt = media.extract(self.video_path, st)
            self.sub = Subtitle(path, self.sub_fmt)
            tag = st.get("tags", {}).get("language")
            self.source, how = detect_language(tag, self.sub)
            self.targets = languages.targets_for(self.source)
            name = languages.ui_name(self.source) if self.source else "Unknown"
            title = st.get("tags", {}).get("title") or ""
            self.ui(self.lbl_lang.configure, text=f"LANGUAGE: {name}")
            self.ui(self.lbl_track.configure, text=f"Track {st['sub_index']} · {self.sub_fmt.upper()} · "
                    f"{len(self.sub.units)} lines · {how} {('· ' + title) if title else ''}")
            labels = [ui for _c, ui in self.targets]
            def _enable():
                self.cmb.configure(values=labels, state="readonly"); self.cmb.set(labels[0])
                self.btn_go.configure(state="normal")
            self.ui(_enable)
            self.log(f"✔ Subtitle extracted. Source language: {name}")
        except Exception as e:
            self.ui(self.lbl_lang.configure, text="LANGUAGE: —")
            self.log(f"✖ {e}")
            self.ui(messagebox.showerror, "Error", str(e))

    # ---------- step 2: PROCEED
    def proceed(self):
        label = self.cmb.get()
        target = next(c for c, ui in self.targets if ui == label)
        self.btn_go.configure(state="disabled"); self.btn_open.configure(state="disabled"); self.cmb.configure(state="disabled")
        threading.Thread(target=self._translate, args=(target,), daemon=True).start()

    def _progress(self, done, total):
        self.ui(self.bar.set, done / total)
        self.ui(self.lbl_prog.configure, text=f"{done}/{total} lines")

    def _translate(self, target):
        try:
            self.log(f"Translating to {languages.ui_name(target)}…")
            tr = Translator(self.source, target, log=self.log, progress=self._progress)
            result = self.sub.apply(tr.translate(self.sub.units))
            stem = os.path.splitext(os.path.basename(self.video_path))[0]
            out = os.path.join(self.video_dir, f"{stem}.{target}.{self.sub_fmt}")
            with open(out, "w", encoding="utf-8", newline="\n") as f:
                f.write(result)
            self.log(f"✔ Saved: {out}")
            self.ui(messagebox.showinfo, "Done", f"Subtitle saved to:\n{out}")
        except Exception as e:
            self.log(f"✖ {e}")
            self.ui(messagebox.showerror, "Error", str(e))
        finally:
            def _reset():
                self.btn_go.configure(state="normal"); self.btn_open.configure(state="normal")
                self.cmb.configure(state="readonly")
            self.ui(_reset)


if __name__ == "__main__":
    App().mainloop()
