# Record the video — read only this file

Everything technical is already done. You do three things: **run one command, click what it says,
read what it says.** Nothing here can break the project — every command only reads.

---

## Before you press record

**Step 1.** Open a terminal, paste this, press enter. Takes about 40 seconds.

```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && .venv/bin/python scripts/video_setup.py
```

It stops old servers, checks the images, loads the detector so there's no loading pause on camera,
tests all three commands, and starts the demo. It finishes by printing **READY TO RECORD**.
If it prints NOT READY instead, stop and send me what it printed.

**Step 2.** Open these two things and leave them open:

| what | where |
|---|---|
| The slides | `deliverables/video-slides.html` — double-click it. Press **F** for fullscreen, **→** for next slide |
| The demo | http://127.0.0.1:7860 in your browser |

**Step 3.** Before recording, take 30 seconds:
- Make your terminal text **big** (18pt+) so it's readable in the video.
- Zoom the browser so the whole verdict box fits without scrolling.
- Close other tabs. Hide your bookmarks bar. Nothing personal on screen.

**Step 4.** Record your whole screen at 1080p. Don't stop and start — record it in one pass. If you
fumble a line, pause, breathe, and say it again; you can cut it later.

---

## What the product actually shows you

Read this once so you can point at things confidently. **When you upload an image and click
"Analyze image", the screen shows six things:**

1. **The verdict** — big text: `AI-GENERATED` or `REAL`
2. **The score** — `p_fake 0.9986`. This is 0 to 1. Higher means more likely AI-made.
3. **The before-and-after** — `Primary CF-384 alone: 0.0166 → after router correction: 0.9986`.
   This is the most important line in the whole demo. It means: *the standard detector on its own
   said 0.0166 — which is "this is a real photo", and it was wrong. Our part corrected it to 0.9986.*
4. **The detector's own score and speed** — two small boxes, `CF-384 p_fake 0.0166` and `221 ms`
5. **Technical details** (click to expand) — image size, format, a content hash, and which frozen
   settings file was used
6. **Then a separate button, "Stress-test this image"** — this is the special part

**When you click "Stress-test this image"** it takes about 3 seconds and shows:

7. **A certificate** — `Verdict retention 17 / 20 stress conditions`, `Forensic reliability: LOW`,
   and *"verdicts at this retention were correct for 84.9% of held-out sources"*
8. **A bar chart** of all 20 versions of the image
9. **A table** (click to expand) with all 20 rows, each marked **held** or **FLIPPED**

### Two things to be clear about, so you don't promise what isn't there

You mentioned "rewind" and "citation". **We do not have those** — please don't refer to them.

- There's **no rewind** feature and **no citation** feature in the app.
- The **before/after comparison** you're thinking of *does* exist — that's point 3 above.
- There **is** hashing, but it's small: the "Technical details" panel shows a `Content hash` and the
  frozen settings ID. That's provenance, not a byte-by-byte diff view.
- The "every number traces to a file" idea is real but it lives in the **README and the slides**,
  not inside the app.

---

## Now record. Ten scenes, in order.

Each scene tells you what's on screen, what to do, and what to say. Read the **SAY** parts out loud
in your normal voice. Short pauses between sentences are good.

---

### Scene 1 — The hook (about 40 seconds) · in the DEMO

**DO:** Drag `deliverables/video-assets/bird_clean.png` into the demo. Click **Analyze image**.
Wait for the verdict. Then drag in `bird_noise_s010.png` and click **Analyze image** again.

**SAY:**
> "This picture was made by an AI. A well-known open-source detector agrees — it's ninety-nine point
> nine percent sure.
>
> Now here's the same picture with a tiny bit of noise added. You can't see any difference.
>
> Look at what that same detector says now: **zero point zero one six**. It now thinks this is a real
> photograph. It's completely wrong.
>
> Our system still gets it right — and it shows you exactly why. That line says the standard detector
> on its own missed this, and our correction is what caught it."

**Point at:** the line `Primary CF-384 alone: 0.0166 → after router correction: 0.9986`.

---

### Scene 2 — Why this matters (about 30 seconds) · SLIDES 2 and 3

**DO:** Switch to the slides. Slide 2, then slide 3.

**SAY:**
> "Detectors like this report near-perfect accuracy — on clean images. But no image on the internet
> stays clean. Every app and every website squashes, resizes and re-compresses what you upload. That
> isn't an attack, it's just what happens when you post something.
>
> So we tested it properly: three thousand images our system had never seen, each one put through all
> twenty of the official transformations. Sixty thousand tests.
>
> On clean images, the standard detector catches seventy-one percent of AI images. Add that
> invisible noise, and it catches **zero point seven percent**.
>
> That's not 'a bit worse'. That's gone. And it breaks the other way too — at that noise level it
> starts calling nearly a third of **real** photographs fake. It doesn't get unsure. It gets
> confidently wrong."

---

### Scene 3 — Why it happens (about 30 seconds) · SLIDE 4

**SAY:**
> "Once you look at the failures, there's a pattern.
>
> Real photographs have a faint texture from the camera sensor. AI images are smoother. Blurring a
> real photo wipes that texture away — so a blurred real photo starts to look, to the detector,
> exactly like an AI one. And adding noise buries the fingerprint the detector was looking for.
>
> So here's the idea the whole project is built on: **if we can measure what's been done to a
> picture, we can work out how much to trust the answer.**"

---

### Scene 4 — How it's built (about 40 seconds) · SLIDE 5

**SAY:**
> "So the system measures the damage before it judges the picture.
>
> First it opens the image carefully, without re-compressing it.
>
> Then a frozen expert detector looks at it — twenty-two million parameters, downloaded, never
> retrained by us, locked to one exact version.
>
> Then we measure the damage: how blurry, how compressed, how noisy. And we re-score the picture
> three more times under small changes, to see how much the score wobbles.
>
> And then the actual thing we built: a correction layer of **one thousand eight hundred and
> twenty-seven** numbers. That's tiny. It takes 'here's what was done to this picture' and turns it
> into a correction to the verdict.
>
> One cut-off, used for every kind of damage — we never tune it per case, because that would be
> cheating.
>
> And the demo, the command line and our testing all run the same code. There's no special demo
> version that looks better than the real thing."

---

### Scene 5 — It knows when it's unsure (about 40 seconds) · in the DEMO

**DO:** Go back to the browser. The noisy image should still be loaded. Click
**"Stress-test this image"**. It takes about 3 seconds — **don't cut the wait**, it's doing 80
checks. Then expand the results table.

**SAY:**
> "This is the part we're most proud of. The system checks its own answer.
>
> It takes this one picture, makes twenty damaged versions of it, and re-runs its own verdict on
> every one. Then it counts how many still agree.
>
> Seventeen out of twenty. So it grades **its own answer** as **low confidence** — and it tells you
> what that grade means: answers this shaky turn out to be right about eighty-five percent of the
> time.
>
> And it shows you exactly which kinds of damage break it. Look — blur and resizing flip this one.
>
> That eighty-five percent isn't a number we invented. It's what we measured on three thousand
> images the system had never seen."

**Point at:** the rows marked **FLIPPED** — `blur_s1.0`, `blur_s2.0`, `resize_0.5`.

---

### Scene 6 — Same system, command line and batch (about 20 seconds) · TERMINAL

**DO:** Switch to the terminal. Run these two, one after the other:

```
.venv/bin/python scripts/audit_image.py deliverables/video-assets/bird_clean.png
.venv/bin/python scripts/infer_dir.py deliverables/video-assets --output predictions.json
```

**SAY:**
> "Same check from the command line — and on the clean picture it's twenty out of twenty, high
> confidence, right ninety-nine percent of the time.
>
> And it runs over a whole folder for bulk use. Same code underneath, every time."

---

### Scene 7 — The headline result (about 40 seconds) · SLIDES 6, 7 and 8

**SAY (slide 6):**
> "So here's the result. On the kind of damage it handles worst, the standard detector catches
> **twelve percent** of AI images. Ours catches **eighty-three**."

**SAY (slide 7 — do not skip this one):**
> "But we have to be fair about that. The other detector was being much more cautious than us — it
> raises far fewer false alarms, and some of our lead is just us being less cautious.
>
> So we gave it every advantage. We set it to raise false alarms at exactly our rate, and we let it
> tune itself on the test answers — something we never allowed ourselves.
>
> Even then, it only gets to thirty-three percent. We're still ahead by **forty-nine points**. That's
> the number we publish."

**SAY (slide 8):**
> "Here's every type of damage, including the ones where we help least. And here's the cost: we
> raise more false alarms than we said we'd allow — eight point three percent against the seven point
> six we set ourselves. We missed our own target, and we're reporting it rather than quietly moving
> the target."

---

### Scene 8 — The official benchmark (about 25 seconds) · SLIDE 10

**SAY:**
> "The organisers gave everyone a reference set of images. We locked it away on day one and never
> trained on it, never tuned to it, never even looked at the results while making decisions.
>
> After everything was frozen, we ran it **once**. A hundred and seventy-four thousand tests, zero
> failures.
>
> Two things didn't carry over to that data, and they're on the slide next to the good news. Our
> lead over a properly-tuned competitor is nine points there, not forty-nine. And our 'ask a human'
> feature did nothing at all — it sent a quarter of the images to a human and got no benefit.
>
> The confidence signal we **trained** didn't survive new data. The one we **measured** — the twenty
> checks — did. Knowing which of your own signals holds up is the thing we'd most want a judge to
> take away."

---

### Scene 9 — Proof it's real (about 15 seconds) · TERMINAL

**DO:** Run these two:

```
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/run_eval.py --config configs/frozen.yaml
```

**SAY:**
> "Every table in this video regenerates from one command, and every number is checked against the
> file it came from. Seven hundred and eighty-seven tests pass."

---

### Scene 10 — What we threw away, and close (about 30 seconds) · SLIDES 11 and 12

**SAY:**
> "Three things worth checking us on.
>
> We found a serious flaw in our own training data — every real image was saved as a JPEG and every
> fake as a PNG, so the file type alone gave away the answer every single time. We found it
> ourselves, fixed it, and added a test that uses no detector at all so nobody can be fooled by that
> again.
>
> We tried two state-of-the-art second opinions and rejected both, for the same reason: they both
> read the fine detail in an image, and fine detail is exactly what noise and compression destroy.
> You can't rescue a damaged image using the part that's damaged.
>
> And we killed five of our own ideas this way — including our own wobble-test, which costs
> eighty-six percent of our running time and, when we measured it properly, bought us nothing. We
> published that too.
>
> Twenty-two million parameters. About one percent of the size limit. A tenth of a second per image
> on a laptop.
>
> A score you can price is worth more than a score you can't."

**FINAL SCREEN:** show the repo link, and this line, which is required:
`Synthetic sample image: SID-Set, CC BY 4.0`

---

## After you stop recording

**Step 1.** Shut everything down cleanly:

```
.venv/bin/python scripts/video_setup.py --stop
```

**Step 2.** Upload to YouTube. Set it to **Public** — not Unlisted, not Private. The brief requires
public.

**Step 3.** Paste the YouTube link into the Devpost description.

**Step 4.** Tell me it's done and I'll tick it off the submission checklist.

---

## If something goes wrong

| problem | what to do |
|---|---|
| Setup says NOT READY | Send me the message. Don't try to fix it yourself. |
| The page at 127.0.0.1:7860 won't load | Re-run the setup command; it restarts the server. |
| A number on screen doesn't match this guide | **Stop and tell me.** Say what you saw. Don't record around it. |
| You stumble on a line | Pause, then say it again. Cut it in editing. |
| The demo feels slow on the stress test | That's correct — it's doing 80 checks. Let it run. |
