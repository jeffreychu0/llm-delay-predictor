import React, { useEffect } from "react";
import { MapContainer } from "react-leaflet";
import { TileLayer } from "react-leaflet";
import { useMap } from "react-leaflet";
import { Marker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";

import L from "leaflet";

// Fix for default marker icon issues in React Leaflet
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.7.1/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.7.1/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.7.1/dist/images/marker-shadow.png",
});


function ChangeView({ center, zoom }) {
  const map = useMap();
  map.setView(center, zoom);
  return null;
}

export default function TrainMap({ stations, selectedLine, station1, station2 }) {
  const s1Obj = stations.find((s) => s["Stop Name"] === station1);
  const s2Obj = stations.find((s) => s["Stop Name"] === station2);

  const center = [40.7128, -74.0060]; // NYC Center

  const renderMarkers = () => {
    const markers = [];
    if (s1Obj) {
      markers.push(
        <Marker
          key="s1"
          position={[parseFloat(s1Obj["GTFS Latitude"]), parseFloat(s1Obj["GTFS Longitude"])]}
        >
          <Popup>
            <strong>{station1}</strong>
            <br />
            Line: {selectedLine}
          </Popup>
        </Marker>
      );
    }
    // Only add second marker if it's different from the first one
    if (s2Obj && (!s1Obj || s1Obj["GTFS Stop ID"] !== s2Obj["GTFS Stop ID"])) {
      markers.push(
        <Marker
          key="s2"
          position={[parseFloat(s2Obj["GTFS Latitude"]), parseFloat(s2Obj["GTFS Longitude"])]}
        >
          <Popup>
            <strong>{station2}</strong>
            <br />
            Line: {selectedLine}
          </Popup>
        </Marker>
      );
    }
    return markers;
  };

  // Determine center based on selection
  let mapCenter = center;
  let zoom = 11
  if (s1Obj && s2Obj) {
    mapCenter = [
      (parseFloat(s1Obj["GTFS Latitude"]) + parseFloat(s2Obj["GTFS Latitude"])) / 2,
      (parseFloat(s1Obj["GTFS Longitude"]) + parseFloat(s2Obj["GTFS Longitude"])) / 2,
    ];
  } else if (s1Obj) {
    mapCenter = [parseFloat(s1Obj["GTFS Latitude"]), parseFloat(s1Obj["GTFS Longitude"])];
  } else if (s2Obj) {
    mapCenter = [parseFloat(s2Obj["GTFS Latitude"]), parseFloat(s2Obj["GTFS Longitude"])];
  }

  return (
    <section className="map-container">
      <div id="map" style={{ height: "100%", width: "100%" }}>
        <MapContainer
          center={mapCenter}
          zoom={zoom}
          scrollWheelZoom={true}
          style={{ height: "100%", width: "100%" }}
        >
          <ChangeView center={mapCenter} zoom={zoom} />
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {renderMarkers()}
        </MapContainer>
      </div>
    </section>
  );
}
