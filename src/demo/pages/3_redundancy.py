"""Redundancy: why stacking the top-ranked detectors fails.

The spine of the demo. Three claims, one per tab, each ending in a table you
can click into so the reader checks it on the data rather than taking it.

"Regret" is the decision-theory term for what a selection rule leaves against
the best choice in hindsight. It is the right word for the paper and the wrong
word for a screen, so the columns here read "left on the table".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import (
    MIN_COVERAGE,
    benchmark_label,
    current_benchmark,
    is_tsb_ad,
    cached_combo_detectors,
    cached_combos,
    cached_heuristics,
    cached_pair_agreement,
    chart_selection,
    combo_datasets,
    get_parser,
    goto_workbench,
    page_header,
    ranked,
    set_scores,
    solo_scores,
    table_selection,
    takeaway,
    vus_buffer_selector,
)

KIND = "uni"
SHORTLIST = 5          # how many detectors a person would plausibly try
TABLE_ROWS = 15

RULE_LABELS = {
    "best": "Best pair (exhaustive)",
    "top_k": "Top-k by solo VUS",
    "least_corr": "Least correlated",
    "least_corr_top10": "Least correlated, top-10 only",
    "max_coverage": "Max coverage (greedy)",
}

page_header("🔁 Redundancy", "Why does stacking the top-ranked detectors fail?")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Reading selection rules ...")
def rule_picks(kind: str, buffer: int, k: int) -> pd.DataFrame:
    """What each selection rule picked on each series, and what it scored."""
    table = cached_heuristics(kind)
    if table.empty:
        return pd.DataFrame()
    block = table[(table.buffer == buffer) & (table.k == k)].copy()
    block["heuristic"] = block.heuristic.astype(str)
    return block


@st.cache_data(show_spinner="Correlating shortlists ...")
def shortlist_agreement(kind: str, buffer: int, threshold: float,
                        shortlist: int) -> pd.DataFrame:
    """Per series: do the detectors you would shortlist agree with each other?

    `rho_top` is the mean Spearman among the top-N by solo VUS, `rho_all` the
    mean over every pair. The gap between them is the finding: redundancy is
    concentrated in the detectors worth shortlisting, which is exactly where it
    costs you.

    `effective` walks the shortlist best-first and keeps a detector only when
    its correlation with everything already kept stays below the threshold --
    "you shortlisted 5, you have 2".
    """
    pairs = cached_pair_agreement(kind)
    solo = solo_scores(kind, buffer)
    if pairs.empty or solo.empty:
        return pd.DataFrame()

    rank = dict(zip(solo.filename + "|" + solo.detector, solo["rank"]))
    pairs = pairs[["filename", "detector_a", "detector_b", "spearman"]].dropna()
    rank_a = (pairs.filename + "|" + pairs.detector_a).map(rank)
    rank_b = (pairs.filename + "|" + pairs.detector_b).map(rank)
    pairs = pairs.assign(rank_a=rank_a, rank_b=rank_b).dropna(subset=["rank_a", "rank_b"])

    rho_all = pairs.groupby("filename", observed=True).spearman.mean()
    top = pairs[(pairs.rank_a <= shortlist) & (pairs.rank_b <= shortlist)]
    rho_top = top.groupby("filename", observed=True).spearman.mean()

    # Greedy distinct-count over the shortlist, best first.
    effective = {}
    for filename, block in top.groupby("filename", observed=True):
        rho = {}
        for a, b, value in zip(block.detector_a, block.detector_b, block.spearman):
            rho[(a, b)] = rho[(b, a)] = value
        order = (solo[solo.filename == filename]
                 .nsmallest(shortlist, "rank").detector.tolist())
        kept = []
        for detector in order:
            if all(rho.get((detector, other), 0.0) < threshold for other in kept):
                kept.append(detector)
        effective[filename] = len(kept)

    table = pd.DataFrame({"rho_top": rho_top, "rho_all": rho_all}).dropna()
    table["effective"] = pd.Series(effective)
    table["shortlist"] = shortlist
    return table.reset_index()


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

if not is_tsb_ad():
    st.info(
        f"Redundancy is read from the exhaustive search over every pair and "
        f"triplet of detectors, which has been run on TSB-AD only. Switch the "
        f"benchmark to TSB-AD in the sidebar to see it. "
        f"(Current: {benchmark_label(current_benchmark())}.)"
    )
    st.stop()

buffer = vus_buffer_selector()
with st.sidebar:
    k = st.radio("Combination size", [2, 3], horizontal=True,
                 help="Every combination of this many detectors was scored "
                      "exhaustively. k=4 is 27,405 per series and is not "
                      "computed yet.")
    threshold = st.slider(
        "Same-behaviour threshold (rho)", 0.3, 0.95, 0.7, 0.05,
        help="Two detectors count as one option when their scores correlate "
             "above this. The count depends on where you draw the line, so "
             "the line is yours to move.",
    )

picks = rule_picks(KIND, buffer, k)
solo = solo_scores(KIND, buffer)

if picks.empty or solo.empty:
    st.info(
        "No step-3/step-4 output yet. Run `src/divergence/run_step3_all.sh` "
        "then `src/divergence/run_step4_all.sh`."
    )
    st.stop()

best_solo = solo.groupby("filename", observed=True).vus.max()
wide = picks.pivot_table(index="filename", columns="heuristic",
                         values="vus", observed=True)
wide = wide.join(best_solo.rename("best_solo"), how="inner")

# ---------------------------------------------------------------------------
# The claim
# ---------------------------------------------------------------------------

columns = st.columns(4)
columns[0].metric("Best single detector", f"{wide.best_solo.mean():.3f}")
if "top_k" in wide:
    columns[1].metric(
        f"Top-{k} by solo VUS", f"{wide.top_k.mean():.3f}",
        delta=f"{wide.top_k.mean() - wide.best_solo.mean():+.3f} vs single")
columns[2].metric(
    f"Best {k}-set (exhaustive)", f"{wide.best.mean():.3f}",
    delta=f"{wide.best.mean() - wide.best_solo.mean():+.3f} vs single")
if "top_k" in wide:
    loses = float((wide.top_k < wide.best_solo).mean())
    columns[3].metric(f"Top-{k} loses to one detector", f"{100 * loses:.1f}%",
                      help="Share of series where adding the second-ranked "
                           "detector made the result worse.")

summary = []
for rule in ["best", "top_k", "least_corr_top10", "max_coverage", "least_corr"]:
    if rule not in wide:
        continue
    summary.append({
        "Selection rule": RULE_LABELS[rule],
        "Mean VUS": wide[rule].mean(),
        "Gain over best single": (wide[rule] - wide.best_solo).mean(),
        "Left on the table": (wide.best - wide[rule]).mean(),
        "Wins outright": float((wide[rule] >= wide.best - 1e-9).mean()),
    })
st.dataframe(
    pd.DataFrame(summary), hide_index=True, width='stretch',
    column_config={
        "Mean VUS": st.column_config.NumberColumn(format="%.3f"),
        "Gain over best single": st.column_config.NumberColumn(
            format="%+.3f", help="What combining bought, against just using "
                                 "the best single detector."),
        "Left on the table": st.column_config.NumberColumn(
            format="%.3f", help="VUS the exhaustive winner got that this rule "
                                "did not. 'Regret' in the paper."),
        "Wins outright": st.column_config.NumberColumn(
            format="percent", help="Share of series where this rule found the "
                                   "exhaustive winner."),
    },
)
st.caption(
    f"{len(wide)} series at L={buffer}, k={k}. Every rule here is an oracle -- "
    "scored with the labels it was selected on -- so these are upper bounds, "
    "which is what makes the top-k row damning rather than merely poor."
)

why, pays, use = st.tabs(["Why it fails", "When it pays", "What to use"])

# ---------------------------------------------------------------------------
# Why it fails
# ---------------------------------------------------------------------------

with why:
    agreement = shortlist_agreement(KIND, buffer, threshold, SHORTLIST)
    if agreement.empty:
        st.info("No pair agreement table yet.")
    else:
        left, right = st.columns([2, 3])
        with left:
            st.metric(f"Mean rho among the top {SHORTLIST}",
                      f"{agreement.rho_top.mean():.3f}")
            st.metric("Mean rho over all pairs", f"{agreement.rho_all.mean():.3f}")
            st.metric(f"Effective options out of {SHORTLIST}",
                      f"{agreement.effective.mean():.1f}")
            st.caption(
                "Detectors in general disagree. The ones worth shortlisting "
                "agree with each other, which is why a shortlist of five is "
                "not five options."
            )
        with right:
            figure = go.Figure()
            for name, values, color in (
                (f"Top {SHORTLIST} by VUS", agreement.rho_top, "#d62728"),
                ("All pairs", agreement.rho_all, "#4C78A8"),
            ):
                figure.add_trace(go.Box(
                    y=values, name=name, boxpoints="all", jitter=0.5, pointpos=0,
                    marker=dict(size=3, opacity=0.4, color=color),
                    line=dict(width=1.4, color=color), fillcolor="rgba(0,0,0,0.05)",
                    showlegend=False,
                ))
            figure.update_layout(
                height=380, margin=dict(l=60, r=20, t=20, b=40),
                yaxis=dict(title="Spearman between detector scores"),
                font=dict(size=13),
            )
            st.plotly_chart(figure, width='stretch')

        st.subheader("Series where your shortlist collapses")
        st.caption(
            f"Ranked by agreement among the top {SHORTLIST}. Click one to see "
            "all five drawn on top of each other."
        )
        collapse = (agreement.sort_values("rho_top", ascending=False)
                    .head(TABLE_ROWS)
                    .assign(amplification=lambda f: f.rho_top - f.rho_all))
        event = st.dataframe(
            collapse[["filename", "rho_top", "rho_all", "amplification", "effective"]],
            hide_index=True, width='stretch', on_select="rerun",
            selection_mode="single-row", key="rd_collapse",
            column_config={
                "filename": st.column_config.TextColumn("Series", width="medium"),
                "rho_top": st.column_config.NumberColumn(
                    f"rho, top {SHORTLIST}", format="%.3f"),
                "rho_all": st.column_config.NumberColumn("rho, all pairs", format="%.3f"),
                "amplification": st.column_config.NumberColumn(
                    "Amplification", format="%+.3f",
                    help="How much more the shortlisted detectors agree than "
                         "detectors in general on this series."),
                "effective": st.column_config.NumberColumn(
                    "Effective options", format="%d",
                    help=f"Distinct behaviours among the top {SHORTLIST} at "
                         f"rho < {threshold}."),
            },
        )
        rows = table_selection(event)
        if rows:
            filename = collapse.iloc[rows[0]].filename
            shortlisted = (solo[solo.filename == filename]
                           .nsmallest(SHORTLIST, "rank").detector.tolist())
            goto_workbench(filename, detectors=shortlisted)

# ---------------------------------------------------------------------------
# When it pays
# ---------------------------------------------------------------------------

with pays:
    bins = [0, 0.5, 0.7, 0.9, 1.01]
    names = ["below 0.5", "0.5 - 0.7", "0.7 - 0.9", "above 0.9"]
    binned = wide.assign(
        band=pd.cut(wide.best_solo, bins=bins, labels=names, right=False),
        gain=wide.best - wide.best_solo,
    )
    grouped = binned.groupby("band", observed=True)
    profile = pd.DataFrame({
        "series": grouped.size(),
        "gain": grouped.gain.mean(),
        "relative": grouped.apply(
            lambda block: (block.gain / block.best_solo.clip(lower=1e-9)).mean(),
            include_groups=False),
    }).reset_index()

    left, right = st.columns([3, 2])
    with left:
        figure = go.Figure(go.Bar(
            x=profile.band.astype(str), y=profile.gain, marker_color="#2b8a3e",
            text=[f"+{value:.3f}" for value in profile.gain], textposition="outside",
            hovertemplate="%{x}<br>+%{y:.3f} VUS<extra></extra>",
        ))
        figure.update_layout(
            height=360, margin=dict(l=60, r=20, t=20, b=60),
            xaxis=dict(title="How strong the best single detector is"),
            yaxis=dict(title="Gain from the best pair"), font=dict(size=13),
        )
        st.plotly_chart(figure, width='stretch')
    with right:
        st.dataframe(
            profile, hide_index=True, width='stretch',
            column_config={
                "band": "Best single",
                "series": st.column_config.NumberColumn("Series", format="%d"),
                "gain": st.column_config.NumberColumn("Mean gain", format="%+.3f"),
                "relative": st.column_config.NumberColumn(
                    "Relative", format="percent",
                    help="Gain as a share of what the single detector already got."),
            },
        )
        weak = binned[binned.best_solo < 0.7]
        st.caption(
            f"{100 * len(weak) / len(binned):.1f}% of series have a best single "
            f"detector below 0.7. Those are the ones where a second detector "
            f"earns its runtime."
        )

    st.subheader(f"Series where picking by rank costs the most")
    st.caption(
        "The gap between the exhaustive best and what ranking would have "
        "picked. Click one to see both pairs drawn together."
    )
    if "top_k" in wide:
        cost = (wide.assign(cost=wide.best - wide.top_k)
                .sort_values("cost", ascending=False).head(TABLE_ROWS).reset_index())
        picked = picks.set_index(["filename", "heuristic"]).detectors
        cost["best_set"] = [picked.get((f, "best"), "") for f in cost.filename]
        cost["top_set"] = [picked.get((f, "top_k"), "") for f in cost.filename]
        event = st.dataframe(
            cost[["filename", "best_solo", "top_k", "best", "cost",
                  "top_set", "best_set"]],
            hide_index=True, width='stretch', on_select="rerun",
            selection_mode="single-row", key="rd_cost",
            column_config={
                "filename": st.column_config.TextColumn("Series", width="medium"),
                "best_solo": st.column_config.NumberColumn("Best single", format="%.3f"),
                "top_k": st.column_config.NumberColumn(f"Top-{k}", format="%.3f"),
                "best": st.column_config.NumberColumn("Best set", format="%.3f"),
                "cost": st.column_config.NumberColumn("Cost of ranking", format="%+.3f"),
                "top_set": "What ranking picked",
                "best_set": "What actually wins",
            },
        )
        rows = table_selection(event)
        if rows:
            row = cost.iloc[rows[0]]
            top_pair = [m for m in str(row.top_set).split("|") if m]
            best_pair = [m for m in str(row.best_set).split("|") if m]
            # Both pairs' members, and both pairs' averaged scores. The averaged
            # score is what the VUS in this table was computed on, so without
            # those two rows the reader is looking at the ingredients and being
            # asked to trust the number.
            goto_workbench(
                row.filename,
                detectors=list(dict.fromkeys(top_pair + best_pair)),
                combos=[top_pair, best_pair],
            )

# ---------------------------------------------------------------------------
# What to use
# ---------------------------------------------------------------------------

with use:
    meta = get_parser(KIND).meta.reset_index()[["filename", "dataset", "entity_type"]]
    sets = set_scores(KIND, buffer, k)
    if sets.empty:
        st.info(f"No {k}-set scores yet.")
    else:
        types = meta[["filename", "entity_type"]]
        sets = sets.merge(types, on="filename", how="left")
        singles = solo.merge(types, on="filename", how="left")

        left, right = st.columns(2)
        # Page 5 opens on whatever scope was last looked at here, so the advice
        # a reader leaves with is the advice they were just reading.
        dataset_scope = left.selectbox(
            "Dataset", ["All datasets"] + sorted(sets.dataset.unique()),
            key="scope_dataset")
        type_scope = right.selectbox(
            "Entity type", ["All types"] + sorted(sets.entity_type.dropna().unique()),
            key="scope_type")

        def scope(frame: pd.DataFrame) -> pd.DataFrame:
            if dataset_scope != "All datasets":
                frame = frame[frame.dataset == dataset_scope]
            if type_scope != "All types":
                frame = frame[frame.entity_type == type_scope]
            return frame

        scoped, scoped_singles = scope(sets), scope(singles)

        if scoped.empty:
            st.info("No series match that scope.")
        else:
            # The baseline has to be fixed too. "Use KShapeAD + MatrixProfile on
            # Medical" is one choice applied to every Medical series, so it is
            # measured against one detector applied to every Medical series --
            # not against the best-detector-per-series oracle, which nobody can
            # pick in advance and which would make every recommendation look bad.
            single_board = (ranked(scoped_singles, "detector", ["vus"])
                            .sort_values("vus", ascending=False))
            if single_board.empty:
                st.info("No detector covers enough of this scope.")
                st.stop()
            baseline_name = single_board.index[0]
            baseline_vus = float(single_board.vus.iloc[0])

            best_per_series = scoped.groupby("filename", observed=True).vus.max()
            scoped = scoped.assign(
                shortfall=best_per_series.reindex(scoped.filename).to_numpy() - scoped.vus,
                win=lambda f: (f.shortfall < 1e-9).astype(float),
            )
            board = (ranked(scoped, "combination", ["vus", "shortfall", "win"])
                     .assign(gain=lambda f: f.vus - baseline_vus)
                     .reset_index())
            # Sorted by gain, not by wins: this tab answers "what should I run",
            # and a set that wins most often can still lose to one detector --
            # on Medical the most frequent winner is 0.106 VUS *behind* running
            # the best single alone.
            board = board.sort_values("gain", ascending=False).head(TABLE_ROWS)

            if board.empty:
                st.info(f"No {k}-set is scored on enough of this scope.")
                st.stop()

            headline = st.columns(3)
            headline[0].metric(f"Best single here", f"{baseline_vus:.3f}",
                               help=str(baseline_name))
            headline[1].metric(f"Best {k}-set here", f"{board.vus.iloc[0]:.3f}",
                               delta=f"{board.gain.iloc[0]:+.3f} vs single",
                               help=str(board.combination.iloc[0]))
            headline[2].metric("Series in scope", f"{scoped.filename.nunique():,}")
            runners = ", ".join(
                f"{name} {value:.3f}"
                for name, value in single_board.vus.iloc[1:3].items())
            st.caption(
                f"Best single detector for this scope: **{baseline_name}** "
                f"({baseline_vus:.3f}). Next: {runners} -- when those are close, "
                f"the choice of single detector barely matters and the {k}-set "
                f"is doing the work."
            )

            event = st.dataframe(
                board[["combination", "gain", "win", "shortfall", "vus", "coverage"]],
                hide_index=True, width='stretch', on_select="rerun",
                selection_mode="single-row", key="rd_board",
                column_config={
                    "combination": st.column_config.TextColumn(
                        f"{k} detectors", width="medium"),
                    "win": st.column_config.NumberColumn(
                        "Wins", format="percent",
                        help=f"Share of series where this is the best of all "
                             f"{scoped.combination.nunique():,} {k}-sets."),
                    "gain": st.column_config.NumberColumn(
                        "Gain over best single", format="%+.3f",
                        help=f"Against always running {baseline_name} alone on "
                             "this scope. Negative means the single detector "
                             "wins and the second one is not worth its runtime."),
                    "shortfall": st.column_config.NumberColumn(
                        "Left on the table", format="%.3f",
                        help="Mean VUS behind the best set for each series. "
                             "Lower is safer: what you give up by always using "
                             "this one."),
                    "vus": st.column_config.NumberColumn("Mean VUS", format="%.3f"),
                    "coverage": st.column_config.NumberColumn(
                        "Coverage", format="percent",
                        help="Share of the scope's series where this is a "
                             "genuine set -- no member emits a constant score "
                             f"there. Sets below {MIN_COVERAGE:.0%} are hidden."),
                },
            )
            spans = scoped.dataset.nunique() > 1
            st.caption(
                ("Every dataset counts once: averaged within each dataset, then "
                 "across them, so the recommendation is not just a "
                 "recommendation for YAHOO and UCR, which are 56% of the "
                 "benchmark's series."
                 if spans else
                 f"Plain mean over the {scoped.filename.nunique()} series of "
                 f"{dataset_scope}.")
                + " Sorted by gain over the best single detector."
            )
            rows = table_selection(event)
            if rows:
                combination = board.iloc[rows[0]].combination
                here = scoped[scoped.combination == combination]
                target = here.loc[here.vus.idxmax()]
                members = combination.split(" + ")
                goto_workbench(target.filename, detectors=members,
                               combos=[members])

takeaway(
    "Do not stack the leaderboard. Combine when your best single detector is "
    "below 0.7, and start from the pairs above."
)
