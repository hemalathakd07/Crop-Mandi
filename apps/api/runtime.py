"""Runtime paths for the API. Tests may monkeypatch these."""

from pathlib import Path

from cropmandi.config import ROOT

COFFEE_CSV_PATH = ROOT / "data" / "experimental" / "coffee_weekday_sessions.csv"
EXPERIMENT_COMPARISON_PATH = ROOT / "ml" / "experiments" / "model_comparison.json"
COFFEE_XLSX_NAME = "karnataka_daily_coffee_prices_7years.xlsx"
COFFEE_MARKET_XLSX_NAME = "coffee_market_price.xlsx"
PEPPER_MARKET_XLSX_NAME = "pepper_market_price.xlsx"
COFFEE_MARKET_XLSX_PATH = ROOT / COFFEE_MARKET_XLSX_NAME
PEPPER_MARKET_XLSX_PATH = ROOT / PEPPER_MARKET_XLSX_NAME
