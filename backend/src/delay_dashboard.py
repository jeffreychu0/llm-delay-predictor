import argparse
import sqlite3
from datetime import datetime, timedelta, timezone

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.widgets import Button

from db.init_db import DB_PATH


def parse_args():
    parser = argparse.ArgumentParser(
        description="Live delay dashboard for train_observations"
    )
    parser.add_argument(
        "--refresh-seconds",
        type=float,
        default=3.0,
        help="How often to refresh the chart",
    )
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=60,
        help="Time window (minutes) for plotting recent points",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=2000,
        help="Maximum rows to query each refresh",
    )
    parser.add_argument(
        "--bucket-seconds",
        type=int,
        default=30,
        help="Time-bucket size in seconds for averaging burst data",
    )
    parser.add_argument(
        "--routes",
        type=str,
        default="",
        help="Comma-separated route filter (example: A,C,E). Empty means all routes.",
    )
    return parser.parse_args()


def get_coverage_stats(conn, route_filter, window_minutes):
    """Return per-route matched vs. null-delay counts within the time window."""
    cursor = conn.cursor()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()

    if route_filter:
        placeholders = ",".join(["?"] * len(route_filter))
        query = f'''
            SELECT route_id,
                   COUNT(*) AS total,
                   SUM(CASE WHEN delay_seconds IS NOT NULL THEN 1 ELSE 0 END) AS matched
            FROM train_observations
            WHERE timestamp >= ?
              AND route_id IN ({placeholders})
            GROUP BY route_id
        '''
        params = [cutoff, *route_filter]
    else:
        query = '''
            SELECT route_id,
                   COUNT(*) AS total,
                   SUM(CASE WHEN delay_seconds IS NOT NULL THEN 1 ELSE 0 END) AS matched
            FROM train_observations
            WHERE timestamp >= ?
            GROUP BY route_id
        '''
        params = [cutoff]

    cursor.execute(query, params)
    stats = {}
    for route_id, total, matched in cursor.fetchall():
        null_count = total - matched
        stats[route_id] = {
            "total": total,
            "matched": matched,
            "null_count": null_count,
            "pct_null": round(null_count / total * 100, 1) if total > 0 else 0.0,
            "pct_matched": round(matched / total * 100, 1) if total > 0 else 0.0,
        }
    return stats


def get_rows(conn, max_points, route_filter):
    cursor = conn.cursor()
    if route_filter:
        placeholders = ",".join(["?"] * len(route_filter))
        query = f'''
                        SELECT observation_id, route_id, trip_id, timestamp, delay_seconds
            FROM train_observations
            WHERE delay_seconds IS NOT NULL
              AND route_id IN ({placeholders})
            ORDER BY observation_id DESC
            LIMIT ?
        '''
        params = [*route_filter, max_points]
    else:
        query = '''
            SELECT observation_id, route_id, trip_id, timestamp, delay_seconds
            FROM train_observations
            WHERE delay_seconds IS NOT NULL
            ORDER BY observation_id DESC
            LIMIT ?
        '''
        params = [max_points]

    cursor.execute(query, params)
    rows = cursor.fetchall()
    rows.reverse()
    return rows


def parse_timestamp(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts)).replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.strptime(str(ts), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def _floor_to_bucket(dt, bucket_seconds):
    if bucket_seconds <= 1:
        return dt
    epoch = int(dt.timestamp())
    floored = epoch - (epoch % bucket_seconds)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def _aggregate_mean_by_time(rows, bucket_seconds):
    buckets = {}
    for dt, value in rows:
        bucket_dt = _floor_to_bucket(dt, bucket_seconds)
        values = buckets.setdefault(bucket_dt, [])
        values.append(value)

    points = []
    for dt in sorted(buckets.keys()):
        vals = buckets[dt]
        points.append((dt, sum(vals) / len(vals)))
    return points


def build_route_series(rows, window_minutes, bucket_seconds):
    now = datetime.now(timezone.utc)
    min_time = now - timedelta(minutes=window_minutes)
    route_buckets = {}

    for _, route_id, _trip_id, timestamp, delay_seconds in rows:
        dt = parse_timestamp(timestamp)
        if dt is None or dt < min_time:
            continue

        route_points = route_buckets.setdefault(route_id, [])
        route_points.append((dt, delay_seconds))

    by_route = {}
    for route_id, pairs in route_buckets.items():
        agg_points = _aggregate_mean_by_time(pairs, bucket_seconds)
        by_route[route_id] = {
            "x": [p[0] for p in agg_points],
            "y": [p[1] for p in agg_points],
        }

    return by_route


def build_trip_series_for_route(rows, route_id, window_minutes, bucket_seconds):
    now = datetime.now(timezone.utc)
    min_time = now - timedelta(minutes=window_minutes)
    trip_buckets = {}

    for _, row_route_id, trip_id, timestamp, delay_seconds in rows:
        if row_route_id != route_id:
            continue

        dt = parse_timestamp(timestamp)
        if dt is None or dt < min_time:
            continue

        key = trip_id or "unknown_trip"
        trip_points = trip_buckets.setdefault(key, [])
        trip_points.append((dt, delay_seconds))

    by_trip = {}
    for trip_id, pairs in trip_buckets.items():
        agg_points = _aggregate_mean_by_time(pairs, bucket_seconds)
        by_trip[trip_id] = {
            "x": [p[0] for p in agg_points],
            "y": [p[1] for p in agg_points],
        }

    return by_trip


def compute_stats(values):
    if not values:
        return 0, 0.0, 0.0

    n = len(values)
    mean = sum(values) / n
    if n == 1:
        return n, mean, 0.0

    variance = sum((v - mean) ** 2 for v in values) / n
    stddev = variance ** 0.5
    return n, mean, stddev


def draw_coverage_bars(ax, coverage_stats):
    """Horizontal stacked bar chart: matched (blue) vs null-delay (red) per route."""
    ax.clear()
    if not coverage_stats:
        ax.text(0.5, 0.5, "No coverage data", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        return

    routes = sorted(coverage_stats.keys())
    matched_pcts = [coverage_stats[r]["pct_matched"] for r in routes]
    null_pcts = [coverage_stats[r]["pct_null"] for r in routes]
    y_pos = list(range(len(routes)))

    ax.barh(y_pos, matched_pcts, color="steelblue", label="Matched", height=0.6)
    ax.barh(y_pos, null_pcts, left=matched_pcts, color="tomato", label="Null delay", height=0.6)

    for i, route in enumerate(routes):
        pct_null = null_pcts[i]
        total = coverage_stats[route]["total"]
        if pct_null >= 5:
            ax.text(
                matched_pcts[i] + pct_null / 2, i,
                f"{pct_null:.0f}%",
                ha="center", va="center", fontsize=8, color="white", fontweight="bold",
            )
        ax.text(102, i, f"n={total}", ha="left", va="center", fontsize=8)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(routes, fontsize=9)
    ax.set_xlim(0, 115)
    ax.set_xlabel("% of observations", fontsize=9)
    ax.set_title("Match coverage", fontsize=10)
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="x", alpha=0.3)


def render_stats_text(by_route, coverage_stats=None):
    lines = ["Route stats (N / avg / std / null%):"]
    for route_id in sorted(by_route.keys()):
        y = by_route[route_id]["y"]
        n, mean, stddev = compute_stats(y)
        cov = coverage_stats.get(route_id) if coverage_stats else None
        null_str = f"  null={cov['pct_null']:.0f}% ({cov['null_count']}/{cov['total']})" if cov else ""
        lines.append(f"{route_id}: {n} / {mean:.1f}s / {stddev:.1f}s{null_str}")

    all_values = []
    for route_data in by_route.values():
        all_values.extend(route_data["y"])

    n_all, mean_all, std_all = compute_stats(all_values)
    lines.append("")
    lines.append(f"All routes: {n_all} / {mean_all:.1f}s / {std_all:.1f}s")
    return "\n".join(lines)


def render_route_trip_stats(route_id, by_trip):
    lines = [f"Route {route_id} trip stats (N / avg / std):"]

    sortable = []
    for trip_id, data in by_trip.items():
        y = data["y"]
        n, mean, stddev = compute_stats(y)
        sortable.append((n, trip_id, mean, stddev))

    sortable.sort(reverse=True)
    for n, trip_id, mean, stddev in sortable[:12]:
        lines.append(f"{trip_id}: {n} / {mean:.1f}s / {stddev:.1f}s")

    all_values = []
    for data in by_trip.values():
        all_values.extend(data["y"])

    n_all, mean_all, std_all = compute_stats(all_values)
    lines.append("")
    lines.append(f"Route total: {n_all} / {mean_all:.1f}s / {std_all:.1f}s")
    return "\n".join(lines)


def main():
    args = parse_args()
    route_filter = [r.strip() for r in args.routes.split(",") if r.strip()] if args.routes else []

    conn = sqlite3.connect(DB_PATH + "/mta.db")

    fig = plt.figure(figsize=(16, 9))
    gs = fig.add_gridspec(2, 2, height_ratios=[3, 1], width_ratios=[3, 2], hspace=0.35, wspace=0.35)
    ax_plot = fig.add_subplot(gs[0, :])
    ax_stats = fig.add_subplot(gs[1, 0])
    ax_coverage = fig.add_subplot(gs[1, 1])

    fig.suptitle("Live Delay Dashboard", fontsize=14)
    ax_stats.axis("off")
    plt.subplots_adjust(top=0.86)

    color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    state = {
        "active_tab": "Overview",
        "available_routes": [],
        "tab_buttons": [],
        "tab_axes": [],
    }

    def set_active_tab(label):
        state["active_tab"] = label

    def rebuild_tab_bar(routes):
        if routes == state["available_routes"]:
            return

        for btn in state["tab_buttons"]:
            btn.disconnect_events()
        for ax in state["tab_axes"]:
            ax.remove()

        state["tab_buttons"] = []
        state["tab_axes"] = []
        state["available_routes"] = list(routes)

        labels = ["Overview"] + list(routes)
        count = len(labels)
        if count == 0:
            return

        left = 0.06
        right = 0.98
        total_width = max(0.1, right - left)
        width = min(0.12, total_width / max(1, count))
        gap = 0.005
        y = 0.89
        height = 0.045

        x = left
        for label in labels:
            if x + width > right:
                break
            tab_ax = fig.add_axes([x, y, width, height])
            button = Button(tab_ax, label)
            button.on_clicked(lambda _evt, lbl=label: set_active_tab(lbl))
            state["tab_axes"].append(tab_ax)
            state["tab_buttons"].append(button)
            x += width + gap

        if state["active_tab"] not in labels:
            state["active_tab"] = "Overview"

    def draw_overview(by_route, coverage_stats):
        for i, route_id in enumerate(sorted(by_route.keys())):
            route_data = by_route[route_id]
            color = color_cycle[i % len(color_cycle)] if color_cycle else None
            ax_plot.plot(
                route_data["x"],
                route_data["y"],
                marker="o",
                markersize=3,
                linewidth=1.5,
                color=color,
                label=route_id,
                alpha=0.9,
            )

        ax_plot.set_title("Route delay means by pull time")
        ax_plot.legend(title="Route", loc="upper left", ncol=2)

        ax_stats.clear()
        ax_stats.axis("off")
        stats_text = render_stats_text(by_route, coverage_stats)
        ax_stats.text(0.01, 0.95, stats_text, va="top", family="monospace", fontsize=10)

    def draw_route_detail(rows, route_id, coverage_stats):
        by_trip = build_trip_series_for_route(rows, route_id, args.window_minutes, args.bucket_seconds)
        if not by_trip:
            ax_plot.text(0.5, 0.5, f"No trip data yet for route {route_id}", ha="center", va="center", transform=ax_plot.transAxes)
            ax_stats.clear()
            ax_stats.axis("off")
            ax_stats.text(0.01, 0.95, f"Waiting for route {route_id} rows...", va="top", family="monospace")
            return

        # Show busiest trip_ids first to keep the chart readable.
        ranked = sorted(by_trip.items(), key=lambda item: len(item[1]["y"]), reverse=True)
        top = ranked[:10]

        for i, (trip_id, trip_data) in enumerate(top):
            color = color_cycle[i % len(color_cycle)] if color_cycle else None
            ax_plot.plot(
                trip_data["x"],
                trip_data["y"],
                marker="o",
                markersize=2.5,
                linewidth=1.2,
                color=color,
                label=trip_id,
                alpha=0.9,
            )

        ax_plot.set_title(f"Route {route_id}: trip_id delay means by pull time (top 10 trips)")
        ax_plot.legend(title="Trip ID", loc="upper left", fontsize=8)

        ax_stats.clear()
        ax_stats.axis("off")
        stats_text = render_route_trip_stats(route_id, by_trip)
        # Append null coverage for this specific route below the trip stats.
        cov = coverage_stats.get(route_id) if coverage_stats else None
        if cov:
            stats_text += f"\n\nMatch coverage: {cov['pct_matched']:.0f}% ({cov['matched']}/{cov['total']})"
        ax_stats.text(0.01, 0.95, stats_text, va="top", family="monospace", fontsize=9)

    def update(_frame):
        rows = get_rows(conn, args.max_points, route_filter)
        by_route = build_route_series(rows, args.window_minutes, args.bucket_seconds)
        coverage_stats = get_coverage_stats(conn, route_filter, args.window_minutes)

        routes = sorted(by_route.keys())
        rebuild_tab_bar(routes)

        ax_plot.clear()
        ax_plot.axhline(0, color="gray", linewidth=1, linestyle="--")
        ax_plot.set_xlabel("Time (UTC)")
        ax_plot.set_ylabel("Delay seconds")
        ax_plot.grid(alpha=0.3)

        draw_coverage_bars(ax_coverage, coverage_stats)

        if not by_route:
            ax_plot.text(0.5, 0.5, "No delay data yet", ha="center", va="center", transform=ax_plot.transAxes)
            ax_stats.clear()
            ax_stats.axis("off")
            ax_stats.text(0.01, 0.95, "Waiting for rows in train_observations...", va="top", family="monospace")
            return

        if state["active_tab"] == "Overview":
            draw_overview(by_route, coverage_stats)
        else:
            draw_route_detail(rows, state["active_tab"], coverage_stats)

        ax_plot.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        fig.autofmt_xdate(rotation=15)

    interval_ms = int(max(args.refresh_seconds, 0.5) * 1000)
    _ani = FuncAnimation(fig, update, interval=interval_ms)

    try:
        plt.tight_layout()
        plt.show()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
