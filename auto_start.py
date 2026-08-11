"""Auto-start do fluxo ao vivo.

ADICIONADO NESTE FORK — nao faz parte do VisoMaster original.

Motivo: subir o clone ao vivo exigia uma sequencia manual que nao esta escrita
em lugar nenhum da interface (marcar o filtro de webcam, selecionar a camera,
carregar a foto, marcar o card, vincular ao rosto detectado). Toda vez que o
app reinicia, tudo isso se perde. Aqui a sequencia acontece sozinha.

Nao e cosmetico: no fluxo de webcam os rostos sao re-detectados continuamente,
entao o estado precisa se restabelecer sem intervencao.

Para desligar: defina a variavel de ambiente AVATARKIT_NO_AUTOSTART=1.

Cada passo e defensivo por design — se algo falhar, o app continua utilizavel
manualmente. Um auto-start que derruba a aplicacao seria pior que nenhum.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6 import QtCore

PASTA_FOTOS = Path(r"C:\AvatarKit\fotos-fonte")
EXTENSOES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Atrasos em ms. O carregamento de fotos e a enumeracao de webcams sao
# assincronos (QThread workers), entao cada passo espera o anterior assentar.
# Folgados de proposito: enumerar dispositivos DirectShow pode levar segundos,
# e um passo que roda cedo demais falha em silencio (lista ainda vazia).
ATRASO_FOTOS = 2000
ATRASO_WEBCAMS = 2500
ATRASO_MARCAR_FACE = 6000
ATRASO_SELECIONAR_WEBCAM = 8000


def _log(msg: str) -> None:
    print(f"[auto-start] {msg}")


def _ha_fotos() -> bool:
    if not PASTA_FOTOS.exists():
        return False
    return any(p.suffix.lower() in EXTENSOES for p in PASTA_FOTOS.iterdir() if p.is_file())


def _carregar_fotos(janela) -> None:
    try:
        from app.ui.widgets.actions import list_view_actions

        arquivos = sorted(
            str(p) for p in PASTA_FOTOS.iterdir()
            if p.is_file() and p.suffix.lower() in EXTENSOES
        )
        if not arquivos:
            _log("pasta de fotos vazia")
            return

        # ATENCAO: source_type NAO pode ser "folder" nem "files".
        # Nesses dois casos select_input_face_images ABRE UM QFileDialog e
        # SOBRESCREVE o folder_name/files_list recebido — um dialogo modal que
        # trava este callback esperando clique do usuario. Com qualquer outro
        # valor a funcao vai direto para o InputFacesLoaderWorker usando a
        # lista que passamos, que e o que queremos.
        list_view_actions.select_input_face_images(
            janela, source_type="auto", files_list=arquivos
        )
        janela.inputFacesPathLineEdit.setText(str(PASTA_FOTOS))
        _log(f"{len(arquivos)} foto(s) enviada(s) para carregamento")
    except Exception as exc:  # noqa: BLE001
        _log(f"nao consegui carregar as fotos: {exc}")


def _carregar_webcams(janela) -> None:
    """Forca a enumeracao das webcams.

    O checkbox de filtro nasce marcado (mudanca deste fork), mas a lista so e
    populada pelo sinal `toggled` — que NAO dispara quando o valor ja nasce
    marcado. Sem esta chamada explicita o checkbox aparece ligado e a lista
    fica vazia, que e pior do que nascer desmarcado.
    """
    try:
        from app.ui.widgets.actions import list_view_actions

        list_view_actions.load_target_webcams(janela)
        _log("enumeracao de webcams disparada")
    except Exception as exc:  # noqa: BLE001
        _log(f"nao consegui enumerar webcams: {exc}")


def _marcar_primeira_face(janela) -> None:
    """Marca todas as faces de origem.

    Marcar TODAS (e nao so a primeira) e proposital: com varias fotos da mesma
    pessoa, o embedding medio e mais estavel sob mudanca de pose e de luz que
    qualquer foto isolada. E o maior ganho de qualidade disponivel de graca.
    """
    try:
        faces = getattr(janela, "input_faces", {}) or {}
        if not faces:
            _log("nenhuma face de origem apareceu — pulando")
            return
        marcadas = 0
        for botao in faces.values():
            if hasattr(botao, "setChecked") and not botao.isChecked():
                botao.click()  # click() dispara os handlers; setChecked() nao
                marcadas += 1
        _log(f"{marcadas} face(s) de origem marcada(s) de {len(faces)}")
    except Exception as exc:  # noqa: BLE001
        _log(f"nao consegui marcar as faces: {exc}")


def _selecionar_webcam(janela) -> None:
    try:
        alvos = getattr(janela, "target_videos", {}) or {}
        webcams = [b for b in alvos.values() if getattr(b, "file_type", "") == "webcam"]
        if not webcams:
            _log("nenhuma webcam na lista de alvos — conecte a camera e selecione a mao")
            return
        webcams[0].click()
        _log(f"webcam selecionada ({len(webcams)} disponivel(is))")
    except Exception as exc:  # noqa: BLE001
        _log(f"nao consegui selecionar a webcam: {exc}")


def agendar(janela) -> None:
    """Agenda a sequencia. Chamado por main.py depois de window.show()."""
    if os.environ.get("AVATARKIT_NO_AUTOSTART"):
        _log("desativado por AVATARKIT_NO_AUTOSTART")
        return
    if not _ha_fotos():
        _log(f"sem fotos em {PASTA_FOTOS} — auto-start nao faz nada")
        return

    QtCore.QTimer.singleShot(ATRASO_FOTOS, lambda: _carregar_fotos(janela))
    QtCore.QTimer.singleShot(ATRASO_WEBCAMS, lambda: _carregar_webcams(janela))
    QtCore.QTimer.singleShot(ATRASO_MARCAR_FACE, lambda: _marcar_primeira_face(janela))
    QtCore.QTimer.singleShot(
        ATRASO_SELECIONAR_WEBCAM, lambda: _selecionar_webcam(janela)
    )
    _log("sequencia agendada (fotos -> webcams -> marcar -> selecionar)")
