// The "?" popups: what each page shows and how it is computed. Mechanisms
// only, never findings. One entry is a term and one or two sentences;
// [n] marks point at the citations below. The Needle screens read the same
// text through /api/help.

export type HelpEntry = { term: string; text: string; cites?: number[] };
export type HelpSection = { title: string; entries: HelpEntry[] };

export const CITES: Record<number, { label: string; url?: string }> = {
  1: { label: "Paparrizos, Boniol, Palpanas, Tsay, Elmore, Franklin. Volume Under the Surface: A New Accuracy Evaluation Measure for Time-Series Anomaly Detection. PVLDB 15(11), 2022.", url: "https://doi.org/10.14778/3551793.3551830" },
  2: { label: "Boniol, Paparrizos, Palpanas. VUS: Effective and Efficient Accuracy Measures for Time-Series Anomaly Detection. The VLDB Journal, 2025." },   // TODO link: add the DOI once checked
  3: { label: "Blondel, Guillaume, Lambiotte, Lefebvre. Fast unfolding of communities in large networks. J. Stat. Mech., 2008.", url: "https://doi.org/10.1088/1742-5468/2008/10/P10008" },
  4: { label: "Wu, Keogh. Current Time Series Anomaly Detection Benchmarks are Flawed and are Creating the Illusion of Progress. IEEE TKDE 35(3), 2023.", url: "https://arxiv.org/abs/2009.13807" },
  5: { label: "Vigna. A weighted correlation index for rankings with ties. WWW 2015.", url: "https://doi.org/10.1145/2736277.2741088" },
};

export const HELP: Record<string, HelpSection[]> = {
  "/graph": [{
    title: "The graph",
    entries: [
      { term: "A dot", text: "One series of the benchmark. Click it to see it with its neighbours; double-click opens it in the Workbench." },
      { term: "A link", text: "Two series whose detectors agree. Each series has a profile: the score of every detector on it, by the chosen metric. The link weight is the covariance of the two profiles, and only the ten strongest positive links of each series are kept." },
      { term: "Position", text: "A force layout of those links: linked series pull together, the rest drift apart. Distances are suggestive, not measured. Only the links mean something." },
      { term: "Neighbourhood", text: "A Louvain community of the graph: a group of series more linked to each other than to the rest, named by the detector that wins most often inside it.", cites: [3] },
      { term: "Metric", text: "Which score builds the profiles: AUC-PR or VUS-PR. Switching it rebuilds the graph.", cites: [1, 2] },
    ],
  }],
  "/explore": [
    {
      title: "Landscape",
      entries: [
        { term: "A point", text: "One series, placed at the score of the best detector on it, or at the mean of the top five scores when that option is on." },
        { term: "A box", text: "One dataset or entity type: the box spans the middle half of its series, the line is the median, the whiskers the rest. Boxes are sorted by their median, hardest on the left." },
        { term: "Metric", text: "AUC-PR, or VUS-PR with a buffer of 10 points around every labelled anomaly.", cites: [1, 2] },
      ],
    },
    {
      title: "Rankings",
      entries: [
        { term: "Solves", text: "A detector solves a series when its score is within the gap of the best score on that series. The gap is the first picker; the current value is shown next to it." },
        { term: "Nobody", text: "Nobody solves a series when its best score is under the floor, the second picker." },
        { term: "The histogram", text: "Series grouped by how many detectors solve them, plus the nobody group. Click a bar to look at that group below." },
        { term: "The boxplot", text: "Every detector's scores over the series of the group, best median first. Under it, how many series of the group each detector solves." },
      ],
    },
    {
      title: "Redundancy",
      entries: [
        { term: "A square", text: "How much two detectors agree, averaged over the series in scope. Agreement on one series is the weighted Kendall tau of their two score curves, so the points they rank on top count most. 0 is unrelated, 1 identical.", cites: [5] },
        { term: "Stacking", text: "The top k detectors by rank, averaged point by point, scored like one detector. Compared against the single best and against the best k-set found by trying every set, which is an upper bound reached with hindsight, not a method." },
        { term: "Scope", text: "The whole benchmark or one dataset. The exhaustive search exists for TSB-AD univariate only." },
      ],
    },
  ],
  "/workbench": [{
    title: "The workbench",
    entries: [
      { term: "A lane", text: "One detector's score on this series, min-max scaled to 0 to 1 over the whole series, time aligned with the series above. The yellow band is the labelled anomaly." },
      { term: "Top detectors", text: "The lanes shown are the best N on this series by the chosen metric. Pins add detectors on top and follow you from series to series." },
      { term: "I'm feeling lucky", text: "Eight one-line detectors run in the browser on this series: the absolute first difference, its local z-score, a rolling std, the raw value, its global and local z-scores, a rolling min, and a flat-segment score. Wu and Keogh used one-liners like these to argue that benchmark anomalies are often trivial. Their threshold is dropped; AUC-PR scores the ranking instead. k is the window of the rolling ones.", cites: [4] },
      { term: "AUC while lucky", text: "The one-liners are scored by AUC-PR only, so the page switches every lane to AUC-PR while they are shown, to compare like with like." },
    ],
  }],
  "/game": [{
    title: "The game",
    entries: [
      { term: "The opponent", text: "One detector per series: the one with the highest VUS-PR on that series in the benchmark, out of every detector that was run. You go up against the best there is for that series.", cites: [1, 2] },
      { term: "Its flags", text: "The opponent flags every point where its score rises above a threshold set on that score alone: its mean plus three standard deviations over the window, computed when the series is scored, the same for every detector and every series. Nothing is tuned per detector. Your marks and its flags are judged the same way." },
      { term: "A series", text: "A hit is a labelled anomaly that a mark touches, a false alarm a mark that touches none, a clean decoy a series with no anomaly left unmarked. A mark wider than a tenth of the window is a false alarm whatever it covers." },
      { term: "Round points", text: "A series adds +1 to the round when hits beat false alarms, −1 when they don't, 0 when nothing happened, for you and for the opponent alike. Ten series make a round." },
      { term: "Difficulty", text: "Easy: six easy series, two medium, two decoys, 60 seconds each. Normal: three easy, three medium, two unsolved, two decoys, 45 seconds. Hard: two medium, six unsolved, two decoys, 30 seconds. A series is easy when most detectors reach a VUS-PR of 0.5 on it, unsolved when none does." },
    ],
  }],
};
