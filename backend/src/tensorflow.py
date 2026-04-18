#TODO determine which tensor flow models to do and use

from re import I

import tensorflow as tf
import numpy as np
import pandas as pd


class DelayPredictor:
    def __init__(self):
        self.model = None

    def train(self, X_train, y_train):
        # Define a simple feedforward neural network
        self.model = tf.keras.Sequential([
            tf.keras.layers.Dense(64, activation='relu', input_shape=(X_train.shape[1],)),
            tf.keras.layers.Dense(32, activation='relu'),
            tf.keras.layers.Dense(1)  # Output layer for regression
        ])

        # Compile the model
        self.model.compile(optimizer='adam', loss='mean_squared_error')

        # Train the model
        self.model.fit(X_train, y_train, epochs=50, batch_size=32)

    def predict(self, X_test):
        if self.model is None:
            raise ValueError("Model has not been trained yet.")
        return self.model.predict(X_test)   
    