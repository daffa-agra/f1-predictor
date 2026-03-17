import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import RandomizedSearchCV, train_test_split
from sklearn.metrics import mean_squared_error
from f1_predictor.data_fetcher import fetch_race_results, fetch_qualifying_results, fetch_historical_data
from f1_predictor.preprocessor import FeatureProcessor
from f1_predictor.model import ModelPipeline
import fastf1
from datetime import datetime
import joblib

def get_completed_season_data(year):
    """Identify and fetch all completed race data for the current season."""
    schedule = fastf1.get_event_schedule(year)
    now = pd.Timestamp.now().tz_localize(None)
    
    # Filter for rounds where the race session has already occurred
    # Session5DateUtc corresponds to the Race in a standard F1 weekend
    completed_events = schedule[(schedule['Session5DateUtc'].dt.tz_localize(None) < now) & 
                                (schedule['EventFormat'] != 'testing')]
    
    rounds = completed_events['RoundNumber'].tolist()
    if not rounds:
        print(f"No completed rounds found for {year} yet.")
        return pd.DataFrame()

    print(f"Found completed rounds: {rounds}")
    all_results = []
    for r in rounds:
        print(f"Fetching data for {year} Round {r}...")
        race_df = fetch_race_results(year, r)
        qual_df = fetch_qualifying_results(year, r)
        if not race_df.empty and not qual_df.empty:
            merged = pd.merge(race_df, qual_df[['DriverNumber', 'QualifyingPosition']], on='DriverNumber', how='left')
            all_results.append(merged)
            
    return pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()

def fine_tune():
    # 1. Load data
    current_year = datetime.now().year
    print(f"Loading historical data (2020-{current_year-1})...")
    hist_df = fetch_historical_data(2020, current_year-1)
    
    print(f"Fetching {current_year} season context...")
    try:
        df_current = get_completed_season_data(current_year)
    except Exception as e:
        print(f"Warning: Could not fetch {current_year} data: {e}")
        df_current = pd.DataFrame()
    
    if df_current.empty:
        full_df = hist_df
    else:
        full_df = pd.concat([hist_df, df_current], ignore_index=True)
    
    if full_df.empty or len(full_df) < 10:
        print("Error: Insufficient data for fine-tuning. Need at least 10 samples.")
        return

    # 2. Preprocess
    processor = FeatureProcessor()
    processor.fit(full_df)
    X, y = processor.transform(full_df)
    
    if len(X) < 10:
        print(f"Error: Insufficient samples after preprocessing ({len(X)}). Need at least 10.")
        return

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.1, random_state=42)
    
    # 3. Hyperparameter Tuning
    print("Starting hyperparameter tuning...")
    # ... (rest of the code)
    
    xgb_reg = xgb.XGBRegressor(objective='reg:squarederror', random_state=42)
    cv_folds = min(3, len(X_train) // 2)
    if cv_folds < 2:
        print("Error: Too few samples for cross-validation.")
        return

    random_search = RandomizedSearchCV(
        xgb_reg, param_distributions=param_dist, n_iter=10, 
        scoring='neg_mean_squared_error', cv=cv_folds, verbose=1, random_state=42
    )
    random_search.fit(X_train, y_train)
    
    best_model = random_search.best_estimator_
    print(f"Best Parameters: {random_search.best_params_}")
    
    # Evaluate on test set
    preds = best_model.predict(X_test)
    mse = mean_squared_error(y_test, preds)
    print(f"Fine-tuned Model MSE: {mse:.2f}")
    
    # 4. Save
    pipeline = ModelPipeline(model=best_model, processor=processor)
    pipeline.save("models/f1_pipeline.joblib")
    print("Fine-tuned model saved as models/f1_pipeline.joblib")

if __name__ == "__main__":
    fine_tune()
