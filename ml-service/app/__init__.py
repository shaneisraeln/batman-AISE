"""Real ML inference service protected by BATMAN.

A genuine tabular binary classifier (Breast Cancer Wisconsin) served over HTTP.
This is the *protected model*, deliberately independent of BATMAN so that BATMAN
proxies to it exactly as it would any third-party ML API.
"""

__version__ = "1.0.0"
