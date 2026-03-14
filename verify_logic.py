import sys
import pandas as pd
from pathlib import Path

# Setup paths specifically for WSL
wsl_root = Path("/home/bnm54/strategy-mining")
sys.path.insert(0, str(wsl_root))

from config.config import PARQUET_DIR
import pyarrow.parquet as pq

# Load engine functions
from data.processor import merge_market_data
from engine.backtest import (
    calculate_tva_state,
    calculate_price_zone,
    _enrich,
    detect_group_sequence
)
from config.sentiment_layers import SentimentLayerSystem

def load_stock(stock_id="2330"):
    df = merge_market_data(stock_id)
    return _enrich(df)

def main():
    stock_id = "2330"
    df = load_stock(stock_id)
    print(f"Loaded {stock_id} data: {len(df)} rows.")
    
    # 1. T/V/A States
    tva = calculate_tva_state(df["Close"])
    
    # 2. Price Zones
    pz = calculate_price_zone(df["Close"], window=250)
    
    # 3. Sentiment Layers
    sys_sentiment = SentimentLayerSystem()
    sentiment = sys_sentiment.create_sentiment_layer_series(df["margin_balance"], df["Volume"], df["Close"])
    
    # 4. M-Class (e.g. Foreign buy, Margin drop)
    m_class = detect_group_sequence(df["foreign_net"], df["margin_balance"].diff(), 3, 5, 0.7)
    
    # Combine into a view for the last 20 days
    view = pd.DataFrame({
        "Close": df["Close"],
        "TVA State (1-8)": tva,
        "Price Zone (0-4)": pz,
        "Sentiment Layer": sentiment,
        "M-Class Trigger (A/B)": m_class
    }).tail(20)
    
    print("\n=== Verification Report for 2330 (Last 20 Days) ===")
    print(view.to_string())

if __name__ == "__main__":
    main()
