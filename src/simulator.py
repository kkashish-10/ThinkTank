import pandas as pd
from config.config import INITIAL_CAPITAL, MAX_DRAWDOWN, RISK_PER_TRADE

def simulate_trades(strategy, data, initial_capital=INITIAL_CAPITAL):
    capital = initial_capital
    position = 0
    entry_price = 0
    trades = []
    max_drawdown = 0
    peak_capital = capital

    for index, row in data.iterrows():
        signal = 1 if isinstance(row['Signal'], (int, float)) and pd.notna(row['Signal']) and row['Signal'] == 1 else 0

        if position == 0 and signal == 1:  # Buy
            risk_amount = capital * RISK_PER_TRADE
            shares = risk_amount / row['Close']
            position = shares
            entry_price = row['Close']
            capital -= risk_amount  # Reserve for risk

        elif position > 0:
            stop_loss = entry_price * (1 - strategy.stop_loss_pct)
            take_profit = entry_price * (1 + strategy.take_profit_pct)

            if row['Low'] <= stop_loss:  # Stop loss hit
                exit_price = stop_loss
                capital += position * exit_price
                trades.append({'type': 'sell', 'price': exit_price, 'shares': position, 'pnl': (exit_price - entry_price) * position})
                position = 0
            elif row['High'] >= take_profit:  # Take profit hit
                exit_price = take_profit
                capital += position * exit_price
                trades.append({'type': 'sell', 'price': exit_price, 'shares': position, 'pnl': (exit_price - entry_price) * position})
                position = 0

        # Check drawdown
        if capital > peak_capital:
            peak_capital = capital
        drawdown = (peak_capital - capital) / peak_capital
        if drawdown > max_drawdown:
            max_drawdown = drawdown
        if drawdown > MAX_DRAWDOWN:
            break  # Stop trading

    # Close any open position at end
    if position > 0:
        exit_price = data.iloc[-1]['Close']
        capital += position * exit_price
        trades.append({'type': 'sell', 'price': exit_price, 'shares': position, 'pnl': (exit_price - entry_price) * position})

    total_pnl = sum(trade['pnl'] for trade in trades)
    return {'final_capital': capital, 'total_pnl': total_pnl, 'trades': trades, 'max_drawdown': max_drawdown}