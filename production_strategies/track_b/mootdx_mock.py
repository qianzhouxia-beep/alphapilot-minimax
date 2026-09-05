# -*- coding: utf-8 -*-
"""
mootdx_mock.py -- Offline mock of mootdx Quotes for tests.

Mimics mootdx.quotes.Quotes.factory(market='std', multithread=True)
and the client.transaction(symbol=...) API. Not used in production.
"""
import random

try:
    import pandas as pd
except ImportError:
    pd = None


class _MockTransactionClient(object):
    """Single client object mimicking mootdx Quotes client."""

    def __init__(self, rng=None):
        self._rng = rng or random.Random(42)

    def transaction(self, symbol=None, date=None):
        if pd is None:
            return None
        if date is not None:
            # mootdx history transaction not supported -> empty
            return pd.DataFrame(columns=["time", "price", "vol", "num",
                                         "buyorsell", "volume"])
        rng = self._rng
        n = rng.randint(200, 800)
        rows = []
        for i in range(n):
            hh = rng.randint(9, 14)
            mm = rng.randint(0, 59)
            ss = rng.randint(0, 59)
            t = "%02d:%02d" % (hh, mm)
            price = round(10.0 + rng.random() * 40.0, 2)
            vol = rng.randint(1, 500)
            # mostly 0/1 (active buy/sell), occasional 2 (neutral), 8 (auction)
            r = rng.random()
            if r < 0.55:
                bs = 0
            elif r < 0.92:
                bs = 1
            elif r < 0.97:
                bs = 2
            else:
                bs = 8
            rows.append([t, price, vol, rng.randint(1, 50), bs, vol])
        cols = ["time", "price", "vol", "num", "buyorsell", "volume"]
        return pd.DataFrame(rows, columns=cols)


class _MockQuotes(object):
    """Mimics mootdx Quotes.factory()"""

    _instances = {}

    @classmethod
    def factory(cls, market="std", multithread=False):
        key = market
        if key not in cls._instances:
            cls._instances[key] = _MockTransactionClient()
        return cls._instances[key]
