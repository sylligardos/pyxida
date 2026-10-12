# Needle: design handoff

Visual design for the Needle game described in `../GAME_BRIEF.md` (ICDE 2027 demo).
The live canvas is https://claude.ai/artifact/16NM4KwNBF3vA4h2VFNbsf (private to the
owner). The files in `project/` are a snapshot of it from 2026-10-10.

The files are design comps, not production code. Each `*.dc.html` file is one screen in
a small template format (`{{hole}}` bindings, `<sc-for>`, `<sc-if>`, `<dc-import>`),
with a `renderVals()` block that holds the sample data. Use them for layout, copy,
colours and type. Do not ship them. All series in them are synthetic, made by
`Chart.dc.html`.

## What is final

The arcade direction is the one to build. Use these screens, in flow order:

| Screen | File |
| --- | --- |
| 1. Start (attract mode) | `project/MainArcade2.dc.html` |
| 2. Round | `project/RoundArcade.dc.html` |
| 3. Reveal | `project/RevealArcade.dc.html` |
| 4. Round summary | `project/SummaryArcade.dc.html` |
| 5. Leaderboard | `project/LeaderboardArcade.dc.html` |
| Shared series chart | `project/Chart.dc.html` (`theme="arcade"`) |

The states from the brief are the same screens with a different setting:

| State | File | Setting |
| --- | --- | --- |
| Loading a series | `StateLoading` | Round, `loading` |
| Zero ranges marked | `StateEmpty` | Round, `marks=0` |
| Five ranges, the maximum | `StateMax` | Round, `marks=5` |
| Reveal, single-point anomaly | `StatePoint` | Reveal, `variant=point` |
| Reveal, decoy | `StateDecoy` | Reveal, `variant=decoy` |
| Empty leaderboard | `StateBoardEmpty` | Leaderboard, `empty` |
| Narrow window (760 px) | `StateNarrow` | Round at 760 px wide |

Light mode exists only for the Start screen (`project/MainLight.dc.html`). It shows
the light direction; the other screens have no light version yet.

The archive is not to be built: `MainArcade.dc.html` (alternative Start), and
`Main`, `Round`, `Reveal` (the first, calm direction).

## Design rules

- **Words:** say "detectors", never "CPU". The detectors are a team of five
  named detectors, but the screens must not hard-code the names or the count.
- **Colour roles**, kept the same on every screen:

  | Role | Dark | Light |
  | --- | --- | --- |
  | Background | `#0B0A1F` with a 24 px dot grid | `#FBF7EF` with a dot grid |
  | Chart screen | `#07061A`, border `#2C2754` | `#FFFFFF`, 3 px `#17132E` border, offset shadow |
  | Panels | `#15132E`, border `#2C2754` | `#FFFFFF`, 3 px border, offset shadow |
  | Text | `#F4F1FF`, secondary `#C9C3E6` / `#A9A2D4` | `#17132E`, secondary `#3D3863` / `#5B5680` |
  | Player | magenta `#FF3D9A` | `#D6136F` |
  | Detectors | cyan `#22D3EE` | teal `#0E7490` |
  | Labeled anomaly, actions | yellow `#FFE14D` | yellow `#FFD60A` as a fill, never as text |

- **Type:** Bungee for display (title, verdicts, scores, buttons), Space Grotesk for
  body text, Space Mono for numbers and labels. All three are on Google Fonts.
- **Primary button:** yellow, with dark text and a solid 6 px drop below. In light
  mode it is dark, with yellow text and a magenta drop.
- **Chart while marking (Round):** strong highlights. Player ranges get a solid
  edge, a top bar, a number tag, drag handles and a remove (×) button. There are
  horizontal gridlines only, so nothing lines up with the anomaly, and no series
  title. A "Map" strip under the chart shows the zoomed window.
- **Chart on Reveal:** soft highlights, so the series stays readable while the
  player answers. Fills are about half as strong, edges are thin, tags are outlined,
  and there are no scanlines. The labeled anomaly is a yellow dashed band, player
  ranges are magenta, and the detectors' flags are cyan bars at the bottom. A
  detector score strip sits under the chart.
- **Summary card per series:**
  - **Result banner:** YOU WIN (magenta), DETECTORS WIN (cyan), TIE · BOTH FOUND
    IT (near-white bar with a magenta and a cyan diamond) or TIE · NOBODY FOUND IT
    (dim).
  - **Winner's row:** tinted and outlined. The loser's row fades.
  - **Totals:** computed from the cards.
- **Result marks, everywhere:** a filled diamond is found or left clean, a hollow
  diamond is missed, a flat bar is a false alarm. On the leaderboard, a
  magenta diamond is a series the player won, an outlined one a tie, a cyan one a
  series the detectors won.

## Placeholders

`[NAME]`, `[N]` plays, `[X]%`, `[score]` and `[s]` (the detectors' reference score)
are to be filled from real data. The leaderboard nicknames and scores, the detector
names on Reveal, and all series are samples.

## Open design items

- A Reveal and summary card for series with several labeled anomalies. The chart
  draws only one band, the verdicts are all-or-nothing, and the summary has no
  "2 of 3" result.
- Light mode for screens 2 to 5.
- Motion: none is designed (series transitions, reveal, score count-up).
