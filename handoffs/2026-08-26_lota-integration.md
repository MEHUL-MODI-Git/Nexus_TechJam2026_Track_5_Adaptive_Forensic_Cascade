# LOTA Integration Research

**Repo:** https://github.com/hongsong-wang/LOTA (commit tree read on `main` branch, 2026-08-26)
**Paper:** ICCV 2025, "LOTA: Bit-Planes Guided AI-Generated Image Detection", arXiv:2510.14230
- arXiv abstract: https://arxiv.org/abs/2510.14230
- Open-access PDF: https://openaccess.thecvf.com/content/ICCV2025/papers/Wang_LOTA_Bit-Planes_Guided_AI-Generated_Image_Detection_ICCV_2025_paper.pdf
- Authors: Hongsong Wang, Renxi Cheng, Yang Zhang, Chaolei Han, Jie Gui (Southeast University, Nanjing)

All findings below were read directly from raw file contents fetched from
`https://raw.githubusercontent.com/hongsong-wang/LOTA/main/<file>` and from
`https://api.github.com/repos/hongsong-wang/LOTA/git/trees/main?recursive=1` on 2026-08-26.
Anything not directly observed in these files is marked **UNVERIFIED**.

---

## 1. Repo structure

Full file tree (from GitHub API, sizes in bytes):

```
LICENSE                              1,069
README.md                            5,104
bit_patch.py                         2,063
config.py                            4,769
extract_noise_image.py               1,722
images/                              (figures only: intro_00.png, method_00.png, abc)
loader.py                            6,307
model.py                             6,461
requirements.txt                       134
results/results_scaling_patch32.txt  7,798,063
test.py                              4,821
train.py                             7,557
util.py                              1,105
```
Source: https://api.github.com/repos/hongsong-wang/LOTA/git/trees/main?recursive=1

Mapping of the three architectural modules described in the paper ("Bit-Planes Guided Noisy Image Generation", "Maximum Gradient Patch Selection", classification head) to files:

- **(a) Bit-plane noisy image generation** — `bit_patch.py`, function `bit_patch(img, img_height, bit_mode, patch_size, patch_mode)`. When `bit_mode == "scaling"` it takes the raw uint8 image array, masks each channel with `0x07` (lowest 3 bits), then rescales `0..7 -> 0..255` via `*(255//7)` and merges channels with `cv2.merge`. `bit_mode == "thresholding"` is a stub (`combined_image = img_np # To be modified`) — **not implemented**, only `"scaling"` works.
  There is also a separate, simpler standalone script `extract_noise_image.py` (`process_single_image`) that does a boolean "any of the lowest 3 bits set -> 0/255" mask per channel over a whole folder of images — this looks like a visualization/offline utility, not the one used in `loader.py`'s actual training/inference pipeline. Only `bit_patch.py`'s `bit_patch()` is wired into the classifier pipeline (confirmed by `loader.py`: `from bit_patch import bit_patch as bit_patch_process`).
- **(b) Maximum gradient patch selection** — also in `bit_patch.py`. Helper `compute(patch)` sums absolute horizontal + vertical + both diagonal pixel differences within a patch (a gradient/roughness score). `bit_patch()` then extracts `num_patch = (img_height // patch_size) ** 2` random 32×32 crops of the bit-plane noise image via `torchvision.transforms.RandomCrop`, scores each with `compute()`, and for `patch_mode == "max"` picks the highest-scoring patch (paper's "maximum gradient patch selection"); `"min"` picks the lowest; anything else picks a uniformly random patch. Training uses `patch_mode='random'`, evaluation uses `patch_mode='max'` (per README commands).
- **(c) Classifier** — `model.py`. Class `model(nn.Module)` wraps a from-scratch-reimplemented `resnet50` (defined in the same file, not `torchvision.models.resnet50`) with `pretrained=True` (loads **ImageNet** weights from `https://download.pytorch.org/models/resnet50-19c8e357.pth` via `torch.utils.model_zoo`), then replaces the final FC layer with `nn.Linear(2048, 1)` — i.e., single-logit binary classification head.
- **Entry points**: `train.py` (training loop) and `test.py` (evaluation loop) are the only executable scripts. **There is no single-image inference script/CLI in the repo** — both scripts assume the GenImage directory layout (`<image_root>/<subset_name>/{train,val}/{nature,ai}/*.png`) via `loader.py`'s `GenerativeImageTrainingSet` / `GenerativeImageValidationSet` classes.

Sources:
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/bit_patch.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/extract_noise_image.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/model.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/loader.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/test.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/train.py

---

## 2. Pretrained weights

From README.md (https://raw.githubusercontent.com/hongsong-wang/LOTA/main/README.md):

> "we provide the pretrained weights trained on [Stable_Diffusion_v1.4](https://pan.baidu.com/s/1H0IceEHzpB_ADh5J487bkA?pwd=imjw) (code: imjw) and [Stable_Diffusion_v1.5](https://pan.baidu.com/s/1h9qN-tWjZrXT1wQsHhZBpw?pwd=a942) (code: a942) for evaluation."

- SD v1.4 weights: https://pan.baidu.com/s/1H0IceEHzpB_ADh5J487bkA?pwd=imjw (extraction code `imjw`) — link verified reachable (HTTP 302 redirect to Baidu share page confirmed via `curl -I`, 2026-08-26).
- SD v1.5 weights: https://pan.baidu.com/s/1h9qN-tWjZrXT1wQsHhZBpw?pwd=a942 (extraction code `a942`).
- **No Google Drive / HuggingFace / direct-download mirror is provided anywhere in the repo.** Both weight sets are only on Baidu Netdisk (百度网盘), which typically requires a Baidu account/app and is slow or login-gated from non-China IPs.
- **File sizes: UNVERIFIED.** Baidu share pages require JS/login to reveal file metadata; not obtainable via a plain HTTP fetch. Given the architecture is a ResNet-50 with a single-output FC layer, the state_dict should be roughly the standard ResNet-50 size (~90–100 MB) by analogy, but this is an estimate, not a measurement — **UNVERIFIED, do not treat as authoritative.**
- **Which to use for "general-purpose" detection**: the README frames Stable_Diffusion_v1.5 as the primary example throughout (used in the sample training command `--choice 0 0 0 0 1 0 0 0`, i.e. index 4 = `Stable_Diffusion_v1.5`), and the shipped `results/results_scaling_patch32.txt` evaluation dump is consistent with a model evaluated across all 8 GenImage subsets after training on one of them. The paper's headline "cross-generator generalization" claims (>98.2% GAN→Diffusion, >99.2% Diffusion→GAN) are the basis for recommending either checkpoint for out-of-distribution detection, but the README does not explicitly say "use this one for general images outside GenImage" — **that recommendation is our inference, not a repo claim.** No weights trained on the full/mixed 8-subset training data are offered — only single-subset (SD v1.4 or SD v1.5) checkpoints.

Source: https://raw.githubusercontent.com/hongsong-wang/LOTA/main/README.md

---

## 3. Exact preprocessing pipeline

Traced end-to-end through `loader.py::create_preprocessing_pipeline` / `apply_preprocessing`, `bit_patch.py::bit_patch`, and `config.py` defaults:

1. **Input image loading**: `Image.open(path).convert('RGB')` — a **PIL RGB image at its original, undecoded/unresized resolution** (`GenerativeImageTrainingSet._load_rgb` / `GenerativeImageValidationSet._load_rgb` in `loader.py`). No resize happens before `bit_patch()` is called — **confirmed: the ORIGINAL image resolution is what bit-plane extraction operates on**, not a pre-resized copy.
2. **Bit-plane noise extraction** (`bit_patch.py`, `bit_mode='scaling'`): convert to `np.array`, mask each of R/G/B channels with `0x07` (lowest 3 bits), rescale `value * (255 // 7)` → uint8 image same H×W×3 as input.
3. **Patch extraction/selection**:
   - `img_height` default = **256** (`config.py: --img_height default=256`).
   - `patch_size` default = **32** (`config.py: --patch_size default=32`; also literally used in both README commands).
   - If `min(H, W) < patch_size`, the noise image is first resized to `(img_height, img_height)` (i.e. 256×256) via `transforms.Resize` before cropping — this only triggers for very small inputs.
   - `num_patch = (img_height // patch_size) ** 2` = `(256 // 32) ** 2` = **64** random 32×32 crops are drawn via `RandomCrop`.
   - Each candidate patch is scored by `compute()` (sum of abs horizontal + vertical + 2-diagonal pixel differences — a roughness/gradient measure) and, for `patch_mode='max'` (used at **eval time**, per README), the single highest-scoring patch is kept.
   - The selected 32×32 patch is then **upsampled back to `(img_height, img_height)` = 256×256 via `cv2.resize`** before being handed to the classifier. So the final network input is a 256×256 image that is actually an interpolated blow-up of a 32×32 bit-plane-noise crop, not the raw 256×256 noise map.
4. **Tensor conversion + normalization** (`loader.py::create_preprocessing_pipeline`): `transforms.ToTensor()` (scales uint8 0–255 → float 0–1) then `transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])` — **standard ImageNet normalization statistics**, applied to the bit-plane-derived patch, not to natural RGB values. Value range after normalization is roughly the usual ImageNet-normalized float range (not bounded to a fixed interval).
5. Batches are collated as plain stacked tensors (`torch.stack`) in `create_validation_loader`.

Training uses `patch_mode='random'` (per README/train command); evaluation uses `patch_mode='max'`. `bit_mode` in all provided commands is `'scaling'` — `'thresholding'` is unimplemented, do not use it.

Sources:
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/loader.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/bit_patch.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/config.py

---

## 4. Output semantics

- Model (`model.py`) has a single-unit final layer: `self.disc.fc = nn.Linear(2048, 1)` — forward pass returns a **single raw logit per image**, no softmax/sigmoid applied inside the model.
- Loss function used in training: `nn.BCEWithLogitsLoss()` (`util.py::bceLoss`) — consistent with a single-logit binary setup.
- Label convention (`loader.py`): **natural/real images are labeled `1`**, **AI-generated/fake images are labeled `0`** (`GenerativeImageTrainingSet`: `torch.ones(len(natural))`, `torch.zeros(len(ai))`; `GenerativeImageValidationSet(is_natural=...)` same convention).
- Inference-time interpretation (`test.py`/`train.py`, identical logic in both):
  ```python
  prediction_scores = torch.sigmoid(predictions).flatten()
  correct = ((prediction_scores > 0.5) & (target_labels == 1)) | ((prediction_scores < 0.5) & (target_labels == 0))
  ```
  So **`sigmoid(logit) > 0.5` ⇒ predicted REAL/natural**, **`sigmoid(logit) < 0.5` ⇒ predicted FAKE/AI-generated**.
- This exactly matches the shipped results file `results/results_scaling_patch32.txt`, whose header/rows are:
  ```
  image_path,true_label,prob_real,prob_fake
  GenImage/BigGAN/val/ai/920_biggan_00039.png,fake,0.000000,1.000000
  ```
  confirming `prob_real = sigmoid(logit)` and `prob_fake = 1 - sigmoid(logit)`.
- **Summary for integration**: to get "P(fake)" for a new image, run the model to get the raw logit, apply `sigmoid`, and take `1 - sigmoid(logit)` as the fake-probability. `sigmoid(logit) > 0.5` is real, `< 0.5` is fake.

Sources:
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/model.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/util.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/loader.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/test.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/train.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/results/results_scaling_patch32.txt

---

## 5. Dependencies & Apple Silicon / MPS risk

`requirements.txt` (full, verbatim):
```
numpy==1.24.4
opencv_python==4.8.1.78
opencv_python_headless==4.9.0.80
Pillow==10.3.0
scipy==1.10.1
torch==1.12.1
torchvision==0.13.1
```
Source: https://raw.githubusercontent.com/hongsong-wang/LOTA/main/requirements.txt

Notes/risks for Apple Silicon (M-series) / MPS:
- **No custom CUDA kernels** — the model is a plain `nn.Conv2d`/`nn.BatchNorm2d`/`nn.Linear` ResNet-50 reimplementation (`model.py`), and all preprocessing (`bit_patch.py`) is pure NumPy/OpenCV/PIL/`torchvision.transforms` on CPU. Nothing here is architecturally CUDA-only.
- **Hardcoded `.cuda()` calls throughout the training/eval path** — must be patched to run on MPS/CPU:
  - `model.py`/`train.py`/`test.py`: `NeuralNetwork().cuda()` / `network_instance = DeepLearningModel().cuda()`.
  - `train.py`/`test.py`: `inputs = inputs.cuda()`, `targets = targets.cuda()` (in both train and val/test loops).
  - `test.py::configure_computation_device` / `train.py::configure_gpu`: `os.environ["CUDA_VISIBLE_DEVICES"] = device_id` — harmless no-op on Mac but a sign the scripts were never made device-agnostic.
  - None of these are gated behind `torch.cuda.is_available()` checks — **running `test.py`/`train.py` unmodified on a machine without CUDA will crash** (`.cuda()` raises `AssertionError: Torch not compiled with CUDA enabled` on non-CUDA builds, or `RuntimeError` if CUDA unavailable).
  - `util.py::set_random_seed` also calls `torch.cuda.manual_seed_all(seed)` unconditionally — this call is a documented no-op when CUDA isn't available in stock PyTorch, but has not been empirically verified here (**UNVERIFIED** whether it raises on an MPS-only build).
- **Pinned `torch==1.12.1`** is from mid-2022, predates mature MPS support (MPS backend was introduced experimentally in 1.12 but had many operator gaps back then). For Apple Silicon you would almost certainly want to install a modern PyTorch (2.x) with MPS support rather than the pinned version, and there is nothing in the code requiring exactly 1.12.1 (no version-specific APIs observed in `model.py`/`bit_patch.py`/`loader.py`).
- **Implicit network dependency at model construction time**: `model.py`'s `resnet50(pretrained=True)` calls `torch.utils.model_zoo.load_url(...)` to download **ImageNet** weights from `download.pytorch.org` every time `model()` is instantiated, *before* the LOTA checkpoint is loaded on top of it via `load_state_dict`. This means even pure inference requires internet access to `download.pytorch.org` once (or a pre-populated torch hub cache) unless the vendored code is patched to skip the ImageNet download (e.g., pass `pretrained=False`, since the LOTA checkpoint fully overwrites those weights anyway).
- `opencv_python` and `opencv_python_headless` are both pinned — only one is actually needed at runtime; harmless but redundant.

Sources:
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/requirements.txt
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/model.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/train.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/test.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/util.py

---

## 6. License

- **Code**: MIT License, `LICENSE` file, copyright "hongsongwang" 2025. Full permissive license (use/modify/distribute/sublicense/sell permitted; must retain copyright+permission notice; no warranty).
  Source: https://raw.githubusercontent.com/hongsong-wang/LOTA/main/LICENSE
- **Weights**: **No explicit license is stated anywhere for the pretrained checkpoints.** The README only gives Baidu download links + extraction codes with no accompanying license text or statement that the MIT LICENSE file also covers the weights. **UNVERIFIED** whether the weights inherit the MIT license or are unlicensed/all-rights-reserved by default — treat weight redistribution/commercial use as legally ambiguous until the authors clarify. (Contact given in README: Hongsong Wang, hongsongwang@seu.edu.cn.)
- Note: the repo's acknowledgments cite three other codebases it borrows from — CNNDetection (https://github.com/PeterWang512/CNNDetection), PatchCraft (https://github.com/cvlcgabriel/PatchCraft), and SSP (https://github.com/bcmi/SSP-AI-Generated-Image-Detection) — none of those projects' own licenses are re-stated in the LOTA repo; if vendoring code verbatim from `model.py` (which is structurally very close to a standard torchvision ResNet-50, itself BSD-licensed) this is unlikely to be an issue, but it's not explicitly disclosed.

Source: https://raw.githubusercontent.com/hongsong-wang/LOTA/main/README.md

---

## 7. Integration difficulty assessment

**Cannot be used as an installable library.** There is no `setup.py`/`pyproject.toml`/`__init__.py`/package structure anywhere in the tree (confirmed via the full GitHub API tree listing in section 1) — it is a flat collection of standalone scripts meant to be run from within a cloned checkout with relative imports (`from bit_patch import bit_patch`, `from model import model`, `from loader import ...`, `from config import ...`, `from util import ...`). **You must vendor (copy) the relevant files into your project.**

Minimum files to vendor for single-image inference (none of these need `train.py`/`loader.py`'s dataset classes or `config.py`'s argparse):
- `bit_patch.py` (preprocessing — `bit_patch()` function only; the `compute()` helper is used internally)
- `model.py` (architecture — `resnet50` + `model` class)

You will need to hand-roll a small inference wrapper (does not exist in the repo) that:
1. Loads a PIL image, calls `bit_patch(img, 256, 'scaling', 32, 'max')`.
2. Applies `ToTensor()` + `Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])` exactly as in `loader.py::create_preprocessing_pipeline`.
3. Builds `model(pretrain=True)` — **recommend patching to `pretrained=False`** inside a local copy of `resnet50(...)` to avoid an unnecessary/blocking ImageNet download, since `load_state_dict` from the LOTA checkpoint will overwrite all weights anyway.
4. Replaces every hardcoded `.cuda()` with `.to(device)` where `device` is resolved via `torch.device("mps" if torch.backends.mps.is_available() else "cpu")` on Apple Silicon (or `"cuda"`/`"cpu"` elsewhere).
5. Loads the checkpoint: `model.load_state_dict(torch.load(weights_path, map_location=device))`.
6. Runs forward pass → `sigmoid(logit)` → `prob_real`, `1 - prob_real` = `prob_fake`.

Hardcoded issues found in the inference-adjacent code path (`test.py`, `model.py`, `config.py`):
- `test.py`/`train.py`: hardcoded `.cuda()` on model and every batch tensor (see section 5) — must be edited to run anywhere but a CUDA GPU.
- `test.py`/`train.py`: `os.environ["CUDA_VISIBLE_DEVICES"] = gpu_id` — CUDA-specific, harmless but dead code off-CUDA.
- `config.py`: hardcoded dataset/output paths as **defaults** (`--image_root default='/home/hdd1/chengrenxi/GenImage'`, `--save_path default='/home/hdd1/chengrenxi/sdv5_thresholding2/'`, `--gpu_id default='5'`) — irrelevant if you bypass `config.py`/`test.py`/`train.py` entirely and write your own inference script (recommended), but a trap if you try to run `test.py` as-is.
- **README/code mismatch**: README's example commands use flag `--choice 1 1 1 1 1 1 1 1` / `--choice 0 0 0 0 1 0 0 0`, but `config.py` actually defines the argument as `--choices` (plural) with `argument_parser.add_argument('--choices', ...)`, and both `loader.py` and the rest of the codebase reference `options.choices`. Because `config.py::collect_arguments` calls `self.argument_parser.parse_args()` (not `parse_known_args`) on the second parse, running the literal README command as written will likely raise `error: unrecognized arguments: --choice ...`. **If you ever invoke `train.py`/`test.py` directly, use `--choices` not `--choice`.**
- `bit_mode='thresholding'` is an unimplemented stub (`combined_image = img_np  # To be modified` in `bit_patch.py`) — only `'scaling'` is functional; don't select thresholding mode.

**Overall difficulty: moderate.** The model architecture and preprocessing are small, self-contained, and framework-standard (no exotic ops, no CUDA kernels) — easy to port to CPU/MPS. The real friction is (a) no packaging/library surface — must vendor ~2 small files and write your own inference glue from scratch, (b) weights are Baidu-only with no verified size/mirror and an unclear license for the checkpoint files themselves, and (c) the repo has at least one confirmed inconsistency (`--choice` vs `--choices`) and one confirmed non-functional feature (`thresholding` mode) that could cost debugging time if followed literally from the README.

Sources:
https://api.github.com/repos/hongsong-wang/LOTA/git/trees/main?recursive=1
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/config.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/test.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/train.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/model.py
https://raw.githubusercontent.com/hongsong-wang/LOTA/main/bit_patch.py

---

## ADDENDUM — 2026-08-26 ~22:45 (Claude): mirror search exhausted, weights confirmed Baidu-only

Re-verified the original finding and searched for any alternative distribution before spending the Phase-1 kill-cap budget on integration code:

1. **GitHub README re-fetched.** Pretrained weights are offered through **exactly two Baidu Netdisk links and nothing else** — no Google Drive, HuggingFace, OneDrive, Dropbox, GitHub Release, or direct URL:
   - SD v1.4: `https://pan.baidu.com/s/1H0IceEHzpB_ADh5J487bkA?pwd=imjw` (code `imjw`)
   - SD v1.5: `https://pan.baidu.com/s/1h9qN-tWjZrXT1wQsHhZBpw?pwd=a942` (code `a942`)
   - Repository license: **MIT** (so redistribution would be permitted if we could obtain the files).
2. **HuggingFace Hub searched** for a third-party mirror of the ICCV-2025 LOTA detector — **none exists** (all `lota` hits are unrelated name collisions: LoRA adapters and LLMs).
3. Conclusion: obtaining the weights requires a **Baidu account**, and Baidu Netdisk typically forces its desktop client for files of this size. The extraction codes are already embedded in the share URLs, so the blocker is account access, not the codes.

**This is now an escalation to Mehul, not a research task.** Options, in order of preference:
- **(A) Mehul obtains the two `.pth` files** via a Baidu account (or anyone with one) and drops them in `checkpoints/lota/`. The adapter work is fully specced and can then proceed inside the 4h kill cap.
- **(B) Email the authors** (Hongsong Wang, Southeast University — ICCV 2025 paper) asking for a direct link. Cheap to send, but response time is unpredictable against a 1 Sept deadline; worth sending in parallel with (A) regardless.
- **(C) Kill LOTA, substitute the second expert.** Propose **RIGID** (training-free, no checkpoint to obtain) as the cheap second expert, or run single-expert + rescue. The cascade design already tolerates N≥1 experts (Codex ACKed this in B-006 §5), and the eval harness does not hard-depend on LOTA existing.

**Recommendation:** send (B) now, ask Mehul for (A) when he is back, and set a hard decision point at **Phase-1 entry**: if the weights are not in hand by then, take (C) rather than letting a download hunt eat the schedule. Nothing in the current build depends on the outcome — CF-384 is the primary and is already green.
