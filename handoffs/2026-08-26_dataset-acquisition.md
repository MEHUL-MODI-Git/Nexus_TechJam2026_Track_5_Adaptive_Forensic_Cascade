# Dataset Acquisition Research — AI-Generated Image Detection (Hackathon)

Context: Mac, 166GB free disk. Goal is small, fast subsets — NOT full dataset downloads. Researched 2026-08-26.

---

## 1. COCO train2017 images (need only ~200–500 images, never val2017)

**Fastest method — do NOT download the 18GB train2017.zip.**

Option A (recommended, smallest download): use a metadata-only mirror that already contains `file_name`/`coco_url` per image, then pull just the images you need directly from the CDN.

- Metadata parquet mirror: `phiyodr/coco2017` on Hugging Face — **30.2 MB total**, contains `filename`, COCO/Flickr URLs, dimensions, captions for all 118,287 train + 5,000 val images (train2017 rows only needed).
  ```python
  from datasets import load_dataset
  ds = load_dataset("phiyodr/coco2017", split="train", streaming=True)  # train2017 only
  subset = list(ds.take(300))
  import urllib.request, os
  os.makedirs("coco_subset", exist_ok=True)
  for row in subset:
      urllib.request.urlretrieve(row["coco_url"], f"coco_subset/{row['file_name']}")
  ```
  Source: https://huggingface.co/datasets/phiyodr/coco2017

Option B (official, still avoids full image zip): download only the annotations zip (**241 MB**, `annotations_trainval2017.zip` from `http://images.cocodataset.org/annotations/annotations_trainval2017.zip`), parse `instances_train2017.json` for image `file_name`s, then fetch individual images directly:
```
http://images.cocodataset.org/train2017/{12-digit-zero-padded-id}.jpg
```
e.g. `http://images.cocodataset.org/train2017/000000522418.jpg`. This pattern is documented/standard (confirmed via COCO format docs and HF dataset schema).

**Partial/streaming download:** Yes — both options above avoid the full 18GB zip; you only fetch the N images you pick.
**Total size vs subset:** Full train2017 images zip ≈ 18GB; annotations zip 241MB; metadata parquet 30MB; a 300-image subset ≈ 30–60MB of JPEGs.
**License:** Annotations are CC BY 4.0 (COCO Consortium). **Images themselves are NOT CC-licensed by COCO** — each image is subject to its original Flickr uploader's license; COCO explicitly disclaims copyright ownership and tells users to respect Flickr Terms of Use. For a hackathon this is normally fine but don't redistribute the images commercially. (Sources: cocodataset.org license page discussion, https://github.com/cocodataset/cocoapi/issues/81, https://github.com/cocodataset/cocoapi/issues/551)
**Registration:** None required for either method.

---

## 2. GenImage (real/fake pairs, 8 generators: ADM, GLIDE, VQDM, SD1.4, SD1.5, Wukong, Midjourney, BigGAN)

**Official hosting:** GitHub repo https://github.com/GenImage-Dataset/GenImage — original full dataset (~1.3M real + 1.35M fake, 2.68M images total) is only distributed via **Baidu Yunpan** (access code `ztf1`) and a **Google Drive** folder (https://drive.google.com/drive/folders/1jGt10bwTbhEZuGXLyvrCuxOI0cBqQ1FS). Full size is not stated precisely on the repo but is commonly cited as several hundred GB (the "Unbiased GenImage" mirror below states ~500GB for a cleaned copy).

**Easier mirror for Western users:** https://www.unbiased-genimage.org/ — hosted on Harvard Dataverse, ships a `download_genimage.py` script with `--continue` (resume) and `--destination` flags; downloads split `.zip.00x` fragments that must be `cat`'d together. **UNVERIFIED whether the script supports partial/generator-only download** — the script itself appears to fetch the whole archive; the site does provide a standalone `metadata.csv` (recommended to download separately) that lets you filter by generator before deciding what to fetch, but does not offer per-file selective download at the CDN level.

**Practical fast subset route — Hugging Face mirrors (recommended for hackathon):**
- `TheKernel01/Tiny-GenImage` — **8.36 GB total**, 35,000 images (28k train / 7k val) across real + all 8 generators. This is the best "grab it and go" option; still needs trimming further for a 1-5k subset but is small enough to download whole, then subsample locally with `datasets` `.take(n)` or `.select(range(n))`.
  ```python
  from datasets import load_dataset
  ds = load_dataset("TheKernel01/Tiny-GenImage", split="validation", streaming=True)
  small = list(ds.take(2000))
  ```
  https://huggingface.co/datasets/TheKernel01/Tiny-GenImage (license CC-BY-NC-SA-4.0)
- `jzousz/GenImage` on HF — **679 GB**, imagefolder format (`default/test/<idx>/image/image.png`), a single "test" split with 100,000 rows. `huggingface_hub.snapshot_download` with `allow_patterns=["default/test/0/**", "default/test/1/**", ...]` or `allow_patterns=["*000*"]`-style globs could in principle grab a few hundred images without pulling the whole 679GB, but the exact folder→generator mapping is **UNVERIFIED** (need to inspect the repo file tree in a browser/`huggingface-cli`, e.g. `huggingface-cli scan-cache` won't help — use `from huggingface_hub import list_repo_files; list_repo_files("jzousz/GenImage", repo_type="dataset")` first to confirm which indices correspond to which generator before writing `allow_patterns`).
  https://huggingface.co/datasets/jzousz/GenImage
- Other partial mirrors surfaced but not vetted for structure: `blorg469/genimage`, `Lunahera/genimagepp`.

**Recommendation:** For a 1-5k subset with guaranteed generator diversity and minimal effort, use **Tiny-GenImage** (8.36GB, all 8 generators represented) rather than trying to slice the 679GB or 500GB mirrors.

**License:** Not explicit on the official GitHub repo beyond a `License` file (unread); GenImage is widely used for academic/research purposes. Tiny-GenImage mirror is CC-BY-NC-SA-4.0. Treat as research-only.
**Registration:** None found for Baidu/Google Drive/HF routes (Baidu Yunpan may prompt for a free Baidu account to download from its web UI — UNVERIFIED whether truly anonymous).

---

## 3. SID-Set (https://huggingface.co/datasets/saberzl/SID_Set)

**Structure:** Parquet format, columns `img_id` (matches OpenImages V7 ids for real images), `image`, `mask` (binary mask for tampered regions), `width`, `height`, `label` (0 = Real, 1 = Fully-Synthetic, 2 = Tampered).

**Splits:** Train 210,000 / Validation 30,000 / Test 60,000 (test set requires the official GitHub repo, not on HF — https://github.com/hzlsaber/SIDA). Viewer shows 240,000 rows accessible directly on HF.

**Total size:** ~140 GB.

**Download only real + fully-synthetic subset:**
```python
from datasets import load_dataset
ds = load_dataset("saberzl/SID_Set", split="validation", streaming=True)  # avoid full download
subset = ds.filter(lambda x: x["label"] in (0, 1)).take(2000)
```
Streaming + filter avoids materializing the full 140GB; alternatively use `huggingface_hub.snapshot_download(allow_patterns=["*val*"])` if the repo shards parquet files by split (verify shard names via `list_repo_files` first — **UNVERIFIED** exact shard naming).

**License:** CC BY 4.0, with a requirement to also comply with the source datasets' terms (COCO, OpenImages V7, Flickr30k) since real images are drawn from those.
**Registration:** None for the HF-hosted train/val portion; the held-out test set needs the GitHub repo (may have its own access process — UNVERIFIED).

---

## 4. WildFake (ModelScope: https://modelscope.cn/datasets/hy2628982280/WildFake)

**Downloading from outside China:** ModelScope's site is JS-rendered and its file-tree API (`/api/v1/datasets/.../repo/files`) requires exact query params I could not fully reverse-engineer (kept returning `参数错误`/param error via curl). The reliable path is the **`modelscope` pip package**:
```bash
pip install modelscope
modelscope download --dataset hy2628982280/WildFake --include "*coco*" --local_dir ./wildfake_subset
```
`modelscope download` supports `--include`/`--exclude` glob patterns analogous to `huggingface-cli download --include`. There is an open GitHub issue (modelscope/modelscope#1237) showing that glob-based `--include` filtering on file paths works at the raw file level, but that `MsDataset.load(..., subset_name=...)` does *not* reliably expose folder-level subsets — so for a sealed eval subset, prefer the raw CLI download with `--include` glob(s) rather than `MsDataset.load`. No VPN/registration was found to be strictly required for the pip client (ModelScope has historically been usable globally via `pip install modelscope`), but **this is UNVERIFIED for your specific network/region** — test with a `--include` pattern that matches very few files first.

**Overall dataset facts (from the WildFake/AAAI-2025 paper, arXiv:2402.11843, and the ModelScope repo metadata JSON):**
- Total dataset size on ModelScope: **~1.2 TB** (1,291,478,056,101 bytes), license listed as **Apache 2.0** on the ModelScope repo page itself (paper doesn't state a license explicitly).
- Total images: 3,694,313 (1,013,446 real + 2,680,867 fake), split 4:1 train:test per generator.
- Real images sourced from: COCO, FFHQ, ImageNet, LSUN Church, CelebA-HQ, AFHQ, LAION-5B, Wukong.
- Hierarchical structure, 5 levels: **Cross-Generator** (GANs / DMs / Others) → **Cross-Time** (Early/Latest, for GANs & Others) → **Cross-Architecture** (for DMs: DALLE, ADM, Imagen, DDPM, DDIM, VQDM, Midjourney, SD) → **Cross-Weight** (for SD: Original / Personalized / with-Adaptor) → **Cross-Version** (Typical vs Advanced, applied to DALLE and Midjourney).
- **"DALL-E Advanced" is a real, named subset**: under Cross-Version, DALLE splits into **Typical = DALLE.2** and **Advanced = DALLE.3**. So "DALL-E Advanced" ≈ the DALLE.3-generated fake images subset. (Confirmed directly from Figure 1 of the paper.)
- **"COCO-val2017" as a named subset is NOT confirmed in the paper** — the paper only says real images are "sampled from COCO" generically, without specifying train vs val split. It is plausible the ModelScope file tree literally has a folder named `COCO-val2017` (common practice, since val2017 is the smaller/cleaner COCO split used as a real-image pool), but I could not verify this — **UNVERIFIED**. Likewise the exact count **13,841 files is UNVERIFIED** — I could not access ModelScope's JS-rendered file browser or its files API from this environment.

**Action needed before treating your 13,841-file eval set as sealed:** Have someone with normal browser/network access open https://modelscope.cn/datasets/hy2628982280/WildFake/files, confirm the literal folder names (likely something like `real/COCO-val2017/` and `fake/DMs/DALLE/Advanced/` or similar), and get the exact counts, THEN download with:
```bash
modelscope download --dataset hy2628982280/WildFake \
  --include "*COCO-val2017*" "*DALLE*Advanced*" \
  --local_dir ./wildfake_eval_sealed
```
(patterns are placeholders pending confirmed folder names).

**License:** Apache 2.0 (per ModelScope repo metadata).
**Registration:** None apparent for public ModelScope datasets; the pip client typically works without login for public repos.

---

## 5. CIFAKE on Kaggle

**One-liner:**
```bash
kaggle datasets download -d birdy654/cifake-real-and-ai-generated-synthetic-images
```
(requires `~/.kaggle/kaggle.json` API token — standard Kaggle CLI auth, i.e. free Kaggle account registration required).

**Size:** 120,000 images total (60,000 real from CIFAR-10 + 60,000 AI-generated via Stable Diffusion 1.4), 32×32 px, split 100,000 train (50k/class) + 20,000 test (10k/class). Small enough (low tens of MB, since images are 32×32) to just download whole — no partial-download trick needed.
**License:** Kaggle page doesn't state an explicit restrictive license beyond standard Kaggle dataset terms; underlying CIFAR-10 portion is freely usable for research; treat as research/non-commercial to be safe (**UNVERIFIED** exact license text — check the Kaggle page's "Usability"/license badge directly).
**Registration:** Free Kaggle account + API token needed for CLI download.

Source: https://www.kaggle.com/datasets/birdy654/cifake-real-and-ai-generated-synthetic-images

---

## 6. Ready-made small (<2GB) mixed real/AI benchmarks on Hugging Face for smoke-testing

1. **`TheKernel01/Tiny-GenImage`** — 8.36GB total (exceeds 2GB budget for the *whole* set, but the validation split alone is 7,000 images and can be streamed/sliced down to a sub-2GB chunk easily). Generator diversity: real + SD1.4, SD1.5, GLIDE, Midjourney, ADM, VQDM, Wukong, BigGAN (all 8 GenImage generators). License CC-BY-NC-SA-4.0. A documented smoke-test convention already exists for it: 20 real + 20 fake images from the validation shard (40 images total) — good starting point. https://huggingface.co/datasets/TheKernel01/Tiny-GenImage

2. **`TheKernel01/AIGC-Detection-Benchmark`** — **32GB / 125,026 images**, too big for a <2GB budget as-is, but its "Apache 2.0" license and rich 18-class label set (real + ADM, DALL-E 2, Midjourney, SD 1.4/1.5/XL, GLIDE, VQDM, Wukong, BigGAN, CycleGAN, GauGAN, ProGAN, StarGAN, StyleGAN, StyleGAN2, WhichFaceIsReal) make it worth streaming a small slice from (`load_dataset(..., streaming=True).take(n)`) rather than downloading whole. Best generator/architecture diversity of anything found (GANs + diffusion + commercial models together). https://huggingface.co/datasets/TheKernel01/AIGC-Detection-Benchmark

3. **`lrzpellegrini/AI-GenBench-fake_part`** — 35.2GB / 180,000 images (144k train / 36k val), ~30+ generators (StyleGAN family, ProGAN, BigGAN, SD variants, DALL-E 3, Midjourney, FLUX, DeepFloyd IF, etc.), aggregated from 12+ source datasets. Too large to download whole under a 2GB budget but has the broadest generator coverage of all candidates found; stream + `.take(n)` for a smoke set. License is multi-source — check per-image provenance before redistributing. https://huggingface.co/datasets/lrzpellegrini/AI-GenBench-fake_part

**Caveat:** None of the three is natively ≤2GB as a full download; all are "small enough to stream a slice from quickly" rather than "small enough to grab whole." If a literal <2GB *full* download is required, **Tiny-GenImage's validation split alone (7,000 images, roughly 1.5-2GB of the 8.36GB total — UNVERIFIED exact split-level size)** is the closest fit; otherwise use `streaming=True` + `.take(n)` on any of the three above, which effectively caps bandwidth regardless of total dataset size.
(`aidetectarena/ai-image-detector-benchmark` was also found in search but its HF repo currently shows as empty/metadata-only — not usable as-is, excluded from recommendations.)

---

## Summary table

| # | Dataset | Fastest subset method | Subset size | Full size | License | Registration |
|---|---|---|---|---|---|---|
| 1 | COCO train2017 (subset) | `phiyodr/coco2017` parquet metadata + direct `images.cocodataset.org` URL pulls | ~30-60MB for 300 imgs | 18GB (train2017 zip) | Annotations CC BY 4.0; images = Flickr terms | None |
| 2 | GenImage | HF `TheKernel01/Tiny-GenImage` (whole) or stream+filter from `jzousz/GenImage` | 8.36GB (Tiny) | ~500GB-1.3M+ pairs (official) | CC-BY-NC-SA-4.0 (Tiny mirror); unclear (official) | None (Tiny/HF); Baidu account UNVERIFIED |
| 3 | SID-Set | `datasets` streaming + `.filter(label in [0,1])` | a few GB for a few k imgs | 140GB | CC BY 4.0 + source dataset terms | None (train/val); test set via GitHub |
| 4 | WildFake | `modelscope download --include` glob | UNVERIFIED (target ~13,841 files) | ~1.2TB | Apache 2.0 | None apparent |
| 5 | CIFAKE | `kaggle datasets download -d birdy654/cifake-real-and-ai-generated-synthetic-images` | whole set is small (32×32px) | 120,000 imgs, low tens of MB | UNVERIFIED (Kaggle terms) | Free Kaggle account + API token |
| 6 | Smoke-test sets | Stream + `.take(n)` from Tiny-GenImage / AIGC-Detection-Benchmark / AI-GenBench-fake_part | <2GB achievable via streaming | 8.36GB / 32GB / 35.2GB | Varies (CC-BY-NC-SA / Apache 2.0 / multi-source) | None |

---

## Key unverified items flagged for follow-up

- WildFake's exact ModelScope folder names and the 13,841-file count for "COCO-val2017 + DALL-E Advanced" — needs manual browser check of https://modelscope.cn/datasets/hy2628982280/WildFake/files (JS-rendered, could not scrape).
- Whether `modelscope` pip client needs a VPN/mainland-China network for large downloads in practice.
- Whether Baidu Yunpan GenImage download requires a Baidu account for anonymous users.
- Exact license text on Kaggle's CIFAKE page.
- Exact shard/folder naming inside `saberzl/SID_Set` and `jzousz/GenImage` repos for precise `allow_patterns` targeting (recommend running `huggingface_hub.list_repo_files(...)` locally before writing final download scripts).
