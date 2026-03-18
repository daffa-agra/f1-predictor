import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import RandomizedSearchCV, train_test_split
from sklearn.metrics import mean_squared_error
from f1_predictor.data_fetcher import fetch_race_results, fetch_qualifying_results, fetch_historical_data, save_historical_data
from f1_predictor.preprocessor import FeatureProcessor
from f1_predictor.model import ModelPipeline
import fastf1
from datetime import datetime
from pathlib import Path
import joblib

def get_completed_season_data(year, existing_df=pd.DataFrame()):
    """Identify and fetch all completed race data for the current season, skipping already cached rounds."""
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

    # Identify which rounds we already have for this year
    existing_rounds = set()
    if not existing_df.empty and 'Year' in existing_df.columns and 'RoundNumber' in existing_df.columns:
        existing_rounds = set(existing_df[existing_df['Year'] == year]['RoundNumber'].unique())
    
    missing_rounds = [r for r in rounds if r not in existing_rounds]
    
    print(f"Season {year} status: {len(rounds)} rounds completed.")
    print(f"  - Cached rounds: {len(existing_rounds.intersection(set(rounds)))}")
    print(f"  - Rounds to fetch: {len(missing_rounds)} {missing_rounds if missing_rounds else ''}")

    new_results = []
    for r in missing_rounds:
        print(f"Fetching data for {year} Round {r}...")
        race_df = fetch_race_results(year, r)
        qual_df = fetch_qualifying_results(year, r)
        if not race_df.empty and not qual_df.empty:
            merged = pd.merge(race_df, qual_df[['DriverNumber', 'QualifyingPosition']], on='DriverNumber', how='left')
            new_results.append(merged)
    
    # Extract only this year's data from existing_df
    current_year_df = existing_df[existing_df['Year'] == year].copy() if not existing_df.empty else pd.DataFrame()
    
    if new_results:
        new_df = pd.concat(new_results, ignore_index=True)
        current_year_df = pd.concat([current_year_df, new_df], ignore_index=True)
        print(f"Fetched {len(new_results)} new rounds for {year}.")
    else:
        if missing_rounds:
            print(f"Warning: Failed to fetch any new data for {year}.")
        else:
            print(f"No new rounds to fetch for {year}.")
            
    return current_year_df

def fine_tune():
    # 1. Load data
    current_year = datetime.now().year
    print(f"\n=== F1 Predictor Fine-Tuning Pipeline ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")
    
    # Load historical data (handles incremental loading year-by-year)
    print(f"Loading historical data (2020-{current_year-1})...")
    hist_df = fetch_historical_data(2020, current_year-1)
    
    # Load any existing data for the current year from the main CSV
    generic_path = Path("data/historical_data.csv")
    full_existing_df = pd.DataFrame()
    if generic_path.exists():
        try:
            full_existing_df = pd.read_csv(generic_path)
        except Exception as e:
            print(f"Warning: Could not load {generic_path}: {e}")
    
    print(f"Fetching {current_year} season context...")
    try:
        df_current = get_completed_season_data(current_year, full_existing_df)
    except Exception as e:
        print(f"Warning: Could not fetch {current_year} data: {e}")
        df_current = pd.DataFrame()
    
    # Combine historical and current
    if df_current.empty:
        full_df = hist_df
    else:
        full_df = pd.concat([hist_df, df_current], ignore_index=True)
    
    if full_df.empty or len(full_df) < 10:
        print("Error: Insufficient data for fine-tuning. Need at least 10 samples.")
        return

    # Deduplicate based on Year, RoundNumber, DriverNumber
    before_dedup = len(full_df)
    full_df = full_df.drop_duplicates(subset=['Year', 'RoundNumber', 'DriverNumber'])
    after_dedup = len(full_df)
    
    if before_dedup > after_dedup:
        print(f"Removed {before_dedup - after_dedup} duplicate records.")
    
    print(f"Total dataset size: {len(full_df)} records across {full_df['Year'].nunique()} seasons.")
    
    # Save the consolidated full_df back to historical storage
    save_historical_data(full_df, generic_path)
    print(f"Updated consolidated historical storage at {generic_path}")

    # 2. Preprocess
    print("\n--- Preprocessing Phase ---")
    processor = FeatureProcessor()
    processor.fit(full_df)
    X, y = processor.transform(full_df)
    
    if len(X) < 10:
        print(f"Error: Insufficient samples after preprocessing ({len(X)}). Need at least 10.")
        return

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.1, random_state=42)
    
    # 3. Hyperparameter Tuning
    print("Starting hyperparameter tuning...")
    param_dist = {
        'n_estimators': [100, 200, 300],
        'max_depth': [3, 5, 7],
        'learning_rate': [0.01, 0.1, 0.2],
        'subsample': [0.8, 1.0],
        'colsample_bytree': [0.8, 1.0]
    }
    
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
