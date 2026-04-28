import { useEffect, useMemo, useState } from "react";

import { apiGet } from "../utils/api";

export default function PredictionDisplay({ selectedLine, station1, station2, direction, stations }) {
  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fromStation = useMemo(
    () => stations.find((station) => station["GTFS Stop ID"] === station1),
    [stations, station1],
  );
  const toStation = useMemo(
    () => stations.find((station) => station["GTFS Stop ID"] === station2),
    [stations, station2],
  );

  useEffect(() => {
    let cancelled = false;

    async function fetchPrediction() {
      if (selectedLine && fromStation && toStation && direction) {
        setLoading(true);
        setError("");

        try {
          const payload = await apiGet("/delays/estimate", {
            line: selectedLine,
            from_stop_id: fromStation["GTFS Stop ID"],
            to_stop_id: toStation["GTFS Stop ID"],
            direction: direction === "south" ? "southbound" : "northbound",
          });

          if (!cancelled) {
            setPrediction({
              delay: payload.segment_average_delay_seconds,
              stopCount: payload.stop_count,
              timestamp: new Date().toLocaleTimeString(),
            });
          }
        } catch (error) {
          if (!cancelled) {
            setPrediction(null);
            setError(error.message);
          }
        } finally {
          if (!cancelled) {
            setLoading(false);
          }
        }
      } else {
        setPrediction(null);
        setError("");
      }
    }

    fetchPrediction();
    const interval = setInterval(fetchPrediction, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [selectedLine, fromStation, toStation, direction]);

  if (!selectedLine || !station1 || !station2) {
    return (
      <section className="prediction-display">
        <h2>Live Delay</h2>
        <p className="prediction-placeholder">Pick a line and two stations to see the current MTA delay estimate.</p>
      </section>
    );
  }

  return (
    <section className="prediction-display">
      <h2>Live Delay</h2>
      <p>
        Estimated delay for <strong>{selectedLine}</strong> between <strong>{fromStation?.["Stop Name"] || station1}</strong> and <strong>{toStation?.["Stop Name"] || station2}</strong>.
      </p>

      {loading ? <div className="delay-value">Loading...</div> : null}
      {!loading && prediction ? (
        <>
          <div className="delay-value">
            {prediction.delay == null ? "No estimate" : `${(prediction.delay / 60).toFixed(1)} min`}
          </div>
          <p className="timestamp">{prediction.stopCount} stops sampled · Updated {prediction.timestamp}</p>
        </>
      ) : null}
      {error ? <p className="inline-error">{error}</p> : null}
    </section>
  );
}
