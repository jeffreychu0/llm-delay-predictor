#TODO determine which tensor flow models to do and use

from re import I
from tkinter import N

import ai_edge_litert as litert
import tensorflow as tf
import numpy as np
import pandas as pd
import math
#TODO: not done yet, need to implement a few stuff 

class DelayPredictor:
    def __init__(self, model_path:None):
        if model_path:
        
        self.model = self.build_model()

    def time_encoding(self, time_str:str)->tuple(float, float):
        try:
            time_stamp = time_str.split(" ")[1] #get the time part of the string
            time_parts = time_stamp.split(":")
            hours = int(time_parts[0])
            minutes = int(time_parts[1])
            seconds = int(time_parts[2])
            total_time_in_seconds = hours * 3600 + minutes * 60 + seconds
            x = math.cos(2 * math.pi * total_time_in_seconds / 86400) #encode the time as a point on a unit circle
            y = math.sin(2 * math.pi * total_time_in_seconds / 86400)
            return (x, y)
        except:
            return (0.0, 0.0) #if the time string is not in the correct format, return (0.0, 0.0) as a default value
    
    def line_encoding(self, line:str)->int:
        line_dict = {
            "1": 0,
            "2": 1,
            "3": 2,
            "4": 3,
            "5": 4,
            "6": 5,
            "7": 6,
            "A": 7,
            "C": 8,
            "E": 9,
            "B": 10,
            "D": 11,
            "F": 12,
            "M": 13,
            "G": 14,
            "J": 15,
            "Z": 16,
            "L": 17,
            "N": 18,
            "Q": 19,
            "R": 20,
            "W": 21
        }
        return line_dict.get(line, -1) #return -1 if the line is not in the dictionary
    

    def day_encoding(self, day:str)->int:
        day_dict = {
            "Monday": 0,
            "Tuesday": 1,
            "Wednesday": 2,
            "Thursday": 3,
            "Friday": 4,
            "Saturday": 5,
            "Sunday": 6
        }
        return day_dict.get(day, -1) #return -1 if the day is not in the dictionary

    def weather_encoding(self, percip: float, temp: float)->tuple(float, float):
        #encode the weather as a point in a 2D space where the x-axis represents the percipitation and the y-axis represents the temperature
        x = percip / 100.0 #normalize the percipitation to be between 0 and 1
        y = (temp + 10) / 120.0 #normalize the temperature to be between 0 and 1
        return (x, y)
       
    def build_model(self):
        model = tf.keras.Sequential([
            tf.keras.layers.Dense(64, activation='relu', input_shape=(10,)),
            tf.keras.layers.Dense(32, activation='relu'),
            tf.keras.layers.Dense(1)
        ])
        model.compile(optimizer='adam', loss='mse')
        return model
        


    