# 🎬 Video Compressor - Training Videos

[🇧🇷 Português](README.md) | 🇺🇸 English

A desktop app for **Windows, macOS and Linux** that **compresses videos to an exact target size** (default **490 MB**, to fit a platform's 500 MB upload limit) and lets you **edit before compressing**: remove black borders (automatic or manual crop, with preview) and remove several time ranges. It shows the **bitrate estimate** before starting and lets you **cancel** the compression at any time.

> ℹ️ The app interface is in Brazilian Portuguese; button names below are translated, with the original label where it helps.

---

## ✅ Requirements

| Item | Version | How to install |
|---|---|---|
| System | Windows 10/11, macOS or Linux | Windows: `setup.bat` does everything · macOS/Linux: see [Running without the .bat files](#-running-without-the-bat-files-macos-linux-or-terminal) |
| Python | 3.8+ (setup installs 3.12) | `setup.bat` or [python.org](https://www.python.org/downloads/) |
| Libraries | `customtkinter`, `Pillow`, `CTkMessagebox` (listed in `requirements.txt`) | `setup.bat` (in a `.venv` virtual environment) |
| FFmpeg + FFprobe | any recent version | `setup.bat`, `install_ffmpeg.bat` or [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) |

> Manual Python install: check **"Add python.exe to PATH"** in the installer.
> Manual FFmpeg install: extract to `C:\ffmpeg\` and add `C:\ffmpeg\bin` to PATH.
> If `CTkMessagebox` is not installed, the app still works using the system's standard dialog boxes.
>
> The `.bat` files are a **shortcut for Windows users** who'd rather not use a terminal. On macOS, Linux (or Windows from a terminal), see [Running without the .bat files](#-running-without-the-bat-files-macos-linux-or-terminal).

---

## 🚀 How to use

1. **First time:** double-click `setup.bat` and wait while Python, the libraries and FFmpeg are installed. The libraries go into a virtual environment (the project's `.venv` folder) — your system Python is left untouched.
2. Double-click `start.bat` to open the app.
3. Under **📁 Input video**, click **📂 Browse** (*Procurar*) and pick the video. On the right you'll see size, duration, resolution, codec and bitrate (in **red** if over 500 MB, **green** otherwise) and the **🎯 Target** line with the video bitrate that will be used.
4. *(Optional)* Under **✂️ Crop / Cut borders**:
   - **🔍 Auto** → click **Detect black borders**. The manual fields are filled in automatically.
   - **✏️ Manual** → type how many pixels to cut from Top, Bottom, Left and Right.
   - Click **🖼️ Preview** to see the original and cropped frame side by side.
5. *(Optional)* Under **⏱️ Cut time ranges**, enter **From** and **To** (`HH:MM:SS` or `MM:SS`) and click **➕ Add** (or press **ENTER**) for each range to **remove**. To take a range off the list, select its row and click **🗑️ Remove** (with nothing selected, it removes the last one). **🧹 Clear** deletes all of them.
6. Under **⚙️ Compression**, set the **target size** (100–500 MB), the **mode** (🎯 Maximum Quality is the default) and the **📐 Resolution** (Original, 1080p, 720p or 480p). The estimate on the right updates instantly.
7. Click **🚀 Compress Video** and follow the progress and remaining time (ETA). To stop, click **❌ Cancel** — the partial output and temporary files are deleted.
8. When it finishes, the file `name_compressed.mp4` is saved **in the same folder as the original** and the app offers to open the folder.

> Target size, mode and resolution are remembered the next time you open the app.

---

## 💻 Running without the .bat files (macOS, Linux or terminal)

The Python code runs on all three systems; only the installation differs.

**1. Install FFmpeg and Python 3.8+ with Tkinter**

| System | Command |
|---|---|
| macOS (Homebrew) | `brew install ffmpeg python-tk` |
| Ubuntu / Debian | `sudo apt install ffmpeg python3-venv python3-tk` |
| Fedora | `sudo dnf install ffmpeg python3-tkinter` |
| Windows | `winget install Gyan.FFmpeg` and Python from [python.org](https://www.python.org/downloads/) |

**2. Create the virtual environment and install the dependencies**

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**3. Run the app**

```bash
python video_compressor.py
```

Next time, just activate `.venv` and run step 3.

> **macOS:** always open the app from Terminal, as above. Opened any other way, macOS may not load the Homebrew PATH and the app won't find FFmpeg.

**Tested systems:** Windows 10/11 is the main platform (with the `.bat` files) · Linux: tested · macOS: should work, but not tested yet.

---

## ⚙️ How compression works

### Bitrate formula

```
duration     = video duration after removing ranges (seconds)
total_kbps   = (target_MB × 1024 × 1024 × 8) / (duration × 1000)
with audio:    video_kbps = total_kbps − 128   (AAC audio 128 kbps)
without audio: video_kbps = total_kbps          (nothing reserved for audio)
```

If `video_kbps < 100`, the app refuses (bitrate too low) and asks you to increase the target size.

### Modes and presets

| Mode | Passes | libx264 preset | When to use |
|---|---|---|---|
| 🎯 Maximum Quality (default) | 2 (two-pass) | `slow` | Final delivery: best image for the same size |
| ⚡ Fast | 1 | `faster` | In a hurry or testing; minimal loss on training content (slides, screen) |

In **two-pass**, the 1st pass analyzes the whole video and the 2nd places the bits where they matter most — the final size ends up closer to the target. It takes much longer than Fast mode.

### Pipeline

1. **Range cutting** (if any): the kept ranges are copied without re-encoding (`-ss`/`-t` + `-c copy`) and joined into a temporary file.
2. **Video filters:** `crop=...` (borders) and `scale=-2:1080/720/480` (resolution).
3. **Encoding:** H.264 (`libx264`) + AAC 128k (if there is audio), with `-movflags +faststart` (the video starts playing before it fully downloads).

### Output format

- **MP4** container, **H.264** video, **AAC 128 kbps** audio (or no audio if the original has none).
- Name: `video_compressed.mp4`; if it already exists, `video_compressed_1.mp4`, `_2`, etc.
- Temporary files (cut, preview, two-pass logs) are deleted at the end, on error and on cancel.

---

## 📊 Examples (490 MB target, video with audio)

| Final duration | Total bitrate | Video bitrate | Suggested resolution |
|---|---|---|---|
| 30 min | ~2284 kbps | 2155k | Original / 1080p |
| 1 h | ~1142 kbps | 1013k | 1080p for lectures/screen |
| 1 h 30 | ~761 kbps | 633k | 720p |
| 2 h | ~571 kbps | 442k | 720p |
| 3 h | ~381 kbps | 252k | 720p or 480p |
| 4 h | ~285 kbps | 157k | 480p — or split the video |

> Tip: on long videos, **removing black borders**, **useless ranges** (breaks, silence) and **lowering the resolution** frees bitrate for what matters.

---

## ❓ FAQ

**1. The final file is a bit smaller than the target. Is that normal?**
Yes. The calculation aims at the exact size, but the encoder saves bits on simple scenes (slides, still screen). The 490 MB default leaves margin under the 500 MB limit.

**2. The app says "FFmpeg not found". What now?**
Click **📦 Install via Winget** in the warning or run `install_ffmpeg.bat`. If you already installed it and the warning persists, close and reopen the app (or restart the PC). The app also looks in `C:\ffmpeg\bin`, in an `ffmpeg\bin` folder next to the script and in the Winget folder.
On **macOS**, install it with `brew install ffmpeg` and reopen the app from Terminal. On **Linux**, use your package manager (`sudo apt install ffmpeg` or `sudo dnf install ffmpeg`). On these systems the in-app warning already shows the right command.

**3. Are the time cuts accurate to the second?**
Almost. To be fast and lossless, cutting copies the video without re-encoding, so it starts at the nearest **keyframe** before the requested time — usually a 1–2 second difference (a tiny bit of the removed range may remain). The bitrate is calculated from the real duration after cutting, so the final size is still correct.

**4. Which resolution should I choose?**
Use the examples table: the lower the available bitrate, the lower the ideal resolution. A 720p video with plenty of bitrate usually looks sharper than a "squeezed" 1080p one. Check the **🎯 Target** line before compressing.

**5. I cancelled the compression. Are there leftover files?**
No. On cancel, FFmpeg is stopped and the app deletes the partial output, the cut file and the two-pass logs. The status shows **⚠️ Cancelled** and you can adjust the settings and start again.

---

## 📂 Files

```
video-compressor/
├── video_compressor.py   # Full application (UI + logic)
├── requirements.txt      # Python dependencies (pip install -r requirements.txt)
├── setup.bat             # Windows: installs Python 3.12, creates .venv, installs libraries and FFmpeg
├── start.bat             # Windows: opens the app using .venv
├── install_ffmpeg.bat    # Windows: installs FFmpeg (Winget or manual)
├── README.md             # Portuguese version of this file
├── README.en.md          # This file
├── .gitignore
└── .venv/                # Virtual environment (created on install; not in Git)

~/.video_compressor_settings.json   # saved settings (%USERPROFILE% on Windows; created when closing the app)
```
