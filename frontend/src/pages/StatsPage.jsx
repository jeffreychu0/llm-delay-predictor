import { useEffect, useMemo, useState } from "react";

import SelectionInterface from "../components/SelectionInterface";
import { apiGet } from "../utils/api";
import { useStations } from "../utils/useStations";
import "../App.css";

function StatCard({ title, value, subtitle }) {
  return (
    <article className="stat-card">
      <span>{title}</span>
      <strong>{value}</strong>
      {subtitle ? <p>{subtitle}</p> : null}
    </article>
  );
}

function BarList({ title, items, valueFormatter = (value) => value, emptyText = "No data available yet." }) {
  const maxValue = Math.max(...items.map((item) => Number(item.value) || 0), 1);

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
      </div>
      <div className="bar-list">
        {items.length ? (
          items.map((item) => (
            <div className="bar-row" key={item.label}>
              <div className="bar-row__label">
                <strong>{item.label}</strong>
                {item.meta ? <span>{item.meta}</span> : null}
              </div>
              <div className="bar-row__track">
                <div
                  className="bar-row__fill"
                  style={{ width: `${Math.max((Number(item.value) || 0) / maxValue, 0.04) * 100}%` }}
                />
              </div>
              <div className="bar-row__value">{valueFormatter(item.value)}</div>
            </div>
          ))
        ) : (
          <p className="panel-empty">{emptyText}</p>
        )}
      </div>
    </section>
  );
}

export default function StatsPage() {
  const { stations, lines, loading, error } = useStations();
  const [selection, setSelection] = useState({
    selectedLine: "",
    direction: "north",
    station1: "",
    station2: "",
    station1Name: "",
    station2Name: "",
    filteredStations: [],
  });
  const [lineSummary, setLineSummary] = useState(null);
  const [headsigns, setHeadsigns] = useState([]);
  const [lineLive, setLineLive] = useState(null);
  const [stationLive, setStationLive] = useState(null);
  const [stationAverages, setStationAverages] = useState([]);
  const [segmentEstimate, setSegmentEstimate] = useState(null);
  const [loadingData, setLoadingData] = useState(true);
  const [dataError, setDataError] = useState("");

  const selectedStation = useMemo(
    () => selection.filteredStations.find((station) => station["GTFS Stop ID"] === selection.station1),
    [selection.filteredStations, selection.station1],
  );
  const secondaryStation = useMemo(
    () => selection.filteredStations.find((station) => station["GTFS Stop ID"] === selection.station2),
    [selection.filteredStations, selection.station2],
  );

  useEffect(() => {
    let cancelled = false;

    async function loadOverview() {
      setLoadingData(true);
      setDataError("");

      try {
        const [averagePayload, stationAveragePayload] = await Promise.all([
          apiGet("/delays/average"),
          apiGet("/stations/delays/average", { min_observations: 10 }),
        ]);

        if (cancelled) {
          return;
        }

        setLineSummary(averagePayload);
        setStationAverages(stationAveragePayload.stations || []);
      } catch (error) {
        if (!cancelled) {
          setDataError(error.message);
        }
      } finally {
        if (!cancelled) {
          setLoadingData(false);
        }
      }
    }

    loadOverview();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selection.selectedLine) {
      setHeadsigns([]);
      setLineLive(null);
      setSegmentEstimate(null);
      return;
    }

    let cancelled = false;

    async function loadLineData() {
      try {
        const [headsignPayload, linePayload] = await Promise.all([
          apiGet("/stations/headsigns", { line: selection.selectedLine }),
          apiGet(`/lines/${selection.selectedLine}/delays`, { window_minutes: 30 }),
        ]);

        if (!cancelled) {
          setHeadsigns(headsignPayload.headsigns || []);
          setLineLive(linePayload);
        }
      } catch (error) {
        if (!cancelled) {
          setDataError(error.message);
        }
      }
    }

    loadLineData();

    return () => {
      cancelled = true;
    };
  }, [selection.selectedLine]);

  useEffect(() => {
    if (!selectedStation) {
      setStationLive(null);
      return;
    }

    let cancelled = false;

    async function loadStationData() {
      try {
        const stationPayload = await apiGet(`/stations/${selectedStation["GTFS Stop ID"]}/delays`, { window_minutes: 120 });
        if (!cancelled) {
          setStationLive(stationPayload);
        }
      } catch (error) {
        if (!cancelled) {
          setDataError(error.message);
        }
      }
    }

    loadStationData();

    return () => {
      cancelled = true;
    };
  }, [selectedStation]);

  useEffect(() => {
    if (!selection.selectedLine || !selectedStation || !secondaryStation) {
      setSegmentEstimate(null);
      return;
    }

    let cancelled = false;

    async function loadEstimate() {
      try {
        const estimatePayload = await apiGet("/delays/estimate", {
          line: selection.selectedLine,
          from_stop_id: selectedStation["GTFS Stop ID"],
          to_stop_id: secondaryStation["GTFS Stop ID"],
          direction: selection.direction === "south" ? "southbound" : "northbound",
        });

        if (!cancelled) {
          setSegmentEstimate(estimatePayload);
        }
      } catch (error) {
        if (!cancelled) {
          setSegmentEstimate({ error: error.message });
        }
      }
    }

    loadEstimate();

    return () => {
      cancelled = true;
    };
  }, [selection.selectedLine, selection.direction, selectedStation, secondaryStation]);

  const lineDelayBars = (lineSummary?.per_line || []).slice(0, 12).map((entry) => ({
    label: entry.route_id,
    value: entry.average_delay_seconds ?? 0,
    meta: `${entry.observation_count} obs`,
  }));

  const stationDelayBars = stationAverages.slice(0, 12).map((entry) => ({
    label: entry.stop_name || entry.stop_id,
    value: entry.average_delay_seconds ?? 0,
    meta: `${entry.observation_count} obs`,
  }));

  if (loading) return <div className="loading">Loading stations...</div>;
  if (error) return <div className="error">Error: {error.message}</div>;

  return (
    <div className="page page--stats">
      <section className="page-hero">
        <div>
          <p className="eyebrow">Page 3</p>
          <h1>Delay Statistics</h1>
          <p className="page-lede">A minimalist data room for the database, with charts and the live API endpoints.</p>
        </div>
        <div className="hero-chip">mta.db</div>
      </section>

      {loadingData ? <div className="panel panel--loading">Loading analytics...</div> : null}
      {dataError ? <div className="panel panel--error">{dataError}</div> : null}

      <section className="panel panel--stacked">
        <div className="panel-heading">
          <h2>Focus Filters</h2>
          <p>Use these controls to inspect a route, a station, and a travel direction.</p>
        </div>
        <SelectionInterface stations={stations} lines={lines} onSelectionChange={setSelection} />
      </section>

      <div className="stats-grid">
        <StatCard
          title="Global delay average"
          value={lineSummary?.global_average_delay_seconds == null ? "—" : `${(lineSummary.global_average_delay_seconds / 60).toFixed(1)} min`}
          subtitle={`${lineSummary?.observation_count || 0} observations`}
        />
        <StatCard
          title="Selected line"
          value={selection.selectedLine || "None"}
          subtitle={`${lineLive?.currently_running_trains || 0} live train samples`}
        />
        <StatCard
          title="Selected station"
          value={selectedStation ? selectedStation["Stop Name"] : "None"}
          subtitle={stationLive?.observation_count ? `${stationLive.observation_count} station observations` : "No station focus yet"}
        />
        <StatCard
          title="Segment estimate"
          value={segmentEstimate?.segment_average_delay_seconds == null ? "—" : `${(segmentEstimate.segment_average_delay_seconds / 60).toFixed(1)} min`}
          subtitle={segmentEstimate?.error || (segmentEstimate ? `${segmentEstimate.stop_count} stops in span` : "Pick two stations")}
        />
      </div>

      <div className="stats-grid stats-grid--two">
        <BarList
          title="Average delay by line"
          items={lineDelayBars}
          valueFormatter={(value) => `${(Number(value) / 60).toFixed(1)}m`}
          emptyText="No route delay averages yet."
        />
        <BarList
          title="Average delay by station"
          items={stationDelayBars}
          valueFormatter={(value) => `${(Number(value) / 60).toFixed(1)}m`}
          emptyText="No station delay averages yet."
        />
      </div>

      <div className="stats-grid stats-grid--two">
        <section className="panel">
          <div className="panel-heading">
            <h2>Headsigns</h2>
            <p>{selection.selectedLine ? `Headsigns found for ${selection.selectedLine}.` : "Pick a line to inspect headsigns."}</p>
          </div>
          <div className="mini-list">
            {headsigns.length ? headsigns.slice(0, 10).map((item) => (
              <div className="mini-list__item" key={`${item.route_id}-${item.headsign}`}>
                <strong>{item.headsign}</strong>
                <span>{item.samples} samples</span>
              </div>
            )) : <p className="panel-empty">No headsign data available for the chosen line.</p>}
          </div>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>Live trains</h2>
            <p>{selection.selectedLine ? `Recent train observations for ${selection.selectedLine}.` : "Pick a line to review live samples."}</p>
          </div>
          <div className="table-list">
            {(lineLive?.trains || []).slice(0, 8).length ? (lineLive.trains.slice(0, 8).map((row) => (
              <div className="table-list__row" key={`${row.trip_id}-${row.timestamp}`}>
                <strong>{row.stop_name || row.stop_id}</strong>
                <span>{row.delay_seconds == null ? "No delay" : `${(row.delay_seconds / 60).toFixed(1)} min`}</span>
              </div>
            ))) : <p className="panel-empty">No live train samples for this route yet.</p>}
          </div>
        </section>
      </div>

      <div className="stats-grid stats-grid--two">
        <section className="panel">
          <div className="panel-heading">
            <h2>Station detail</h2>
            <p>{selectedStation ? `Observations for ${selectedStation["Stop Name"]}.` : "Pick a station to review its observations."}</p>
          </div>
          <div className="table-list">
            {(stationLive?.observations || []).slice(0, 8).length ? (stationLive.observations.slice(0, 8).map((row) => (
              <div className="table-list__row" key={`${row.trip_id}-${row.timestamp}`}>
                <strong>{row.route_id}</strong>
                <span>{row.delay_seconds == null ? "No delay" : `${(row.delay_seconds / 60).toFixed(1)} min`}</span>
              </div>
            ))) : <p className="panel-empty">No station observations available yet.</p>}
          </div>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>Segment estimate</h2>
            <p>{selection.station1Name && selection.station2Name ? `${selection.station1Name} to ${selection.station2Name}` : "Choose two stops to estimate delay across the segment."}</p>
          </div>
          {segmentEstimate && !segmentEstimate.error ? (
            <div className="segment-summary">
              <strong>
                {segmentEstimate.segment_average_delay_seconds == null
                  ? "No estimate"
                  : `${(segmentEstimate.segment_average_delay_seconds / 60).toFixed(1)} min`}
              </strong>
              <p>{segmentEstimate.direction}</p>
              <span>{segmentEstimate.stop_count} stops analyzed</span>
            </div>
          ) : (
            <p className="panel-empty">{segmentEstimate?.error || "No segment estimate yet."}</p>
          )}
        </section>
      </div>
    </div>
  );
}