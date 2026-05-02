import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockLatestBarRequest
from config.config import API_KEY, API_SECRET

def fetch_historical_data(symbol, period='1y', interval='1d'):
    """
    Fetch historical stock data using yfinance.
    For live data, switch to Alpaca API.
    """
    data = yf.download(symbol, period=period, interval=interval)
    data = data.reset_index()
    data = data.drop_duplicates('Date')
    data.index = data['Date']
    data = data[['Open', 'High', 'Low', 'Close', 'Volume']]
    return data

def fetch_real_time_data(symbol):
    """
    Fetch real-time stock data using Alpaca API.
    Returns the latest bar data as a DataFrame.
    """
    client = StockHistoricalDataClient(API_KEY, API_SECRET)
    request = StockLatestBarRequest(symbol_or_symbols=[symbol])
    response = client.get_stock_latest_bar(request)
    
    if symbol not in response:
        raise ValueError(f"No data found for symbol {symbol}")
    
    bar = response[symbol]
    data = pd.DataFrame({
        'Date': [bar.timestamp],
        'Open': [bar.open],
        'High': [bar.high],
        'Low': [bar.low],
        'Close': [bar.close],
        'Volume': [bar.volume]
    })
    data.index = data['Date']
    return data