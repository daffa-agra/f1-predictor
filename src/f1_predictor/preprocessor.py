import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder

class FeatureProcessor:
    """Stateful feature engineering pipeline for F1 race prediction."""
    
    def __init__(self):
        self.le_driver = LabelEncoder()
        self.le_team = LabelEncoder()
        self.le_event = LabelEncoder()
        self.baselines = {}
        self.is_fitted = False
        self.feature_cols = [
            'QualifyingPosition', 'GridPosition', 'DriverAvgFinish', 
            'TeamAvgFinish', 'EventAvgFinish', 'DriverID', 'TeamID', 'EventID'
        ]

    def fit(self, df):
        """Fit encoders and calculate historical baseline statistics."""
        # Ensure data is sorted for temporal calculations
        df = df.sort_values(['Year', 'RoundNumber'])
        
        # Fit LabelEncoders
        self.le_driver.fit(df['Abbreviation'].unique())
        self.le_team.fit(df['TeamName'].unique())
        self.le_event.fit(df['EventName'].unique())
        
        # Calculate global baselines (using only historical data) for imputation
        self.baselines['global_mean'] = df['Position'].mean()
        self.baselines['driver_means'] = df.groupby('Abbreviation')['Position'].mean().to_dict()
        self.baselines['team_means'] = df.groupby('TeamName')['Position'].mean().to_dict()
        
        self.is_fitted = True
        return self

    def _calculate_rolling_features(self, df):
        """Calculate rolling averages with a shift to avoid data leakage."""
        df = df.copy()
        df = df.sort_values(['Year', 'RoundNumber'])
        
        # 1. Driver rolling performance (avg finish position in last 5 races)
        # We shift by 1 to only use data from previous races for the current race prediction
        df['DriverAvgFinish'] = df.groupby('Abbreviation')['Position'].transform(
            lambda x: x.rolling(window=5, min_periods=1).mean().shift(1)
        )
        
        # 2. Team rolling performance
        df['TeamAvgFinish'] = df.groupby('TeamName')['Position'].transform(
            lambda x: x.rolling(window=5, min_periods=1).mean().shift(1)
        )
        
        # 3. Track History (Average finish at this specific event)
        df['EventAvgFinish'] = df.groupby(['Abbreviation', 'EventName'])['Position'].transform(
            lambda x: x.expanding().mean().shift(1)
        )
        
        # Impute missing values using global mean (NO look-ahead bias if using training mean)
        global_mean = self.baselines.get('global_mean', df['Position'].mean())
        df['DriverAvgFinish'] = df['DriverAvgFinish'].fillna(global_mean)
        df['TeamAvgFinish'] = df['TeamAvgFinish'].fillna(global_mean)
        df['EventAvgFinish'] = df['EventAvgFinish'].fillna(global_mean)
        
        return df

    def transform(self, df):
        """Clean and engineer features for training."""
        if not self.is_fitted:
            raise ValueError("FeatureProcessor must be fitted before transform.")
            
        # Drop rows missing critical targets during training
        df = df.dropna(subset=['QualifyingPosition', 'Position'])
        
        # Calculate features
        df = self._calculate_rolling_features(df)
        
        # Encode categorical IDs
        df['DriverID'] = self.le_driver.transform(df['Abbreviation'])
        df['TeamID'] = self.le_team.transform(df['TeamName'])
        df['EventID'] = self.le_event.transform(df['EventName'])
        
        X = df[self.feature_cols]
        y = df['Position']
        
        return X, y

    def transform_for_prediction(self, race_df, external_baselines=None):
        """Prepare real-time features for inference using stored statistics."""
        if not self.is_fitted:
            raise ValueError("FeatureProcessor must be fitted before transform_for_prediction.")
            
        # Use provided baselines or internal ones
        baselines = external_baselines if external_baselines is not None else self.baselines
        
        race_df = race_df.copy()
        event_name = race_df['EventName'].iloc[0] if 'EventName' in race_df.columns else "Unknown"
        
        drivers_data = []
        global_mean = baselines.get('global_mean', 10.0)
        
        for _, driver in race_df.iterrows():
            abbr = driver.get('Abbreviation', 'UNKNOWN')
            team = driver.get('TeamName', 'UNKNOWN')
            
            # Use pre-calculated means instead of re-fetching historical DF
            driver_avg = baselines.get('driver_means', {}).get(abbr, global_mean)
            team_avg = baselines.get('team_means', {}).get(team, global_mean)
            
            # Event specific average - default to global if not specific
            # In a more advanced version, we'd store event-driver means too
            event_avg = global_mean

            # Map IDs
            try:
                driver_id = self.le_driver.transform([abbr])[0]
                team_id = self.le_team.transform([team])[0]
                event_id = self.le_event.transform([event_name])[0]
            except ValueError:
                driver_id = 0
                team_id = 0
                event_id = 0

            features = {
                'QualifyingPosition': driver['QualifyingPosition'],
                'GridPosition': driver.get('GridPosition', driver['QualifyingPosition']),
                'DriverAvgFinish': driver_avg,
                'TeamAvgFinish': team_avg,
                'EventAvgFinish': event_avg,
                'DriverID': driver_id,
                'TeamID': team_id,
                'EventID': event_id
            }
            drivers_data.append(features)
            
        X_pred = pd.DataFrame(drivers_data)
        return X_pred[self.feature_cols]

def preprocess_data(df):
    """Legacy wrapper for compatibility during transition."""
    processor = FeatureProcessor()
    processor.fit(df)
    X, y = processor.transform(df)
    return X, y, processor.le_driver, processor.le_team, processor.le_event
