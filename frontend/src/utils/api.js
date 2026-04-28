const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function buildQuery(params = {}) {
  const query = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, value);
    }
  });

  const queryString = query.toString();
  return queryString ? `?${queryString}` : "";
}

export async function apiGet(path, params) {
  const response = await fetch(`${API_BASE_URL}${path}${buildQuery(params)}`);

  if (!response.ok) {
    const fallbackMessage = `Request failed: ${response.status}`;
    let message = fallbackMessage;

    try {
      const payload = await response.json();
      const raw = payload?.detail || payload?.message;
      message = Array.isArray(raw)
        ? raw.map((e) => e?.msg || JSON.stringify(e)).join("; ")
        : raw || fallbackMessage;
    } catch {
      try {
        const text = await response.text();
        if (text) {
          message = text;
        }
      } catch {
        message = fallbackMessage;
      }
    }

    throw new Error(message);
  }

  return response.json();
}

export { API_BASE_URL };