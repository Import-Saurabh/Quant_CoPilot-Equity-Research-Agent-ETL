from etl.pipeline import run_pipeline


def execute_pipeline(symbol: str):
    symbol = symbol.strip().upper()

    if not symbol:
        raise ValueError("Ticker symbol cannot be empty")

    run_pipeline(symbol)

    return {
        "status": "success",
        "symbol": symbol,
        "message": f"Pipeline executed successfully for {symbol}"
    }