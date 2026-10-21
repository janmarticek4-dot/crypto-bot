"""Research only. Closed informative candles are shifted by Freqtrade merge.
No live-trading entrypoint is provided. Compare components before combined rules.
"""
from freqtrade.strategy import IStrategy, informative
from pandas import DataFrame
import talib.abstract as ta


class TrendComponent(IStrategy):
    INTERFACE_VERSION=3
    timeframe='4h'
    can_short=False
    startup_candle_count=220
    minimal_roi={"0":100.0}  # No fixed profit-taking at 10–30%.
    stoploss=-.20
    trailing_stop=False
    process_only_new_candles=True
    use_exit_signal=True

    @informative('1d')
    def populate_indicators_1d(self, dataframe:DataFrame, metadata:dict)->DataFrame:
        dataframe['ema50']=ta.EMA(dataframe,timeperiod=50)
        dataframe['ema200']=ta.EMA(dataframe,timeperiod=200)
        return dataframe

    def populate_indicators(self,dataframe:DataFrame,metadata:dict)->DataFrame:
        for n in (20,50,100,200):dataframe[f'ema{n}']=ta.EMA(dataframe,timeperiod=n)
        dataframe['rsi']=ta.RSI(dataframe)
        dataframe['adx']=ta.ADX(dataframe)
        dataframe['atr']=ta.ATR(dataframe)
        dataframe['hist']=ta.MACD(dataframe)['macdhist']
        dataframe['rvol']=dataframe['volume']/dataframe['volume'].shift(1).rolling(20).mean()
        dataframe['support']=dataframe['low'].shift(1).rolling(20).min()
        dataframe['broken']=(dataframe['close']<dataframe['support']) & (dataframe['close'].shift(1)<dataframe['support'].shift(1))
        return dataframe

    def populate_entry_trend(self,dataframe:DataFrame,metadata:dict)->DataFrame:
        signal=(dataframe['close']>dataframe['ema200']) & (dataframe['ema20']>dataframe['ema50']) & (dataframe['hist']>0) & (dataframe['volume']>0)
        dataframe.loc[signal,['enter_long','enter_tag']]=(1,'trend')
        return dataframe

    def populate_exit_trend(self,dataframe:DataFrame,metadata:dict)->DataFrame:
        signal=dataframe['broken'] & (dataframe['rvol']>=1.5) & (dataframe['close']<dataframe['ema50_1d']) & (dataframe['hist']<0)
        dataframe.loc[signal,['exit_long','exit_tag']]=(1,'protective_breakdown')
        return dataframe


class PullbackComponent(TrendComponent):
    def populate_entry_trend(self,dataframe:DataFrame,metadata:dict)->DataFrame:
        signal=(dataframe['close']>dataframe['ema200_1d']) & dataframe['rsi'].between(40,60) & (dataframe['rsi'].shift(1)<40) & (dataframe['hist']>0) & (dataframe['rvol']>=1.1) & (dataframe['volume']>0)
        dataframe.loc[signal,['enter_long','enter_tag']]=(1,'pullback')
        return dataframe


class CombinedStrategy(TrendComponent):
    def populate_entry_trend(self,dataframe:DataFrame,metadata:dict)->DataFrame:
        score=((dataframe['close']>dataframe['ema50']) & (dataframe['ema20']>dataframe['ema50'])).astype(int)
        score+=(dataframe['close']>dataframe['ema200_1d']).astype(int)
        score+=((dataframe['hist']>0) & dataframe['rsi'].between(40,68)).astype(int)
        score+=(dataframe['rvol']>=1.1).astype(int)
        score+=((dataframe['close'].rolling(5).min()>dataframe['close'].shift(5).rolling(5).min()) & (dataframe['close'].rolling(5).max()>dataframe['close'].shift(5).rolling(5).max())).astype(int)
        score+=(dataframe['adx']>=20).astype(int)
        # Net return and risk include conservative 0.2% per-side extra costs.
        entry=dataframe['close'];stop=dataframe['support']-1.5*dataframe['atr']
        target=dataframe['high'].shift(1).rolling(20).max()
        factor=(1-.012)/(1+.012)
        gain=target/entry*factor-1;loss=1-stop/entry*factor
        signal=(score>=5) & (gain>=.03) & (gain/loss>=1.5) & (dataframe['volume']>0)
        dataframe.loc[signal,['enter_long','enter_tag']]=(1,'combined')
        return dataframe
