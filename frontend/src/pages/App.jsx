import React, { useState, useCallback } from "react";
import { useStations } from "../utils/useStations";
import TrainMap from "../components/TrainMap";
import SelectionInterface from "../components/SelectionInterface";
import PredictionDisplay from "../components/PredictionDisplay";
import "../App.css";

export default function App() {
  const { stations, lines, loading, error } = useStations();
  const [selection, setSelection] = useState({
    selectedLine: "",
    station1: "",
    station2: "",
    filteredStations: [],
  });

  const handleSelectionChange = useCallback((newSelection) => {
    setSelection(newSelection);
  }, []);

  if (loading) return <div className="loading">Loading stations...</div>;
  if (error) return <div className="error">Error: {error.message}</div>;

  return (
    <div className="App">
      <main className="App-content">
        <div className="main-layout">
          <div className="left-panel">
            <SelectionInterface
              stations={stations}
              lines={lines}
              onSelectionChange={handleSelectionChange}
            />
            <PredictionDisplay
              selectedLine={selection.selectedLine}
              station1={selection.station1}
              station2={selection.station2}
            />
          </div>
          <TrainMap
            stations={selection.filteredStations}
            selectedLine={selection.selectedLine}
            station1={selection.station1}
            station2={selection.station2}
          />
        </div>
      </main>
    </div>
  );
}
