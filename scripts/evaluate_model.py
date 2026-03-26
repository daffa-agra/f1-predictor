import pandas as pd
import numpy as np
from f1_predictor.model import ModelPipeline
from f1_predictor.data_fetcher import fetch_race_results, fetch_qualifying_results, fetch_historical_data
import fastf1

def calculate_metrics(predicted_df, actual_df):
    """Calculate podium accuracy, top 10 accuracy, and MAE."""
    actual_top_3 = set(actual_df.head(3)['BroadcastName'])
    pred_top_3 = set(predicted_df.head(3)['BroadcastName'])
    podium_accuracy = len(actual_top_3.intersection(pred_top_3)) / 3.0
    
    actual_top_10 = set(actual_df.head(10)['BroadcastName'])
    pred_top_10 = set(predicted_df.head(10)['BroadcastName'])
    top_10_accuracy = len(actual_top_10.intersection(pred_top_10)) / 10.0
    
    # Merge to compare positions
    merged = pd.merge(predicted_df, actual_df[['BroadcastName', 'Position']], on='BroadcastName', suffixes=('_pred', '_actual'))
    mae = np.abs(merged['PredictedPosition'] - merged['Position']).mean()
    
    return podium_accuracy, top_10_accuracy, mae

def evaluate(year, rounds):
    pipeline = ModelPipeline.load()
    hist_year_start = year - 1
    full_hist_df = fetch_historical_data(hist_year_start, year)
    
    all_metrics = []
    
    for r in rounds:
        print(f"Evaluating Round {r}...")
        actual_df = fetch_race_results(year, r)
        qual_df = fetch_qualifying_results(year, r)
        
        # Enrich qual_df with BroadcastName
        session = fastf1.get_session(year, r, 'Q')
        session.load(laps=False, telemetry=False, weather=False, messages=False)
        results = session.results[['DriverNumber', 'BroadcastName', 'Abbreviation', 'TeamName']]
        qual_df = pd.merge(qual_df, results, on='DriverNumber', how='left')
        qual_df['EventName'] = session.event['EventName']
        
        # Calculate QDelta
        for q_col in ['Q1', 'Q2', 'Q3']:
            if q_col in qual_df.columns:
                if qual_df[q_col].dtype == object:
                    qual_df[q_col] = pd.to_timedelta(qual_df[q_col]).dt.total_seconds()
                elif pd.api.types.is_timedelta64_dtype(qual_df[q_col]):
                    qual_df[q_col] = qual_df[q_col].dt.total_seconds()
        if 'Q1' in qual_df.columns:
            qual_df['DriverBestQTime'] = qual_df[['Q1', 'Q2', 'Q3']].min(axis=1)
            session_best = qual_df['DriverBestQTime'].min()
            if pd.notna(session_best) and session_best > 0:
                qual_df['QDelta'] = (qual_df['DriverBestQTime'] - session_best) / session_best
            else:
                qual_df['QDelta'] = np.nan
        
        # Filter history for current round
        hist_df = full_hist_df[~((full_hist_df['Year'] == year) & (full_hist_df['RoundNumber'] >= r))]

        # Predict
        X_pred = pipeline.processor.transform_for_prediction(hist_df, qual_df)
        preds = pipeline.predict(X_pred)
        
        pred_df = qual_df.copy()
        pred_df['PredictedScore'] = preds
        # Rank: highest score is 1st
        pred_df['PredictedPosition'] = pred_df['PredictedScore'].rank(ascending=False, method='min').astype(int)
        pred_df = pred_df.sort_values('PredictedPosition')
        
        metrics = calculate_metrics(pred_df, actual_df)
        all_metrics.append(metrics)
        print(f"  Podium: {metrics[0]*100:.1f}%, Top 10: {metrics[1]*100:.1f}%, MAE: {metrics[2]:.2f}")
    
    avg_podium = np.mean([m[0] for m in all_metrics])
    avg_top10 = np.mean([m[1] for m in all_metrics])
    avg_mae = np.mean([m[2] for m in all_metrics])
    
    print(f"\nOverall Success Rate ({year} R{rounds[0]}-R{rounds[-1]}):")
    print(f"Avg Podium Accuracy: {avg_podium*100:.1f}%")
    print(f"Avg Top 10 Accuracy: {avg_top10*100:.1f}%")
    print(f"Avg Position MAE:    {avg_mae:.2f}")

if __name__ == "__main__":
    evaluate(2026, [1, 2])
