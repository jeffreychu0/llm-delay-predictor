import React, { useState, useEffect } from "react";

import { filterStationsByLine } from "../utils/csvParser";

export default function SelectionInterface({
  stations,
  lines,
  onSelectionChange,
  showDirection = true,
  showToStation = true,
}) {
  const [selectedLine, setSelectedLine] = useState("");
  const [direction, setDirection] = useState("north");
  const [station1, setStation1] = useState("");
  const [station2, setStation2] = useState("");

  const filteredStations = React.useMemo(() => {
    return filterStationsByLine(stations, selectedLine);
  }, [stations, selectedLine]);
  // Get representative labels for the selected station
  const selectedStationObj = filteredStations.find((s) => s["GTFS Stop ID"] === station1);
  const northLabel = selectedStationObj ? selectedStationObj["North Direction Label"] : "Northbound";
  const southLabel = selectedStationObj ? selectedStationObj["South Direction Label"] : "Southbound";

  // Auto-switch direction if current becomes invalid
  useEffect(() => {
    if (northLabel === "Last Stop" && direction === "north") setDirection("south");
    if (southLabel === "Last Stop" && direction === "south") setDirection("north");
  }, [northLabel, southLabel, direction]);

  // Notify parent whenever selection changes
  useEffect(() => {
    onSelectionChange({
      selectedLine,
      direction,
      station1,
      station2,
      station1Name: selectedStationObj ? selectedStationObj["Stop Name"] : "",
      station2Name: filteredStations.find((s) => s["GTFS Stop ID"] === station2)?.["Stop Name"] || "",
      filteredStations
    });
  }, [selectedLine, direction, station1, station2, filteredStations, selectedStationObj, onSelectionChange]);

  return (
    <section className="selection-interface">
      <div className="input-group">
        <label htmlFor="train-line">Select Train Line:</label>
        <select
          id="train-line"
          value={selectedLine}
          onChange={(e) => {
            const val = e.target.value;
            setSelectedLine(val);
            setStation1("");
            setStation2("");
          }}
        >
          <option value="">-- Choose a line --</option>
          {lines.map((line) => (
            <option key={line} value={line}>
              {line} Train
            </option>
          ))}
        </select>
      </div>

      <div className="input-group">
        <label htmlFor="station1">From Station:</label>
        <select
          id="station1"
          value={station1}
          onChange={(e) => setStation1(e.target.value)}
          disabled={!selectedLine}
        >
          <option value="">-- Select station --</option>
          {filteredStations.map((s, index) => (
            <option
              key={`${s["GTFS Stop ID"]}-1-${index}`}
              value={s["GTFS Stop ID"]}
            >
              {s["Stop Name"]} ({s["GTFS Stop ID"]})
            </option>
          ))}
        </select>
      </div>

      {showDirection && (
        <div className="input-group">
          <label htmlFor="direction">Direction:</label>
          <select
            id="direction"
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
            disabled={!selectedLine || !station1}
          >
            {northLabel !== "Last Stop" && (
              <option value="north">Northbound ({northLabel})</option>
            )}
            {southLabel !== "Last Stop" && (
              <option value="south">Southbound ({southLabel})</option>
            )}
          </select>
        </div>
      )}

      {showToStation && (
        <div className="input-group">
          <label htmlFor="station2">To Station:</label>
          <select
            id="station2"
            value={station2}
            onChange={(e) => setStation2(e.target.value)}
            disabled={!selectedLine || !station1}
          >
            <option value="">-- Select station --</option>
            {filteredStations.map((s, index) => (
              <option
                key={`${s["GTFS Stop ID"]}-2-${index}`}
                value={s["GTFS Stop ID"]}
              >
                {s["Stop Name"]} ({s["GTFS Stop ID"]})
              </option>
            ))}
          </select>
        </div>
      )}
    </section>
  );
}
