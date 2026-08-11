# Changelog do fork (xdzleo)

Linha de versão própria, separada do upstream, no formato `<versão-upstream>+xdz.<n>`.
O `+xdz.N` sobe **a cada mudança nossa**; a parte da esquerda só muda quando
sincronizamos com o upstream.

Assim dá para saber, olhando o título do app, exatamente qual build está rodando —
o app já mostra `VisoMaster Fusion - 3.9.3+xdz.1 (<hash>)`.

---

## 3.9.3+xdz.1 — 11/ago/2026

Base: upstream `v3.9.3`.

### Performance

- **cuDNN autotune + TF32 ligados para Blackwell** (`blackwell_tuning.py`,
  chamado por `main.py`). O pipeline normaliza todo swap para um template
  canônico de 512, ou seja, o shape das convoluções é constante entre frames —
  que é exatamente o caso em que `cudnn.benchmark` compensa. O upstream não seta
  nenhuma flag de backend do torch.

  Medido em RTX 5090 (sm_120, torch 2.11.0+cu130), 200 iterações após warmup,
  em ops representativas do pipeline (convs 3×3, resize bilinear e matmul a 512):

  | | ms/iter | it/s |
  |---|---|---|
  | baseline | 0,260 | 3849 |
  | com tuning | 0,171 | 5836 |

  **34% mais rápido.** Escopo honesto: acelera o lado PyTorch (máscaras,
  transforms, affine de paste-back, face editor / LivePortrait). O swapper roda
  no ONNX Runtime e não é afetado por estas flags.

### Documentação

- **`docs/INSTALL-RTX50-VENV.md`** — documenta o fallback silencioso para CPU no
  caminho `.venv` + `uv` em RTX 50xx. Duas causas independentes, nenhuma delas dá
  erro visível:
  1. `requirements_cu13.txt` fixa runtime CUDA 13 mas resolve
     `onnxruntime-gpu==1.26.0`, que é build de CUDA **12** (pede `cufft64_12.dll`).
     O build CUDA 13 é o `1.28.0`.
  2. As DLLs dos wheels `nvidia-*` ficam em `site-packages` sem entrar no caminho
     de busca do Windows, e o código nunca chama `os.add_dll_directory()`. O Conda
     mascara isso; um `.venv` puro não.

  Vale destaque porque `get_available_providers()` **lista** CUDA/TensorRT mesmo
  quando eles não carregam — ele reporta o que foi compilado, não o que funciona.
  O único teste válido é conferir `session.get_providers()[0]` após criar a sessão.

---

## Como sincronizar com o upstream

```bash
git fetch upstream
git merge upstream/main
# resolver conflitos (esperados só em main.py e version.json)
# depois: bump +xdz.N e registrar aqui
```
