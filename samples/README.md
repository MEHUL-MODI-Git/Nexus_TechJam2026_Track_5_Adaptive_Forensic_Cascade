# Sample images

Two images so every command in the main README runs immediately, with no files of
your own.

| File | What it is |
|---|---|
| `ai_generated_clean.png` | An AI-generated photograph, exactly as it was produced |
| `ai_generated_jpeg_q70.png` | **The same image** saved as an ordinary quality-70 JPEG — the compression every messaging app and website applies |

They look identical. The point is what happens underneath:

```
                                  raw detector      our cascade
  ai_generated_clean.png                0.7070           0.9625   both correct
  ai_generated_jpeg_q70.png             0.0993           0.9062   detector fooled
```

On the compressed copy the frozen detector alone drops to **0.0993** — below the
0.5 mark, so on its own it would call this a real photograph. The reliability
router corrects it back to **0.9062**. That gap is the entire project in one pair
of files.

Try it:

```bash
.venv/bin/python scripts/infer_dir.py samples --output predictions.json
```

## Attribution

Both are derived from **SID-Set**, licensed **CC BY 4.0**. The second is the first
re-encoded at JPEG quality 70 by this repository's own transform pipeline
(`src/pipeline/transforms.py`), so it is reproducible rather than hand-edited.
