from src.data_fetcher import fetch_historical_data
from src.strategies import MovingAverageCrossover, RSIOversoldBounce, BollingerBandsSqueeze, MACDSignalCrossover, MeanReversion
from src.simulator import simulate_trades
from config.config import SYMBOLS

def run_backtest():
    strategies = [
        MovingAverageCrossover(),
        RSIOversoldBounce(),
        BollingerBandsSqueeze(),
        MACDSignalCrossover(),
        MeanReversion()
    ]

    for symbol in SYMBOLS:
        data = fetch_historical_data(symbol)
        for strategy in strategies:
            data_with_signals = strategy.generate_signals(data.copy())
            result = simulate_trades(strategy, data_with_signals)
            print(f"Symbol: {symbol}, Strategy: {strategy.__class__.__name__}")
            print(f"Final Capital: ${result['final_capital']:.2f}, Total P&L: ${result['total_pnl']:.2f}, Trades: {len(result['trades'])}, Max Drawdown: {result['max_drawdown']:.2%}")
            print("---")

if __name__ == "__main__":
    run_backtest()