"""Unit tests for data module (market_data and feature_engineering).

Tests data fetching, caching, feature computation, and validation.
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data.market_data import MarketDataFetcher
from data.feature_engineering import FeatureEngineer


class MockAlpacaClient:
    """Mock Alpaca API client for testing."""
    
    def get_bars(self, symbol, timeframe, start=None, end=None, limit=None):
        """Return mock OHLCV data."""
        # Generate synthetic OHLCV data
        dates = pd.date_range(end='2024-01-31', periods=252)
        close_prices = np.random.normal(100, 10, 252).cumsum() + 100
        
        bars = []
        for i, date in enumerate(dates):
            bars.append({
                't': date,
                'o': close_prices[i] - np.random.rand() * 2,
                'h': close_prices[i] + np.random.rand() * 2,
                'l': close_prices[i] - np.random.rand() * 2,
                'c': close_prices[i],
                'v': np.random.randint(1000000, 10000000)
            })
        
        if limit:
            return bars[-limit:]
        if start and end:
            # Filter by date range
            start_date = pd.to_datetime(start)
            end_date = pd.to_datetime(end)
            return [b for b in bars if start_date <= b['t'] <= end_date]
        
        return bars


class TestMarketDataFetcher(unittest.TestCase):
    """Test cases for MarketDataFetcher."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = MockAlpacaClient()
        self.fetcher = MarketDataFetcher(self.mock_client)
    
    def test_initialization(self):
        """Test fetcher initialization."""
        self.assertIsNotNone(self.fetcher)
        self.assertIsNotNone(self.fetcher._data_cache)
        self.assertEqual(len(self.fetcher._data_cache), 0)
    
    def test_fetch_historical_success(self):
        """Test successful historical data fetch."""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 12, 31)
        
        df = self.fetcher.fetch_historical('SPY', start_date, end_date)
        
        self.assertIsInstance(df, pd.DataFrame)
        self.assertGreater(len(df), 0)
        self.assertIn('open', df.columns)
        self.assertIn('close', df.columns)
        self.assertIn('volume', df.columns)
    
    def test_fetch_historical_column_names(self):
        """Test that fetched data has correct columns."""
        df = self.fetcher.fetch_historical(
            'SPY',
            datetime(2023, 1, 1),
            datetime(2023, 12, 31)
        )
        
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            self.assertIn(col, df.columns, f"Missing column: {col}")
    
    def test_fetch_latest_single_symbol(self):
        """Test fetching latest data for single symbol."""
        result = self.fetcher.fetch_latest(['SPY'], limit=5)
        
        self.assertIn('SPY', result)
        self.assertIsInstance(result['SPY'], pd.DataFrame)
        self.assertLessEqual(len(result['SPY']), 5)
    
    def test_fetch_latest_multiple_symbols(self):
        """Test fetching latest data for multiple symbols."""
        symbols = ['SPY', 'QQQ', 'IWM']
        result = self.fetcher.fetch_latest(symbols, limit=10)
        
        for symbol in symbols:
            self.assertIn(symbol, result)
    
    def test_fetch_latest_caching(self):
        """Test that fetch_latest uses cache."""
        symbols = ['SPY']
        
        # First fetch
        result1 = self.fetcher.fetch_latest(symbols)
        
        # Second fetch (should use cache)
        result2 = self.fetcher.fetch_latest(symbols)
        
        # Results should be equal (cached)
        pd.testing.assert_frame_equal(result1['SPY'], result2['SPY'])
    
    def test_fetch_empty_symbols(self):
        """Test error handling for empty symbols list."""
        with self.assertRaises(ValueError):
            self.fetcher.fetch_latest([])
    
    def test_validate_data_success(self):
        """Test successful data validation."""
        df = self.fetcher.fetch_historical(
            'SPY',
            datetime(2023, 1, 1),
            datetime(2023, 12, 31)
        )
        
        is_valid = self.fetcher.validate_data(df, 'SPY')
        self.assertTrue(is_valid)
    
    def test_validate_data_empty(self):
        """Test validation fails for empty DataFrame."""
        df = pd.DataFrame()
        is_valid = self.fetcher.validate_data(df, 'SPY')
        self.assertFalse(is_valid)
    
    def test_validate_data_missing_column(self):
        """Test validation fails for missing required column."""
        df = pd.DataFrame({
            'open': [100, 101],
            'high': [102, 103],
            'low': [99, 100],
            'close': [100.5, 101.5]
            # Missing 'volume'
        })
        
        is_valid = self.fetcher.validate_data(df, 'SPY')
        self.assertFalse(is_valid)
    
    def test_clear_cache_all(self):
        """Test clearing all cache."""
        # Populate cache
        self.fetcher.fetch_latest(['SPY'])
        self.assertGreater(len(self.fetcher._data_cache), 0)
        
        # Clear cache
        self.fetcher.clear_cache()
        self.assertEqual(len(self.fetcher._data_cache), 0)
    
    def test_clear_cache_specific(self):
        """Test clearing specific symbol cache."""
        self.fetcher.fetch_latest(['SPY', 'QQQ'])
        initial_size = len(self.fetcher._data_cache)
        
        self.fetcher.clear_cache('SPY')
        
        # At least one entry should be removed
        self.assertLess(len(self.fetcher._data_cache), initial_size)


class TestFeatureEngineer(unittest.TestCase):
    """Test cases for FeatureEngineer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.engineer = FeatureEngineer()
        
        # Generate synthetic price data
        dates = pd.date_range('2023-01-01', periods=252)
        self.price_data = pd.DataFrame({
            'open': np.random.normal(100, 5, 252),
            'high': np.random.normal(102, 5, 252),
            'low': np.random.normal(98, 5, 252),
            'close': np.random.normal(100, 5, 252).cumsum() + 100,
            'volume': np.random.randint(1000000, 10000000, 252)
        }, index=dates)
        
        # Ensure high > low
        self.price_data['high'] = self.price_data[['open', 'high', 'close']].max(axis=1) + 1
        self.price_data['low'] = self.price_data[['open', 'low', 'close']].min(axis=1) - 1
    
    def test_initialization(self):
        """Test feature engineer initialization."""
        self.assertIsNotNone(self.engineer)
        self.assertEqual(self.engineer.volatility_window, 20)
    
    def test_compute_returns(self):
        """Test log returns computation."""
        returns = self.engineer.compute_returns(self.price_data['close'])
        
        self.assertIsInstance(returns, pd.Series)
        self.assertEqual(len(returns), len(self.price_data))
        # First return should be NaN (no previous day)
        self.assertTrue(np.isnan(returns.iloc[0]))
    
    def test_compute_returns_no_inf(self):
        """Test that returns contain no inf values."""
        returns = self.engineer.compute_returns(self.price_data['close'])
        
        self.assertFalse(np.isinf(returns).any())
    
    def test_compute_volatility(self):
        """Test rolling volatility computation."""
        returns = self.engineer.compute_returns(self.price_data['close'])
        volatility = self.engineer.compute_volatility(returns, window=20)
        
        self.assertIsInstance(volatility, pd.Series)
        self.assertEqual(len(volatility), len(returns))
        # All volatility values should be positive
        self.assertTrue((volatility >= 0).all() or volatility.isna().any())
    
    def test_compute_volatility_insufficient_data(self):
        """Test volatility computation with insufficient data."""
        short_returns = pd.Series([0.01, 0.02])
        volatility = self.engineer.compute_volatility(short_returns, window=20)
        
        self.assertIsInstance(volatility, pd.Series)
    
    def test_compute_trend_indicators(self):
        """Test trend indicator computation."""
        indicators = self.engineer.compute_trend_indicators(self.price_data)
        
        self.assertIsInstance(indicators, dict)
        self.assertIn('rsi', indicators)
        self.assertIn('macd', indicators)
        self.assertIn('sma_12', indicators)
    
    def test_compute_hmm_features(self):
        """Test HMM feature computation."""
        features = self.engineer.compute_hmm_features(self.price_data)
        
        self.assertIsInstance(features, pd.DataFrame)
        self.assertGreater(len(features), 0)
        self.assertIn('returns', features.columns)
        self.assertIn('volatility', features.columns)
        # Should have no NaN values after fill
        self.assertEqual(features.isnull().sum().sum(), 0)
    
    def test_compute_strategy_features(self):
        """Test strategy feature computation."""
        features = self.engineer.compute_strategy_features(self.price_data)
        
        self.assertIsInstance(features, pd.DataFrame)
        self.assertGreater(len(features), 0)
        self.assertIn('returns', features.columns)
        self.assertIn('volatility', features.columns)
        self.assertIn('rsi', features.columns)
    
    def test_validate_features_valid(self):
        """Test feature validation on valid data."""
        features = self.engineer.compute_hmm_features(self.price_data)
        is_valid, msg = self.engineer.validate_features(features)
        
        self.assertTrue(is_valid, f"Validation failed: {msg}")
    
    def test_validate_features_empty(self):
        """Test feature validation on empty DataFrame."""
        empty_df = pd.DataFrame()
        is_valid, msg = self.engineer.validate_features(empty_df)
        
        self.assertFalse(is_valid)
    
    def test_validate_features_nan(self):
        """Test feature validation detects NaN."""
        df = pd.DataFrame({'col1': [1.0, np.nan, 3.0]})
        is_valid, msg = self.engineer.validate_features(df)
        
        self.assertFalse(is_valid)
    
    def test_validate_features_inf(self):
        """Test feature validation detects infinite values."""
        df = pd.DataFrame({'col1': [1.0, np.inf, 3.0]})
        is_valid, msg = self.engineer.validate_features(df)
        
        self.assertFalse(is_valid)


class TestDataIntegration(unittest.TestCase):
    """Integration tests for data pipeline."""
    
    def test_data_to_features_pipeline(self):
        """Test complete pipeline from fetching to features."""
        mock_client = MockAlpacaClient()
        fetcher = MarketDataFetcher(mock_client)
        engineer = FeatureEngineer()
        
        # Fetch data
        price_data = fetcher.fetch_historical(
            'SPY',
            datetime(2023, 1, 1),
            datetime(2023, 12, 31)
        )
        
        # Compute features
        features = engineer.compute_hmm_features(price_data)
        
        # Validate
        is_valid, msg = engineer.validate_features(features)
        self.assertTrue(is_valid, f"Features invalid: {msg}")
        self.assertEqual(len(features), len(price_data))


if __name__ == '__main__':
    unittest.main()
