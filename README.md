# Monitor do Sistema

Card flutuante, sempre no topo, com CPU, GPU (NVIDIA), memória, rede e disco. Um único código
(Python + Qt/PySide6) para **Linux** e **Windows**.

- Modo curto (CPU, GPU, memória, rede, disco) e modo avançado (temperaturas, núcleos, top processos…).
- Nunca rouba o foco, aparece em todas as áreas de trabalho, arrasta com o mouse.
- Mostra/esconde por atalho global.

## Rodar em modo dev

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip ...
.venv/bin/python sysmon.py                          # abre (ou alterna, se já estiver rodando)
```

Opções: `--toggle`, `--show`, `--hide`, `--advanced`, `--quit`, `--hidden` (inicia escondido),
`--autostart on|off` (início automático no login).

## Linux (Ubuntu / GNOME)

Requisito: `sudo apt install libxcb-cursor0` (o Qt usa o X11/XWayland; no Wayland o card roda via XWayland
para poder ficar no topo e se posicionar. `SYSMON_NATIVE=1` força o Wayland nativo).

```bash
./build.sh                  # gera dist/sysmon/sysmon (+ dist/sysmon-linux-x86_64.tar.gz)
./install-linux.sh          # atalho Ctrl+Page Up, autostart e entrada no menu
SHORTCUT='<Super>m' ./install-linux.sh
./install-linux.sh --uninstall
```

Sem o build, o instalador usa `.venv/bin/python sysmon.py`.

## Windows

```powershell
python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python sysmon.py                      # modo dev
.\build.ps1                                         # gera dist\sysmon.exe
dist\sysmon.exe --autostart on                      # abre junto com o Windows
```

- Atalho global padrão: **Ctrl+Alt+M**. Para mudar: `--hotkey ctrl+shift+m` ou a chave `"hotkey"` em
  `%APPDATA%\sysmon\config.json`.
- Ícone na bandeja do sistema (clique alterna; botão direito: avançado / sair).
- Limitações atuais: sem temperatura de CPU/disco (o Windows não expõe isso sem driver de terceiros),
  e a leitura/escrita de disco é o total da máquina (o psutil não separa por partição no Windows).
  GPU: só NVIDIA (via `nvml.dll`, que vem com o driver).

## Gerar os executáveis no GitHub

O workflow `.github/workflows/build.yml` compila Linux e Windows. Rode manualmente (Actions → build) ou
crie uma tag `v1.0.0`: os arquivos saem como artefatos e anexados à Release.

## Testes

```bash
.venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q
```

`legado/` guarda a versão original em GTK (somente Linux), mantida como referência.
