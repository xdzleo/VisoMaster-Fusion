"""Ajustes de performance para RTX 5090 (Blackwell, sm_120).

ADICIONADO MANUALMENTE — nao faz parte do VisoMaster-Fusion original.
Chamado por main.py. Para reverter: apague a chamada em main.py.

O que faz e por que:

1. cudnn.benchmark = True
   O pipeline trabalha num template canonico de tamanho FIXO (512). Com shape
   fixo, o cuDNN roda um autotune uma vez e depois reusa o melhor algoritmo de
   convolucao. Este e exatamente o caso de uso em que ele rende — e o VisoMaster
   nao liga isso em lugar nenhum do codigo. Em shapes variaveis seria ruim
   (re-autotune a cada shape novo), mas nao e o caso aqui.

2. TF32 nos tensor cores (matmul + cudnn)
   Blackwell executa TF32 nos tensor cores com precisao suficiente para visao.
   Sem isso o torch usa FP32 puro nas convolucoes/matmuls e deixa desempenho
   na mesa. Os modelos ONNX ja sao fp16, entao isso afeta o lado torch:
   mascaras, transforms, affine de paste-back, face editor / LivePortrait.

3. set_float32_matmul_precision("high")
   Mesma familia do item 2, no caminho novo de API do torch.

ESCOPO HONESTO: isto acelera as operacoes que rodam em PyTorch. A inferencia do
swapper em si roda no ONNX Runtime (CUDA/TensorRT), que nao e afetado por estas
flags — la o ganho vem do provider TensorRT e dos modelos fp16.
"""

from __future__ import annotations


def apply(verbose: bool = True) -> bool:
    """Aplica as flags. Retorna True se a GPU foi detectada e ajustada."""
    try:
        import torch
    except ImportError:
        return False

    if not torch.cuda.is_available():
        if verbose:
            print("[tuning] CUDA indisponivel — nenhum ajuste aplicado.")
        return False

    name = torch.cuda.get_device_name(0)
    major, minor = torch.cuda.get_device_capability(0)

    # 1) Autotune de convolucao — vale porque o shape do template e fixo.
    torch.backends.cudnn.benchmark = True

    # 2) TF32 nos tensor cores.
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    # 3) Caminho novo da API para o mesmo trade-off.
    try:
        torch.set_float32_matmul_precision("high")
    except AttributeError:
        pass  # torch antigo — itens 1 e 2 ja cobrem o essencial

    if verbose:
        print(
            f"[tuning] {name} (sm_{major}{minor}) — "
            "cudnn.benchmark ON, TF32 ON, matmul=high"
        )
    return True
