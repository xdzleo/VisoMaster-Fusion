# Changelog do fork (xdzleo)

Linha de versão própria, separada do upstream, no formato `<versão-upstream>+xdz.<n>`.
O `+xdz.N` sobe **a cada mudança nossa**; a parte da esquerda só muda quando
sincronizamos com o upstream.

Assim dá para saber, olhando o título do app, exatamente qual build está rodando —
o app já mostra `VisoMaster Fusion - 3.9.3+xdz.1 (<hash>)`.

---

## 3.9.3+xdz.11 — 11/ago/2026

### Integração — Master 4K (FaceFusion) dentro do VisoMaster

Menu **Ver → Master 4K (FaceFusion)…** abre uma janela Qt com a interface do
FaceFusion embutida (`QWebEngineView`), para o caminho **offline** de qualidade
máxima. O servidor sobe sob demanda e é encerrado ao fechar a janela — não faz
sentido manter um segundo processo pesado vivo durante uma live.

Sejamos precisos sobre o que isto é: **não é a GUI do FaceFusion reescrita em
Qt**. Os dois usam frameworks incompatíveis (Qt nativo vs Gradio/web); reescrever
seriam 22 mil linhas. O que existe é o servidor dele embutido numa janela nossa,
de modo que tudo fica num app só.

Por que os dois coexistem, e não é preferência: o VisoMaster normaliza todo swap
para o template canônico de **512**, o que é certo para tempo real mas é um teto;
o FaceFusion warpa o crop do enhancer a partir do frame em **resolução cheia** e,
sendo offline, aceita `pixel_boost 1024` e `gpen_bfr_2048`, que não cabem em
33,3 ms. Cada um ganha exatamente onde o outro não pode.

Dois bugs corrigidos no caminho, ambos meus:

- **`--open-browser false`** — o argumento é `action='store_true'`, ou seja
  **flag sem valor**. Passar `false` fazia o argparse abortar com
  `unrecognized arguments: false`, e o servidor morria antes de subir.
- **Porta fantasma** — `ui.launch()` do FaceFusion não recebe `server_port` nem
  expõe flag de porta na CLI. A porta agora é fixada por `GRADIO_SERVER_PORT`
  no ambiente, em vez de torcer para cair na 7860.

E uma lição de método: eu havia posto `stdout=DEVNULL, stderr=DEVNULL` no
subprocesso, então quando o servidor morria **o motivo ia para o lixo** e a
janela só conseguia dizer "encerrou sozinho". A saída agora vai para arquivo e a
janela **mostra as últimas linhas do log** quando o servidor cai.

### Usabilidade — o terceiro diálogo modal bloqueante

- **`AutoLoadWorkspaceToggle` default `True`.** Assim que existe um
  `last_workspace.json`, o app abria um modal *"carregar o último workspace?"* e
  travava em `load_dialog.exec_()` — **antes** de qualquer inicialização
  automática, então `auto_start` e o item de menu do Master 4K nunca rodavam.

  Sutileza que quase passou: o toggle é lido **de dentro do JSON do workspace
  salvo**, não dos defaults do código. Mudar o default sozinho não conserta um
  arquivo já existente; é preciso corrigir os dois lados.

Este é o **terceiro** diálogo modal que travou a inicialização (provider,
workspace, e o `QFileDialog` dentro de `select_input_face_images`). O padrão se
repete: bloqueiam antes de qualquer automação e não dão nenhum sinal de que estão
ali.

### Higiene

- `.gitignore` para estado local: `last_workspace.json`, `provider_escolhido.txt`,
  `crash_logs/`, `tensorrt-engines/`, `model_assets/`.

---

## 3.9.3+xdz.10 — 11/ago/2026

### Latência — lote bit-idêntico de ~8,5 ms/frame

Seis mudanças que **eliminam trabalho redundante sem alterar um pixel**. Todas
medidas na RTX 5090 real (não estimadas) e verificadas com `np.array_equal` /
`torch.equal`.

| onde | de → para | ganho | prova |
|---|---|---|---|
| `frame_worker.py:606` cauda do frame | 5,902 → 0,238 ms | **5,50 ms** | `np.array_equal` |
| `frame_worker.py:575` HWC→CHW | 1,009 → 0,170 ms | 0,84 ms | `torch.equal` |
| `frame_worker_pipeline.py:3024` paste-back | 1,375 → 0,735 ms | 0,64 ms | `torch.equal` (3ch + máscara) |
| `video_processor.py:1126` BGR→RGB | 2,565 → 0,321 ms | 2,24 ms* | `np.array_equal` |

\* thread **feeder**: melhora latência vidro-a-OBS, não FPS.

**A cauda do frame era pior do que aparentava.** `permute(1,2,0).cpu()` *preserva*
os strides permutados (medido: `(1280, 1, 921600)`, `C_CONTIGUOUS=False`), e o
`.astype` com `order='K'` preserva a não-contiguidade — então o `if` da linha
seguinte disparava **sempre**, e o `[..., ::-1]` devolvia stride negativo que a
linha 406 materializava numa **quarta** cópia. Fazendo tudo na GPU, desce um
buffer já contíguo e a 406 vira no-op de verdade.

**O paste-back tem a causa mais interessante:** cada `kornia.warp_affine` chama
`torch.linalg.inv` **duas vezes**, e uma inversão 3×3 na CUDA custa **0,217 ms** —
precisa ler o `info` do cuSOLVER, o que força sincronização de dispositivo. Duas
chamadas = quatro inversões por frame. Concatenar em 4 canais paga isso uma vez.

### Correção latente

- **`faceutil.py:566`** — gêmeo não corrigido do bug do template arcface128
  (`src[:, 0]` → `src[..., 0]`). Mesma causa do que foi corrigido em `+xdz.2`:
  `arcface_src` é `(1,5,2)`, então `[:, 0]` indexa o keypoint 0 inteiro.

### Resultado medido — e como interpretá-lo

| | mediana | fps |
|---|---|---|
| antes deste lote | 34–36 ms | 28–29 |
| depois | 31,5–33,5 ms | **30–32** |

A mediana caiu ~3 ms, não 8,5 — **e isso é o esperado**. Com o app terminando em
~26 ms e a câmera entregando a cada 33,3 ms (30 fps), **o gargalo passou a ser a
câmera**. A economia é real, só não tem onde aparecer. Para convertê-la em ganho,
subir *Webcam FPS* de 30 para 60 na interface.

---

## 3.9.3+xdz.9 — 11/ago/2026

### Thread de GUI — correções sem ganho mensurável (registrado como tal)

Duas mudanças na thread que agora entrega o frame. Ambas são corretas, **nenhuma
rendeu diferença mensurável**, e isso está registrado em vez de inflado.

- **`get_gpu_memory` usa `torch.cuda.mem_get_info` em vez de `nvidia-smi`.**
  O método é chamado por QTimer de 5 s na thread de GUI, e `sp.check_output`
  cria um PROCESSO (100–400 ms no Windows) bloqueando-a. `mem_get_info` é
  chamada de driver. *Por que não apareceu na medição:* roda a cada 5 s, então
  afetaria o pior caso, não a mediana — e amostras de ~145 frames cobrem ~5 s.
- **`QImage.Format_BGR888` em vez de `Format_RGB888` + `.rgbSwapped()`.**
  Eliminava uma cópia de frame inteiro por frame na thread de GUI. Em 1280×720
  isso é ~1–2 ms: real, mas abaixo do ruído da medição.

### Qualidade — color transfer mascarado

- **`Reinhard Transfer` → `Reinhard Transfer (Masked)`.** A variante sem máscara
  usa "todo pixel com soma > 0,01" do crop 512 **inteiro** — o **fundo entra na
  estatística que casa o tom de pele**. A máscara correta (núcleo XSeg) já está
  construída logo acima no pipeline e as duas variantes custam a mesma indexação
  booleana. Provável responsável pelo ~1 ms a mais na mediana; é troca de
  qualidade, não regressão.

### Estado da medição

| | mediana | p95 |
|---|---|---|
| baseline (metrônomo) | 66,2 ms | 100,1 ms |
| + entrega na chegada | 32,4–34,5 ms | 45–60 ms |
| + estas mudanças | 34,1–36,0 ms | 49–58 ms |

Orçamento restante: cadeia de GPU custa **14,0 ms** de uma mediana de ~35 ms.
Sobram **~21 ms fora da GPU** — é aí que está o próximo ganho, e ele está nas
threads worker/feeder, não na de GUI.

---

## 3.9.3+xdz.8 — 11/ago/2026

### Latência — **FPS DOBRADO** (15 → 30)

O maior ganho de todo o trabalho, e não veio da GPU.

`display_next_frame` só entregava o frame no tique do metrônomo. Se o frame não
estivesse pronto naquele instante exato, fazia `return` e esperava um **período
inteiro**. Com tick de 33,3 ms (30 fps), um pipeline de 35 ms não perdia 1,7 ms —
perdia 33,3, e a taxa colapsava para exatamente metade.

**A assinatura do bug estava nos números**, antes de qualquer leitura de código:

| | medido | é |
|---|---|---|
| mediana | 66,2 ms | **2 × 33,3** |
| p95 | 100,1 ms | **3 × 33,3** |

Múltiplos exatos do período do tick. Isso é quantização, não carga — carga real
produz distribuição contínua.

**Correção:** entregar em `store_webcam_frame_to_display`, na *chegada* do frame,
e não no tique. A UI (QPixmap) continua no metrônomo, que é onde ela deve ficar:
a tela não precisa de mais que a taxa de refresh, mas o OBS precisa do frame
assim que ele existir.

Seguro por construção: o slot já roda na thread de GUI (conectado por sinal a
partir do worker), o mesmo contexto de onde `display_next_frame` chamava — nenhuma
concorrência nova no driver da câmera virtual.

**Medido, 5 amostras consecutivas de ~150 frames cada:**

| | antes | depois |
|---|---|---|
| taxa | 15,1 fps | **29,0 – 30,9 fps** |
| mediana | 66,2 ms | **32,4 – 34,5 ms** |
| p95 | 100,1 ms | **45,1 – 59,6 ms** |

Vale registrar o contexto: a cadeia de GPU custa 14,01 ms dos 33,3 ms disponíveis.
O gargalo nunca foi a placa — era espera. A RTX 5090 fazia sua parte em 14 ms e
ficava parada esperando o relógio.

---

## 3.9.3+xdz.7 — 11/ago/2026

### Instrumentação — contador de FPS

O app não tinha **nenhum** indicador de FPS ou de tempo de frame. Sem medir não
há como otimizar: qualquer ajuste vira fé.

`video_processor._contar_fps_saida()` mede no envio para a câmera virtual — o
último passo do pipeline, então o número engloba captura, detecção, swap,
restorer, máscaras, blend e paste-back. Loga a cada 5 s:

```
[fps]  28.4 fps  |  frame: mediana  35.2 ms  p95  41.0 ms  pior  58.3 ms  (142 frames)
```

Reporta **mediana e p95**, não média, porque média esconde engasgo: um pipeline
com mediana 16 ms e p95 90 ms parece "60 fps" na média e trava visivelmente na
prática. Avisa explicitamente quando p95 > 2× mediana.

### Medição de referência (RTX 5090, com o swap rodando)

| | |
|---|---|
| utilização GPU | ~78% (70–87%) |
| clock SM | 2955–2970 MHz (boost máximo) |
| consumo | 480–514 W (de ~575 W) |
| VRAM | 6,75 GB |
| temperatura | 72–76 °C |

Registrado porque desfaz uma suposição comum: **a VRAM baixa não indica placa
ociosa.** 500 W em boost máximo é a placa trabalhando de verdade. Os modelos de
rosto são 256 px e por natureza pequenos; alocar mais VRAM não compraria
desempenho nenhum. A folga real é os ~22% de utilização, e gasta-se ela em
qualidade (modelo/resolução maior), não em memória.

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
