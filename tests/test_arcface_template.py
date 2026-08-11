"""Trava de regressao para o template arcface128.

O bug: `arcface_src` tem forma (1, 5, 2) por causa do expand_dims em
faceutil.py:117, entao `template[:, 0]` indexa o keypoint 0 (retornando o par
[x, y] dele) em vez da coluna x dos cinco pontos. O deslocamento de centragem
caia num unico ponto, nos dois eixos.

Efeito medido em 512: distancia interpupilar do template ia para 113.77 px em
vez de 140.95 px — um crop 19.3% pequeno demais, com o keypoint do olho esquerdo
deslocado 32 px em y. Os modelos de swap sao treinados no template arcface
canonico, entao isso os alimentava fora da distribuicao de treino.
"""

import numpy as np

from app.processors.utils import faceutil


def test_deslocamento_cai_na_coluna_x_e_nao_num_keypoint():
    """So as coordenadas x mudam; nenhum y e tocado."""
    tmpl = np.squeeze(np.asarray(faceutil.get_arcface_template(512, "arcface128")))
    base = np.squeeze(faceutil.arcface_src.copy()) * 4.0

    np.testing.assert_allclose(tmpl[:, 0], base[:, 0] + 32.0, rtol=0, atol=1e-4)
    np.testing.assert_allclose(tmpl[:, 1], base[:, 1], rtol=0, atol=1e-4)


def test_bate_com_o_template_do_face_restorers():
    """face_restorers.py:118-119 monta o mesmo template num array (5, 2), onde
    `[:, 0]` de fato e a coluna x. As duas construcoes tem que coincidir — era a
    discordancia entre elas que quebrava o modo 'Blend' do restorer."""
    tmpl = np.squeeze(np.asarray(faceutil.get_arcface_template(512, "arcface128")))

    esperado = np.squeeze(faceutil.arcface_src.copy()) * 4.0
    esperado[:, 0] += 32.0

    np.testing.assert_allclose(tmpl, esperado, rtol=0, atol=1e-4)


def test_distancia_interpupilar_do_template():
    """Numero-sentinela: o par de olhos tem que ficar horizontal e com a escala
    certa. Com o bug dava 113.77 px e um roll espurio."""
    tmpl = np.squeeze(np.asarray(faceutil.get_arcface_template(512, "arcface128")))

    olho_esq, olho_dir = tmpl[0], tmpl[1]
    ipd = float(np.linalg.norm(olho_dir - olho_esq))

    assert abs(ipd - 140.95) < 0.05, f"IPD do template = {ipd:.2f}, esperado ~140.95"
    # os dois olhos na mesma altura (sem roll introduzido pelo template)
    assert abs(olho_esq[1] - olho_dir[1]) < 1.0
