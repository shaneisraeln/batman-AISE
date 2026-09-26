import numpy as np

from batman.features.behavioral import (
    FEATURE_ORDER,
    duplicate_and_unique_ratios,
    prediction_entropy,
    query_similarity,
)
from batman.features.extractor import FeatureExtractor
from batman.features.session import SessionStore


def test_feature_vector_matches_order():
    store = SessionStore()
    session = store.get("s")
    session.record(ts=0.0, input_vec=np.array([1.0, 2.0, 3.0]))
    feats = FeatureExtractor().extract(np.array([[1.0, 2.0, 3.0]]), session, now=1.0)
    vec = feats.vector()
    assert vec.shape[0] == len(FEATURE_ORDER)


def test_duplicate_ratio_detects_repeats():
    cur = np.array([1.0, 1.0])
    recent = [np.array([1.0, 1.0]), np.array([1.0, 1.0])]
    dup, uniq = duplicate_and_unique_ratios(cur, recent)
    assert dup > 0.5
    assert uniq < 0.5


def test_unique_ratio_high_for_diverse():
    cur = np.array([9.0, 9.0])
    recent = [np.array([1.0, 2.0]), np.array([3.0, 4.0])]
    dup, uniq = duplicate_and_unique_ratios(cur, recent)
    assert uniq == 1.0
    assert dup == 0.0


def test_query_similarity_nan_safe():
    cur = np.array([1.0, np.nan])
    recent = [np.array([1.0, 1.0])]
    assert query_similarity(cur, recent) == 0.0


def test_prediction_entropy():
    assert prediction_entropy(np.array([1.0, 0.0, 0.0])) == 0.0
    assert prediction_entropy(np.array([0.5, 0.5])) == 1.0
    assert prediction_entropy(None) == 0.0
