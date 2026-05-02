import pandas as pd
import numpy as np

class BaseStrategy:
    def __init__(self, stop_loss_pct=0.02, take_profit_pct=0.04):
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct

    def generate_signals(self, data):
        raise NotImplementedError

class MovingAverageCrossover(BaseStrategy):
    def generate_signals(self, data):
        data['SMA_short'] = data['Close'].rolling(window=20).mean()
        data['SMA_long'] = data['Close'].rolling(window=50).mean()
        data['Signal'] = -1
        data.loc[pd.notna(data['SMA_short']) & pd.notna(data['SMA_long']) & (data['SMA_short'] > data['SMA_long']), 'Signal'] = 1
        return data

class RSIOversoldBounce(BaseStrategy):
    def generate_signals(self, data):
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        data['RSI'] = 100 - (100 / (1 + rs))
        data['Signal'] = 0
        data.loc[pd.notna(data['RSI']) & (data['RSI'] < 30), 'Signal'] = 1
        data.loc[pd.notna(data['RSI']) & (data['RSI'] > 70), 'Signal'] = -1
        return data

class BollingerBandsSqueeze(BaseStrategy):
    def generate_signals(self, data):
        data['SMA'] = data['Close'].rolling(window=20).mean()
        data['STD'] = data['Close'].rolling(window=20).std()
        data['Upper'] = data['SMA'] + 2 * data['STD']
        data['Lower'] = data['SMA'] - 2 * data['STD']
        data['Signal'] = 0
        data.loc[pd.notna(data['Upper']) & (data['Close'] > data['Upper']), 'Signal'] = 1
        data.loc[pd.notna(data['Lower']) & (data['Close'] < data['Lower']), 'Signal'] = -1
        return data

class MACDSignalCrossover(BaseStrategy):
    def generate_signals(self, data):
        exp1 = data['Close'].ewm(span=12).mean()
        exp2 = data['Close'].ewm(span=26).mean()
        data['MACD'] = exp1 - exp2
        data['Signal_Line'] = data['MACD'].ewm(span=9).mean()
        data['Signal'] = -1
        data.loc[pd.notna(data['MACD']) & pd.notna(data['Signal_Line']) & (data['MACD'] > data['Signal_Line']), 'Signal'] = 1
        return data

class MeanReversion(BaseStrategy):
    def generate_signals(self, data):
        data['SMA'] = data['Close'].rolling(window=20).mean()
        data['STD'] = data['Close'].rolling(window=20).std()
        data['Upper'] = data['SMA'] + 2 * data['STD']
        data['Lower'] = data['SMA'] - 2 * data['STD']
        data['Signal'] = 0
        data.loc[pd.notna(data['Upper']) & (data['Close'] < data['Lower']), 'Signal'] = 1
        data.loc[pd.notna(data['Lower']) & (data['Close'] > data['Upper']), 'Signal'] = -1
        return data