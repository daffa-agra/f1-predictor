import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
import joblib
import os
import numpy as np

class ListNetLoss(nn.Module):
    """
    ListNet ranking loss implementation.
    Top-1 probability distribution cross-entropy.
    """
    def __init__(self):
        super(ListNetLoss, self).__init__()

    def forward(self, y_pred, y_true):
        """
        y_pred: (batch_size, 1) - model output scores
        y_true: (batch_size, 1) - actual positions (1, 2, 3...)
        """
        # Target: higher probability for lower actual positions
        target_probs = F.softmax(-y_true, dim=0)
        
        # Prediction: higher probability for higher predicted scores
        pred_probs = F.softmax(y_pred, dim=0)
        
        # Using KL Divergence for stability
        return F.kl_div(torch.log(pred_probs + 1e-10), target_probs, reduction='batchmean')

class Attention(nn.Module):
    def __init__(self, hidden_size):
        super(Attention, self).__init__()
        self.attention = nn.Linear(hidden_size, 1)

    def forward(self, lstm_output):
        # lstm_output shape: (batch_size, time_steps, hidden_size)
        attn_weights = torch.softmax(self.attention(lstm_output), dim=1)
        # attn_weights shape: (batch_size, time_steps, 1)
        context_vector = torch.sum(attn_weights * lstm_output, dim=1)
        # context_vector shape: (batch_size, hidden_size)
        return context_vector

class LSTMModel(nn.Module):
    def __init__(self, input_size, hidden_size=64, num_layers=1, dropout=0.2):
        super(LSTMModel, self).__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout_val = dropout
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=dropout if num_layers > 1 else 0.0)
        # Attention layer
        self.attention = Attention(hidden_size)
        # Apply dropout manually after Attention output
        self.dropout = nn.Dropout(dropout)
        self.fc1 = nn.Linear(hidden_size, 32)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(32, 1)

    def forward(self, x):
        # x shape: (batch, time_steps, features)
        out, _ = self.lstm(x)
        # Apply attention to the full sequence
        out = self.attention(out)
        # out shape: (batch, hidden_size)
        out = self.dropout(out)
        out = self.fc1(out)
        out = self.relu(out)
        out = self.fc2(out)
        return out

class ModelPipeline:
    """Unified container for FeatureProcessor, the ML model, and baseline stats."""
    
    def __init__(self, model=None, processor=None, baselines=None):
        self.model = model
        self.processor = processor
        self.baselines = baselines or {}
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def train(self, X_train, y_train, X_test, y_test, lr=0.001, hidden_size=64, dropout=0.2, epochs=50, batch_size=32, use_ranking_loss=True):
        """Train the internal LSTM Model using PyTorch."""
        if X_train.shape[0] == 0:
            raise ValueError("Training data is empty. Cannot train the model.")
            
        time_steps = X_train.shape[1]
        features = X_train.shape[2]

        # Convert to PyTorch tensors
        X_train_t = torch.tensor(X_train, dtype=torch.float32).to(self.device)
        y_train_t = torch.tensor(y_train, dtype=torch.float32).view(-1, 1).to(self.device)
        X_test_t = torch.tensor(X_test, dtype=torch.float32).to(self.device)
        y_test_t = torch.tensor(y_test, dtype=torch.float32).view(-1, 1).to(self.device)

        if self.model is None:
            self.model = LSTMModel(input_size=features, hidden_size=hidden_size, dropout=dropout).to(self.device)
        
        criterion = ListNetLoss() if use_ranking_loss else nn.MSELoss()
        optimizer = optim.Adam(self.model.parameters(), lr=lr)

        dataset = torch.utils.data.TensorDataset(X_train_t, y_train_t)
        # For ListNet, we ideally want batch_size to keep race context together.
        dataloader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=False)

        # Basic EarlyStopping setup
        patience = 5
        best_loss = float('inf')
        patience_counter = 0
        best_model_state = None

        for epoch in range(epochs):
            self.model.train()
            for batch_x, batch_y in dataloader:
                optimizer.zero_grad()
                outputs = self.model(batch_x)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()
                
            self.model.eval()
            with torch.no_grad():
                val_outputs = self.model(X_test_t)
                val_loss = criterion(val_outputs, y_test_t).item()
                
            if val_loss < best_loss:
                best_loss = val_loss
                best_model_state = self.model.state_dict()
                patience_counter = 0
            else:
                patience_counter += 1
                
            if patience_counter >= patience:
                break
                
        # Restore best weights
        if best_model_state is not None:
            self.model.load_state_dict(best_model_state)
            
        self.model.eval()
        with torch.no_grad():
            preds = self.model(X_test_t).cpu().numpy().flatten()
            if use_ranking_loss:
                # Rank predicted scores (higher score = lower position)
                pred_ranks = len(preds) - np.argsort(np.argsort(preds))
                mse = mean_squared_error(y_test, pred_ranks)
            else:
                mse = mean_squared_error(y_test, preds)
        
        if self.processor and self.processor.is_fitted:
            self.baselines = self.processor.baselines
            
        return mse

    def predict(self, X):
        """Run inference using the internal model."""
        if self.model is None:
            raise ValueError("Model not trained.")
        self.model.eval()
        X_t = torch.tensor(X, dtype=torch.float32).to(self.device)
        with torch.no_grad():
            preds = self.model(X_t).cpu().numpy().flatten()
        return preds

    def save(self, path="models/f1_pipeline.joblib"):
        """Save the entire pipeline to disk."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        pytorch_model = self.model
        self.model = None
        
        joblib.dump(self, path)
        
        if pytorch_model is not None:
            model_path = path.replace('.joblib', '_torch.pth')
            torch.save({
                'state_dict': pytorch_model.state_dict(),
                'input_size': pytorch_model.input_size,
                'hidden_size': pytorch_model.hidden_size,
                'num_layers': pytorch_model.num_layers,
                'dropout': pytorch_model.dropout_val
            }, model_path)
        
        self.model = pytorch_model
        print(f"ModelPipeline saved to {path} and model to {path.replace('.joblib', '_torch.pth')}")

    @classmethod
    def load(cls, path="models/f1_pipeline.joblib"):
        """Load the entire pipeline from disk."""
        pipeline = joblib.load(path)
        model_path = path.replace('.joblib', '_torch.pth')
        if os.path.exists(model_path):
            checkpoint = torch.load(model_path, map_location=pipeline.device, weights_only=True)
            model = LSTMModel(
                input_size=checkpoint['input_size'],
                hidden_size=checkpoint.get('hidden_size', 64),
                num_layers=checkpoint.get('num_layers', 1),
                dropout=checkpoint.get('dropout', 0.2)
            ).to(pipeline.device)
            model.load_state_dict(checkpoint['state_dict'])
            pipeline.model = model
        return pipeline

def train_model(X, y):
    """Legacy wrapper for backward compatibility or direct training."""
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    pipeline = ModelPipeline()
    pipeline.train(X_train, y_train, X_test, y_test)
    return pipeline.model

def save_model(model, le_driver, le_team, le_event):
    """Legacy save function."""
    output_dir = "models"
    os.makedirs(output_dir, exist_ok=True)
    torch.save({
        'state_dict': model.state_dict(),
        'input_size': model.input_size,
        'hidden_size': model.hidden_size if hasattr(model, 'hidden_size') else 64,
        'num_layers': model.num_layers if hasattr(model, 'num_layers') else 1
    }, os.path.join(output_dir, "f1_model_torch.pth"))
    joblib.dump(le_driver, os.path.join(output_dir, "le_driver.joblib"))
    joblib.dump(le_team, os.path.join(output_dir, "le_team.joblib"))
    joblib.dump(le_event, os.path.join(output_dir, "le_event.joblib"))

def load_model():
    """Legacy load function."""
    output_dir = "models"
    checkpoint = torch.load(os.path.join(output_dir, "f1_model_torch.pth"), weights_only=True)
    model = LSTMModel(
        input_size=checkpoint['input_size'],
        hidden_size=checkpoint.get('hidden_size', 64),
        num_layers=checkpoint.get('num_layers', 1)
    )
    model.load_state_dict(checkpoint['state_dict'])
    le_driver = joblib.load(os.path.join(output_dir, "le_driver.joblib"))
    le_team = joblib.load(os.path.join(output_dir, "le_team.joblib"))
    le_event = joblib.load(os.path.join(output_dir, "le_event.joblib"))
    return model, le_driver, le_team, le_event
