"""Builds the structured context dict consumed by templates/home.html.

Aggregates per-team / per-Product-Area stats from existing services. No new
DB queries beyond what `team_service`, `sprint_service`, and `trend_service`
already expose.

Backfill of teams.space_name is handled here (opportunistic, on first home load
where any team has NULL space_name)."""

import logging
from datetime import datetime, timezone
from src.services import team_service
from src.services.sprint_service import get_team_sprints, get_sprint_status
from src.services.trend_service import get_sprint_summary
from src.clickup_client import ClickUpError

log = logging.getLogger(__name__)

SPARKLINE_LEN = 8  # last N closed sprints used for the velocity sparkline


def _humanize_ago(iso_ts: str | None) -> str:
    """Return a short relative-time string like '2h ago' / '3 days ago'.
    Returns 'never' if iso_ts is None / unparseable."""
    if not iso_ts:
        return "never"
    try:
        # Normalise: if it has 'Z' suffix or '+offset', strip to naive UTC
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError):
        return "unknown"
    now = datetime.utcnow()
    delta = now - ts
    secs = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    days = secs // 86400
    if days < 14:
        return f"{days} day{'s' if days != 1 else ''} ago"
    weeks = days // 7
    return f"{weeks} week{'s' if weeks != 1 else ''} ago"


def _team_card(team: dict) -> dict:
    """Build the per-team card payload."""
    sprints = get_team_sprints(team["id"])
    for s in sprints:
        s["status"] = get_sprint_status(s)

    active = next((s for s in sprints if s["status"] == "active"), None)
    closed_sprints = [s for s in sprints if s["status"] == "closed"]
    closed_sorted = sorted(
        closed_sprints,
        key=lambda s: str(s.get("end_date") or s.get("start_date") or ""),
    )

    last_closed = None
    if closed_sorted:
        latest = closed_sorted[-1]
        summary = get_sprint_summary(latest["id"])
        last_closed = {
            "name": latest["name"],
            "completion": summary.get("completion_rate", 0),
            "ago": _humanize_ago(str(latest.get("end_date") or latest.get("start_date") or "")),
        }

    sparkline = []
    for s in closed_sorted[-SPARKLINE_LEN:]:
        summary = get_sprint_summary(s["id"])
        sparkline.append(round(summary.get("velocity", 0)))

    active_card = None
    if active:
        active_card = {"id": active["id"], "name": active["name"]}

    return {
        "id": team["id"],
        "name": team["name"],
        "metric_type": team.get("metric_type", "task_count"),
        "active_sprint": active_card,
        "last_closed": last_closed,
        "velocity_sparkline": sparkline,
        "_closed_count": len(closed_sprints),
        "_closed_summaries": [get_sprint_summary(s["id"]) for s in closed_sorted],
    }


def _area_stats(team_cards: list[dict]) -> dict:
    """Roll up stats across the teams in a single Product Area."""
    active_count = sum(1 for c in team_cards if c["active_sprint"])
    closed_count = sum(c["_closed_count"] for c in team_cards)
    velocities = [
        s.get("velocity", 0)
        for c in team_cards
        for s in c["_closed_summaries"]
    ]
    completions = [
        s.get("completion_rate", 0)
        for c in team_cards
        for s in c["_closed_summaries"]
    ]
    return {
        "active_sprints": active_count,
        "closed_sprints": closed_count,
        "avg_velocity": round(sum(velocities) / len(velocities)) if velocities else 0,
        "avg_completion": (sum(completions) / len(completions)) if completions else 0,
    }


async def _backfill_space_names(client, teams: list[dict]) -> None:
    """Populate teams.space_name for any rows where it's NULL.
    Mutates `teams` in place so callers see the updated values without re-querying."""
    needing = [t for t in teams if not t.get("space_name")]
    if not needing:
        return

    # Group by workspace_id so we minimise API calls (one /space list per workspace)
    workspace_ids = {
        t.get("clickup_workspace_id") or ""
        for t in needing
        if t.get("clickup_workspace_id")
    }
    if not workspace_ids:
        return

    name_by_id: dict[str, str] = {}
    for ws_id in workspace_ids:
        try:
            spaces = await client.get_spaces(ws_id)
            for s in spaces:
                name_by_id[s["id"]] = s["name"]
        except ClickUpError as e:
            log.warning("Could not backfill space_name for ws=%s: %s", ws_id, e)
        except Exception:
            log.exception("Unexpected error backfilling space names for ws=%s", ws_id)

    for t in needing:
        name = name_by_id.get(t.get("clickup_space_id") or "")
        if name:
            team_service.update_team(t["id"], space_name=name)
            t["space_name"] = name


def _group_by_area(teams_with_cards: list[tuple[dict, dict]]) -> list[dict]:
    """Group (team_row, team_card) tuples by space_name. Sort areas + teams alphabetically."""
    areas: dict[str, list[tuple[dict, dict]]] = {}
    for team_row, card in teams_with_cards:
        key = team_row.get("space_name") or "(unassigned)"
        areas.setdefault(key, []).append((team_row, card))

    result = []
    for area_name in sorted(areas.keys(), key=str.lower):
        members = sorted(areas[area_name], key=lambda pair: str(pair[0].get("name") or "").lower())
        team_cards = [card for _, card in members]
        space_id = members[0][0].get("clickup_space_id") if members else None
        result.append({
            "space_id": space_id,
            "space_name": area_name,
            "teams": [_strip_internal(c) for c in team_cards],
            "stats": _area_stats(team_cards),
        })
    return result


def _strip_internal(card: dict) -> dict:
    """Remove keys prefixed with `_` so the template never sees them."""
    return {k: v for k, v in card.items() if not k.startswith("_")}


def _last_activity_label(cards: list[dict]) -> str:
    """Return the freshest 'ago' label across team last_closed entries.
    Returns 'never' if no team has any closed sprint."""
    candidates = [c["last_closed"]["ago"] for c in cards if c.get("last_closed")]
    if not candidates:
        return "never"
    def _ord(s: str) -> int:
        if "just" in s: return 0
        if s.endswith("m ago"): return 1
        if s.endswith("h ago"): return 2
        if "day" in s: return 3
        return 4
    return sorted(candidates, key=_ord)[0]


async def build_home_context(client, teams: list[dict]) -> dict:
    """Top-level entry point. Mutates `teams` in place via backfill if needed."""
    await _backfill_space_names(client, teams)

    pairs = [(t, _team_card(t)) for t in teams]
    product_areas = _group_by_area(pairs)

    all_cards = [card for _, card in pairs]
    total_closed = sum(c["_closed_count"] for c in all_cards)
    all_completions = [
        s.get("completion_rate", 0) for c in all_cards for s in c["_closed_summaries"]
    ]
    workspace = {
        "total_teams": len(teams),
        "total_areas": len(product_areas),
        "total_closed_sprints": total_closed,
        "avg_completion": (sum(all_completions) / len(all_completions)) if all_completions else 0,
        "last_activity": _last_activity_label(all_cards),
    }

    return {"workspace": workspace, "product_areas": product_areas}
