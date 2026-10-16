"""
@what: VUS-PR (Volume Under the PR Surface), computed as TSB-AD computes it.

Source: TSB-AD, TSB_AD/evaluation/basic_metrics.py (basic_metricor:
range_convers_new, new_sequence, sequencing, RangeAUC_volume_opt), commit
6beac72, https://github.com/TheDatumOrg/TSB-AD. Apache License 2.0, a copy in
scripts/LICENSE-TSB-AD.

Changes from the source: plain functions instead of methods; only the PR part
is kept (the ROC volume is dropped); the average precision at every buffer is
returned, so one call gives VUS-PR at every L up to the largest (the AP at a
buffer does not depend on the largest buffer, so the mean over 0..L is what
RangeAUC_volume_opt returns for windowSize=L).

References:
    J. Paparrizos, P. Boniol, T. Palpanas, R. S. Tsay, A. Elmore, M. J. Franklin.
    Volume Under the Surface: A New Accuracy Evaluation Measure for Time-Series
    Anomaly Detection. PVLDB 15(11), 2022.

    Q. Liu, J. Paparrizos. The Elephant in the Room: Towards A Reliable
    Time-Series Anomaly Detection Benchmark. NeurIPS 2024 (Datasets and
    Benchmarks).
"""

import numpy as np


def range_convers_new(label):
    """Binary labels -> ordered list of (start, end) anomaly ranges, inclusive."""
    anomaly_starts = np.where(np.diff(label) == 1)[0] + 1
    anomaly_ends, = np.where(np.diff(label) == -1)
    if len(anomaly_ends):
        if not len(anomaly_starts) or anomaly_ends[0] < anomaly_starts[0]:
            # we started with an anomaly, so the start of the first anomaly is the start of the labels
            anomaly_starts = np.concatenate([[0], anomaly_starts])
    if len(anomaly_starts):
        if not len(anomaly_ends) or anomaly_ends[-1] < anomaly_starts[-1]:
            # we ended on an anomaly, so the end of the last anomaly is the end of the labels
            anomaly_ends = np.concatenate([anomaly_ends, [len(label) - 1]])
    return list(zip(anomaly_starts, anomaly_ends))


def new_sequence(label, sequence_original, window):
    a = max(sequence_original[0][0] - window // 2, 0)
    sequence_new = []
    for i in range(len(sequence_original) - 1):
        if sequence_original[i][1] + window // 2 < sequence_original[i + 1][0] - window // 2:
            sequence_new.append((a, sequence_original[i][1] + window // 2))
            a = sequence_original[i + 1][0] - window // 2
    sequence_new.append((a, min(sequence_original[len(sequence_original) - 1][1] + window // 2, len(label) - 1)))
    return sequence_new


def sequencing(x, L, window=5):
    label = x.copy().astype(float)
    length = len(label)

    for k in range(len(L)):
        s = L[k][0]
        e = L[k][1]

        x1 = np.arange(e + 1, min(e + window // 2 + 1, length))
        label[x1] += np.sqrt(1 - (x1 - e) / (window))

        x2 = np.arange(max(s - window // 2, 0), s)
        label[x2] += np.sqrt(1 - (s - x2) / (window))

    label = np.minimum(np.ones(length), label)
    return label


def range_ap_per_buffer(labels_original, score, windowSize, thre=250):
    """The range-based average precision at every buffer 0..windowSize.

    RangeAUC_volume_opt with the ROC part removed and the per-buffer AP
    returned instead of its mean.
    """
    window_3d = np.arange(0, windowSize + 1, 1)
    P = np.sum(labels_original)
    seq = range_convers_new(labels_original)
    l = new_sequence(labels_original, seq, windowSize)

    score_sorted = -np.sort(-score)

    ap_3d = np.zeros(windowSize + 1)

    tp = np.zeros(thre)
    N_pred = np.zeros(thre)

    for k, i in enumerate(np.linspace(0, len(score) - 1, thre).astype(int)):
        threshold = score_sorted[i]
        pred = score >= threshold
        N_pred[k] = np.sum(pred)

    for window in window_3d:

        labels_extended = sequencing(labels_original, seq, window)
        L = new_sequence(labels_extended, seq, window)

        TF_list = np.zeros((thre + 2, 2))
        Precision_list = np.ones(thre + 1)
        j = 0

        for i in np.linspace(0, len(score) - 1, thre).astype(int):
            threshold = score_sorted[i]
            pred = score >= threshold
            labels = labels_extended.copy()
            existence = 0

            for seg in L:
                labels[seg[0]:seg[1] + 1] = labels_extended[seg[0]:seg[1] + 1] * pred[seg[0]:seg[1] + 1]
                if (pred[seg[0]:(seg[1] + 1)] > 0).any():
                    existence += 1
            for seg in seq:
                labels[seg[0]:seg[1] + 1] = 1

            TP = 0
            N_labels = 0
            for seg in l:
                TP += np.dot(labels[seg[0]:seg[1] + 1], pred[seg[0]:seg[1] + 1])
                N_labels += np.sum(labels[seg[0]:seg[1] + 1])

            TP += tp[j]
            FP = N_pred[j] - TP

            existence_ratio = existence / len(L)

            P_new = (P + N_labels) / 2
            recall = min(TP / P_new, 1)

            TPR = recall * existence_ratio
            N_new = len(labels) - P_new
            FPR = FP / N_new

            Precision = TP / N_pred[j]

            j += 1
            TF_list[j] = [TPR, FPR]
            Precision_list[j] = Precision

        TF_list[j + 1] = [1, 1]  # otherwise, range-AUC will stop earlier than (1,1)

        width_PR = TF_list[1:-1, 0] - TF_list[:-2, 0]
        height_PR = Precision_list[1:]

        AP_range = np.dot(width_PR, height_PR)
        ap_3d[window] = AP_range

    return ap_3d


def vus_pr(label, score, buffers, thre=250):
    """VUS-PR at each buffer L in `buffers`: the mean range AP over buffers 0..L."""
    ap = range_ap_per_buffer(np.asarray(label).astype(int), np.asarray(score, dtype=float), max(buffers), thre)
    return {L: float(ap[:L + 1].mean()) for L in buffers}
