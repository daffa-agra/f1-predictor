import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
import joblib
import os

class ModelPipeline:
    """Unified container for FeatureProcessor, the ML model, and baseline stats."""
    
    def __init__(self, model=None, processor=None, baselines=None):
        self.model = model
        self.processor = processor
        self.baselines = baselines or {}

    def train(self, X_train, y_train, X_test, y_test):
        """Train the internal XGBRegressor."""
        self.model = xgb.XGBRegressor(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=5,
            objective='reg:squarederror',
            random_state=42
        )
        self.model.fit(X_train, y_train)
        
        preds = self.model.predict(X_test)
        mse = mean_squared_error(y_test, preds)
        print(f"Model trained with MSE: {mse:.2f}")
        
        # If processor is available and fitted, sync baselines
        if self.processor and self.processor.is_fitted:
            self.baselines = self.processor.baselines
            print(f"Synced {len(self.baselines.get('driver_means', {}))} driver baselines to pipeline.")
            
        return mse

    def predict(self, X):
        """Run inference using the internal model."""
        if self.model is None:
            raise ValueError("Model not trained.")
        return self.model.predict(X)

    def save(self, path="models/f1_pipeline.joblib"):
        """Save the entire pipeline to disk."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump(self, path)
        print(f"ModelPipeline saved to {path}")

    @classmethod
    def load(cls, path="models/f1_pipeline.joblib"):
        """Load the entire pipeline from disk."""
        return joblib.load(path)

def train_model(X, y):
    """Legacy wrapper for backward compatibility or direct training."""
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model = xgb.XGBRegressor(
        n_estimators=100,
        learning_rate=0.1,
        max_depth=5,
        objective='reg:squarederror',
        random_state=42
    )
    model.fit(X_train, y_train)
    return model

def save_model(model, le_driver, le_team, le_event):
    """Legacy save function."""
    output_dir = "models"
    os.makedirs(output_dir, exist_ok=True)
    joblib.dump(model, os.path.join(output_dir, "f1_model.joblib"))
    joblib.dump(le_driver, os.path.join(output_dir, "le_driver.joblib"))
    joblib.dump(le_team, os.path.join(output_dir, "le_team.joblib"))
    joblib.dump(le_event, os.path.join(output_dir, "le_event.joblib"))

def load_model():
    """Legacy load function."""
    output_dir = "models"
    model = joblib.load(os.path.join(output_dir, "f1_model.joblib"))
    le_driver = joblib.load(os.path.join(output_dir, "le_driver.joblib"))
    le_team = joblib.load(os.path.join(output_dir, "le_team.joblib"))
    le_event = joblib.load(os.path.join(output_dir, "le_event.joblib"))
    return model, le_driver, le_team, le_event
