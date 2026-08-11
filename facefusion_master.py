"""Aba Master 4K — a interface do FaceFusion embutida numa janela do VisoMaster.

ADICIONADO NESTE FORK — nao faz parte do VisoMaster original.

POR QUE ISTO EXISTE
O VisoMaster normaliza todo swap para um template canonico de 512
(frame_worker_pipeline: `swap = self.worker.t512(output)`), o que e a escolha
certa para tempo real mas e um TETO. O FaceFusion warpa o crop do enhancer a
partir do frame em RESOLUCAO CHEIA, sem esse gargalo — e, sendo offline, aceita
pixel_boost 1024 e GPEN-BFR-2048, que nao cabem em 33,3 ms.

Ou seja: nao sao dois candidatos para o mesmo trabalho. Sao duas ferramentas
para dois trabalhos — ao vivo aqui, material gravado la. O split e forcado pelo
codigo dos dois, nao e preferencia.

COMO FUNCIONA
Os dois usam frameworks de UI incompativeis: VisoMaster e Qt nativo, FaceFusion
e Gradio (servidor web). Nao existe "portar a GUI". O que da para fazer — e e o
que esta aqui — e subir o servidor do FaceFusion sob demanda e embutir a pagina
dele num QWebEngineView, dentro de uma janela Qt. Fica tudo num app so.

O servidor sobe apenas quando a janela e aberta, e e encerrado ao fechar: nao ha
motivo para manter um segundo processo pesado vivo durante uma live.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

from PySide6 import QtCore, QtWidgets

FF = Path(r"C:\AvatarKit\master\facefusion")
FFMPEG = Path(r"C:\AvatarKit\_tools\ffmpeg\bin")
PORTA = 7861  # 7860 e o padrao; usamos outra para nao colidir com um FaceFusion aberto a mao


def _ambiente() -> dict:
    """PATH com as DLLs do CUDA 13 + ffmpeg.

    Sem isto o onnxruntime nao acha as DLLs e cai para CPU EM SILENCIO — o app
    abre, funciona, e fica 50-100x mais lento sem dar erro. O FaceFusion tambem
    se recusa a iniciar sem ffmpeg/ffprobe/curl no PATH.
    """
    sp = FF / ".venv" / "Lib" / "site-packages"
    extras = [
        FFMPEG,
        sp / "nvidia" / "cu13" / "bin" / "x86_64",
        sp / "nvidia" / "cudnn" / "bin",
        sp / "tensorrt_libs",
    ]
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(str(p) for p in extras) + os.pathsep + env.get("PATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    # O FaceFusion chama ui.launch() SEM server_port (uis/layouts/default.py:128),
    # e nao expoe flag de porta na CLI. O Gradio respeita esta variavel — e o
    # unico jeito de fixar a porta em vez de torcer para ele cair na 7860.
    env["GRADIO_SERVER_PORT"] = str(PORTA)
    return env


def _porta_viva(porta: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, porta)) == 0


class JanelaMaster(QtWidgets.QMainWindow):
    """Janela com a UI do FaceFusion embutida."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Master 4K — FaceFusion (offline, qualidade máxima)")
        self.resize(1500, 950)
        self.proc: subprocess.Popen | None = None

        central = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        barra = QtWidgets.QWidget()
        bl = QtWidgets.QHBoxLayout(barra)
        bl.setContentsMargins(10, 6, 10, 6)
        self.rotulo = QtWidgets.QLabel("Servidor parado")
        self.btn = QtWidgets.QPushButton("Iniciar")
        self.btn.clicked.connect(self._alternar)
        recarregar = QtWidgets.QPushButton("Recarregar")
        recarregar.clicked.connect(lambda: self.web and self.web.reload())
        bl.addWidget(self.rotulo, 1)
        bl.addWidget(recarregar)
        bl.addWidget(self.btn)
        lay.addWidget(barra)

        dica = QtWidgets.QLabel(
            "  Offline — use para clipe, VOD e thumbnail. Para ao vivo, a janela principal.\n"
            "  Já pré-configurado: hyperswap_1c_256 · pixel_boost 1024 · gpen_bfr_2048 · blend 45"
        )
        dica.setStyleSheet("color:#8fa2a8; padding:4px 10px 8px 10px;")
        lay.addWidget(dica)

        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView

            self.web = QWebEngineView()
            lay.addWidget(self.web, 1)
        except ImportError:
            self.web = None
            aviso = QtWidgets.QLabel(
                "QtWebEngine não disponível neste ambiente.\n"
                "A interface abrirá no navegador padrão quando o servidor iniciar."
            )
            aviso.setAlignment(QtCore.Qt.AlignCenter)
            lay.addWidget(aviso, 1)

        self.setCentralWidget(central)

    # ---- servidor ----
    def _alternar(self):
        if self.proc and self.proc.poll() is None:
            self._parar()
        else:
            self._iniciar()

    def _iniciar(self):
        if _porta_viva(PORTA):
            self._carregar()
            return
        if not (FF / "facefusion.py").exists():
            self.rotulo.setText(f"FaceFusion não encontrado em {FF}")
            return

        self.rotulo.setText("Iniciando servidor… (a 1ª vez baixa modelos, pode demorar)")
        self.btn.setEnabled(False)
        QtWidgets.QApplication.processEvents()

        # NAO passar "--open-browser false": o argumento e action='store_true',
        # ou seja uma FLAG sem valor. Passar "false" faz o argparse abortar com
        # "unrecognized arguments: false" e o servidor morre antes de subir.
        # Quem controla isso e `open_browser` no facefusion.ini.
        #
        # E NAO suprimir a saida com DEVNULL: quando o servidor morre, o motivo
        # some junto e a janela so consegue dizer "encerrou sozinho". A saida vai
        # para um arquivo que a propria janela mostra em caso de falha.
        self.log = Path(os.environ.get("TEMP", ".")) / "facefusion_master.log"
        self._flog = open(self.log, "w", encoding="utf-8", errors="replace")  # noqa: SIM115
        self.proc = subprocess.Popen(
            [
                str(FF / ".venv" / "Scripts" / "python.exe"), "facefusion.py", "run",
                "--ui-layouts", "default",
            ],
            cwd=str(FF), env=_ambiente(),
            stdout=self._flog, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        # Espera a porta abrir. O FaceFusion demora a subir (carrega modelos),
        # entao damos bastante folga em vez de falhar cedo.
        limite = time.time() + 180
        while time.time() < limite:
            if self.proc.poll() is not None:
                self._mostrar_erro()
                self.btn.setEnabled(True)
                self.btn.setText("Iniciar")
                return
            if _porta_viva(PORTA):
                self._carregar()
                self.btn.setEnabled(True)
                return
            QtWidgets.QApplication.processEvents()
            time.sleep(0.4)

        self.rotulo.setText("Tempo esgotado esperando o servidor")
        self.btn.setEnabled(True)

    def _mostrar_erro(self):
        """Mostra POR QUE o servidor morreu, em vez de so dizer que morreu."""
        try:
            self._flog.flush()
        except Exception:  # noqa: BLE001
            pass
        texto = ""
        try:
            linhas = [
                ln.rstrip() for ln in self.log.read_text(encoding="utf-8", errors="replace").splitlines()
                if ln.strip() and "%|" not in ln
            ]
            texto = "\n".join(linhas[-14:])
        except Exception:  # noqa: BLE001
            pass
        self.rotulo.setText("O servidor encerrou sozinho")
        if texto:
            QtWidgets.QMessageBox.warning(
                self, "FaceFusion encerrou",
                f"Saída do servidor (fim do log):\n\n{texto}\n\nLog completo: {self.log}",
            )

    def _carregar(self):
        url = f"http://127.0.0.1:{PORTA}"
        self.rotulo.setText(f"Rodando em {url}")
        self.btn.setText("Parar")
        if self.web is not None:
            self.web.setUrl(QtCore.QUrl(url))
        else:
            import webbrowser

            webbrowser.open(url)

    def _parar(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        if self.web is not None:
            self.web.setUrl(QtCore.QUrl("about:blank"))
        self.rotulo.setText("Servidor parado")
        self.btn.setText("Iniciar")

    def closeEvent(self, event):
        # Nao deixar um segundo processo pesado vivo depois de fechar a janela.
        self._parar()
        super().closeEvent(event)


def instalar_no_menu(janela_principal) -> None:
    """Acrescenta 'Master 4K (FaceFusion)' ao menu Ver da janela principal."""
    try:
        menu = getattr(janela_principal, "menuView", None)
        if menu is None:
            return
        act = menu.addAction("Master 4K (FaceFusion)…")

        def abrir():
            janela = getattr(janela_principal, "_janela_master", None)
            if janela is None:
                janela = JanelaMaster(janela_principal)
                janela_principal._janela_master = janela
            janela.show()
            janela.raise_()
            janela.activateWindow()

        act.triggered.connect(abrir)
        print("[master] item 'Master 4K (FaceFusion)' adicionado ao menu Ver")
    except Exception as exc:  # noqa: BLE001
        print(f"[master] não consegui instalar o item de menu: {exc}")
