# Changelog do fork (xdzleo)

Linha de versão própria, separada do upstream, no formato `<versão-upstream>+xdz.<n>`.
O `+xdz.N` sobe **a cada mudança nossa**; a parte da esquerda só muda quando
sincronizamos com o upstream.

Assim dá para saber, olhando o título do app, exatamente qual build está rodando —
o app já mostra `VisoMaster Fusion - 3.9.3+xdz.1 (<hash>)`.

---

## 3.9.3+xdz.6 — 11/ago/2026

### Usabilidade — o fluxo de webcam agora funciona sozinho

Testando de ponta a ponta pela primeira vez, o pipeline **não funcionava** com os
padrões do upstream — e por dois motivos que a interface não revela.

- **`targetVideosFilterWebcamsCheckBox` marcado por padrão**
  (`app/ui/core/main_window.py`). Desmarcado, a webcam simplesmente **não aparece**
  na lista de alvos, e nada indica que há um filtro escondendo ela. Para um app
  cujo caso de uso é avatar ao vivo, esconder a webcam por padrão é o contrário
  do esperado.

- **`AutoSwapToggle` e `KeepInputToggle` ligados por padrão**
  (`settings_layout_data.py`). Desligados, vincular a foto de origem ao rosto
  detectado é **manual**: clicar no rosto, depois no card. Esse passo não está
  documentado em lugar nenhum da interface e é exatamente onde se trava — tudo
  parece configurado e nada acontece.

  A lógica já existia em `card_actions.py:295-321`, só vinha desativada:

  ```python
  if control.get("KeepInputToggle", False) or control.get("AutoSwapToggle", False):
      # atribui as input faces marcadas ao rosto recém-detectado
  ```

  No fluxo de webcam isso é mais que conveniência: os rostos são re-detectados
  continuamente, então sem auto-atribuição o vínculo se perderia a cada detecção.

---

## 3.9.3+xdz.5 — 11/ago/2026

### Qualidade — modelo de swap (faltava, era o mais importante)

Os commits anteriores ajustaram máscaras, restorer e color transfer mas
deixaram passar o principal: o **modelo de swap** continuava no padrão do
upstream.

- **`SwapModelSelection`: `Inswapper128` → `InStyleSwapper256 Version C`.**
  O Inswapper128 resolve internamente em 128 px: para chegar a 1024 ele precisa
  de **64 forward-passes**, contra **16** de qualquer modelo 256-native — mais
  caro *e* com teto de identidade pior. A Version C é o nível de realismo da
  família (A = rápido, B = equilibrado).
- **`InStyleResCEnableToggle`: `False` → `True`.** É o par do modelo padrão; sem
  ele o swap sai em 256 e fica visivelmente mole contra o vídeo em volta.

Medido (TensorRT, RTX 5090): a cadeia completa fecha em **14,01 ms**, com folga
em 30 fps e em 60 fps.

---

## 3.9.3+xdz.4 — 11/ago/2026

### Qualidade — restorer

- **Restorer ligado** (`FaceRestorerEnableToggle` → `True`). O swapper é
  256-native, então a saída dele sai mole comparada ao vídeo em volta; o restorer
  é o que devolve nitidez. Vinha desligado.
- **`GFPGAN-1024`** em vez de `GFPGAN-v1.4` — resolve em 1024 em vez de 512.
- **Blend `100` → `65`.** *Este* é o ajuste que causa a cara de plástico: em 100 a
  saída idealizada do restorer substitui a pele inteira, apagando poro e
  microtextura, e todo rosto sai com a mesma "cara de restorer". Em 65 sobra ~35%
  da textura real do swap por baixo.

### Orçamento por frame — medido nesta placa (RTX 5090, TensorRT)

| etapa | ms |
|---|---|
| swapper InStyleSwapper256-C | 5,62 |
| restorer GFPGAN-1024 | 5,85 |
| máscara XSeg | 1,90 |
| máscara Occluder | 0,64 |
| **cadeia completa** | **14,01** |

Cabe no orçamento de **30 fps** (33,3 ms) **e de 60 fps** (16,7 ms).
`RestoreFormer++` foi medido e descartado: 14,62 ms sozinho leva a cadeia a
22,78 ms — ok em 30 fps, estoura em 60.

> **Armadilha de medição, registrada porque custou uma conclusão errada:** no
> provider **CUDA** a mesma cadeia dá **32,72 ms** (XSeg sozinho custa 9,94 ms), e
> parecia que as duas máscaras tinham estourado o orçamento de 30 fps. O
> **TensorRT é 2,8× mais rápido** na cadeia inteira e **5,2× no XSeg** — é isso que
> torna os defaults de qualidade viáveis. Quem medir este pipeline no CUDA EP
> chega à conclusão errada.

---

## 3.9.3+xdz.3 — 11/ago/2026

### Qualidade — defaults

Três defaults do upstream deixavam qualidade óbvia na mesa. Este fork mira
qualidade máxima num 5090, então agora o default é o caminho bom.

- **Máscaras ligadas** (`OccluderEnableToggle`, `DFLXSegEnableToggle` → `True`).
  Com os defaults originais, a **única** coisa recortando o composto era o
  retângulo de borda de 128px — o próprio comentário do slider admite que ele
  existe "to prevent black square around the swap when no occlusion is selected".
  Máscara seguindo mandíbula e linha do cabelo é o maior ganho visual isolado
  disponível. Os dois modelos já vêm baixados (XSeg 67 MB, occluder 55 MB).
- **Color transfer ligado** (`EndingColorTransferEnableToggle` → `True`), tipo
  trocado de `CDF Histogram` para **`Reinhard Transfer`**. Sem isso **não existe
  nenhum** casamento de tom de pele na cadeia. Reinhard casa média e desvio em
  LAB (suave, robusto a mudança de fundo); CDF força o histograma inteiro, que
  em vídeo ao vivo oscila frame a frame conforme o fundo muda.

### Latência — webcam

- **`WEBCAM_MAX_IN_FLIGHT = 2`** + drenagem de tasks velhas antes de enfileirar
  (`video_processor.py`). O gate usava `max_display_buffer_size`
  (preroll + num_threads×2 = 28). Como a fila de display se auto-limita em 1,
  isso autorizava **~27 capturas envelhecendo**. A GPU é o gargalo de qualquer
  forma, então esses frames não compravam throughput nenhum — só somavam ~27
  tempos-de-frame entre o rosto e o OBS.

  A drenagem também fecha uma janela de reordenação: todas as tasks de webcam
  carregam `frame_number=0` e o display é "última **chegada** vence", então um
  worker lento podia sobrescrever um frame novo com um velho.

  O feeder de **arquivo** ficou intocado de propósito — lá throughput importa e
  latência não.

> Custo das máscaras/cor e ganho de latência precisam de câmera ao vivo para
> quantificar. Referência já medida nesta placa: swapper InStyleSwapper256-C a
> **9,33 ms (107/s)**, logo há folga de orçamento por frame.

---

## 3.9.3+xdz.2 — 11/ago/2026

### Correção de bug — alinhamento (afeta qualidade de TODO swap)

- **`get_arcface_template` deslocava um keypoint em vez da coluna x**
  (`faceutil.py:508`). `arcface_src` é `(1,5,2)` por causa do `expand_dims` da
  linha 117, então `template[:, 0]` indexa o **keypoint 0** e devolve o par
  `[x, y]` dele — o offset de centragem caía num único ponto, **nos dois eixos**,
  e os outros quatro nunca se moviam. O certo é `template[..., 0]`.

  Medido em 512:

  | | valor |
  |---|---|
  | diferença p/ o correto | `[[0,+32], [-32,0], [-32,0], [-32,0], [-32,0]]` |
  | distância interpupilar do template | **113,77 px** (correto: 140,95) → **19,3% pequeno demais** |
  | olho esquerdo | deslocado 32 px em y, inclinando a linha dos olhos |

  Duas confirmações independentes de que a forma corrigida é a pretendida:
  1. `face_restorers.py:118-119` monta o mesmo template com `dst[:, 0] += 32.0`
     num array `(5,2)`, onde `[:, 0]` **é** a coluna x. As duas construções
     discordavam; agora batem — o que conserta de graça o modo "Blend" do restorer.
  2. Os modelos de swap são de terceiros e treinados no template arcface canônico.
     Um crop 19% menor com um keypoint deslocado os alimentava **fora da
     distribuição de treino**. O embedding da FONTE nunca foi afetado
     (`recognize()` usa arcface112/arcfacemap, que não passam por esse ramo), então
     uma identidade-fonte bem alinhada estava sendo pareada com um crop-alvo
     desalinhado. Essa assimetria era o dano.

  Trava de regressão em `tests/test_arcface_template.py` (3 testes). Verificado
  que falham no código com bug e passam depois; o resto da suíte fica igual
  (as falhas de UI pré-existentes são idênticas antes e depois).

  ⚠️ Muda a distribuição de alinhamento: `tform.scale` sobe ~12,7% e alguns rostos
  cruzam as faixas de `dim` do polyphase em `frame_worker_pipeline.py:296-307`.
  Vale um A/B em material real.

### Correção de bug — diagnóstico

- **Falha alta quando a sessão cai para CPU em silêncio** (`models_processor.py`).
  O log dizia `with provider: {self.provider_name}`, mas isso é o **rótulo do
  dropdown da UI** (`:166`, `:1228`), nunca derivado da sessão. Com as DLLs do
  CUDA falhando, o onnxruntime devolve sessão só-CPU sem erro e o app seguia
  reportando "TensorRT" rodando 50–100× mais devagar. `get_providers()` aparecia
  **zero** vezes no projeto inteiro.

  Agora pergunta à sessão o que ela realmente obteve e levanta erro quando a
  lista volta começando em CPU com GPU pedida.

  Não exigimos `TensorrtExecutionProvider`: `get_providers()` diz quais EPs
  **registraram**, não qual ficou com os nós — TensorRT registrar sem receber nó
  é legítimo aqui (build preguiçoso). Só uma lista começando em CPU prova que os
  EPs de GPU não carregaram.

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
