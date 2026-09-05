# Why CI is not running, and how to check the billing page

**Written for someone who has never opened GitHub's billing settings.** Follow
it top to bottom; it should take about ten minutes.

**The repository:** `RSD-Studio/tokenmill`.
**The symptom, as of 2026-08-24:** CI runs **25 through 76** all failed within
seconds. Run 24 was the last one that worked.

---

## Step 0 — Confirm you are looking at the right problem (2 minutes)

Before touching billing, check the symptom matches. Open:

<https://github.com/RSD-Studio/tokenmill/actions>

You are looking for a list of runs with **red ✗** marks. Click the most recent
one. You should see this pattern:

- **24 jobs listed**, with sensible names (`Test (py3.11 / ubuntu-latest)`,
  `Lint and format`, and so on).
- **Every job failed in under ~20 seconds.** A real test run takes minutes.
- **Clicking into any failed job shows no steps and no logs** — not an error
  message, just nothing. There is no red step to expand.
- **One job, `Docling (weekly and on demand)`, is grey/skipped** rather than
  red. That one is *correct*.

**If that is what you see, it is almost certainly billing.** Here is why that
combination is the giveaway: GitHub *read the workflow file*, *worked out all
24 jobs*, and *correctly decided to skip the docling one*. So the file is fine.
It then failed to give any job a machine to run on. Jobs that never got a
machine have no logs, because nothing ever ran.

**If instead you see jobs with red steps you can expand and read**, this
document is the wrong one — that is a genuine test failure, and the logs will
say what broke.

---

## Step 1 — Find the billing page (2 minutes)

`RSD-Studio` may be a personal account or an organisation. Try the
organisation URL first:

<https://github.com/organizations/RSD-Studio/settings/billing>

- **If that loads**, it is an organisation. Carry on.
- **If you get a 404 or "not found"**, it is a personal account. Use this
  instead: <https://github.com/settings/billing>

> GitHub moves this page around and renames its sections every so often, so the
> exact wording below may differ slightly from what you see. The *things* you
> are looking for are stable even when their labels are not.

You may need to click into a sub-page named something like **"Plans and usage"**,
**"Usage"**, or **"Spending limit"**.

---

## Step 2 — Look for these three things (3 minutes)

### (a) Actions minutes used

Find a section about **Actions** minutes. It will show something like
"1,850 / 2,000 minutes used" or a progress bar.

**What you are checking:** is it at or very near 100%?

Free accounts get 2,000 Actions minutes per month. This project burns them
fast, for a reason worth knowing: **macOS runners bill at 10× and Windows at
2×.** One full CI run here is 24 jobs across all three operating systems, so a
single run can cost well over 100 billable minutes even though it only takes a
few minutes of real time. Seventy-odd runs in a few days will exhaust the
allowance.

### (b) Spending limit

Find **"Spending limit"**. It is usually **$0 by default**.

**What you are checking:** if minutes are exhausted *and* the spending limit is
$0, GitHub stops scheduling runners. That produces exactly the symptom in
Step 0 — jobs created, no machine, no logs.

### (c) Payment method

**What you are checking:** whether one is on file at all, and whether it has
expired or been declined. A declined card produces the same outcome.

---

## Step 3 — Decide what to do

**You have three options. Pick one.**

| Option | What happens | Cost |
|---|---|---|
| **Wait for the monthly reset** | Minutes reset on your billing date; CI starts working again on its own | Free, but CI stays dead until then |
| **Raise the spending limit** | Runs resume immediately, and you pay per minute beyond the free allowance | Real money — set a low cap first, e.g. $5 or $10 |
| **Make the repository public** | Actions minutes are free on public repositories | Free, but the code becomes visible to everyone |

**My suggestion, and it is only a suggestion:** if this project is going to be
open-source anyway — and the README says it is — **making the repository public
is the option that costs nothing and fixes it permanently.** Do that only when
you are ready for the code to be visible; it is not easily undone.

If you are not ready for that, set a **small spending limit** ($5 is plenty to
prove the diagnosis) rather than waiting, because everything built in the last
three sessions is unverified until CI runs.

---

## Step 4 — Test that it actually worked (3 minutes)

**Do not assume it is fixed.** Trigger a run and watch it.

1. Go to <https://github.com/RSD-Studio/tokenmill/actions>
2. Click **"CI"** in the left-hand sidebar.
3. Click the **"Run workflow"** button on the right.
4. Pick the branch — use `Main`, or `phases-10-5-6-work-qxl2rh` to test
   the newest work.
5. Click the green **"Run workflow"** button to confirm.
6. Wait about 30 seconds, then refresh the page.

### What success looks like

- Jobs turn **yellow (running)** and stay yellow for **minutes**, not seconds.
- Clicking a running job shows **steps appearing one by one**, with live log
  output.

**That is the proof.** Yellow-for-minutes with visible logs means a runner was
assigned. Whether the tests then pass or fail is a separate question — and a
genuine test failure would be *good news* here, because it means CI is alive
again and telling you something.

### What failure still looks like

- Jobs go **straight to red in under 20 seconds**, still with no logs.

Then billing was not the cause. See Step 5.

---

## Step 5 — If billing was not the problem

Things to check, roughly in order of likelihood:

1. **Actions disabled for the repository.** Settings → Actions → General. There
   is a setting that can disable Actions entirely, or restrict which workflows
   may run.
2. **Organisation-level Actions policy**, if `RSD-Studio` is an organisation.
   An org can disable Actions for all its repositories, or block certain runner
   types.
3. **A GitHub-wide incident.** Check <https://www.githubstatus.com/>. This
   would be unusual over more than two days, but it is thirty seconds to rule
   out.

---

## What to tell the next session

Whatever you find, write it down — a sentence is enough. For example:

> *"Actions minutes were exhausted (2,000/2,000) with a $0 spending limit.
> Raised to $10; run 77 dispatched on Main and went green across all 24 jobs."*

Add it to `PROGRESS.md` under the verification log, and close **Open question 1**.

If CI does come back, the first things it will verify — none of which has ever
run anywhere — are:

- the whole suite on **Windows, macOS and Python 3.12/3.13**;
- the **clean-core-install** job across 9 cells;
- **real `o200k_base` token counts**, which is the number this project's
  headline claim depends on and which `docs/BENCHMARKS.md` currently refuses to
  publish (defect D3).
