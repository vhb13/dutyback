# DutyBack: how to submit

**Deadline:** check Canvas.
**Everything is in the `SUBMIT_DutyBack` folder** inside `final project`.

| Step | Do this | Files |
|---|---|---|
| 1 | Put the code on GitHub (public repo `vhb13/dutyback`) | `4_Code_for_GitHub/dutyback` |
| 2 | Canvas → Final Project → Start Assignment | `1_Upload_to_Canvas/` |
| 3 | Paste the comment, with the repo link | `2_Email_and_guide/Canvas_comment.txt` |
| 4 | Submit and check, then email the professor (optional) | `2_Email_and_guide/Email_to_professor.txt` |

---

## Step 1: Put the code on GitHub (about 2 minutes)

The repo is already a git repository with one commit, ready to push. From a terminal:

```bash
cd "final project/dutyback"
gh repo create dutyback --public --source . --push
```

Or on the website: github.com → **+** → **New repository** → name `dutyback` → **Public** → no README → **Create**. Then:

```bash
git remote add origin https://github.com/vhb13/dutyback.git
git push -u origin main
```

**Check:** open https://github.com/vhb13/dutyback. The README should show, and `app/`, `data/`, `docs/`, `tests/` should be there. There must be **no `.env`** file in the repo, only `.env.example`.

If you'd rather keep the repo private, add the GitHub user **zlisto** as a collaborator (repo **Settings → Collaborators → Add people**).

## Step 2: Upload to Canvas
Canvas → **Assignments** → **Final Project** → **Start Assignment** → **File Upload**:
1. `report.html`
2. `slides.html`
3. `DutyBack_demo.mp4` (optional backup video)

Use **+ Add Another File** for each. The PDFs in `3_PDF_versions` are optional extras.

## Step 3: Comment box
Paste `Canvas_comment.txt`. It has the repo link.

## Step 4: Submit, check, email
- Click **Submit Assignment**. Check that all files are listed and the video plays.
- Optional: send `Email_to_professor.txt` with `report.pdf`, `slides.pdf` and the video attached.

---

**How the graders run it:** they clone the repo into a folder that has their `.env` one level up. DutyBack reads `.env` from its own folder first, then the folder above, and runs live on `PORTKEY_API_KEY` with gpt-6-luna. Setup is `pip install -r requirements.txt` then `python run.py` (about 2 minutes on a fresh clone).

**Real-user feedback (worth points):** if you can show DutyBack to a small business that imports, a customs broker, or anyone who handles a company's imports, use `docs/feedback_kit.md` (15 minutes). Only what they actually said goes in the report.

**Until grades are posted:** keep the repo public and the app unchanged.
