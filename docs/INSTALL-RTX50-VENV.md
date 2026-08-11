# Instalação em RTX 50xx (Blackwell) usando `.venv` + `uv` no Windows

O guia oficial do repositório (`Step by step guide to install Conda and Visomaster for RTX 50xx series.pdf`)
usa Conda. Quem instala pelo caminho `.venv` + `uv` — que é o outro caminho que o
`Start.bat` aceita — esbarra em **dois problemas que não dão erro visível**: o app
abre, funciona, e roda inteiramente em CPU.

Verificado em 11/ago/2026, RTX 5090 (sm_120), Windows 11, driver 610.88, Python 3.12.10.

---

## Problema 1 — `onnxruntime-gpu` de CUDA 12 junto com runtime CUDA 13

O `requirements_cu13.txt` fixa o runtime **CUDA 13**:

```
cuda-toolkit==13.2.1
nvidia-cublas==13.4.0.1
nvidia-cudnn-cu13==9.21.1.3
tensorrt-cu13==10.16.1.11
```

…e junto fixa `onnxruntime-gpu==1.26.0`. Instalando com `uv` a partir da raiz do
repositório (portanto com os `extra-index-url` do `pyproject.toml` ativos), o wheel
que se resolve para `1.26.0` é build de **CUDA 12**:

```
Error loading "onnxruntime_providers_cuda.dll"
which depends on "cufft64_12.dll" which is missing.
```

Note o `_12`. Ele procura a runtime do CUDA 12 num ambiente onde só existe a do
CUDA 13. O resultado não é uma exceção — é isto:

```
providers   ['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']
CUDAExecutionProvider  -> caiu para CPUExecutionProvider
```

O provider **aparece na lista** (`get_available_providers()` mente: ele lista o que
foi compilado, não o que carrega) e a execução cai para CPU em silêncio.

**Correção:** usar o build CUDA 13, que no PyPI é o `1.28.0`:

```bash
uv pip install --index-url https://pypi.org/simple "onnxruntime-gpu==1.28.0"
```

---

## Problema 2 — as DLLs do CUDA não estão no caminho de busca do Windows

Mesmo com o build certo, os pacotes `nvidia-*` instalam as DLLs dentro de
`site-packages` e **não** as registram no caminho de busca. O código do
VisoMaster não chama `os.add_dll_directory()` em lugar nenhum — no caminho Conda
isso não aparece porque o Conda já coloca as DLLs no `PATH` do ambiente.

Resultado, de novo, é fallback silencioso para CPU.

**Correção:** acrescentar estas três pastas ao `PATH` antes de iniciar:

```
.venv\Lib\site-packages\nvidia\cu13\bin\x86_64
.venv\Lib\site-packages\nvidia\cudnn\bin
.venv\Lib\site-packages\tensorrt_libs
```

---

## Como confirmar que está mesmo na GPU

Listar providers **não** é teste. O único teste válido é executar e conferir qual
provider a sessão realmente usou:

```python
import numpy as np, onnxruntime as ort

sess = ort.InferenceSession("modelo.onnx", providers=["CUDAExecutionProvider"])
assert sess.get_providers()[0] == "CUDAExecutionProvider", "caiu para CPU"
```

Se `get_providers()[0]` voltar `CPUExecutionProvider`, houve fallback — mesmo que
`get_available_providers()` liste CUDA.

---

## Nota

Circula uma recomendação de instalar o wheel `Natfii/onnxruntime-gpu-blackwell`
para "resolver" isso. Não é necessário: o `onnxruntime-gpu` oficial já traz kernels
Blackwell (`120-real`) há tempos, e aquele wheel **rebaixa** a versão, quebrando os
pins deste `requirements_cu13.txt`.
