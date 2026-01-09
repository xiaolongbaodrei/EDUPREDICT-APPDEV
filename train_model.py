import pandas as pd
from sklearn.linear_model import LogisticRegression
import joblib
import logging

data = pd.DataFrame({
    'attendance': [90, 85, 70, 60, 95, 50],
    'grade': [88, 80, 75, 65, 92, 60],
    'dropout': [0, 0, 1, 1, 0, 1]
})

X = data[['attendance', 'grade']]
y = data['dropout']

model = LogisticRegression()
model.fit(X, y)

joblib.dump(model, 'model/risk_model.pkl')
logging.info("Model trained successfully.")

