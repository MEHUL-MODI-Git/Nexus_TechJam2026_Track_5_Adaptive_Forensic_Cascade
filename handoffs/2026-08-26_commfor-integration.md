# Community Forensics AI-Image Detector — Integration Research

- **Model card:** https://huggingface.co/OwensLab/commfor-model-384 (also `OwensLab/commfor-model-224`)
- **Paper:** [Community Forensics: Using Thousands of Generators to Train Fake Image Detectors](https://arxiv.org/abs/2411.04125) (arXiv:2411.04125), CVPR 2025, Park & Owens
- **Official GitHub repo:** https://github.com/JeongsooP/Community-Forensics (author: Jeongsoo Park / JeongsooP)
- **Image-processor companion repo:** https://huggingface.co/OwensLab/commfor-data-preprocessor
- Research date: 2026-08-26. All code below is quoted verbatim from the `main` branch of the GitHub repo (fetched via `raw.githubusercontent.com` and the GitHub REST API) unless marked UNVERIFIED.

---

## 1. Loading the checkpoint

The model class is `ViTClassifier` in [`models.py`](https://github.com/JeongsooP/Community-Forensics/blob/main/models.py), which subclasses `nn.Module` and `huggingface_hub.PyTorchModelHubMixin`. Verbatim:

```python
import torch
import torch.nn as nn
import timm
from huggingface_hub import PyTorchModelHubMixin

class ViTClassifier(nn.Module, PyTorchModelHubMixin):
    def __init__(self,
                 model_size="small",
                 input_size=384,
                 patch_size=16,
                 freeze_backbone=False,
                 device='cuda', dtype=torch.float32):
        """
        ViT Classifier based on huggingface timm module
        """
        super(ViTClassifier, self).__init__()
        self.device=device
        self.dtype=dtype
        if model_size=="small":
            if input_size==224:
                if patch_size==32:
                    self.vit = timm.create_model('vit_small_patch32_224.augreg_in21k_ft_in1k', pretrained=True).to(device)
                elif patch_size==16:
                    self.vit = timm.create_model('vit_small_patch16_224.augreg_in21k_ft_in1k', pretrained=True).to(device)
            elif input_size==384:
                if patch_size==32:
                    self.vit = timm.create_model('vit_small_patch32_384.augreg_in21k_ft_in1k', pretrained=True).to(device)
                elif patch_size==16:
                    self.vit = timm.create_model('vit_small_patch16_384.augreg_in21k_ft_in1k', pretrained=True).to(device)
            if freeze_backbone:
                for param in self.vit.parameters():
                    param.requires_grad = False
            self.vit.head = nn.Linear(in_features=384, out_features=1, bias=True, device=device, dtype=dtype)
        elif model_size=="tiny":
            assert patch_size==16, "Only patch size 16 is available for ViT-Ti"
            if input_size==224:
                self.vit = timm.create_model('vit_tiny_patch16_224.augreg_in21k_ft_in1k', pretrained=True).to(device)
            elif input_size==384:
                self.vit = timm.create_model('vit_tiny_patch16_384.augreg_in21k_ft_in1k', pretrained=True).to(device)
            if freeze_backbone:
                for param in self.vit.parameters():
                    param.requires_grad = False
            self.vit.head = nn.Linear(in_features=192, out_features=1, bias=True, device=device, dtype=dtype)
        for param in self.vit.head.parameters():
            assert param.requires_grad==True, "Model head should be trainable."

    def forward(self, x):
        return self.vit(x)
```

The `config.json` pushed alongside `OwensLab/commfor-model-384` (fetched from `https://huggingface.co/OwensLab/commfor-model-384/raw/main/config.json`) is:

```json
{
  "device": "cuda",
  "freeze_backbone": false,
  "input_size": 384,
  "model_size": "small",
  "patch_size": 16
}
```

i.e. this checkpoint is **ViT-Small, patch 16, input 384** (matches the "21.8M parameters" listed on the HF model card). Because `PyTorchModelHubMixin.from_pretrained()` re-instantiates the class using these saved `__init__` kwargs, calling `.from_pretrained()` on a non-CUDA machine will try to build the backbone with `device="cuda"` first — see the MPS caveat in §4.

**Official minimal load + inference example**, quoted verbatim from [`eval_using_huggingface.ipynb`](https://github.com/JeongsooP/Community-Forensics/blob/main/eval_using_huggingface.ipynb) (cell `09824392` / `90faadd7`):

```python
import models
import torch
import PIL.Image as Image
import dataprocessor_hf as dphf

data_processor = dphf.CommForImageProcessor.from_pretrained('OwensLab/commfor-data-preprocessor', size=384)
model_384 = models.ViTClassifier.from_pretrained('OwensLab/commfor-model-384').to('cuda')
```

```python
# These are test images from Dalle 2
test_img = Image.open("test_images/00000274.png")
...
test_imgs = [test_img, test_img2, test_img3, test_img4, test_img5]
input = data_processor(test_imgs, mode='test')
out = model_384(input['pixel_values'].to('cuda'))
results = torch.sigmoid(out)

print("Results for 384-input size model:")
print(results)
```
Observed notebook output: `tensor([[0.9988],[0.9878],[0.9569],[0.9516],[0.7860]], ...)` for 5 known-fake (Dalle 2) test images — confirms high sigmoid = fake (see §3).

`dataprocessor_hf.py` requires `models.py`, `dataloader.py`, `custom_transforms.py`, `utils.py` to be present locally (it imports `dataloader as dl`), so you cannot use the HF `AutoImageProcessor.from_pretrained` shortcut without cloning the repo — its `auto_map` (`https://huggingface.co/OwensLab/commfor-data-preprocessor/raw/main/preprocessor_config.json`) points at `dataprocessor_hf.CommForImageProcessor`, which is not a self-contained transformers module.

---

## 2. Input preprocessing (EXACT)

Source: [`dataloader.py`](https://github.com/JeongsooP/Community-Forensics/blob/main/dataloader.py) function `get_transform()` (called for `mode="test"` by `CommForImageProcessor.preprocess()` in [`dataprocessor_hf.py`](https://github.com/JeongsooP/Community-Forensics/blob/main/dataprocessor_hf.py)):

```python
def determine_resize_crop_sizes(args):
    if args.input_size==224:
        resize_size=256
        crop_size=224
    elif args.input_size==384:
        resize_size=440
        crop_size=384
    return resize_size, crop_size

def get_transform(args, mode="train", dtype=torch.float32):
    norm_mean = [0.485, 0.456, 0.406] #imagenet norm
    norm_std = [0.229, 0.224, 0.225]
    resize_size, crop_size = determine_resize_crop_sizes(args)
    augment_list = []
    ...
    elif mode=="val" or mode=="test":
        augment_list.append(transforms.Resize(resize_size))
        augment_list.extend([
            transforms.CenterCrop(crop_size),
            ctrans.ToTensor_range(val_min=0, val_max=1),
            transforms.Normalize(mean=norm_mean, std=norm_std),
            transforms.ConvertImageDtype(dtype),
        ])
    transform = transforms.Compose(augment_list)
    return transform
```

Concrete pipeline for the 384-input checkpoint at inference (`mode="test"`):

| Step | Value |
|---|---|
| Resolution | 384×384 final tensor |
| Resize | `torchvision.transforms.Resize(440)` — resizes the **shorter edge to 440 px**, preserving aspect ratio (torchvision default interpolation = bilinear, applied on the PIL image before tensor conversion) |
| Crop | `transforms.CenterCrop(384)` — deterministic **center crop** (no random crop at test time) |
| Tensor conversion | `ctrans.ToTensor_range(val_min=0, val_max=1)` = standard `to_tensor()` (uint8 0–255 → float 0–1), i.e. equivalent to `torchvision.transforms.ToTensor()` |
| Normalization | `transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])` — **standard ImageNet mean/std** |
| Dtype | `transforms.ConvertImageDtype(torch.float32)` |
| Color order | RGB (repo's JPEG helper explicitly does `img = PIL.Image.open(buffer).convert("RGB")`; no BGR handling anywhere) |
| Value range fed to model | Normalized (NOT 0–1, NOT 0–255) — the `ToTensor_range(0,1)` step is followed immediately by ImageNet normalization |

For the 224-input variant: `Resize(256)` → `CenterCrop(224)`, same normalization.

**IMPORTANT confirmed correction (GitHub Issue #5, "which norm_std and norm_mean?")**: there are **two different norm settings across branches** — the `main` branch uses ImageNet norm (above), while the `eval_single` branch uses a different ("huggingface vit setting") norm. Repo author JeongsooP's own comment:

> "Ah good catch! I used the imagenet `norm_std` and `norm_mean` (i.e., norm_mean = [0.485, 0.456, 0.406], norm_std = [0.229, 0.224, 0.225]) for both training and evaluation. It seems I made a mistake using a different norm in the `eval_single` branch... I suggest using the `main` branch as it should be more polished/up-to-date."
> — https://github.com/JeongsooP/Community-Forensics/issues/5

**Use the `main` branch's `dataloader.py`/`dataprocessor_hf.py` transform, not the `eval_single` branch.**

---

## 3. Output semantics

- `ViTClassifier.forward()` returns `self.vit(x)` directly — **the linear head has 1 output feature and no activation is applied in the model itself.** The model returns a raw **logit**, not a probability.
- Confirmed explicitly by the author in [GitHub Issue #4 ("Predicted Probabilities are in negative real numbers range")](https://github.com/JeongsooP/Community-Forensics/issues/4):
  > "Yes, the model outputs logits. If you made any changes to the code, you would have to manually add sigmoid to the output of the model to get the probabilities." — JeongsooP
- `eval.py` uses `criterion = nn.BCEWithLogitsLoss()` (confirms logit output) and evaluation applies sigmoid conditionally: `add_sigmoid=(not args.dont_add_sigmoid)` (sigmoid is added **by default**; pass `--dont_add_sigmoid` to skip it).
- **You must call `torch.sigmoid(model(x))` yourself** to get a probability, exactly as shown in the notebook: `results = torch.sigmoid(out)`.
- **Class convention:** label format default is `--additional_data_label_format "real:0,fake:1"` (see `parse_args()` in `utils.py` and README). So **class 1 / high sigmoid output = AI-generated ("fake")**, class 0 / low sigmoid = real. This matches the notebook example, where 5 known-DALL·E-2 (fake) test images all produced high sigmoid outputs (0.7860–0.9988).

**UNVERIFIED / third-party caution on thresholding:** A non-author commenter ("agentatwork", self-disclosed as an autonomous AI agent, not affiliated with the repo) posted in [Issue #7 ("Results not reproducing")](https://github.com/JeongsooP/Community-Forensics/issues/7) an independent benchmark claiming the raw sigmoid output is heavily skewed (near-0 for real images, only moderately high for fake), and that using the naive 0.5 threshold produces much worse balanced accuracy (~68.6%) than an empirically tuned threshold (~86.2%, they claim the best threshold is near **0.016**, not 0.5). This claim is **not confirmed by the repo author** and comes from an unofficial third-party evaluation (linked to `github.com/agentatwork/local-ai-image-detector`) — treat as an unverified data point, not a documented spec. If building a demo, plan to calibrate/tune the decision threshold on your own validation images rather than assuming 0.5.

---

## 4. Dependencies + Apple Silicon / MPS considerations

`requirements.txt` (verbatim, from `main` branch):

```
torch==2.7.1
torchaudio==2.7.1
torchmetrics==1.7.2
torchvision==0.22.1
datasets==3.6.0
timm==1.0.15
wandb==0.20.1
opencv-python==4.11.0.86
numpy
pandas
huggingface-hub
transformers
```
(README also states: "Two additional libraries required: `huggingface-hub`, `transformers` (included in requirements.txt)".)

**Apple Silicon / MPS risks (mostly UNVERIFIED — not tested by the repo author, no MPS mentions found in README/issues):**

1. **`config.json` hardcodes `"device": "cuda"`.** Because `PyTorchModelHubMixin.from_pretrained()` reconstructs `ViTClassifier(**config)`, the constructor will try `.to('cuda')` internally for the timm backbone (`self.vit = timm.create_model(...).to(device)`) before you get a chance to `.to('mps')` the whole module. On a Mac with no CUDA this call as written **will raise `AssertionError: Torch not compiled with CUDA enabled`** unless you override the device kwarg. Practical fix: call `models.ViTClassifier.from_pretrained('OwensLab/commfor-model-384', device='mps')` (or `'cpu'`) — `from_pretrained` in `huggingface_hub`'s `PyTorchModelHubMixin` allows overriding init kwargs; if that path errors, load `config.json` yourself, instantiate `ViTClassifier(device='mps', ...)`, then load only the `state_dict` from the safetensors file. UNVERIFIED whether `from_pretrained(..., device='mps')` cleanly overrides — worth testing early.
2. `eval.py`'s own pipeline (`ut.dist_setup()`, `dist.barrier()`, `torchrun`, DDP) is built for multi-GPU CUDA training/eval and is **not needed** for single-image inference — use the notebook-style direct `ViTClassifier.from_pretrained(...)` + manual transform path instead, which has no CUDA-specific control flow beyond the device string.
3. `timm==1.0.15` ViT (`vit_small_patch16_384.augreg_in21k_ft_in1k`) is a standard architecture (attention, layernorm, GELU) — no custom CUDA kernels, so it should run under MPS or CPU without architectural blockers, but this is **UNVERIFIED** (no test performed in this research pass; not mentioned in repo).
4. `opencv-python==4.11.0.86` pin is only exercised by `custom_transforms.py`'s `apply_cv2JPEG` training augmentation path (`StochasticJPEG`), not by the test/val transform — for inference-only use you likely don't need functioning `cv2` JPEG codecs, but the import may still occur at module load. No known Apple Silicon build issue for this opencv-python version (standard PyPI wheel exists for macOS arm64).
5. `torch==2.7.1` supports the MPS backend generally; no repo-specific MPS incompatibility was found in issues (issues #1, #3, #4, #5, #6, #7 — none mention Mac/MPS/Apple Silicon).

---

## 5. License

- **Code (GitHub repo):** MIT License. Verbatim from [`LICENSE`](https://github.com/JeongsooP/Community-Forensics/blob/main/LICENSE):
  ```
  MIT License

  Copyright (c) 2025 Jeongsoo Park
  ...
  ```
- **Checkpoint (`OwensLab/commfor-model-384` on Hugging Face):** model card YAML front-matter states `license: mit` (fetched from `https://huggingface.co/OwensLab/commfor-model-384/raw/main/README.md`).
- Datasets (`OwensLab/CommunityForensics`, `-Small`, `-Eval`) are separate HF dataset repos with their own licensing — **not checked in this pass; UNVERIFIED**, check dataset cards separately if you plan to use the training data itself (not just the checkpoint).

---

## 6. Official inference example script(s)

- **Primary single/handful-image example:** [`eval_using_huggingface.ipynb`](https://github.com/JeongsooP/Community-Forensics/blob/main/eval_using_huggingface.ipynb) — full content already quoted in §1. README explicitly recommends this notebook for evaluating "a handful of images": "To simply evaluate a handful of images, please check the `eval_using_huggingface.ipynb` notebook."
- **Batch/dataset evaluation script:** [`eval.py`](https://github.com/JeongsooP/Community-Forensics/blob/main/eval.py) (DDP/torchrun-based, loads model via `ut.load_ckpt_from_huggingface`):
  ```python
  def load_ckpt_from_huggingface(model, hf_repo_id, rank):
      dist.barrier()
      model=model.from_pretrained(hf_repo_id).to(rank)
      if rank==0:
          print(f"Model weights loaded from Hugging Face: {hf_repo_id}")
      return model
  ```
  and the sigmoid-application call site:
  ```python
  test_loss, test_acc, test_ap = ut.evaluate_one_epoch(
      args, epoch=0, model=model, dataloader=testLoader, criterion=criterion,
      rank=rank, evalName="test", separate_eval=True,
      add_sigmoid=(not args.dont_add_sigmoid),
  )
  ```
- **Shell wrapper:** [`example_eval.sh`](https://github.com/JeongsooP/Community-Forensics/blob/main/example_eval.sh):
  ```sh
  HF_MODEL_REPO="OwensLab/commfor-model-384"
  torchrun --nproc_per_node=$NUM_GPUS --nnodes=1 --rdzv_id=123 --rdzv_backend=c10d eval.py \
      --gpus $NUM_GPUS \
      --cpus-per-gpu $NUM_CPUS_PER_GPU \
      --batch_size $BATCH_SIZE_PER_GPU \
      --hf_model_repo $HF_MODEL_REPO
  ```
- There is also a legacy `eval_single` git branch mentioned in the README for "simple image evaluation," but per Issue #5 it contains an outdated/incorrect normalization and the author recommends `main` instead — **do not use `eval_single`.**

---

## 7. Gotchas (from README / issues)

1. **Wrong normalization on `eval_single` branch** (Issue #5) — use `main` branch's ImageNet norm (`mean=[0.485,0.456,0.406]`, `std=[0.229,0.224,0.225]`), confirmed by the author. This is the single most important gotcha for anyone copy-pasting from an older branch or a third-party mirror.
2. **Model returns raw logits, no sigmoid** (Issue #4) — must call `torch.sigmoid()` manually if not using `eval.py`'s `evaluate_one_epoch(..., add_sigmoid=True)`.
3. **`config.json` device defaults to `"cuda"`** — will need explicit override for CPU/MPS use (see §4).
4. **Input size is restricted to 224 or 384** — `CommForImageProcessor.__init__` asserts `self.size in [224, 384]`, so arbitrary custom resolutions are not supported through the official processor.
5. **Non-square image handling:** resize is by shorter edge (aspect-ratio preserving) then a deterministic center crop to a square (384×384 or 224×224) — content outside the center square of very non-square/panoramic images is discarded at test time; there is no letterboxing/padding option in the official `test`/`val` transform.
6. **JPEG:** the model is trained with random in-memory JPEG re-compression as an augmentation (`JPEGinMemory` in `custom_transforms.py`, part of `RandomStateAugmentation`, used only in the **train** transform), so it should have some inherent robustness to compression artifacts, but the official **test/val** transform itself performs no JPEG-specific preprocessing beyond loading the image as RGB — no documented guidance for extreme/heavy compression at inference.
7. **UNVERIFIED third-party note on decision threshold** (Issue #7, non-author comment): claims raw sigmoid outputs are skewed and 0.5 is a poor operating threshold (suggests ~0.016 as empirically better on their own eval set); also claims resize precision (matching official "shortest edge 440 → center-crop 384" vs. naive "resize directly to 384") measurably changes accuracy — reinforcing the importance of matching the exact `Resize(440)` → `CenterCrop(384)` pipeline in §2 rather than a plain `Resize((384,384))`. Not confirmed by the repo author; flagged as unverified.
8. Two open issues (#6, "Documentation Enhancement Suggestion", and #7, unresolved as of fetch time) — #6 is an automated bot-generated documentation suggestion (from a third-party tool called "Crovia"), not actionable repo content; #7 is the "results not reproducing" thread discussed above, open/unresolved by the author as of this research (2026-08-26).

---

## Sources
- https://huggingface.co/OwensLab/commfor-model-384
- https://huggingface.co/OwensLab/commfor-model-384/raw/main/config.json
- https://huggingface.co/OwensLab/commfor-data-preprocessor/raw/main/preprocessor_config.json
- https://arxiv.org/abs/2411.04125
- https://github.com/JeongsooP/Community-Forensics
- https://github.com/JeongsooP/Community-Forensics/blob/main/README.md
- https://github.com/JeongsooP/Community-Forensics/blob/main/models.py
- https://github.com/JeongsooP/Community-Forensics/blob/main/dataloader.py
- https://github.com/JeongsooP/Community-Forensics/blob/main/dataprocessor_hf.py
- https://github.com/JeongsooP/Community-Forensics/blob/main/custom_transforms.py
- https://github.com/JeongsooP/Community-Forensics/blob/main/utils.py
- https://github.com/JeongsooP/Community-Forensics/blob/main/eval.py
- https://github.com/JeongsooP/Community-Forensics/blob/main/eval_using_huggingface.ipynb
- https://github.com/JeongsooP/Community-Forensics/blob/main/example_eval.sh
- https://github.com/JeongsooP/Community-Forensics/blob/main/requirements.txt
- https://github.com/JeongsooP/Community-Forensics/blob/main/LICENSE
- https://github.com/JeongsooP/Community-Forensics/issues/1
- https://github.com/JeongsooP/Community-Forensics/issues/4
- https://github.com/JeongsooP/Community-Forensics/issues/5
- https://github.com/JeongsooP/Community-Forensics/issues/6
- https://github.com/JeongsooP/Community-Forensics/issues/7
