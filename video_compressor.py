#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎬 Video Compressor - Treinamentos

Aplicativo 2-em-1 (COMPRESSOR + EDITOR) para Windows:
  • Comprime vídeos para um tamanho-alvo exato (padrão 490 MB) usando FFmpeg
    (libx264 + AAC, com two-pass opcional).
  • Antes de comprimir, permite remover bordas pretas (crop automático ou
    manual, com preview) e remover vários trechos de minutagem.
  • Permite cancelar a compressão e mostra a estimativa de bitrate antes de começar.

Dependências: customtkinter, Pillow, CTkMessagebox (opcional) + FFmpeg/FFprobe externos.
"""

import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from tkinter import TclError, filedialog

import customtkinter as ctk
from PIL import Image, ImageTk

try:
    from CTkMessagebox import CTkMessagebox
except ImportError:  # fallback mínimo: o app não pode quebrar se o pacote faltar
    from tkinter import messagebox as _tk_messagebox

    class CTkMessagebox:
        """Substituto de CTkMessagebox usando tkinter.messagebox (mesma interface)."""

        def __init__(self, master=None, title="", message="", icon="info",
                     option_1="OK", option_2=None, **_kwargs):
            self._result = option_1
            if option_2:
                yes = _tk_messagebox.askyesno(title, message, parent=master)
                self._result = option_1 if yes else option_2
            elif icon == "cancel":
                _tk_messagebox.showerror(title, message, parent=master)
            elif icon == "warning":
                _tk_messagebox.showwarning(title, message, parent=master)
            else:
                _tk_messagebox.showinfo(title, message, parent=master)

        def get(self):
            return self._result

# ── Constantes ────────────────────────────────────────────────────────────

# Em Windows esconde a janela de console de cada subprocess.
# (getattr permite que o código também rode em outros sistemas para testes.)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

COLOR_SUCCESS = "#a6e3a1"   # verde sucesso
COLOR_ERROR = "#f38ba8"     # vermelho erro
COLOR_INFO = "#89b4fa"      # azul info
COLOR_WARNING = "#f9e2af"   # amarelo aviso
COLOR_GRAY = "#45475a"      # botões neutros
COLOR_GRAY_HOVER = "#585b70"
COLOR_MUTED = "gray60"      # textos secundários
COLOR_TEXT = ("gray10", "gray90")

PLATFORM_LIMIT_MB = 500
DEFAULT_TARGET_MB = 490
DEFAULT_MODE = "quality"
DEFAULT_RESOLUTION = "Original"
AUDIO_BITRATE = "128k"
AUDIO_KBPS = 128
MIN_VIDEO_KBPS = 100

RESOLUTIONS = {"Original": None, "1080p": 1080, "720p": 720, "480p": 480}
PRESETS = {"quality": "slow", "fast": "faster"}
SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".video_compressor_settings.json")

VIDEO_FILETYPES = [
    ("Vídeos", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v"),
    ("Todos", "*.*"),
]

TIME_PROGRESS_RE = re.compile(r"time=\s*(\d+):(\d+):(\d+\.\d+)")
CROP_RE = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")


class CompressionCancelled(Exception):
    """Levantada quando o usuário cancela a compressão."""


def run_hidden(cmd, timeout=None):
    """Executa um comando sem abrir janela de console e captura a saída."""
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )


def safe_float(value, default=0.0):
    """Converte para float; containers podem devolver 'N/A'."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_remove(path):
    """Apaga um arquivo temporário registrando (sem quebrar) qualquer falha."""
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as exc:
        print(f"[aviso] não foi possível apagar {path}: {exc}", file=sys.stderr)


def _tail(text, lines=4):
    """Últimas linhas não vazias de um texto (para mensagens de erro)."""
    parts = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return "\n".join(parts[-lines:])


class VideoCompressorApp:
    """Aplicação principal: GUI + lógica de compressão/edição."""

    # ── Inicialização ─────────────────────────────────────────────────────

    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.app = ctk.CTk()
        self.app.title("🎬 Video Compressor - Treinamentos")
        self.app.geometry("920x720")
        self.app.resizable(True, True)
        self.app.minsize(800, 650)

        settings = self._load_settings()

        # FFmpeg
        self.ffmpeg_path = None

        # Vídeo atual
        self.video_path = ctk.StringVar(value="")
        self.video_width = 0
        self.video_height = 0
        self.video_duration = 0.0
        self.video_size_mb = 0.0
        self.video_codec = ""
        self.video_bitrate_kbps = 0.0
        self.tem_audio = True
        self.video_loaded = False

        # Crop
        self.crop_mode = ctk.StringVar(value="none")
        self.detected_crop = None  # (w, h, x, y)
        self.crop_top = ctk.StringVar(value="0")
        self.crop_bottom = ctk.StringVar(value="0")
        self.crop_left = ctk.StringVar(value="0")
        self.crop_right = ctk.StringVar(value="0")
        self.is_detecting = False

        # Cortes de minutagem: lista de (inicio, fim) em segundos, ordenada
        self.cut_segments = []

        # Compressão
        self.target_size = ctk.DoubleVar(value=settings["target_size_mb"])
        self.compress_mode = ctk.StringVar(value=settings["mode"])
        self.resolution = ctk.StringVar(value=settings["resolution"])
        self.is_compressing = False
        self._process = None
        self._cancel_requested = False
        self._worker = None
        self._encode_start = 0.0
        self._fps_args = None

        self._build_ui()

        for var in (self.crop_top, self.crop_bottom, self.crop_left, self.crop_right):
            var.trace_add("write", lambda *_a, v=var: self._on_crop_entry_change(v))

        self._on_crop_mode_change()
        self._update_duration_label()

        self.app.protocol("WM_DELETE_WINDOW", self._on_close)
        self.app.after(300, self._check_ffmpeg_on_startup)

    def run(self):
        self.app.mainloop()

    # ── Settings ──────────────────────────────────────────────────────────

    @staticmethod
    def _load_settings():
        settings = {"target_size_mb": DEFAULT_TARGET_MB, "mode": DEFAULT_MODE, "resolution": DEFAULT_RESOLUTION}
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return settings
        if not isinstance(data, dict):
            return settings
        try:
            target = int(round(float(data.get("target_size_mb", DEFAULT_TARGET_MB))))
            if 100 <= target <= 500:
                settings["target_size_mb"] = target
        except (ValueError, TypeError):
            pass  # valor inválido → mantém o padrão
        if data.get("mode") in PRESETS:
            settings["mode"] = data["mode"]
        if data.get("resolution") in RESOLUTIONS:
            settings["resolution"] = data["resolution"]
        return settings

    def _save_settings(self):
        data = {
            "target_size_mb": int(round(self.target_size.get())),
            "mode": self.compress_mode.get(),
            "resolution": self.resolution.get(),
        }
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            print(f"[aviso] não foi possível salvar as configurações: {exc}", file=sys.stderr)

    # ── Helpers de thread / UI ────────────────────────────────────────────

    def _ui(self, func, *args, **kwargs):
        """Agenda uma atualização de widget na thread da GUI, com segurança."""
        def _safe():
            try:
                func(*args, **kwargs)
            except TclError:
                pass  # a janela foi fechada enquanto a thread trabalhava
        try:
            self.app.after(0, _safe)
        except (TclError, RuntimeError):
            pass  # mainloop já encerrado

    def _font(self, size=13, bold=False):
        return ctk.CTkFont(size=size, weight="bold" if bold else "normal")

    def _make_section(self, parent, title):
        frame = ctk.CTkFrame(parent, corner_radius=10)
        frame.pack(fill="x", padx=5, pady=(0, 10))
        ctk.CTkLabel(frame, text=title, font=self._font(14, True), anchor="w").pack(
            fill="x", padx=12, pady=(10, 6)
        )
        return frame

    def _warn(self, message, title="Aviso"):
        CTkMessagebox(master=self.app, title=title, message=message, icon="warning")

    def _error(self, message, title="Erro"):
        CTkMessagebox(master=self.app, title=title, message=message, icon="cancel")

    # ── Construção da UI ──────────────────────────────────────────────────

    def _build_ui(self):
        main = ctk.CTkFrame(self.app, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=15, pady=10)
        main.grid_columnconfigure(0, weight=0)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(header, text="🎬 Video Compressor", font=self._font(24, True)).pack()
        ctk.CTkLabel(
            header,
            text="Comprima vídeos para o limite da plataforma",
            font=self._font(12),
            text_color=COLOR_MUTED,
        ).pack()

        # Coluna esquerda
        left = ctk.CTkScrollableFrame(main, label_text="Configurações", width=430)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        self._build_input_section(left)
        self._build_crop_section(left)
        self._build_cuts_section(left)
        self._build_compression_section(left)

        # Coluna direita
        right = ctk.CTkFrame(main, fg_color="transparent")
        right.grid(row=1, column=1, sticky="nsew")
        self._build_info_section(right)
        self._build_progress_section(right)
        self._build_result_section(right)

    def _build_input_section(self, parent):
        sec = self._make_section(parent, "📁 Vídeo de entrada")
        row = ctk.CTkFrame(sec, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 12))
        self.path_entry = ctk.CTkEntry(row, textvariable=self.video_path, state="readonly", height=36)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row, text="📂 Procurar", width=100, height=36, command=self._browse_file).pack(side="right")

    def _build_crop_section(self, parent):
        sec = self._make_section(parent, "✂️ Crop / Cortar bordas")

        radios = ctk.CTkFrame(sec, fg_color="transparent")
        radios.pack(fill="x", padx=12, pady=(0, 6))
        for text, value in (("Sem crop", "none"), ("🔍 Auto", "auto"), ("✏️ Manual", "manual")):
            ctk.CTkRadioButton(
                radios, text=text, value=value, variable=self.crop_mode, command=self._on_crop_mode_change
            ).pack(side="left", padx=(0, 15))

        # Linha Auto
        auto_row = ctk.CTkFrame(sec, fg_color="transparent")
        auto_row.pack(fill="x", padx=12, pady=4)
        self.detect_btn = ctk.CTkButton(
            auto_row,
            text="🔍 Detectar bordas pretas",
            fg_color=COLOR_WARNING,
            hover_color="#e6cf9a",
            text_color="black",
            height=30,
            command=self._detect_crop,
        )
        self.detect_btn.pack(side="left")
        self.auto_status_label = ctk.CTkLabel(auto_row, text="", font=self._font(11), anchor="w")
        self.auto_status_label.pack(side="left", padx=10, fill="x", expand=True)

        # Linha Manual
        manual_row = ctk.CTkFrame(sec, fg_color="transparent")
        manual_row.pack(fill="x", padx=12, pady=4)
        self.manual_entries = []
        for label, var in (
            ("Topo:", self.crop_top),
            ("Baixo:", self.crop_bottom),
            ("Esq:", self.crop_left),
            ("Dir:", self.crop_right),
        ):
            mini = ctk.CTkFrame(manual_row, fg_color="transparent")
            mini.pack(side="left", padx=(0, 8))
            ctk.CTkLabel(mini, text=label, font=self._font(11)).pack(side="left", padx=(0, 3))
            entry = ctk.CTkEntry(mini, textvariable=var, width=55, height=28)
            entry.pack(side="left")
            self.manual_entries.append(entry)

        # Linha Preview
        prev_row = ctk.CTkFrame(sec, fg_color="transparent")
        prev_row.pack(fill="x", padx=12, pady=(4, 12))
        self.preview_btn = ctk.CTkButton(
            prev_row,
            text="🖼️ Preview",
            width=100,
            height=28,
            fg_color=COLOR_GRAY,
            hover_color=COLOR_GRAY_HOVER,
            command=self._show_preview,
        )
        self.preview_btn.pack(side="left")
        self.crop_result_label = ctk.CTkLabel(prev_row, text="", text_color=COLOR_INFO, anchor="w")
        self.crop_result_label.pack(side="left", padx=10)

    def _build_cuts_section(self, parent):
        sec = self._make_section(parent, "⏱️ Cortar minutagens (remover trechos)")
        ctk.CTkLabel(
            sec, text="Formato: HH:MM:SS ou MM:SS", font=self._font(10), text_color=COLOR_MUTED, anchor="w"
        ).pack(fill="x", padx=12)

        row = ctk.CTkFrame(sec, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=6)
        ctk.CTkLabel(row, text="De:", font=self._font(12, True)).pack(side="left", padx=(0, 4))
        self.cut_start_entry = ctk.CTkEntry(row, width=90)
        self.cut_start_entry.insert(0, "00:00:00")
        self.cut_start_entry.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(row, text="Até:", font=self._font(12, True)).pack(side="left", padx=(0, 4))
        self.cut_end_entry = ctk.CTkEntry(row, width=90, placeholder_text="00:00:00")
        self.cut_end_entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="➕ Adicionar", width=100, height=30, command=self._add_cut).pack(side="left")
        for entry in (self.cut_start_entry, self.cut_end_entry):
            entry.bind("<Return>", lambda _e: self._add_cut())

        list_row = ctk.CTkFrame(sec, fg_color="transparent")
        list_row.pack(fill="x", padx=12, pady=4)
        self.cuts_textbox = ctk.CTkTextbox(list_row, height=80, font=self._font(11))
        self.cuts_textbox.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.cuts_textbox.configure(state="disabled")
        btns = ctk.CTkFrame(list_row, fg_color="transparent")
        btns.pack(side="right", fill="y")
        ctk.CTkButton(
            btns, text="🗑️ Remover", width=90, height=28,
            fg_color=COLOR_GRAY, hover_color=COLOR_GRAY_HOVER, command=self._remove_selected_cut,
        ).pack(pady=(0, 6))
        ctk.CTkButton(
            btns, text="🧹 Limpar", width=90, height=28,
            fg_color=COLOR_GRAY, hover_color=COLOR_GRAY_HOVER, command=self._clear_cuts,
        ).pack()

        self.duration_label = ctk.CTkLabel(sec, text="", font=self._font(11), anchor="w")
        self.duration_label.pack(fill="x", padx=12, pady=(2, 12))

    def _build_compression_section(self, parent):
        sec = self._make_section(parent, "⚙️ Compressão")

        size_row = ctk.CTkFrame(sec, fg_color="transparent")
        size_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(size_row, text="Tamanho alvo:").pack(side="left")
        self.target_label = ctk.CTkLabel(
            size_row, text=f"{int(round(self.target_size.get()))} MB", font=self._font(13, True), width=70
        )
        self.target_label.pack(side="left", padx=6)
        self.target_slider = ctk.CTkSlider(
            size_row, from_=100, to=500, number_of_steps=400,
            variable=self.target_size, command=self._on_target_change,
        )
        self.target_slider.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.target_slider.set(self.target_size.get())

        mode_row = ctk.CTkFrame(sec, fg_color="transparent")
        mode_row.pack(fill="x", padx=12, pady=6)
        ctk.CTkLabel(mode_row, text="Modo:").pack(side="left", padx=(0, 10))
        ctk.CTkRadioButton(mode_row, text="⚡ Rápido", value="fast", variable=self.compress_mode).pack(
            side="left", padx=(0, 15)
        )
        ctk.CTkRadioButton(
            mode_row, text="🎯 Qualidade Máxima", value="quality", variable=self.compress_mode
        ).pack(side="left")

        res_row = ctk.CTkFrame(sec, fg_color="transparent")
        res_row.pack(fill="x", padx=12, pady=6)
        ctk.CTkLabel(res_row, text="📐 Resolução:").pack(side="left", padx=(0, 10))
        for name in RESOLUTIONS:
            ctk.CTkRadioButton(
                res_row, text=name, value=name, variable=self.resolution, width=70,
            ).pack(side="left", padx=(0, 6))

        btn_row = ctk.CTkFrame(sec, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(6, 14))
        self.compress_btn = ctk.CTkButton(
            btn_row,
            text="🚀 Comprimir Vídeo",
            height=42,
            fg_color=COLOR_SUCCESS,
            hover_color="#8fd18a",
            text_color="black",
            font=self._font(15, True),
            command=self._start_compression,
        )
        self.compress_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.cancel_btn = ctk.CTkButton(
            btn_row,
            text="❌ Cancelar",
            width=110,
            height=42,
            fg_color=COLOR_ERROR,
            hover_color="#e07a96",
            text_color="white",
            font=self._font(13, True),
            state="disabled",
            command=self._cancel_compression,
        )
        self.cancel_btn.pack(side="right")

    def _build_info_section(self, parent):
        sec = self._make_section(parent, "📊 Informações do vídeo")
        self.info_label = ctk.CTkLabel(
            sec,
            text="Selecione um vídeo para ver suas informações",
            wraplength=380,
            justify="left",
            anchor="w",
            text_color=COLOR_MUTED,
        )
        self.info_label.pack(fill="x", padx=12, pady=(0, 12))

    def _build_progress_section(self, parent):
        sec = self._make_section(parent, "📈 Progresso")
        self.progress_bar = ctk.CTkProgressBar(sec, height=18)
        self.progress_bar.pack(fill="x", padx=12, pady=(4, 6))
        self.progress_bar.set(0)
        self.status_label = ctk.CTkLabel(sec, text="Pronto para comprimir", anchor="w")
        self.status_label.pack(fill="x", padx=12, pady=(0, 12))

    def _build_result_section(self, parent):
        sec = self._make_section(parent, "📋 Resultado")
        self.result_label = ctk.CTkLabel(
            sec,
            text="",
            font=self._font(11),
            wraplength=380,
            justify="left",
            anchor="w",
            text_color=COLOR_SUCCESS,
        )
        self.result_label.pack(fill="x", padx=12, pady=(0, 12))

    # ── FFmpeg Detection ──────────────────────────────────────────────────

    def _find_ffmpeg(self):
        """Procura o FFmpeg no PATH e em locais comuns. Retorna caminho ou None."""
        try:
            if run_hidden(["ffmpeg", "-version"], timeout=15).returncode == 0:
                return "ffmpeg"
        except (OSError, subprocess.SubprocessError):
            pass  # não está no PATH; segue para os caminhos fixos

        script_dir = os.path.dirname(os.path.abspath(sys.argv[0] or __file__))
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(script_dir, "ffmpeg", "bin", "ffmpeg.exe"),
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            os.path.join(os.path.expanduser("~"), "ffmpeg", "bin", "ffmpeg.exe"),
        ]
        # Locais usados pelo Winget (o PATH do processo atual não é atualizado
        # logo após a instalação, então procuramos diretamente).
        if local_appdata:
            candidates.append(os.path.join(local_appdata, "Microsoft", "WinGet", "Links", "ffmpeg.exe"))
            candidates.extend(
                sorted(
                    glob.glob(
                        os.path.join(
                            local_appdata, "Microsoft", "WinGet", "Packages",
                            "Gyan.FFmpeg*", "*", "bin", "ffmpeg.exe",
                        )
                    ),
                    reverse=True,
                )
            )
        for path in candidates:
            if path and os.path.isfile(path):
                return path
        return None

    def _get_ffprobe(self):
        """FFprobe ao lado do FFmpeg encontrado; senão assume que está no PATH."""
        if not self.ffmpeg_path or self.ffmpeg_path == "ffmpeg":
            return "ffprobe"
        folder = os.path.dirname(self.ffmpeg_path)
        ext = os.path.splitext(self.ffmpeg_path)[1]
        candidate = os.path.join(folder, "ffprobe" + ext)
        return candidate if os.path.isfile(candidate) else "ffprobe"

    def _check_ffmpeg_on_startup(self):
        self.ffmpeg_path = self._find_ffmpeg()
        if not self.ffmpeg_path:
            self._show_ffmpeg_dialog()

    def _show_ffmpeg_dialog(self):
        dlg = ctk.CTkToplevel(self.app)
        dlg.title("FFmpeg não encontrado")
        dlg.geometry("480x250")
        dlg.resizable(False, False)
        dlg.transient(self.app)

        self.app.update_idletasks()
        x = self.app.winfo_x() + (self.app.winfo_width() - 480) // 2
        y = self.app.winfo_y() + (self.app.winfo_height() - 250) // 2
        dlg.geometry(f"480x250+{max(0, x)}+{max(0, y)}")

        ctk.CTkLabel(dlg, text="⚠️ FFmpeg não encontrado!", font=self._font(18, True),
                     text_color=COLOR_WARNING).pack(pady=(20, 8))
        is_windows = sys.platform.startswith("win")
        if is_windows:
            help_text = (
                "O FFmpeg é necessário para ler, cortar e comprimir vídeos.\n"
                "Instale automaticamente via Winget ou rode install_ffmpeg.bat.\n"
                "Instalação manual: extraia em C:\\ffmpeg\\ e adicione C:\\ffmpeg\\bin ao PATH."
            )
        elif sys.platform == "darwin":
            help_text = (
                "O FFmpeg é necessário para ler, cortar e comprimir vídeos.\n"
                "Instale pelo Terminal com o Homebrew:\n"
                "brew install ffmpeg\n"
                "Depois feche o app e abra-o de novo pelo Terminal."
            )
        else:
            help_text = (
                "O FFmpeg é necessário para ler, cortar e comprimir vídeos.\n"
                "Instale pelo gerenciador de pacotes, por exemplo:\n"
                "sudo apt install ffmpeg   (Ubuntu/Debian)\n"
                "sudo dnf install ffmpeg   (Fedora)\n"
                "Depois feche e abra o app novamente."
            )
        ctk.CTkLabel(dlg, text=help_text, font=self._font(12), justify="center").pack(padx=15)
        status = ctk.CTkLabel(dlg, text="", font=self._font(11))
        status.pack(pady=6)

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(pady=8)
        # O botão do Winget só existe no Windows
        install_btn = ctk.CTkButton(btns, text="📦 Instalar via Winget", width=180)
        if is_windows:
            install_btn.pack(side="left", padx=6)
        ctk.CTkButton(
            btns, text="Fechar", width=100, fg_color=COLOR_GRAY,
            hover_color=COLOR_GRAY_HOVER, command=dlg.destroy,
        ).pack(side="left", padx=6)

        def _finish(found):
            if found:
                self.ffmpeg_path = found
                if dlg.winfo_exists():
                    dlg.destroy()
                CTkMessagebox(master=self.app, title="FFmpeg", message="✅ FFmpeg instalado e encontrado!",
                              icon="check")
            elif dlg.winfo_exists():
                status.configure(
                    text="❌ Não foi possível concluir. Feche e abra o app novamente\n"
                         "ou use a instalação manual (install_ffmpeg.bat).",
                    text_color=COLOR_ERROR,
                )
                install_btn.configure(state="normal", text="📦 Instalar via Winget")

        def _worker():
            try:
                run_hidden([
                    "winget", "install", "-e", "--id", "Gyan.FFmpeg",
                    "--accept-source-agreements", "--accept-package-agreements",
                ])
            except OSError as exc:
                print(f"[aviso] falha ao executar o winget: {exc}", file=sys.stderr)
            self._ui(_finish, self._find_ffmpeg())

        def _install():
            install_btn.configure(state="disabled", text="⏳ Instalando...")
            status.configure(text="Instalando FFmpeg via Winget, aguarde...", text_color=COLOR_INFO)
            threading.Thread(target=_worker, daemon=True).start()

        install_btn.configure(command=_install)
        dlg.after(100, lambda: (dlg.lift(), dlg.focus_force(), dlg.grab_set()))

    def _require_ffmpeg(self):
        if self.ffmpeg_path:
            return True
        self.ffmpeg_path = self._find_ffmpeg()
        if not self.ffmpeg_path:
            self._show_ffmpeg_dialog()
            return False
        return True

    # ── File Selection & Video Info ───────────────────────────────────────

    def _browse_file(self):
        if self.is_compressing:
            return
        path = filedialog.askopenfilename(title="Selecione o vídeo", filetypes=VIDEO_FILETYPES)
        if not path:
            return
        self._select_video(os.path.normpath(path))

    def _select_video(self, path):
        self.video_path.set(path)

        # Reseta o estado ligado ao vídeo anterior
        self.video_loaded = False
        self.video_width = self.video_height = 0
        self.video_duration = 0.0
        self.tem_audio = True
        self.detected_crop = None
        for var in (self.crop_top, self.crop_bottom, self.crop_left, self.crop_right):
            var.set("0")
        self.auto_status_label.configure(text="")
        self.cut_segments = []
        self._refresh_cuts_list()
        self.result_label.configure(text="")
        self.progress_bar.set(0)
        self.status_label.configure(text="Pronto para comprimir", text_color=COLOR_TEXT)
        self._on_crop_mode_change()

        if not self._require_ffmpeg():
            self.info_label.configure(
                text="⚠️ FFmpeg não encontrado — não é possível ler as informações.", text_color=COLOR_WARNING
            )
            return
        self.info_label.configure(text="⏳ Lendo informações do vídeo...", text_color=COLOR_INFO)
        threading.Thread(target=self._load_video_info, args=(path,), daemon=True).start()

    def _probe(self, path):
        result = run_hidden(
            [self._get_ffprobe(), "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path]
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError("Não foi possível ler o vídeo com o FFprobe.")
        try:
            return json.loads(result.stdout)
        except ValueError as exc:
            raise RuntimeError("Resposta inválida do FFprobe.") from exc

    def _probe_duration(self, path):
        data = self._probe(path)
        duration = safe_float(data.get("format", {}).get("duration"))
        if duration <= 0:
            vstream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
            duration = safe_float(vstream.get("duration"))
        return duration

    def _load_video_info(self, path):
        try:
            data = self._probe(path)
            fmt = data.get("format", {})
            streams = data.get("streams", [])
            vstream = next((s for s in streams if s.get("codec_type") == "video"), None)
            if vstream is None:
                raise RuntimeError("Nenhuma faixa de vídeo encontrada no arquivo.")

            duration = safe_float(fmt.get("duration"))
            if duration <= 0:
                duration = safe_float(vstream.get("duration"))
            size = safe_float(fmt.get("size"))
            if size <= 0:
                try:
                    size = float(os.path.getsize(path))
                except OSError:
                    size = 0.0
            bit_rate = safe_float(fmt.get("bit_rate"))
            if bit_rate <= 0 and duration > 0:
                bit_rate = size * 8 / duration

            info = {
                "duration": duration,
                "size_mb": size / (1024 * 1024),
                "kbps": bit_rate / 1000,
                "width": int(safe_float(vstream.get("width"))),
                "height": int(safe_float(vstream.get("height"))),
                "codec": vstream.get("codec_name", "?"),
                "has_audio": any(s.get("codec_type") == "audio" for s in streams),
            }
            self._ui(self._apply_video_info, path, info)
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            self._ui(self._apply_video_info_error, path, str(exc))

    def _apply_video_info(self, path, info):
        if path != self.video_path.get():
            return  # usuário já trocou de arquivo
        self.video_duration = info["duration"]
        self.video_width = info["width"]
        self.video_height = info["height"]
        self.video_size_mb = info["size_mb"]
        self.video_codec = info["codec"]
        self.video_bitrate_kbps = info["kbps"]
        self.tem_audio = info["has_audio"]
        self.video_loaded = True
        self._render_info()
        self._on_crop_mode_change()
        self._update_duration_label()

    def _apply_video_info_error(self, path, msg):
        if path != self.video_path.get():
            return
        self.video_loaded = False
        self.info_label.configure(text=f"❌ {msg}", text_color=COLOR_ERROR)
        self._on_crop_mode_change()

    def _calc_video_kbps(self, target_mb, duration, has_audio):
        """Bitrate de vídeo para atingir o alvo (desconta 128k só se houver áudio)."""
        if duration <= 0:
            return 0.0
        total_kbps = (target_mb * 1024 * 1024 * 8) / (duration * 1000)
        return total_kbps - (AUDIO_KBPS if has_audio else 0)

    def _estimate_line(self):
        target = int(round(self.target_size.get()))
        duration = self._final_duration()
        if duration <= 0:
            return f"🎯 Alvo: {target} MB → duração desconhecida"
        video_kbps = self._calc_video_kbps(target, duration, self.tem_audio)
        audio_txt = f"áudio {AUDIO_KBPS} kbps" if self.tem_audio else "sem áudio"
        line = f"🎯 Alvo: {target} MB → vídeo ~{video_kbps:.0f} kbps + {audio_txt}"
        if video_kbps < MIN_VIDEO_KBPS:
            line += "\n⚠️ Bitrate muito baixo — aumente o tamanho alvo ou remova trechos."
        return line

    def _render_info(self):
        if not self.video_loaded:
            return
        text = (
            f"📊 {self.video_size_mb:.1f} MB  |  ⏱️ {self._format_time(self.video_duration)}  |  "
            f"📐 {self.video_width}×{self.video_height}  |  🎬 {self.video_codec}  |  "
            f"📶 {self.video_bitrate_kbps:.0f} kbps"
        )
        if not self.tem_audio:
            text += "  |  🔇 sem áudio"
        text += "\n" + self._estimate_line()
        color = COLOR_ERROR if self.video_size_mb > PLATFORM_LIMIT_MB else COLOR_SUCCESS
        if self.video_size_mb <= self.target_size.get():
            text += "\n✅ Já está dentro do limite!"
        self.info_label.configure(text=text, text_color=color)

    def _on_target_change(self, value):
        self.target_label.configure(text=f"{int(round(value))} MB")
        self._render_info()

    # ── Crop Functions ────────────────────────────────────────────────────

    def _on_crop_mode_change(self):
        mode = self.crop_mode.get()
        loaded = self.video_loaded
        self.detect_btn.configure(
            state="normal" if (mode == "auto" and loaded and not self.is_detecting) else "disabled"
        )
        entry_state = "normal" if mode == "manual" else "disabled"
        for entry in self.manual_entries:
            entry.configure(state=entry_state)
        self.preview_btn.configure(state="normal" if loaded else "disabled")
        self._update_crop_label()

    def _on_crop_entry_change(self, var):
        value = var.get()
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits != value:
            var.set(digits)  # dispara o trace de novo com o valor limpo
            return
        self._update_crop_label()

    def _get_manual_crop(self):
        def _val(var):
            v = var.get().strip()
            return int(v) if v.isdigit() else 0
        return _val(self.crop_top), _val(self.crop_bottom), _val(self.crop_left), _val(self.crop_right)

    def _manual_crop_size(self):
        top, bottom, left, right = self._get_manual_crop()
        nw = self.video_width - left - right
        nh = self.video_height - top - bottom
        # libx264 (yuv420p) exige dimensões pares
        nw -= nw % 2
        nh -= nh % 2
        return nw, nh, left, top

    def _update_crop_label(self):
        label = getattr(self, "crop_result_label", None)
        if label is None:
            return
        mode = self.crop_mode.get()
        if not self.video_loaded or mode == "none":
            label.configure(text="", text_color=COLOR_INFO)
            return
        W, H = self.video_width, self.video_height
        if mode == "auto":
            if self.detected_crop:
                w, h, _x, _y = self.detected_crop
                label.configure(text=f"✂️ {W}×{H} → {w}×{h}", text_color=COLOR_INFO)
            else:
                label.configure(text="", text_color=COLOR_INFO)
            return
        nw, nh, _l, _t = self._manual_crop_size()
        if nw <= 0 or nh <= 0:
            label.configure(text="❌ Inválido!", text_color=COLOR_ERROR)
        else:
            label.configure(text=f"✂️ {W}×{H} → {nw}×{nh}", text_color=COLOR_INFO)

    def _build_crop_filter(self):
        """Retorna 'crop=...' ou None. Lança ValueError se inválido."""
        mode = self.crop_mode.get()
        if mode == "none":
            return None
        if mode == "auto":
            if not self.detected_crop:
                raise ValueError("Detecte as bordas primeiro!")
            w, h, x, y = self.detected_crop
            return f"crop={w}:{h}:{x}:{y}"
        top, bottom, left, right = self._get_manual_crop()
        if top == bottom == left == right == 0:
            return None
        nw, nh, left, top = self._manual_crop_size()
        if nw <= 0 or nh <= 0:
            raise ValueError("Valores de crop inválidos!")
        return f"crop={nw}:{nh}:{left}:{top}"

    def _build_video_filter(self):
        crop = self._build_crop_filter()
        filters = [crop] if crop else []
        height = RESOLUTIONS.get(self.resolution.get())
        if height:
            filters.append(f"scale=-2:{height}")
        return ",".join(filters) if filters else None

    def _safe_seek(self, seconds):
        """Garante que o seek fique dentro da duração do vídeo."""
        if self.video_duration > 0:
            return max(0.0, min(seconds, self.video_duration - 1))
        return seconds

    def _detect_crop(self):
        if not self.video_loaded or self.is_detecting or not self._require_ffmpeg():
            return
        self.is_detecting = True
        self.detect_btn.configure(text="⏳ Detectando...", state="disabled")
        self.auto_status_label.configure(text="Analisando 3 pontos do vídeo...", text_color=COLOR_INFO)
        args = (self.video_path.get(), self.video_duration, self.video_width, self.video_height)
        threading.Thread(target=self._detect_crop_worker, args=args, daemon=True).start()

    def _detect_crop_worker(self, path, duration, W, H):
        samples = []
        error = None
        try:
            for pct in (25, 50, 75):
                seek = self._safe_seek(max(5, duration * pct / 100))
                result = run_hidden([
                    self.ffmpeg_path, "-hide_banner", "-ss", f"{seek:.2f}", "-i", path,
                    "-vframes", "10", "-vf", "cropdetect=24:2", "-f", "null", "-",
                ])
                matches = CROP_RE.findall(result.stderr)
                if matches:
                    samples.append(tuple(int(v) for v in matches[-1]))
        except (OSError, subprocess.SubprocessError) as exc:
            error = str(exc)
        self._ui(self._apply_detected_crop, samples, W, H, error)

    def _apply_detected_crop(self, samples, W, H, error):
        self.is_detecting = False
        self.detect_btn.configure(text="🔍 Detectar bordas pretas")
        if error:
            self.auto_status_label.configure(text=f"❌ {error}", text_color=COLOR_ERROR)
            self._on_crop_mode_change()
            return
        best = min(samples, key=lambda c: c[0] * c[1]) if samples else None
        if best is None or (best[0] >= W and best[1] >= H):
            self.detected_crop = None
            self.auto_status_label.configure(text="✅ Sem bordas!", text_color=COLOR_SUCCESS)
            self.crop_mode.set("none")
            self._on_crop_mode_change()
            return

        w, h, x, y = best
        self.detected_crop = best
        # y/x são o deslocamento a partir do topo/esquerda
        top, bottom = y, max(0, H - h - y)
        left, right = x, max(0, W - w - x)
        self.crop_top.set(str(top))
        self.crop_bottom.set(str(bottom))
        self.crop_left.set(str(left))
        self.crop_right.set(str(right))
        self.auto_status_label.configure(
            text=f"Cortar: {top}px topo, {bottom}px baixo, {left}px esq, {right}px dir",
            text_color=COLOR_SUCCESS,
        )
        self._on_crop_mode_change()

    # ── Preview ───────────────────────────────────────────────────────────

    def _show_preview(self):
        if not self.video_loaded or not self._require_ffmpeg():
            return
        try:
            crop = self._build_crop_filter()
        except ValueError as exc:
            self._warn(str(exc))
            return
        self.preview_btn.configure(state="disabled", text="⏳...")
        args = (self.video_path.get(), self.video_duration, crop)
        threading.Thread(target=self._preview_worker, args=args, daemon=True).start()

    def _preview_worker(self, path, duration, crop):
        tmp = tempfile.gettempdir()
        orig_png = os.path.join(tmp, "vc_prev_orig.png")
        crop_png = os.path.join(tmp, "vc_prev_crop.png")
        seek = self._safe_seek(max(5, duration * 0.1))
        error = None
        try:
            safe_remove(orig_png)
            safe_remove(crop_png)
            run_hidden([self.ffmpeg_path, "-y", "-ss", f"{seek:.2f}", "-i", path,
                        "-vframes", "1", "-q:v", "2", orig_png])
            if crop:
                run_hidden([self.ffmpeg_path, "-y", "-ss", f"{seek:.2f}", "-i", path,
                            "-vframes", "1", "-q:v", "2", "-vf", crop, crop_png])
            if not os.path.exists(orig_png):
                error = "Não foi possível extrair o frame do vídeo."
        except (OSError, subprocess.SubprocessError) as exc:
            error = str(exc)
        self._ui(self._open_preview_window, orig_png, crop_png if crop else None, error)

    def _open_preview_window(self, orig_png, crop_png, error):
        self.preview_btn.configure(text="🖼️ Preview")
        self._on_crop_mode_change()
        if error:
            self._error(error)
            return

        def _load(p):
            if p and os.path.exists(p):
                with Image.open(p) as im:
                    return im.copy()
            return None

        try:
            orig_img = _load(orig_png)
            crop_img = _load(crop_png) if crop_png else None
        except OSError as exc:
            self._error(f"Não foi possível abrir o frame: {exc}")
            return
        if orig_img is None:
            self._error("Não foi possível extrair o frame do vídeo.")
            return
        if crop_img is None:
            crop_img = orig_img.copy()

        win = ctk.CTkToplevel(self.app)
        win.title("🖼️ Preview")
        win.geometry("720x350")
        win.transient(self.app)
        win._photo_refs = []  # mantém referência das imagens (evita coleta pelo GC)

        cols = ctk.CTkFrame(win, fg_color="transparent")
        cols.pack(fill="both", expand=True, padx=10, pady=10)
        cols.grid_columnconfigure((0, 1), weight=1)

        for col, (title, img) in enumerate((("Original", orig_img), ("Com crop", crop_img))):
            ctk.CTkLabel(cols, text=title, font=self._font(12, True)).grid(row=0, column=col, pady=(0, 6))
            dims = f"{img.width}x{img.height}"
            thumb = img.copy()
            thumb.thumbnail((330, 240), Image.LANCZOS)
            photo = ImageTk.PhotoImage(thumb)
            win._photo_refs.append(photo)
            ctk.CTkLabel(cols, text="", image=photo).grid(row=1, column=col, padx=5)
            ctk.CTkLabel(cols, text=dims, font=self._font(10), text_color=COLOR_MUTED).grid(
                row=2, column=col, pady=(4, 0)
            )

        def _close():
            safe_remove(orig_png)
            safe_remove(crop_png)
            win.destroy()

        ctk.CTkButton(win, text="Fechar", width=100, fg_color=COLOR_GRAY,
                      hover_color=COLOR_GRAY_HOVER, command=_close).pack(pady=(0, 12))
        win.protocol("WM_DELETE_WINDOW", _close)
        win.after(100, win.lift)

    # ── Time Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_time(text):
        """Converte HH:MM:SS, MM:SS ou SS em segundos. Retorna -1 se inválido."""
        try:
            parts = (text or "").strip().split(":")
            if not parts or len(parts) > 3 or any(p.strip() == "" for p in parts):
                return -1
            values = [float(p) for p in parts]
            if any(v < 0 for v in values):
                return -1
            # minutos/segundos que não são o primeiro campo precisam ser < 60
            if any(v >= 60 for v in values[1:]):
                return -1
            total = 0.0
            for v in values:
                total = total * 60 + v
            return total
        except (ValueError, TypeError):
            return -1

    @staticmethod
    def _format_time(seconds):
        """MM:SS, ou HH:MM:SS se houver horas."""
        total = int(max(0, seconds or 0))
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    # ── Cut Segments (minutagens) ─────────────────────────────────────────

    def _add_cut(self):
        if not self.video_loaded or self.video_duration <= 0:
            self._warn("Selecione um vídeo primeiro!")
            return
        start = self._parse_time(self.cut_start_entry.get())
        end = self._parse_time(self.cut_end_entry.get())
        if start < 0 or end < 0:
            self._warn("Tempo inválido! Use HH:MM:SS ou MM:SS")
            return
        if end <= start:
            self._warn("O fim deve ser maior que o início!")
            return
        if end > self.video_duration:
            if end - self.video_duration < 1:
                end = self.video_duration  # tolerância de arredondamento
            else:
                self._warn(f"Fim excede a duração ({self._format_time(self.video_duration)})")
                return
        for s, e in self.cut_segments:
            if start < e and end > s:
                self._warn("Trecho se sobrepõe com outro!")
                return

        self.cut_segments.append((start, end))
        self.cut_segments.sort(key=lambda seg: seg[0])
        self.cut_start_entry.delete(0, "end")
        self.cut_start_entry.insert(0, "00:00:00")
        self.cut_end_entry.delete(0, "end")
        self._refresh_cuts_list()

    def _remove_selected_cut(self):
        if not self.cut_segments:
            return
        index = len(self.cut_segments) - 1  # sem seleção: remove o último
        try:
            line = int(self.cuts_textbox.index("sel.first linestart").split(".")[0])
            if 1 <= line <= len(self.cut_segments):
                index = line - 1
        except TclError:
            pass  # nenhuma linha selecionada
        self.cut_segments.pop(index)
        self._refresh_cuts_list()

    def _clear_cuts(self):
        self.cut_segments = []
        self._refresh_cuts_list()

    def _refresh_cuts_list(self):
        lines = [
            f"  {i}. Remover {self._format_time(s)} → {self._format_time(e)} ({self._format_time(e - s)})"
            for i, (s, e) in enumerate(self.cut_segments, start=1)
        ]
        self.cuts_textbox.configure(state="normal")
        self.cuts_textbox.delete("1.0", "end")
        self.cuts_textbox.insert("1.0", "\n".join(lines))
        self.cuts_textbox.configure(state="disabled")
        self._update_duration_label()
        self._render_info()

    def _removed_duration(self):
        return sum(e - s for s, e in self.cut_segments)

    def _final_duration(self):
        return max(0.0, self.video_duration - self._removed_duration())

    def _update_duration_label(self):
        if not self.video_loaded:
            self.duration_label.configure(text="⏱️ Duração: --:--", text_color=COLOR_MUTED)
            return
        if not self.cut_segments:
            self.duration_label.configure(
                text=f"⏱️ Duração: {self._format_time(self.video_duration)}", text_color=COLOR_TEXT
            )
            return
        removed = self._removed_duration()
        self.duration_label.configure(
            text=(
                f"⏱️ {self._format_time(self.video_duration)} → {self._format_time(self._final_duration())} "
                f"(−{self._format_time(removed)})"
            ),
            text_color=COLOR_INFO,
        )

    @staticmethod
    def _keep_segments(segments, duration):
        """Complemento dos trechos removidos sobre [0, duração]."""
        keep = []
        cursor = 0.0
        for s, e in sorted(segments):
            if s > cursor + 0.05:
                keep.append((cursor, s))
            cursor = max(cursor, e)
        if duration - cursor > 0.05:
            keep.append((cursor, duration))
        return keep

    def _trim_video(self, path, segments, duration, codec, has_audio, temp_files):
        """Remove os trechos com stream copy (-ss/-t). Retorna o arquivo aparado.

        Todo arquivo criado é registrado em temp_files para limpeza (inclusive
        em erro ou cancelamento)."""
        keep = self._keep_segments(segments, duration)
        if not keep:
            raise RuntimeError("Os trechos removem o vídeo inteiro!")

        stamp = int(time.time() * 1000)
        tmp = tempfile.gettempdir()
        trimmed = os.path.join(tmp, f"vc_trim_{stamp}.mp4")
        temp_files.append(trimmed)

        if len(keep) == 1:
            s, e = keep[0]
            rc, err = self._run_cancellable([
                self.ffmpeg_path, "-y", "-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i", path,
                "-c", "copy", "-avoid_negative_ts", "make_zero", trimmed,
            ])
            if rc != 0 or not os.path.exists(trimmed):
                raise RuntimeError("Falha ao cortar trechos:\n" + _tail(err))
            return trimmed

        bsf = "hevc_mp4toannexb" if codec in ("hevc", "h265") else "h264_mp4toannexb"
        ts_files = []
        try:
            for i, (s, e) in enumerate(keep):
                ts = os.path.join(tmp, f"vc_seg_{stamp}_{i}.ts")
                ts_files.append(ts)
                rc, err = self._run_cancellable([
                    self.ffmpeg_path, "-y", "-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i", path,
                    "-c", "copy", "-bsf:v", bsf, "-f", "mpegts", ts,
                ])
                if rc != 0 or not os.path.exists(ts):
                    raise RuntimeError(f"Falha ao extrair o segmento {i + 1}:\n" + _tail(err))
            audio_bsf = ["-bsf:a", "aac_adtstoasc"] if has_audio else []
            rc, err = self._run_cancellable([
                self.ffmpeg_path, "-y", "-i", "concat:" + "|".join(ts_files),
                "-c", "copy", *audio_bsf, "-movflags", "+faststart", trimmed,
            ])
            if rc != 0 or not os.path.exists(trimmed):
                raise RuntimeError("Falha ao juntar os segmentos:\n" + _tail(err))
            return trimmed
        finally:
            for ts in ts_files:
                safe_remove(ts)

    # ── Compression ───────────────────────────────────────────────────────

    def _set_status(self, text, color=None, pct=None):
        self.status_label.configure(text=text, text_color=color or COLOR_TEXT)
        if pct is not None:
            self.progress_bar.set(max(0.0, min(1.0, pct / 100)))

    def _set_busy(self, busy):
        if busy:
            self.compress_btn.configure(text="⏳ Comprimindo...", state="disabled", fg_color=COLOR_GRAY_HOVER)
            self.cancel_btn.configure(state="normal")
        else:
            self.compress_btn.configure(text="🚀 Comprimir Vídeo", state="normal", fg_color=COLOR_SUCCESS)
            self.cancel_btn.configure(state="disabled")

    @staticmethod
    def _get_output_path(input_path):
        base, _ext = os.path.splitext(input_path)
        out = f"{base}_compressed.mp4"
        i = 1
        while os.path.exists(out):
            out = f"{base}_compressed_{i}.mp4"
            i += 1
        return out

    def _start_compression(self):
        if self.is_compressing:
            return
        path = self.video_path.get()
        if not path or not os.path.isfile(path):
            self._warn("Selecione um vídeo válido primeiro!")
            return
        if not self._require_ffmpeg():
            return
        if not self.video_loaded:
            self._warn("Aguarde a leitura das informações do vídeo.")
            return
        if self.crop_mode.get() == "auto" and not self.detected_crop:
            self._warn("Detecte as bordas primeiro!")
            return
        try:
            vf = self._build_video_filter()
            crop = self._build_crop_filter()
        except ValueError as exc:
            self._warn(str(exc))
            return

        params = {
            "path": path,
            "target_mb": int(round(self.target_size.get())),
            "mode": self.compress_mode.get(),
            "resolution": self.resolution.get(),
            "vf": vf,
            "crop": crop,
            "segments": list(self.cut_segments),
            "duration": self.video_duration,
            "codec": self.video_codec,
            "has_audio": self.tem_audio,
        }
        self.is_compressing = True
        self._cancel_requested = False
        self._set_busy(True)
        self.result_label.configure(text="", text_color=COLOR_SUCCESS)
        self._set_status("Preparando...", COLOR_INFO, 0)
        self._worker = threading.Thread(target=self._compress_worker, args=(params,), daemon=True)
        self._worker.start()

    def _cancel_compression(self):
        if not self.is_compressing or self._cancel_requested:
            return
        self._cancel_requested = True
        self.cancel_btn.configure(state="disabled")
        self._set_status("⏳ Cancelando...", COLOR_WARNING)
        self._terminate_process()

    def _terminate_process(self):
        proc = self._process
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError as exc:
                print(f"[aviso] não foi possível encerrar o FFmpeg: {exc}", file=sys.stderr)

    def _check_cancel(self):
        if self._cancel_requested:
            raise CompressionCancelled()

    def _popen(self, cmd):
        """Inicia o FFmpeg guardando o processo em self._process (para cancelar)."""
        self._check_cancel()
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        self._process = proc
        if self._cancel_requested:  # cancelou entre a checagem e o Popen
            self._terminate_process()
        return proc

    def _run_cancellable(self, cmd):
        """Roda um comando curto (corte) que pode ser cancelado. Retorna (rc, stderr)."""
        proc = self._popen(cmd)
        try:
            _out, err = proc.communicate()
        finally:
            self._process = None
        self._check_cancel()
        return proc.returncode, err

    def _run_ffmpeg_with_progress(self, cmd, duration, phase):
        """Roda o FFmpeg lendo o stderr linha a linha e atualizando o progresso."""
        proc = self._popen(cmd)
        last_lines = []
        last_update = 0.0
        labels = {"pass1": "Passo 1/2 - Analisando...", "pass2": "Passo 2/2 - Codificando...",
                  "single": "Comprimindo..."}
        prefix = labels[phase]
        try:
            for line in proc.stderr:
                line = line.strip()
                if line:
                    last_lines.append(line)
                    if len(last_lines) > 30:
                        last_lines.pop(0)
                match = TIME_PROGRESS_RE.search(line)
                if not match or duration <= 0 or self._cancel_requested:
                    continue
                h, m, s = match.groups()
                current = int(h) * 3600 + int(m) * 60 + float(s)
                pct = min(99.0, (current / duration) * 100)
                if phase == "pass1":
                    pct = pct / 2
                elif phase == "pass2":
                    pct = 50 + pct / 2
                now = time.time()
                if now - last_update < 0.25:
                    continue
                last_update = now
                elapsed = now - self._encode_start
                if pct > 0:
                    eta = (elapsed / pct) * (100 - pct)
                    eta_txt = f"{int(eta // 60)}:{int(eta % 60):02d}"
                else:
                    eta_txt = "--:--"
                self._ui(self._set_status, f"{prefix}  {pct:.1f}% | ETA: {eta_txt}", COLOR_INFO, pct)
            proc.wait()
        finally:
            self._process = None
        self._check_cancel()
        if proc.returncode != 0:
            raise RuntimeError("O FFmpeg falhou:\n" + "\n".join(last_lines[-4:]))

    def _get_fps_mode_args(self):
        """Mesmo tratamento de timestamps nos dois passes (evita erro do x264
        em vídeos VFR/aparados). Usa -fps_mode (FFmpeg 5.1+) ou -vsync."""
        if self._fps_args is None:
            try:
                help_text = run_hidden([self.ffmpeg_path, "-hide_banner", "-h", "long"]).stdout
            except (OSError, subprocess.SubprocessError):
                help_text = ""
            self._fps_args = ["-fps_mode", "vfr"] if "-fps_mode" in help_text else ["-vsync", "vfr"]
        return self._fps_args

    def _compress_worker(self, p):
        temp_files = []
        passlog = None
        out_path = None
        try:
            in_path = p["path"]
            in_mb = os.path.getsize(in_path) / (1024 * 1024)
            src = in_path
            has_audio = p["has_audio"]

            # 1) Corte de trechos
            if p["segments"]:
                self._ui(self._set_status, "✂️ Cortando trechos...", COLOR_INFO, 0)
                src = self._trim_video(in_path, p["segments"], p["duration"], p["codec"], has_audio, temp_files)
            self._check_cancel()

            # 2) Cálculo de bitrate
            duration = self._probe_duration(src)
            if duration <= 0:
                raise RuntimeError("Não foi possível obter a duração do vídeo.")
            video_kbps = self._calc_video_kbps(p["target_mb"], duration, has_audio)
            if video_kbps < MIN_VIDEO_KBPS:
                raise RuntimeError("Bitrate muito baixo. Aumente o tamanho alvo.")
            vb = f"{int(video_kbps)}k"
            vf_args = ["-vf", p["vf"]] if p["vf"] else []
            audio_args = ["-c:a", "aac", "-b:a", AUDIO_BITRATE] if has_audio else []
            preset = PRESETS.get(p["mode"], "slow")

            out_path = self._get_output_path(in_path)
            self._encode_start = time.time()

            # 3) Codificação
            if p["mode"] == "quality":
                fps_args = self._get_fps_mode_args()
                passlog = os.path.join(tempfile.gettempdir(), f"vc_passlog_{int(time.time() * 1000)}")
                self._ui(self._set_status, "Passo 1/2 - Analisando...", COLOR_INFO, 0)
                pass1 = [
                    self.ffmpeg_path, "-y", "-i", src, "-c:v", "libx264", "-preset", preset, "-b:v", vb,
                    "-pass", "1", "-passlogfile", passlog, *fps_args, *vf_args, "-an", "-f", "null", "-",
                ]
                self._run_ffmpeg_with_progress(pass1, duration, "pass1")
                self._ui(self._set_status, "Passo 2/2 - Codificando...", COLOR_INFO, 50)
                pass2 = [
                    self.ffmpeg_path, "-y", "-i", src, "-c:v", "libx264", "-preset", preset, "-b:v", vb,
                    "-pass", "2", "-passlogfile", passlog, *fps_args,
                    *audio_args, "-movflags", "+faststart", *vf_args, out_path,
                ]
                self._run_ffmpeg_with_progress(pass2, duration, "pass2")
            else:
                self._ui(self._set_status, "Comprimindo...", COLOR_INFO, 0)
                cmd = [
                    self.ffmpeg_path, "-y", "-i", src, "-c:v", "libx264", "-preset", preset, "-b:v", vb,
                    *audio_args, "-movflags", "+faststart", *vf_args, out_path,
                ]
                self._run_ffmpeg_with_progress(cmd, duration, "single")

            if not os.path.exists(out_path):
                raise RuntimeError("O arquivo de saída não foi criado.")
            out_mb = os.path.getsize(out_path) / (1024 * 1024)
            change = (out_mb / in_mb - 1) * 100 if in_mb else 0
            change_txt = f"−{abs(change):.1f}%" if change <= 0 else f"+{change:.1f}%"

            result = (
                f"✅ Concluído!\n📁 {os.path.basename(out_path)}\n"
                f"📊 {in_mb:.1f} MB → {out_mb:.1f} MB ({change_txt})\n"
                f"🎬 Vídeo: {vb} | Áudio: {AUDIO_BITRATE if has_audio else 'nenhum'}"
            )
            if p["crop"]:
                result += f"\n✂️ Crop: {p['crop']}"
            if RESOLUTIONS.get(p["resolution"]):
                result += f"\n📐 Resolução: {p['resolution']}"
            if p["segments"]:
                result += f"\n⏱️ {len(p['segments'])} trecho(s) removido(s)"
            self._ui(self._on_compression_success, result, os.path.dirname(out_path))
        except CompressionCancelled:
            safe_remove(out_path)
            self._ui(self._on_compression_cancelled)
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            safe_remove(out_path)  # remove saída incompleta
            if self._cancel_requested:
                self._ui(self._on_compression_cancelled)
            else:
                self._ui(self._on_compression_error, str(exc))
        finally:
            for f in temp_files:
                safe_remove(f)
            if passlog:
                for f in glob.glob(passlog + "*"):
                    safe_remove(f)
            self._process = None
            self.is_compressing = False

    def _on_compression_success(self, result_text, folder):
        self.is_compressing = False
        self._set_status("✅ Concluído!", COLOR_SUCCESS, 100)
        self.result_label.configure(text=result_text, text_color=COLOR_SUCCESS)
        self._set_busy(False)
        box = CTkMessagebox(
            master=self.app,
            title="Sucesso",
            message="Compressão concluída! Abrir pasta?",
            icon="check",
            option_1="Sim",
            option_2="Não",
        )
        if box.get() == "Sim":
            self._open_folder(folder)

    def _on_compression_cancelled(self):
        self.is_compressing = False
        self._cancel_requested = False
        self._set_status("⚠️ Cancelado", COLOR_WARNING, 0)
        self.result_label.configure(text="")
        self._set_busy(False)

    def _on_compression_error(self, msg):
        self.is_compressing = False
        self._set_status("❌ Erro", COLOR_ERROR)
        self.result_label.configure(text=f"❌ {msg}", text_color=COLOR_ERROR)
        self._set_busy(False)
        self._error(msg)

    @staticmethod
    def _open_folder(folder):
        try:
            if hasattr(os, "startfile"):
                os.startfile(folder)  # Windows
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])  # macOS
            else:
                subprocess.Popen(["xdg-open", folder])  # Linux
        except OSError as exc:
            print(f"[aviso] não foi possível abrir a pasta: {exc}", file=sys.stderr)

    # ── Encerramento ──────────────────────────────────────────────────────

    def _on_close(self):
        if self.is_compressing:
            box = CTkMessagebox(
                master=self.app,
                title="Compressão em andamento",
                message="Uma compressão está em andamento. Deseja cancelar e sair?",
                icon="question",
                option_1="Sim",
                option_2="Não",
            )
            if box.get() != "Sim":
                return
            self._cancel_requested = True
            self._terminate_process()
            if self._worker is not None:
                self._worker.join(timeout=5)  # deixa a thread limpar os temporários
        self._save_settings()
        self.app.destroy()


if __name__ == "__main__":
    VideoCompressorApp().run()
