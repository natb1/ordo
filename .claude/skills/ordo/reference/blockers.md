# Blockers: when something breaks

Procedure for a TODO item that names what it stops: a `todo/<id>` document in the
store whose `blocks` names it (the skill, "The Rule lives in the store"; `inbox` is the
list's old collection and is read by nothing). The reasoning is hypomnemata › breakdown
and › undertaking.

## Is it even a breakdown?

Most missed tasks are not. Apply one test:

> **If you went and did it right now, would it work?**

**Yes, and you didn't** → a **lapse**. No item, no edge, nothing on the TODO list. It is
logged as an event and that is the end of it.
**No — something is broken, missing or unavailable** → a **breakdown**.

The obstacle has to be *outside you*. Not wanting to is a lapse; the machine being
dead is a breakdown. Filing a lapse as a breakdown to stop it counting is the failure
mode this test exists to prevent, and it is an easy one to fall into honestly.

**Breakdowns that need no item:**

- **Fixed on the spot** — nothing to capture. The TODO list wants work, not a ceremony.
- **Blocking nothing** — a split hose in December blocks a garden item winter already
  takes off the page. An ordinary TODO item, with no edge.

## What a breakdown is

A TODO item, and not a kind of its own: a TODO item that **blocks** something
recurring — an Office item, a periodic item (the washer of the laundry), a fixture
(the car of tomorrow's appointment). The edge does everything a ticket once did:

- **Blocked, not missed.** What the item names is blocked, never missed, for as long as the
  item is open. It does not count against adherence or against the backlog gate's
  four-week criterion. A breakdown must never be able to close the gate on a goal —
  that would make a failed appliance into a reason you don't get to learn guitar.
- **Urgency.** The item takes the tier and the rank of what it stops and stands just
  before it in the work order, the two drawn as bound. One that stops an Office item
  stands at that item's next day on the page — a daily one's is today; a blocker of
  Tuesday's trash stands at Tuesday — and the item it stops keeps its row, blocked
  and not missed. A periodic item has no slot of its own: it waits past its due date
  while blocked — blocked, not overdue — just after its repair. A fixture's blocker
  stands at the fixture's next day. The work order is the whole of it: nothing lends
  a repair a slot.
- **Capture on the phone,** as an ordinary TODO item that names what it stops —
  there is no separate breakdown form — because the block has to start the moment
  you notice or the blocked item logs as missed all week.

There is no triage sitting and no Saturday reserve. The work order is the triage;
Saturday afternoon is a focus slot like any other.

## First, the thing that is not obvious

**Separate what is perishing from what is broken.** They almost always have
different clocks, and conflating them is what makes a breakdown feel urgent for days
when the urgent part lasted an hour.

A washer that won't drain is not urgent. A wet load sitting in standing water is —
mildew in roughly a day. Get the clothes out and dried elsewhere and the emergency is
over; what remains is an ordinary scheduled repair. Same shape for a dead freezer
(the food is urgent, the appliance is not), a leak (the water is urgent, the pipe can
wait for a plumber), a car that won't start (tomorrow's commitment is urgent, the car
is not).

So the perishable part is a **second TODO item, due today**, separate from
the repair. Ask it first, every time: **what is actually on a clock here?** Usually it
is small, and rescuing it buys back all of the pressure.

Note what isn't asked: how annoying it is, and how much you want to fix it right
now. Both are strong signals and neither is about priority.

## The timebox

A repair is a gated activity — see hypomnemata › breakdown and › gated. Absorbing,
unbounded, and the "almost done" feeling peaks exactly when you should stop. Any
TODO item that blocks something recurring gets one (`rule/policy › todo.timebox`):

- **25 minutes per diagnostic session.** The bell applies. Exit rite at the bell.
- **Two sessions maximum**, then escalate.
- At each bell, say one of three things out loud: **resolved** / **money problem** /
  **back to the sort**.

**"This is a money problem, not a time problem" is a legitimate and usually correct
answer**, and after two sessions it is the default rather than a concession. The
Rule does not require you to be your own repairman — Benedict gives the monastery a
cellarer [RB-31] rather than expecting each monk to fix the plumbing. A weekend spent
on a repair a professional resolves in an hour is not thrift.

## Closing one

Mark it done on the page. Or, told at the desk, close it through the record gate,
never by hand: a `close` fact to `tools/record.py`, and only the batch it prints is
sent (the skill, "Writing the record"). That one fact closes the `todo/<id>` item and,
where a `breakdowns/<id>` entry is still open, that entry too. It is closed when the
store's result confirms the write, and not before. No retrospective, no note about how
long it took.

If the same thing breaks a third time, that is not a breakdown any more — it is a
standing condition, and it belongs in the backlog as "replace the washer," with a
cue, a slot and a cost like anything else.

## Sources

> Registry keys: [RB-31] [RB-32] [MARCUS-5.20] [SENECA-PREMEDITATIO]
> [RUSSELL-VINSEL-2016] [EPICTETUS-ENCH-1] — full entries in `tradition/sources.yaml`.
>
> Note on [MARCUS-5.20]: the familiar "what stands in the way becomes the way" is
> Hays's 2002 phrasing, not a literal translation. Cite it as his.
