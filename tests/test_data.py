import numpy as np
import pandas as pd

from auditlens.data import _numeric_value, _publication_date


def test_numeric_value_matches_period_across_datetime_precisions():
    column = np.datetime64("2024-12-31", "us")
    frame = pd.DataFrame([[123.0]], index=["Total Revenue"], columns=[column])
    value = _numeric_value(frame, ("Total Revenue",), pd.Timestamp("2024-12-31"))
    assert value == 123.0


def test_publication_date_uses_reported_date_before_fallback():
    dates = pd.DatetimeIndex(["2025-03-20", "2025-04-30"])
    publication_date, source = _publication_date(pd.Timestamp("2024-12-31"), dates, 150, 120)
    assert publication_date == pd.Timestamp("2025-03-20")
    assert source == "reported_earnings_date"
