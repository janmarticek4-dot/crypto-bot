"""Diagnostic ablation only: original entries/hard stop, no protective signal exit."""
from ActiveBullrun import TrendComponent


class LegacyNoProtectiveExit(TrendComponent):
    def populate_exit_trend(self, dataframe, metadata):
        dataframe['exit_long']=0
        return dataframe
