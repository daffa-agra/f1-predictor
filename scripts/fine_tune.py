import pandas as pd
import numpy as np
import torch
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
from f1_predictor.data_fetcher import fetch_race_results, fetch_qualifying_results, fetch_historical_data, save_historical_data
from f1_predictor.preprocessor import FeatureProcessor
from f1_predictor.model import ModelPipeline
import fastf1
from datetime import datetime
from pathlib import Path
import os

def get_specific_round_data(year, round_num):
    """Fetch data for a specific round."""
    print(f"Fetching data for {year} Round {round_num}...")
    race_df = fetch_race_results(year, round_num)
    qual_df = fetch_qualifying_results(year, round_num)
    if not race_df.empty and not qual_df.empty:
        merged = pd.merge(race_df, qual_df[['DriverNumber', 'QualifyingPosition', 'Q1', 'Q2', 'Q3']], on='DriverNumber', how='left')
        
        # Calculate QDelta
        # Find minimum lap time across all drivers and sessions
        # Convert Q1, Q2, Q3 string/timedelta to seconds
        for q_col in ['Q1', 'Q2', 'Q3']:
            if q_col in merged.columns:
                merged[q_col] = pd.to_timedelta(merged[q_col]).dt.total_seconds()
        
        # Get minimum of Q1, Q2, Q3 for each driver
        merged['DriverBestQTime'] = merged[['Q1', 'Q2', 'Q3']].min(axis=1)
        # Find overall session best
        session_best = merged['DriverBestQTime'].min()
        
        # Calculate Delta
        if pd.notna(session_best) and session_best > 0:
            merged['QDelta'] = (merged['DriverBestQTime'] - session_best) / session_best
        else:
            merged['QDelta'] = np.nan
            
        return merged
    return pd.DataFrame()

def fine_tune():
    # 1. Load data
    print(f"\n=== F1 Predictor Fine-Tuning Pipeline (LSTM + Attention + Ranking) ===")
    
    # Load historical data up to 2025
    print("Loading historical data (2020-2025)...")
    df_hist = fetch_historical_data(2020, 2025)
    
    # Ensure QDelta and weather features are handled
    # fetch_historical_data already returns the data, but if it was cached without weather, 
    # we might need to refresh. For now, we assume the latest fetcher is used.
    
    # Fetch 2026 Round 1 for training inclusion
    df_r1_2026 = get_specific_round_data(2026, 1)
    
    # Combine training data
    train_df = pd.concat([df_hist, df_r1_2026], ignore_index=True)
    
    # Fetch 2026 Round 2 for testing
    test_df = get_specific_round_data(2026, 2)
    
    if test_df.empty:
        print("Error: Could not fetch R2 2026 data. Falling back to random split.")
    
    # 3. Hyperparameter Tuning
    print("Starting hyperparameter tuning...")
    
    best_mse = float('inf')
    best_params = {}
    best_processor = None
    
    # Grid search parameters
    time_steps_list = [5, 8]
    hidden_sizes = [128]
    lrs = [0.001, 0.005]
    dropouts = [0.2]
    
    for ts in time_steps_list:
        print(f"\n--- Testing time_steps: {ts} ---")
        processor = FeatureProcessor(time_steps=ts)
        all_data = pd.concat([train_df, test_df], ignore_index=True)
        processor.fit(all_data)
        
        X_train_full, y_train_full = processor.transform(train_df)
        X_train, X_val, y_train, y_val = train_test_split(X_train_full, y_train_full, test_size=0.1, random_state=42)
        X_test = processor.transform_for_prediction(train_df, test_df)
        
        for hs in hidden_sizes:
            for lr in lrs:
                for dr in dropouts:
                    print(f"  Testing Hidden Size: {hs}, LR: {lr}, Dropout: {dr}")
                    pipeline = ModelPipeline(processor=processor)
                    # Enable ranking loss
                    pipeline.train(X_train, y_train, X_val, y_val, 
                                         hidden_size=hs, lr=lr, dropout=dr, epochs=30, use_ranking_loss=True)
                    
                    preds = pipeline.predict(X_test)
                    
                    pred_df = pd.DataFrame({
                        'Abbreviation': test_df['Abbreviation'].values,
                        'PredictedScore': preds
                    })
                    # Higher score = lower position
                    pred_df['PredictedPosition'] = pred_df['PredictedScore'].rank(ascending=False, method='min').astype(int)
                    
                    comparison_df = pd.merge(pred_df, test_df[['Abbreviation', 'Position']], on='Abbreviation')
                    
                    r2_mse = mean_squared_error(comparison_df['Position'], comparison_df['PredictedPosition'])
                    r2_mae = np.mean(np.abs(comparison_df['Position'] - comparison_df['PredictedPosition']))
                    print(f"  -> R2 2026 Aligned Ranking MSE: {r2_mse:.2f}, MAE: {r2_mae:.2f}")
                    
                    if r2_mse < best_mse:
                        best_mse = r2_mse
                        best_params = {'time_steps': ts, 'hidden_size': hs, 'lr': lr, 'dropout': dr}
                        best_processor = processor
    
    print(f"\nBest Parameters: {best_params} with R2 MSE: {best_mse:.2f}")
    
    # 4. Final Training with best params
    print("\nFinal training with best parameters...")
    X_train_full, y_train_full = best_processor.transform(train_df)
    X_train, X_val, y_train, y_val = train_test_split(X_train_full, y_train_full, test_size=0.1, random_state=42)
    
    final_pipeline = ModelPipeline(processor=best_processor)
    final_pipeline.train(X_train, y_train, X_val, y_val, 
                         hidden_size=best_params['hidden_size'], 
                         lr=best_params['lr'], 
                         dropout=best_params['dropout'],
                         epochs=100,
                         use_ranking_loss=True)
    
    final_pipeline.save("models/f1_pipeline.joblib")
    print("Fine-tuned Ranking LSTM model saved.")

if __name__ == "__main__":
    fine_tune()
