import { useState, useEffect } from "react";
import { parseStationsCSV, getUniqueLines } from "./csvParser";

/**
 * Custom hook to handle fetching and parsing of station data.
 */
export function useStations() {
  const [stations, setStations] = useState([]);
  const [lines, setLines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/stations.csv")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch stations");
        return res.text();
      })
      .then((data) => {
        const parsed = parseStationsCSV(data);
        setStations(parsed);
        setLines(getUniqueLines(parsed));
        setLoading(false);
      })
      .catch((err) => {
        console.error("Error loading stations:", err);
        setError(err);
        setLoading(false);
      });
  }, []);

  return { stations, lines, loading, error };
}
