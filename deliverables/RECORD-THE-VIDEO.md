# Record the video — read only this file

Target length: **4 minutes 40 seconds.** Hard cap 5:00. The narration below has been word-counted
against a normal speaking pace, so if you read it at a natural speed and don't ad-lib, you land
under the cap.

Everything technical is done. You run one command, click what it says, read what it says.

---

## Before you press record

**1. Run this.** Takes about 40 seconds.

```
cd "/Users/mehulmodi/MEHUL WORK/Hackathon/TechJam 2026" && .venv/bin/python scripts/video_setup.py
```

It must finish with **READY TO RECORD**. If it says NOT READY, stop and send me the message.

**2. Open two Chrome tabs and one terminal:**

| | what | how to show it |
|---|---|---|
| Tab 1 | The demo — http://127.0.0.1:7860 | Windowed. Leave the address bar visible — it proves the demo is really running |
| Tab 2 | The slides — `deliverables/video-slides.html` | Press **F** for fullscreen (hides your file path) |
| Terminal | the one you just used | Font 18pt or bigger |

**3. Clean up Chrome** (from your screenshot, these are showing):
- Remove the **"Ask Gemini"** button — that's someone else's brand in every frame
- Click **"Relaunch to update"** and let Chrome restart, so it can't interrupt you mid-recording
- Hide the bookmarks bar, close all other tabs

**4. Set the demo zoom to 150%** (Cmd and + three times). Check: after you analyze an image, the
verdict, the `Primary CF-384 alone` line, and the `CF-384 score` box should all be visible together.

**5. Record the whole screen** — Cmd + Shift + 5 → Record Entire Screen.

---

## The seven scenes

Read the **SAY** lines at a natural pace. Short pauses are fine — they're in the budget.

---

### Scene 1 · The demo (about 45 seconds) — TAB 1

**DO:** Drag in `deliverables/video-assets/bird_clean.png` → click **Analyze image**.
Then drag in `deliverables/video-assets/bird_jpeg_q30.png` → click **Analyze image**.

**SAY:**
> "This image was made by an AI. A well-known open detector agrees. It's ninety-nine point nine
> percent sure.
>
> Now the same image, saved as an ordinary compressed JPEG. Exactly what happens when you send a
> photo through a messaging app. It looks fine.
>
> That same detector now says zero point zero one nine. It thinks this is a real photograph, and it's
> wrong.
>
> Ours still catches it. And look what else it says: it worked out that the image was JPEG
> compressed, it flags that compression is where it's weakest, and it says it isn't confident enough
> and wants a human to check."

**Point at, in order:** `Primary CF-384 alone: 0.0191 → after router correction: 0.9458` ·
`Detected image history: JPEG compression (99% confidence)` · the yellow **DEFERRED** box.

---

### Scene 2 · Why it matters (about 30 seconds) — TAB 2, slides 1 → 2

**SAY:**
> "Detectors report near-perfect accuracy on clean images. But no image online stays clean. Every app
> and every website recompresses what you upload.
>
> So we tested properly. Three thousand images the system had never seen, each one through all twenty
> official transformations. Sixty thousand tests.
>
> On clean images the standard detector catches seventy-one percent of AI images. Add mild noise and
> it catches zero point seven percent. That's not worse. That's gone."

---

### Scene 3 · How it's built (about 40 seconds) — slide 3

**SAY:**
> "So our system measures the damage before it judges the picture.
>
> A frozen expert detector looks at the image — twenty-two million parameters, downloaded, never
> retrained by us. Then we measure how blurry, how compressed and how noisy the picture is.
>
> And then the part we built: a correction layer of one thousand eight hundred and twenty-seven
> numbers, which turns what was done to this picture into a correction of the verdict.
>
> One cut-off for every kind of damage. And the demo, the command line and our testing all run the
> same code."

---

### Scene 4 · It checks its own answer (about 40 seconds) — TAB 1

**DO:** Back to the demo. The compressed image is still loaded. Scroll down, click
**"Stress-test this image"**. Wait ~3 seconds — don't cut it. Then expand the results table.

**SAY:**
> "Now the part that matters most. The system checks its own answer.
>
> It makes twenty damaged versions of this picture and re-runs its own verdict on each one, then
> counts how many still agree.
>
> Eighteen out of twenty. So it grades its own answer medium confidence, and tells you what that
> means: answers this solid are right about ninety-five percent of the time. And it names the two
> kinds of damage that would break it.
>
> That percentage isn't invented. It's measured on three thousand unseen images."

**Point at:** the two rows marked **FLIPPED** — `blur_s2.0` and `resize_0.25`.

---

### Scene 5 · Results (about 40 seconds) — TAB 2, slides 4 → 5 → 6

**SAY (slide 4):**
> "On the damage it handles worst, the standard detector catches twelve percent of AI images. Ours
> catches eighty-three."

**SAY (slide 5 — don't skip this one):**
> "But we have to be fair. That detector was being far more cautious, so some of our lead is just us
> being less cautious. So we gave it our exact false-alarm rate, and let it tune itself on the test
> answers — which we never allowed ourselves. Even then it only reaches thirty-three percent. We're
> still ahead by forty-nine points. That's the number we publish."

**SAY (slide 6):**
> "And here's every kind of damage, including the ones where we help least."

---

### Scene 6 · The organizers' data (about 25 seconds) — slide 7

**SAY:**
> "The organizers gave everyone a reference set. We sealed it on day one and never trained or tuned
> on it. After everything was frozen, we ran it once. A hundred and seventy-four thousand tests, zero
> failures.
>
> And it did better than on our own data. Eighty-eight percent on the hardest damage, and false
> alarms down at one and a half percent."

---

### Scene 7 · Close (about 30 seconds) — TERMINAL, then slide 8

**DO:** Switch to the terminal and run these two. Both finish in about 2 seconds.

```
.venv/bin/python scripts/infer_dir.py deliverables/video-assets --output predictions.json
.venv/bin/python scripts/run_eval.py --config configs/frozen.yaml
```

**SAY (over the terminal):**
> "It runs over a whole folder for bulk use. And every table in this video regenerates from one
> command, checked against the file it came from."

**DO:** Switch to slide 8.

**SAY:**
> "Twenty-two million parameters. One percent of the size limit. A tenth of a second per image on a
> laptop.
>
> A score you can price is worth more than a score you can't."

**FINAL SCREEN:** your repo link, and this line, which is required:
`Synthetic sample image: SID-Set, CC BY 4.0`

---

## After recording

```
.venv/bin/python scripts/video_setup.py --stop
```

Then: upload to YouTube as **Public**, paste the link into Devpost, and tell me.

---

## What's on the demo screen, so you can point confidently

After **Analyze image**:

1. Verdict — `AI-GENERATED`
2. Score — `p_fake 0.9458` (0 to 1; higher means more likely AI)
3. **The before/after** — `Primary CF-384 alone: 0.0191 → after router correction: 0.9458`
4. `CF-384 score` and speed boxes
5. `Detected image history: JPEG compression (99% confidence)`
6. Yellow **DEFERRED** box

After **Stress-test this image**:

7. Certificate — `18 / 20`, `MEDIUM`, "correct for 94.9% of held-out sources"
8. A bar chart of all 20 versions
9. A table where `blur_s2.0` and `resize_0.25` are marked **FLIPPED**

**The app has no "rewind" and no "citation" feature** — don't refer to those. The before/after
comparison is item 3.

---

## If something goes wrong

| problem | do this |
|---|---|
| Setup says NOT READY | Send me the message. Don't improvise. |
| A number on screen differs from this guide | **Stop and tell me.** Don't record around it. |
| You stumble | Pause, say the line again, cut it later. |
| Stress test feels slow | Correct — it's doing 80 checks. Let it run. |
