"""Detection metrics.

Binary framing: an event is "suspicious" if its ground-truth label is not
NORMAL. A detector prediction is "flagged" if it would result in a non-ALLOW
action (or an anomaly/extraction score over threshold, depending on baseline).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Metrics:
    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def fpr(self) -> float:
        d = self.fp + self.tn
        return self.fp / d if d else 0.0

    @property
    def tpr(self) -> float:
        # True-positive rate is identical to recall; exposed explicitly so
        # reports can list TPR/FPR as a pair.
        return self.recall

    @property
    def tnr(self) -> float:
        d = self.tn + self.fp
        return self.tn / d if d else 0.0

    @property
    def accuracy(self) -> float:
        # Classification accuracy. NOTE: this is NOT F1. Kept distinct on purpose.
        total = self.tp + self.fp + self.tn + self.fn
        return (self.tp + self.tn) / total if total else 0.0

    def confusion_matrix(self) -> dict:
        """2x2 confusion matrix with explicit cell names (suspicious = positive)."""
        return {
            "true_positive": self.tp,
            "false_negative": self.fn,
            "false_positive": self.fp,
            "true_negative": self.tn,
        }

    def to_dict(self) -> dict:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "true_positive_rate": round(self.tpr, 4),
            "false_positive_rate": round(self.fpr, 4),
            "true_negative_rate": round(self.tnr, 4),
            "classification_accuracy": round(self.accuracy, 4),
            "confusion_matrix": self.confusion_matrix(),
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
        }


def compute_metrics(y_true_suspicious: list[bool], y_pred_flagged: list[bool]) -> Metrics:
    tp = fp = tn = fn = 0
    for truth, pred in zip(y_true_suspicious, y_pred_flagged):
        if truth and pred:
            tp += 1
        elif truth and not pred:
            fn += 1
        elif not truth and pred:
            fp += 1
        else:
            tn += 1
    return Metrics(tp=tp, fp=fp, tn=tn, fn=fn)
