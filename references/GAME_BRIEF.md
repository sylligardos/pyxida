# Needle: game design brief

Working title: Needle. Tagline: "Can you find what the detectors cannot?"

Brief written for the ICDE 2027 demo, October 2026. Pasteable into a design
tool as is. See also the Pyxida demo (src/demo) which stays separate.

## What it is

A browser game played at a conference booth. The player sees a real time
series from a public anomaly detection benchmark, with no labels. They mark
where they think the anomalies are. Then the game reveals the ground truth and
what a team of state-of-the-art detectors flagged, and scores both. The series
are chosen so that some are trivial, some are solved only by a few detectors,
and some are solved by none. The hidden purpose is to learn whether the
unsolved cases are visible to a human at all. Every play is logged anonymously
for later analysis, but the analysis is not part of the game.

## Audience and context

Researchers and engineers at a database conference. They walk up, play for two
to three minutes, and leave. Primary device is a laptop with a trackpad or
mouse, often mirrored on a large screen behind the booth. Touch support is a
bonus, not a requirement. No account, no login, no personal data. A player may
enter a nickname for the leaderboard.

## Tone

Data forward and calm. The time series is the hero and takes most of the
screen. Minimal chrome, no decorative illustration, no mascots. Confident,
slightly playful copy. It should feel like a precise instrument that happens to
be fun, not a casual mobile game. Works in both light and dark, dark preferred
on the booth screen.

## Flow

Five screens.

### 1. Start

Title, one sentence of what to do, a "Play" button, and a one-line notice that
plays are logged anonymously for research. Optional nickname field. A small
live counter: "N plays so far, humans found X% of the anomalies the detectors
missed."

### 2. Round

One series at a time, six per round. The chart fills the width. Above it, a
thin progress strip showing position in the round, such as 3 of 6. Below it, a
short instruction: "Drag over the regions you think are anomalous."

Controls: drag on the chart to create a highlighted range, drag the edges of a
range to adjust it, click a small x on a range to remove it, scroll or pinch to
zoom, drag the axis to pan, a "Reset view" button. Two primary actions:
"Nothing here" and "Submit". The player can mark up to five ranges. No timer by
default, but a small elapsed-time indicator is fine.

No hints about where the anomaly is: no vertical gridlines aligned with it, no
axis labels that leak dataset names, no series title that reveals the source.
Show only a neutral id such as "Series 14" and the number of points.

### 3. Reveal

Same chart, now with three layers the player can toggle: the ground-truth
anomaly as a shaded band, the player's ranges in one color, and the detectors'
ranges in another. Underneath the chart, a thin strip showing the detectors'
raw anomaly score as a sparkline, so the player can see where the machines were
suspicious.

A compact score card: hits and false alarms for the player, hits and false
alarms for the detectors, and a verdict line such as "You found it, the
detectors did not" or "Nobody found this one" or "This window had no anomaly".

Then one required tap, three buttons: "I see it now", "I still cannot see it",
"I think something else is the anomaly". Only after the tap does "Next" become
active. If the player picks "something else", keep their ranges highlighted so
it is clear which region they mean.

### 4. Round summary

Total score for the player versus the detectors across the six series, shown
side by side. A row of six small thumbnails of the series, each marked found,
missed, or false alarm, for the player and for the detectors. A line that tells
the player which difficulty tiers they met: "You played 2 easy, 2 medium,
1 unsolved, 1 decoy." Buttons: "Play again" and "Leaderboard".

### 5. Leaderboard

Top nicknames by score, the detectors shown as a fixed reference entry in the
list, and the aggregate line from the start screen. This screen should look
good left idle on the booth monitor.

## Scoring

The design should make this legible. A hit is a player range that overlaps a
labeled anomaly. A false alarm is a player range that overlaps nothing. Each
hit is plus one, each false alarm is minus one, a decoy left unmarked is plus
one. The detectors are scored the same way with the same number of flagged
points as the player, taken from the top of their anomaly score, so the
comparison is fair and the rule fits in one sentence.

## Opponent

A team of five named detectors, shown as five small chips on the reveal screen
with the ones that caught the anomaly lit up. The exact five may change
(Shapley top five against the oracle, or per-series best detector, to be
decided from the results), so the design should not hard-code names or count.

## Content constraints

Series are between one thousand and about ten thousand points; the chart must
render and brush smoothly at that size. Values are shown on a plain numeric
axis. Some rounds are decoys with no anomaly at all. Anomalies may be a single
point or a long segment, so ranges must be creatable at both scales, with zoom
to help on single points.

## States to design

Loading a series, a round with zero ranges marked, maximum ranges reached, a
reveal where the anomaly is a single point, a reveal for a decoy, an empty
leaderboard, and a narrow window where the chart has to shrink.

## Out of scope

Multivariate series, user accounts, the research analysis dashboard, and any
detector configuration.
