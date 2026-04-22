import { parse } from 'csv-parse/browser/esm/sync';

export interface IStation {
  "GTFS Stop ID": string;
  "Station ID": string;
  "Complex ID": string;
  "Division": string;
  "Line": string;
  "Stop Name": string;
  "Borough": string;
  "CBD": string;
  "Daytime Routes": string;
  "Structure": string;
  "GTFS Latitude": string;
  "GTFS Longitude": string;
  "North Direction Label": string;
  "South Direction Label": string;
  "ADA": string;
  "ADA Northbound": string;
  "ADA Southbound": string;
  "ADA Notes": string;
  "Georeference": string;
  [key: string]: string;
}

/**
 * Parses the stations.csv content into an array of IStation objects using csv-parse.
 */
export const parseStationsCSV = (csvData: string): IStation[] => {
  try {
    const records = parse(csvData, {
      columns: true,
      skip_empty_lines: true,
      trim: true
    });
    return records as IStation[];
  } catch (err) {
    console.error("CSV Parsing Error:", err);
    return [];
  }
};

/**
 * Filters stations that belong to a specific train line.
 */
export const filterStationsByLine = (stations: IStation[], line: string): IStation[] => {
  if (!line) return [];
  return stations.filter((s) => {
    const routes = s["Daytime Routes"] ? s["Daytime Routes"].split(" ") : [];
    return routes.includes(line);
  });
};

/**
 * Extracts unique train lines from the parsed stations.
 */
export const getUniqueLines = (stations: IStation[]): string[] => {
  const allLines = new Set<string>();
  stations.forEach((s) => {
    if (s["Daytime Routes"]) {
      s["Daytime Routes"].split(" ").forEach((line) => {
        if (line) allLines.add(line);
      });
    }
  });
  return Array.from(allLines).sort();
};
