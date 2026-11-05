# 🎬 Video Compressor - Treinamentos

🇧🇷 Português | [🇺🇸 English](README.en.md)

Aplicativo desktop para **Windows, macOS e Linux** que **comprime vídeos para um tamanho-alvo exato** (padrão **490 MB**, para caber no limite de 500 MB da plataforma) e permite **editar antes de comprimir**: remover bordas pretas (crop automático ou manual, com preview) e remover vários trechos de minutagem. Mostra a **estimativa de bitrate** antes de começar e permite **cancelar** a compressão a qualquer momento.

---

## ✅ Pré-requisitos

| Item | Versão | Como instalar |
|---|---|---|
| Sistema | Windows 10/11, macOS ou Linux | Windows: `setup.bat` faz tudo · macOS/Linux: veja [Rodando sem os .bat](#-rodando-sem-os-bat-macos-linux-ou-terminal) |
| Python | 3.8+ (o setup instala o 3.12) | `setup.bat` ou [python.org](https://www.python.org/downloads/) |
| Bibliotecas | `customtkinter`, `Pillow`, `CTkMessagebox` (listadas em `requirements.txt`) | `setup.bat` (num ambiente virtual `.venv`) |
| FFmpeg + FFprobe | qualquer versão recente | `setup.bat`, `install_ffmpeg.bat` ou [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) |

> Instalação manual do Python: marque **"Add python.exe to PATH"** no instalador.
> Instalação manual do FFmpeg: extraia em `C:\ffmpeg\` e adicione `C:\ffmpeg\bin` ao PATH.
> Se o `CTkMessagebox` não estiver instalado, o app continua funcionando com as caixas de diálogo padrão do sistema.
>
> Os arquivos `.bat` são um **atalho para quem usa Windows** e não quer usar o terminal. Em macOS, Linux (ou Windows pelo terminal), veja [Rodando sem os .bat](#-rodando-sem-os-bat-macos-linux-ou-terminal).

---

## 🚀 Como usar

1. **Primeira vez:** dê duplo clique em `setup.bat` e aguarde a instalação do Python, das bibliotecas e do FFmpeg. As bibliotecas ficam num ambiente virtual (pasta `.venv` do projeto) — o Python do sistema não é alterado.
2. Dê duplo clique em `start.bat` para abrir o aplicativo.
3. Em **📁 Vídeo de entrada**, clique em **📂 Procurar** e escolha o vídeo. À direita aparecem tamanho, duração, resolução, codec e bitrate (em **vermelho** se passa de 500 MB, em **verde** caso contrário) e a linha **🎯 Alvo**, com o bitrate de vídeo que será usado.
4. *(Opcional)* Em **✂️ Crop / Cortar bordas**:
   - **🔍 Auto** → clique em **Detectar bordas pretas**. Os campos manuais são preenchidos automaticamente.
   - **✏️ Manual** → digite quantos pixels cortar em Topo, Baixo, Esq e Dir.
   - Clique em **🖼️ Preview** para ver o frame original e o cortado lado a lado.
5. *(Opcional)* Em **⏱️ Cortar minutagens**, informe **De** e **Até** (`HH:MM:SS` ou `MM:SS`) e clique em **➕ Adicionar** (ou tecle **ENTER**) para cada trecho a **remover**. Para tirar um trecho da lista, selecione a linha dele e clique em **🗑️ Remover** (sem seleção, remove o último). **🧹 Limpar** apaga todos.
6. Em **⚙️ Compressão**, ajuste o **tamanho alvo** (100–500 MB), o **modo** (🎯 Qualidade Máxima é o padrão) e a **📐 Resolução** (Original, 1080p, 720p ou 480p). A estimativa à direita é atualizada na hora.
7. Clique em **🚀 Comprimir Vídeo** e acompanhe o progresso e o tempo restante (ETA). Para interromper, clique em **❌ Cancelar** — a saída parcial e os temporários são apagados.
8. Ao terminar, o arquivo `nome_compressed.mp4` fica **na mesma pasta do original** e o app oferece abrir a pasta.

> O tamanho alvo, o modo e a resolução são lembrados na próxima vez que você abrir o app.

---

## 💻 Rodando sem os .bat (macOS, Linux ou terminal)

O código Python funciona nos três sistemas; só a instalação muda.

**1. Instale o FFmpeg e o Python 3.8+ com Tkinter**

| Sistema | Comando |
|---|---|
| macOS (Homebrew) | `brew install ffmpeg python-tk` |
| Ubuntu / Debian | `sudo apt install ffmpeg python3-venv python3-tk` |
| Fedora | `sudo dnf install ffmpeg python3-tkinter` |
| Windows | `winget install Gyan.FFmpeg` e Python de [python.org](https://www.python.org/downloads/) |

**2. Crie o ambiente virtual e instale as dependências**

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**3. Rode o app**

```bash
python video_compressor.py
```

Nas próximas vezes, basta ativar o `.venv` e rodar o passo 3.

> **macOS:** abra o app sempre pelo Terminal, como acima. Aberto de outro jeito, o macOS pode não carregar o PATH do Homebrew e o app não encontra o FFmpeg.

**Sistemas testados:** Windows 10/11 é a plataforma principal (com os `.bat`) · Linux: testado · macOS: deve funcionar, mas ainda não foi testado.

---

## ⚙️ Como funciona a compressão

### Fórmula do bitrate

```
duração      = duração do vídeo após remover os trechos (segundos)
total_kbps   = (alvo_MB × 1024 × 1024 × 8) / (duração × 1000)
com áudio:   vídeo_kbps = total_kbps − 128   (áudio AAC 128 kbps)
sem áudio:   vídeo_kbps = total_kbps          (nada é reservado para áudio)
```

Se `vídeo_kbps < 100`, o app recusa (bitrate baixo demais) e pede para aumentar o tamanho alvo.

### Modos e presets

| Modo | Passes | Preset libx264 | Quando usar |
|---|---|---|---|
| 🎯 Qualidade Máxima (padrão) | 2 (two-pass) | `slow` | Entrega final: melhor imagem para o mesmo tamanho |
| ⚡ Rápido | 1 | `faster` | Pressa ou testes; perda mínima em conteúdo de treinamento (slides, tela) |

No **two-pass**, o 1º passo analisa o vídeo inteiro e o 2º distribui os bits onde mais importam — o tamanho final fica mais próximo do alvo. Leva bem mais tempo que o modo Rápido.

### Pipeline

1. **Corte de trechos** (se houver): os trechos mantidos são copiados sem recodificar (`-ss`/`-t` + `-c copy`) e unidos num arquivo temporário.
2. **Filtros de vídeo:** `crop=...` (bordas) e `scale=-2:1080/720/480` (resolução).
3. **Codificação:** H.264 (`libx264`) + AAC 128k (se houver áudio), com `-movflags +faststart` (o vídeo começa a tocar antes de baixar inteiro).

### Formato de saída

- Contêiner **MP4**, vídeo **H.264**, áudio **AAC 128 kbps** (ou sem áudio, se o original não tiver).
- Nome: `video_compressed.mp4`; se já existir, `video_compressed_1.mp4`, `_2`, etc.
- Arquivos temporários (corte, preview, logs do two-pass) são apagados ao final, em caso de erro e ao cancelar.

---

## 📊 Exemplos (alvo 490 MB, vídeo com áudio)

| Duração final | Bitrate total | Bitrate de vídeo | Resolução sugerida |
|---|---|---|---|
| 30 min | ~2284 kbps | 2155k | Original / 1080p |
| 1 h | ~1142 kbps | 1013k | 1080p para aulas/tela |
| 1 h 30 | ~761 kbps | 633k | 720p |
| 2 h | ~571 kbps | 442k | 720p |
| 3 h | ~381 kbps | 252k | 720p ou 480p |
| 4 h | ~285 kbps | 157k | 480p — ou divida o vídeo |

> Dica: em vídeos longos, **remover bordas pretas**, **trechos inúteis** (intervalos, silêncio) e **reduzir a resolução** libera bitrate para o que importa.

---

## ❓ FAQ

**1. O arquivo final ficou um pouco menor que o alvo. É normal?**
Sim. O cálculo mira o tamanho exato, mas o encoder economiza bits em cenas simples (slides, tela parada). O padrão de 490 MB deixa margem para o limite de 500 MB.

**2. O app diz "FFmpeg não encontrado". E agora?**
Clique em **📦 Instalar via Winget** no aviso ou rode `install_ffmpeg.bat`. Se já instalou e o aviso continua, feche e abra o app (ou reinicie o PC). O app também procura em `C:\ffmpeg\bin`, numa pasta `ffmpeg\bin` ao lado do script e na pasta do Winget.
No **macOS**, instale com `brew install ffmpeg` e abra o app de novo pelo Terminal. No **Linux**, use o gerenciador de pacotes (`sudo apt install ffmpeg` ou `sudo dnf install ffmpeg`). Nesses sistemas o aviso do app já mostra o comando certo.

**3. Os cortes de minutagem são exatos ao segundo?**
Quase. Para ser rápido e não perder qualidade, o corte copia o vídeo sem recodificar e por isso começa no **keyframe** mais próximo antes do tempo pedido — normalmente 1–2 segundos de diferença (pode sobrar um pedacinho do trecho removido). O bitrate é calculado com a duração real após o corte, então o tamanho final continua correto.

**4. Qual resolução escolher?**
Use a tabela de exemplos: quanto menor o bitrate disponível, menor a resolução ideal. Um 720p com bitrate folgado costuma ficar mais nítido que um 1080p "espremido". Confira a linha **🎯 Alvo** antes de comprimir.

**5. Cancelei a compressão. Sobrou algum arquivo?**
Não. Ao cancelar, o FFmpeg é encerrado e o app apaga a saída parcial, o arquivo de corte e os logs do two-pass. O status mostra **⚠️ Cancelado** e você pode ajustar as configurações e começar de novo.

---

## 📂 Arquivos

```
video-compressor/
├── video_compressor.py   # Aplicativo completo (interface + lógica)
├── requirements.txt      # Dependências Python (pip install -r requirements.txt)
├── setup.bat             # Windows: instala Python 3.12, cria o .venv, instala bibliotecas e FFmpeg
├── start.bat             # Windows: abre o aplicativo usando o .venv
├── install_ffmpeg.bat    # Windows: instala o FFmpeg (Winget ou manual)
├── README.md             # Este arquivo
├── README.en.md          # Versão em inglês
├── .gitignore
└── .venv/                # Ambiente virtual (criado na instalação; fora do Git)

~/.video_compressor_settings.json   # configurações salvas (%USERPROFILE% no Windows; criado ao fechar o app)
```
