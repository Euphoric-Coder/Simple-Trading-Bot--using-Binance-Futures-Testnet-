python bot.py ping
python bot.py symbols
python bot.py order --symbol BTCUSDT --side BUY  --type MARKET --quantity 0.001
python bot.py order --symbol BTCUSDT --side SELL --type LIMIT  --quantity 0.001 --price 85000 --timeInForce GTC
# Bonus: Stop-Limit (STOP) and Stop-Market
python bot.py order --symbol BTCUSDT --side SELL --type STOP --quantity 0.001 --price 84000 --stopPrice 84500 --timeInForce GTC
python bot.py order --symbol BTCUSDT --side SELL --type STOP_MARKET --quantity 0.001 --stopPrice 84500
# Query/cancel
python bot.py status --symbol BTCUSDT --orderId 123456789
python bot.py cancel --symbol BTCUSDT --orderId 123456789
