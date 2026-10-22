# A Rule of Life

A rule of life and the tooling that runs it. The keeper's own Rule and record live in the
page's store, never here: what is here is the page, the tools, the skill, the registry and
the notebook's root.

**The reasoning is not here.** What a rule is, what keeping this one requires, and every
appeal to tradition it rests on live in the **hypomnemata**, the Rule's notebook of
questions and the source of truth: a Claude Docs document, read where it stands, which
[`.principal/notebook.json`](.principal/notebook.json) names; nothing of it is committed
here. The keeper's own notebook is private. To keep a Rule of your own, start your own
notebook from the root question, [`ti-esti.md`](ti-esti.md), as the CanonDB `principal`
plugin's README says, and put its ids in `.principal/notebook.json` in your copy. Everywhere in this repo, *hypomnemata › bell* means the
notebook's `bell` tab.

This file holds only what answers no question there: the setup, the runbook, the
numbers behind the drink and weight items, the page's mechanics, and the map. If a
paragraph here starts explaining *why the Rule is shaped this way*, it belongs in the
notebook instead. One copy of each claim.

| Part | For |
|---|---|
| [I. Setup, once](#i-setup-once) | Twenty minutes with your phone. Once — and step 4 again whenever a bell moves. |
| [II. Running it](#ii-running-it) | What you do, what prompts it, and how to maintain it. |
| [III. Drinking and weight](#iii-drinking-and-weight) | The numbers behind the ration and the weigh-in. |
| [IV. The page and the calendars](#iv-the-page-and-the-calendars) | Mechanics and limits. |
| [V. Map](#v-map) | Files and commands. |

---

# I. Setup, once

Work top to bottom. It takes about twenty minutes.

### 1. Put Cadence on your home screen

Cadence is your own page: publish `web/cadence.html` as a claude.ai artifact of your own
(with the `db` capability, so it has a store), and write its link into
`ordo.local.json` at the repository's root, which git ignores:

```json
{"cadence": "https://claude.ai/artifact/<your page's id>"}
```

`/ordo` reads the page from there, and asks for it when the file is missing. Then open
that link in **Safari** (not Chrome — only Safari can install to the home screen),
**Share → Add to Home Screen → Add**. It now opens full-screen, like an app.

Do this on the phone you actually carry. This is the surface you'll touch every day.

### 2. Get the Cadence calendar onto the phone

**Settings → Apps → Calendar → Calendar Accounts → Add Account → Google**, sign in as
the account whose calendar holds your fixtures and meetings (the default project's
`calendar` in the store). Then open **Calendar → Calendars** (bottom) and tick **Cadence**.

### 3. Let the bells through Focus — both kinds

**Settings → Notifications → Calendar → Allow Notifications** on, then **Time
Sensitive Notifications** on. Don't skip the second one: without it a Focus mode
silently swallows every warning during exactly the focus sessions they exist to
interrupt.

Then, if you run a Focus during focus sessions, add **Clock** *and* **Calendar** to
its allowed notifications.

### 4. Build the alarms

Clock → Alarms, each **labelled with the bell's name** (Lauds, Sext, Vespers,
Compline) — the label is what the lock screen shows. The times are in the Rule
(the page's store), and `/ordo` prints from it, with `tools/notifiers.py`, the table of alarms
they come to today (no table is kept here: a written one went stale within a week):

- **One alarm per block** at its `bell:`, repeating every day — except any weekday a
  commitment moves that bell off.
- **One more for each moved bell**: a commitment with `derived_anchor_bell:` moves the
  bell its `sets_anchor_bell:` names, on its `weekday`. Untick that weekday on the
  block's alarm, and add an alarm at the moved time repeating on that weekday only.
- **iOS alarms have no end date and no single-date skip.** When that commitment's
  `until:` passes, delete the moved alarm and tick the weekday back on the block's
  alarm; on a week it is cancelled, turn the usual alarm on and the moved one off
  for that day. `tools/notifiers.py` says when.

This is the one part of the notifiers still kept by hand. The Cadence calendar already
follows a fixture date by date and goes back by itself; the phone will too once an app
schedules the alarms from that calendar (postponed until there is one to install).
Until then `/ordo` says, with the date, each alarm to change.

Alarms are the bells and nothing else; the ten-minute warnings come from the calendar
(why: *hypomnemata › bell*). Nothing else belongs in the Clock app.

**Turn snooze off on all of them.** If that's too much at once, leave snooze on but
put the phone across the room — leaving the room is a step of the rite anyway.

### 5. Confirm the travel times

Every fixture's travel time is in its `commitments` document in the store. Confirm
any you have not timed yourself; a leave-by derived from an estimate is only as good
as the estimate.

### 6. Dry run

Open Cadence. It should show the current block, what you're doing now, and the next
bell. Open the current bell's card to see that it asks the right thing, then close it
**without answering**. An answer is a real record: its time and delay are the
measurement, and a focus bell also ticks the session it closes and saves whatever is
typed as that project's next step. So answer your first bell when it actually rings.

Setup is done. You should not need this section again, except step 4 when a bell
moves (II, "Maintaining it").

---

# II. Running it

## What you have to remember

This is the whole list. The right-hand column is what prompts each one; the two with
nothing are unprompted by design (*hypomnemata › cue*).

| You do this | What prompts you |
|---|---|
| Open Cadence | The alarm, at every bell |
| Tick what you did | The item list, once the page is open |
| **Tap `+1 poured` when you pour** | Nothing ⚠️ |
| Capture a blocker on the TODO list, naming what it stops | Nothing ⚠️ |
| Answer the bell — resume line, stand, water | The alarm, and the button at the top of the page |
| Enter this morning's weight | It's an item in the morning block |
| Run the Examen | It's an item in the evening block |
| The Sunday sitting | Its calendar event |
| Pick a project when you start a focus session | Tap the focus item: it suggests the one furthest behind, and **Take this** makes it the plan. The closing bell records what you worked on and ticks the session |
| Capture an ad-hoc task ("I should sort out X") | Nothing ⚠️ — the Docket's TODO card, in your own words |
| Set the week's focus allocation | The weekly review |

**You run `/ordo` once on a normal day, at Lauds:** the "Sync the day" item, after
breakfast and before the first work session. It carries the calendar to the page and
the notifiers, and it can be run again whenever the calendar changes. Nothing else
needs a terminal: if you're opening one to tick a box, something has gone wrong. If one of the unprompted rows becomes a habit you keep
dropping, say so at a sitting and we change the design rather than your willpower.

## The Sunday sitting

On the calendar. Open Claude Code and run `/ordo weekly`, and `/ordo monthly`
when the docket shows it due. What each covers is in
`.claude/skills/ordo/SKILL.md`, not here.

## How you observe it

Four windows, in ascending order of how far back they see:

1. **Right now** — the page's Day view. What's in this block, what's blocked.
2. **This week** — the page's Week view, and beside it the Docket view.
3. **The weekly review** — `/ordo weekly`.
4. **The monthly backlog review** — `/ordo monthly`.

## Maintaining it

**The Rule is not in this repo.** It lives in the Cadence page's store, and `/ordo`
changes it there: it exports the store, makes the change, and sends only what
`tools/gate.py` lets through — the gate runs the compiler's refusals and the capacity
check, and writes the compiled Rule the page reads and a snapshot beside it. An open
page repaints when the write lands. No commit, no pull request, no republish
(*hypomnemata › record*).

Git holds the code: the page's source, the tools, the skill, the tradition registry.
A change to those is a reviewed diff, and the page is republished only then.

```
./tools/preflight.sh                  # all of the tests below; before any merge or publish
python3 -m unittest tools/test_*.py   # the rule, the notifiers, the loader, the gate — on tools/fixture/rule
python3 tools/sync_assets.py --check  # the pages carry the current shared files
python3 tools/sync_assets.py          # write those files into the pages
python3 tradition/check.py            # every cited source is registered
python3 tradition/check.py --strict   # ...and audited

# on an export of the store (ArtifactData, out_dir), as /ordo runs them:
ORDO_RULE=<dir> python3 tools/check_capacity.py   # no block asks for more minutes than it has
ORDO_RULE=<dir> python3 tools/rule.py             # each event: meeting or fixture, and why
ORDO_RULE=<dir> python3 tools/notifiers.py        # what the calendar and the phone should hold
python3 tools/gate.py <dir> --change <file> --versions <file> --out <batch dir>   # a checked change, as a batch; never into the export
```

| Cadence | Task |
|---|---|
| Weekly | The Sunday sitting |
| When the docket shows it due | Backlog review |
| Whenever something breaks | Capture it on the page as a TODO item that blocks what it stops (or tell `/ordo` at the desk); rescue what perishes today |
| Whenever the Rule changes | `/ordo` sends it to the store through the gate, then checks the notifiers — see below |
| Weekly, at the sitting | `/ordo weekly` keeps a snapshot of the Rule in the store, the last twelve |
| Daily, at Lauds, and whenever a fixture changes on either calendar | `/ordo`, the sync — see below |
| When a fixture's `until:` passes | Nothing. Its `until:` retires it on the page, and what it caused with it (`commitment:` on the items and variation), while the days it covered still show as they were run; its Cadence series end with it and no date of the usual bell is cancelled any more; on the phone, delete its alarm and tick the weekday back on the usual one (I.4) |
| Occasionally | Promote an un-audited source in `tradition/sources.yaml` before leaning on it |

**What no checker can see.** Fixture times live in Google's data, and the alarms on
the phone, so no check here can verify them. `/ordo` carries them, both ways, with
the calendar winning for fixtures: it reads the next 14 days of the calendar into
the store's `commitments` (a series by `weekday:`, a one-time fixture by `date:`),
through the gate, cancels the usual bell on each fixture date in the
window and checks the Cadence events against the rest (`SKILL.md`, "Sync"). It asks for directions when a fixture has
somewhere new to go, and it stops without writing when a day no longer fits.
The alarms stay yours: nothing can reach the Clock app. `tools/notifiers.py`, run on
an export as above, prints what the calendar and the phone should hold:

1. A new or changed fixture on the calendar → the Rule, then the derived events and
   alarms.
2. A changed bell, or a changed travel, prep, return or settle time → the bell's
   event, the leave-by event, and the alarm.
3. A new commitment that moves a bell → its "Leave for…" series, a series at the
   moved time on its schedule, the usual bell cancelled on each of its dates; on the
   phone, an alarm at the moved time on its weekday, and that weekday off the usual
   alarm (I.4).
4. A fixture ending → its `until:`, and the entry stays (what it caused goes with it
   on the page). Its series end with it and no date is cancelled after it, so Cadence
   is back with no step; the phone's alarms go back by hand (I.4).
5. Every event and every commitment is on the calendar first: the gate
   refuses a commitment with no `calendar_event:`.
6. A block's contents changing at a review → any event description that names them.

---

# III. Drinking and weight

The ration's *form* — a budget seen before the act, never a tally, and a surface that
never reacts to it — is the Rule's, and lives in *hypomnemata › count*. What follows is
the arithmetic behind its numbers, which is about a body and not about keeping a
rule. The numbers themselves are the keeper's own and live in the store, `rule/ledger ›
drink` and `rule/ledger › protein`; none is written here.

**Where to start.** Count the week as it is: nights drinking × drinks a night, in
standard drinks. NIAAA defines low-risk for men as **no more than 4 on any day *and*
no more than 14 per week** [NIAAA-PATTERNS], and 5 in about two hours is the binge
threshold, so a week can sit inside the weekly limit while touching the daily one
every time it drinks. A body-mass index is not by itself very informative for someone
who lifts.

**Why they're one problem.** A standard drink is roughly 110–140 kcal, so ten a
week is 1,100–1,400 kcal — about a third of a pound of fat, before anything else. The
bigger effect is indirect: alcohol is oxidized preferentially, suppressing fat
oxidation for hours [SILER-1999]; it degrades sleep; and it reliably arrives paired
with the comfort food. Cutting the heaviest night will usually do more for body fat
than adding a gym day.

**The ration.** The Rule takes *less* first — a real cut from where the count started,
not a fantasy. Its numbers are in `rule/ledger › drink` in the store. No stock in the
house: buy per occasion. The heaviest night is the target night.

**Protein.** Benefit for lean-mass retention plateaus around **1.6 g/kg/day**
[MORTON-2018]; the floor it sets is `rule/ledger › protein`, built at breakfast. A
modest deficit plus continued resistance training is the whole mechanism.

**The weigh-in, and why it is daily.** Body-fat % from a home scale is a bad
instrument measuring a stable quantity; bioimpedance swings with hydration. Body
weight is a good instrument measuring a noisy quantity: the scale is accurate to a
tenth of a pound, and a body moves two pounds a day on water, glycogen and sodium. The
mean of seven daily readings has roughly √7 — about two and a half times — less
standard error than one, so a week of dailies beats one careful weekly weighing.
Hence: daily, first thing and before breakfast, same hour and same state; the trend is
read at the weekly review.

More frequent self-weighing is *associated* with greater weight loss and with no
consistent adverse psychological effect [ZHENG-2015] — association, not effect: only
2 of its 17 studies had objective data. A reason to be unworried by a daily number,
not proof the number does the work.

*Two caveats, meant seriously.* Home body-fat measurements are unreliable enough that
chasing them will mislead you — track waist circumference and lifts instead. And a
deficit, a drink target and bloodwork are worth ten minutes with a doctor; this is the
literature, not medical advice.

---

# IV. The page and the calendars

Why there are three layers, and why the store is the system of record and the page
how it is engaged with: *hypomnemata › record*. The mechanics:

- **Offline, and on more than one device.** The page records to the device's local
  storage first. Each change is sent to the store as a patch — only what changed,
  a removed entry as a blank — and waits on the device until the store has taken it:
  it goes on the next save, when the page is hidden or closed, when the network comes
  back, and every 30 seconds after a failure. What shows is the store's copy,
  followed live, with this device's unsent changes over it, so the phone, the desk
  and the review's writes add up rather than replace one another. Drinks are kept as
  pours, so two devices' drinks add up too. Two devices changing the same entry keep
  whichever change reaches the store last. The merge is the store's own; the page
  adds none. After the page is republished, reload every open tab: an older page
  still writes whole days.
- **First open needs network** on a new device. The alarms don't.
- **A breakdown** is a TODO item that names what it blocks — captured on the
  page's TODO card like any other item and closed there. What it names is blocked while it
  is open, and the repair stands just before it in the work order, which is the triage.
- **The surface** is the shared shell: the day, with navigation beside it on a wide
  window (behind ☰ on the phone), and everything that used to be a modal — the bell,
  a row's input, a group's parts — as a card on the right. Where there is room
  (about 816px and up) the card sits beside the day; narrower, it slides over it,
  and on the phone it covers the day's whole width, the day untouchable under it
  until the card's × closes it. Nothing blocks the page to ask you something, and no
  card covers the toolbar or the departure strip. A departure sits in that strip,
  pinned under the day, so scrolling cannot lose it; it changes colour once you
  should have left, and goes when the fixture ends.

**The calendars.**

| | Holds | Notifies |
|---|---|---|
| **Your own calendar** | **Every fixture and meeting** — the classes, the game, the appointments; the trainer, the Sunday sitting, Sunday's leisure — with its location | Its own defaults |
| **`Cadence`** | No fixtures, no item lists | A **−10 min** alert on each bell's event (the warning bell; none at the hour, since the alarm is the bell), and **"Leave for…"** at each leave-by, which alerts twice: when prep starts, and when you leave |

Every Cadence time derives from the Rule. No event description carries
a list; an event points at the page, or tells you to leave.

---

# V. Map

| | |
|---|---|
| **Hypomnemata** | The notebook `.principal/notebook.json` names: the Rule's reasoning, requirements and traditions. The source of truth. The keeper's is private. |
| `.principal/` | `notebook.json`, the notebook the `principal` plugin's skills read and write; `bootstrap.json`, the manifest of what its bootstrap rounds built (their older pull requests are in a private repository). |
| `ordo.local.json` | Not committed: the link to your own Cadence page, `{"cadence": "<url>"}`, which `/ordo` reads. |
| `ti-esti.md` | The notebook's root question: what a rule is, and what keeping one requires. |
| **`README.md`** | This file. Setup, runbook, the arithmetic behind the drink and weight items, the page's mechanics. |
| **The store** | The Rule, and the record. The Cadence page's database: `rule/*`, `commitments`, `backlog`, `projects`, the TODO list (`todo`), `periodic`, the `days`, `snapshots`, `synclog`. The skill, "The Rule lives in the store", says what each holds. |
| **`web/cadence.html`** | The page's source. Published to the artifact; version-controlled here. It carries no copy of the Rule. Its token, layout and script blocks are generated from those files — edit those, never the page's copies. |
| **`web/tokens.css`** | Every colour and typeface, once. Pages carry inlined copies because an artifact is one file. |
| `web/layout.css` · `web/layout.js` | The application shell — toolbar, collapsible nav, content with a pinned footer, context cards. App-agnostic; talks to an app only through `Shell.mount`. |
| `web/layout-demo.html` | The shell's harness and its documentation. Exercises every mode; open it and drag the window edge. |
| *The blog layout* | Moved to the public [`natb1/blogs`](https://github.com/natb1/blogs) repo, as its `engine/`, beside the sites that use it. |
| `tools/preflight.sh` | Runs every check on the code. |
| `tools/ruledir.py` | Loads the Rule from an export of the store, strictly. Every tool reads the Rule through it. |
| `tools/compiler.py` | Compiles the Rule into what the page reads, and refuses what it cannot run. |
| `tools/gate.py` | The one way a change reaches the Rule: applies it to an export, runs the compiler and the capacity check, and writes the batch to send, with a snapshot. Also the weekly snapshot and a restore. |
| `tools/rule.py` | What a calendar event is to the day: a meeting or a fixture, computed from where it falls. |
| `tools/check_capacity.py` | Fails if a block asks for more minutes than it has, or if a fixture's derived times do not follow from its travel, prep and settle. A weekday whose fixture has an `until:` is checked with it and without it. |
| `tools/notifiers.py` | What the Clock alarms and the Cadence calendar should hold, derived from the Rule. |
| `tools/record.py` | The record gate: what `/ordo` writes to the record (`days`, `todo`, `periodic`, `synclog`), checked, as a pinned batch. |
| `tools/items.py` | The item contract: the shape of a `todo` or `periodic` document, which an owner outside this repository checks by too. |
| `tools/counts.py` | The horizon counts: what the record says against what was decided, at each stretch. |
| `tools/fixture/rule/` · `tools/fixture/record/` | An invented Rule and an invented record, for the tests only. Never updated to follow the store, and holding no one's data: `tools/test_fixture_public.py` keeps them to example values. |
| `tools/ruleyaml.py` | Loads `tradition/sources.yaml` strictly: a key given twice fails. |
| `tools/sync_assets.py` | Writes the shared files into the pages that declare them, and the derived dark block into `tokens.css`; `--check` fails if a copy is stale. |
| `.claude/skills/ordo/` | The `/ordo` skill — **executable**, not documentation. The procedure the notebook is the reasoning for. |
| `…/reference/blockers.md` | What a blocker is. Separate what perishes from what's broken. |
| **`tradition/sources.yaml`** | Every appeal to tradition, with audit status. |
| `tradition/check.py` | Fails if a cited key isn't registered, in any markdown file or in an export of the Rule. |

## Commands

The `/ordo` commands are listed at the top of `.claude/skills/ordo/SKILL.md`.

## Why not `/morning`

`anthropic-skills:morning` was considered as a base and rejected: it's a stateless
read surface over connected work tools, morning-only, with no notion of a rule to
adhere to or a transition between blocks. Its voice rules and its three-act day were
borrowed with thanks. The two compose — `/morning` answers *what is today*, this
answers *what now*.
