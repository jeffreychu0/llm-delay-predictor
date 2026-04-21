import React, { useState, useEffect } from "react";

export default function PredictionDisplay({ selectedLine, station1, station2 }) {
  const [prediction, setPrediction] = useState(null);

  useEffect(() => {
    const fetchPrediction = () => {
      if (selectedLine && station1 && station2) {
        console.log("Fetching predictions for", selectedLine, station1, station2);
        // Dummy prediction logic (TODO: fetch from real API)
        const dummyDelay = Math.floor(Math.random() * 15);
        setPrediction({
          delay: dummyDelay,
          timestamp: new Date().toLocaleTimeString(),
        });
      } else {
        setPrediction(null);
      }
    };

    fetchPrediction(); // Initial call
    const interval = setInterval(fetchPrediction, 30000);
    return () => clearInterval(interval);
  }, [selectedLine, station1, station2]);

  if (!prediction) return null;

  return (
    <section className="prediction-display">
      <h2>Current Prediction</h2>
      <p>
        Estimated Delay for <strong>{selectedLine}</strong> line
        between <strong>{station1}</strong> and <strong>{station2}</strong>:
      </p>
      <div className="delay-value">{prediction.delay} minutes</div>
      <p className="timestamp">Last updated: {prediction.timestamp}</p>
    </section>
  );
}
