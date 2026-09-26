import os
import tempfile

import numpy as np
import pytest


@pytest.fixture
def tmp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def reference():
    from sklearn.datasets import load_digits

    return load_digits().data.astype(float)[:200]
