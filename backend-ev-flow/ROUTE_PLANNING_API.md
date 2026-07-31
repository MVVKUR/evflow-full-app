# Route planning API (Epic 2)

What the trip-planning and navigation screens talk to. Every example below was
captured from a running server against the seeded database, so the numbers are
real rather than illustrative.

The interactive spec at `<base>/docs` is always the source of truth. This file
explains the parts that are easy to get wrong.

## Contents

1. [What you have to change](#1-what-you-have-to-change)
2. [Auth](#2-auth)
3. [POST /api/v1/route-plans](#3-post-apiv1route-plans)
4. [route_status is the field that drives the UI](#4-route_status-is-the-field-that-drives-the-ui)
5. [Reading a charging stop](#5-reading-a-charging-stop)
6. [POST /api/v1/route-plans/active/evaluate](#6-post-apiv1route-plansactiveevaluate)
7. [DELETE /api/v1/route-plans/{id}](#7-delete-apiv1route-plansid)
8. [Destination search](#8-destination-search)
9. [The service area](#9-the-service-area)
10. [Things that will bite you](#10-things-that-will-bite-you)
11. [GET /api/v1/stations/{id}/status](#11-get-apiv1stationsidstatus)
12. [GET /api/v1/stations/{id}/occupancy](#12-get-apiv1stationsidoccupancy)

---

## 1. What you have to change

Nothing you already send has changed meaning. Existing fields kept their names
and their semantics, so the screens you have today keep working. Three things
are new:

| # | Change | Why |
|---|--------|-----|
| 1 | Call `POST /api/v1/route-plans/active/evaluate` while navigating | AC 2.1.1 and AC 2.4.2 |
| 2 | Send `waypoint_station_id` when the driver taps "Add Stop to Route" | AC 2.2.5 |
| 3 | Branch on `route_status` instead of inferring state yourself | AC 2.1.2, 2.1.3, 2.2.6 |

Two smaller ones, both optional:

- Stop sending `minimum_arrival_soc_pct`. Leave it out and the server applies
  the configured reserve, so the threshold lives in one place.
- `steps` and `estimated_arrival_at` are now returned, which is what the
  navigation view needs for "next instruction" and arrival time.

---

## 2. Auth

`Authorization: Bearer <token>` from `POST /api/v1/auth/login` or
`/auth/register`, same as the charging and wallet endpoints. `getAuthHeaders()`
in `@evflow/shared` already produces it.

The two geocoding endpoints are the exception. They take no token on purpose,
because the demo password ships inside the web bundle and a token there would
prove nothing while breaking the destination picker for anyone not signed in.
They are protected by rate limits and a cache instead.

---

## 3. POST /api/v1/route-plans

### Request

```json
{
  "origin":      { "latitude": -6.2088, "longitude": 106.8456, "label": "Monas" },
  "destination": { "latitude": -6.5971, "longitude": 106.7996, "label": "Bogor" },
  "current_soc_pct": 75,
  "preferences": {
    "route_type": "fastest",
    "maximum_detour_km": 8,
    "prefer_fast_charging": true
  }
}
```

Only `origin`, `destination` and `current_soc_pct` are required.

Where the vehicle comes from, in the order the server tries:

1. `vehicle: { usable_range_km, battery_kwh?, name? }` in the body
2. `ev_model_id` in the body
3. the signed-in user's saved profile

Send nothing and a driver with a saved profile is planned for. A driver without
one gets `409`, which is your cue to ask for a car or a range. An unknown
`ev_model_id` gives `404`.

### Response, direct route

```json
{
  "route_plan_id": "plan-3fc3c3a1578b",
  "route_status": "direct_route_available",
  "directly_reachable": true,
  "margin_is_tight": false,
  "charging_stops": [],
  "warning": null,
  "summary": {
    "distance_km": 50.76,
    "duration_minutes": 45.2,
    "estimated_energy_kwh": 6.71,
    "estimated_arrival_soc_pct": 49.9,
    "minimum_arrival_soc_pct": 20.0,
    "effective_reserve_km": 46.4,
    "direct_arrival_soc_pct": 49.9,
    "soc_margin_pct": 29.9,
    "computed_at": "2026-07-27T06:33:16.643219Z",
    "estimated_arrival_at": "2026-07-27T07:18:28.643219Z"
  }
}
```

`estimated_arrival_at` is computed on the server and already includes charging
time when there is a stop. Render it directly instead of adding
`duration_minutes` to the device clock, otherwise two phones with slightly
different clocks disagree about the same trip.

### Response, out of area

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "destination"],
      "msg": "Value error, outside the configured route service area 'Indonesia (national SPKLU coverage)' (latitude -11.2 to 6.3, longitude 94.6 to 141.3)"
    }
  ]
}
```

HTTP `422`, and no route is generated. `detail[].loc` names the field, so you can
attach the message to the right input rather than showing a general failure.
Battery outside 0 to 100 behaves the same way with `loc` of
`["body", "current_soc_pct"]`.

---

## 4. route_status is the field that drives the UI

One field decides what the screen shows.

| Value | Meaning | What to render |
|-------|---------|----------------|
| `direct_route_available` | Arrives above the reserve without charging | Green state. `charging_stops` is guaranteed empty, `warning` is null |
| `charging_required` | Cannot reach the destination with the reserve intact | Show `charging_stops`, plus `warning` |
| `no_suitable_station` | Charging is needed, nothing usable was found | Explain, and offer the actions in `warning.suggested_actions` |

You do not need to filter `charging_stops` yourself. On a direct route the
server empties it and sets `recommended_stop` to null, so a stale stop can never
leak into the green state.

`margin_is_tight` is separate from the status. It is true when the arrival
battery clears the reserve but not by much, which is a good trigger for an amber
badge. The route is still direct, so keep hiding the stop list.

For `no_suitable_station`, `warning.suggested_actions` carries a fixed
vocabulary you can map to buttons:

```
choose_another_route | adjust_preferences | charge_before_departure
```

It is populated for that status. On `charging_required` it is empty, because the
plan already contains the answer.

---

## 5. Reading a charging stop

Each entry in `charging_stops` carries the full `station` object plus the fields
below. This is a real stop from Jakarta to Bandung in a Wuling Air EV:

```json
{
  "detour_km": 7.7,
  "distance_basis": "road",
  "arrival_soc_pct": 51.1,
  "recommended_target_soc_pct": 95.8,
  "projected_destination_soc_pct": 20.0,
  "completes_trip": true,
  "blocking_reasons": [],
  "energy_to_add_kwh": 11.93,
  "estimated_charging_minutes": 39.4,
  "effective_charging_power_kw": 20.0,
  "matched_connector_type": "AC Type 2",
  "connector_match_inferred": true,
  "available_connector_count": 1,
  "available_by_type": { "AC Type 2": 1, "CCS2": 6 },
  "total_connector_count": 7,
  "best_available_power_kw": 22.0,
  "detour_budget_km": 8.0,
  "detour_within_budget": true
}
```

Worth knowing:

- `available_connector_count` counts plugs that are free **and** usable by this
  car. Here the station has 7 plugs and 6 free CCS2 ones, but the Air EV cannot
  take CCS2, so the usable count is 1. Showing `total_connector_count` alone
  would tell the driver something untrue.
- `connector_match_inferred: true` means the match relies on the assumption that
  every EV has an AC Type 2 inlet. It is a safe assumption in Indonesia, but it
  is an assumption, so label it the way the map already labels inferred
  connector types.
- `completes_trip` is the honest one. A stop can be reachable and compatible and
  still leave the driver short. When it is false, `blocking_reasons` says why.
- `effective_charging_power_kw` is the lower of the station power and what the
  car can take. In the example the station offers 22 kW and the car accepts 20,
  so 39 minutes is the real figure rather than the optimistic one.
- `detour_within_budget: false` means every candidate exceeded
  `maximum_detour_km` and this was the least bad. The stop is still valid. Say so
  rather than hiding it.

---

## 6. POST /api/v1/route-plans/active/evaluate

Call this while navigation is running. It answers AC 2.1.1 and AC 2.4.2.

```json
{
  "current_position": { "latitude": -6.45, "longitude": 106.82 },
  "destination":      { "latitude": -6.9175, "longitude": 107.6191 },
  "current_soc_pct": 18,
  "route_plan_id": "plan-3fc3c3a1578b"
}
```

Response, trimmed:

```json
{
  "route_status": "charging_required",
  "projected_arrival_soc_pct": 0.0,
  "raw_projected_arrival_soc_pct": -51.4,
  "remaining_distance_km": 140.06,
  "remaining_duration_minutes": 118.4,
  "estimated_arrival_at": "2026-07-27T08:31:44Z",
  "warning": {
    "triggered": true,
    "code": "battery_below_reserve",
    "severity": "critical",
    "message": "Projected arrival battery is -51%, below your 20% reserve. Add a charging stop to reach your destination safely.",
    "shortfall_soc_pct": 71.4,
    "can_dismiss": true
  },
  "candidate_stops": [],
  "out_of_service_area": false,
  "advisories": []
}
```

The three actions in AC 2.1.1 map straight onto this:

- **view available stations** is `candidate_stops`, already ranked
- **add as a stop** is `waypoint_station_id` on a fresh `POST /route-plans`
- **dismiss and continue** is `warning.can_dismiss`

Two fields are easy to confuse. `projected_arrival_soc_pct` is clamped to 0 to
100 and is what you display. `raw_projected_arrival_soc_pct` can go negative, as
above, and is what tells you how badly short the driver is. Use the raw one for
severity, never for a battery gauge.

Crossing the service-area boundary does not stop this endpoint from answering.
You get a normal evaluation plus `out_of_service_area: true` and an entry in
`advisories`. A driver who is already on the road still needs the battery
warning, so the boundary is enforced when planning and only advised while
driving. `warning` stays reserved for the battery, and an advisory can never
push it aside.

Polling every 15 to 30 seconds, or on a meaningful position change, is enough.
There is no server-side session, so calls are independent.

---

## 7. DELETE /api/v1/route-plans/{id}

Call this on End Navigation. Returns `204`.

Route plans are never stored, so there is no record to remove. What this does
delete is the coordinate cached by any `/geocoding/reverse` call the session
made, which is the one place a position lingers. Pass the same `route_plan_id`
you sent to `/geocoding/reverse` and only that session's entries go.

Skipping it is not a disaster. Those entries expire on their own within 30
seconds, swept by a background task, so AC 2.3.3 holds either way. Calling it
makes the deletion immediate.

---

## 8. Destination search

`GET /api/v1/geocoding/search?q=Bandung&lat=-6.2088&lon=106.8456&limit=5`

Unchanged, apart from one addition worth reading carefully.

`distance_km` still means distance from the position the caller supplied, and is
still null when no position was sent. That did not change, so your current
rendering stays correct.

When the driver has no GPS fix, the estimate now arrives in a different field:

```json
{
  "label": "Bandung",
  "distance_km": null,
  "distance_from_reference_km": 115.2,
  "distance_from": "reference_point",
  "distance_reference_label": "Jakarta",
  "in_service_area": true
}
```

They are deliberately separate. A distance measured from Jakarta city centre is
useful, but shown in `distance_km` it would read as "115 km from you" to someone
standing in Bandung. Use `distance_from` to pick the field and the label:
`"115 km from Jakarta"` rather than `"115 km away"`.

`in_service_area` tells you whether the planner would accept this suggestion.
Add `&in_service_area_only=true` to drop the rest, or keep them and grey them
out. Either way the picker stops offering destinations the planner then refuses.

---

## 9. The service area

A bounding box, configured by environment variable, that origins and
destinations must fall inside. The default covers Indonesia, which is the
footprint the station dataset actually describes. Every one of the 2,931 seeded
stations is inside it.

It is enforced on `POST /api/v1/route-plans` with a `422`, and only advised on
`/active/evaluate`. Search results carry `in_service_area` computed from the same
values, so the three surfaces cannot drift apart.

Being a rectangle over an archipelago, it also admits Singapore and parts of
Malaysia. A request there is accepted, finds no stations, and comes back as
`no_suitable_station`. That is a truthful answer rather than an invented route.

---

## 10. Things that will bite you

**Do not add `duration_minutes` to the device clock.** Use
`estimated_arrival_at`. It is anchored on the server and includes charging time.

**Do not read `total_connector_count` as availability.** It counts every plug at
the station, including ones in use and ones this car cannot use. The field you
want is `available_connector_count`.

**Do not treat `projected_arrival_soc_pct` as the severity.** It is clamped at 0.
A driver 51 points short and a driver 1 point short both show 0. Use
`raw_projected_arrival_soc_pct` or `warning.shortfall_soc_pct`.

**Do not send your own `minimum_arrival_soc_pct` unless a user set it.** The
server reserve is 20 percent plus a floor in kilometres, because 20 percent of a
small pack is only about 40 km. Overriding it silently weakens the guarantee.

**Check `turn_by_turn_available` in `assumptions` before promising navigation.**
Routing falls back to a straight line when the OSRM demo server is slow or down.
The response is still `200`, but `steps` collapses to a single placeholder. The
flag tells you the difference so the UI can say the route is approximate.

**A `422` is per field.** Read `detail[].loc` and attach the message to that
input. Showing one general error for every validation failure wastes the field
information the API sends.

**Do not render a null `waiting_time` as "~0 mins".** On
`/stations/{id}/status`, null means nobody knows and `0` means a plug is free
right now. They are opposite answers, and printing the first as the second
promises the driver a bay that may be hours away. Section 11.

**Do not index occupancy days with `Date.getDay()`.** `day_of_week` is ISO, so
`1` is Monday and `7` is Sunday, while `getDay()` is `0` for Sunday. Used as an
array index it shifts every bar by a day. Section 12.

---

## 11. GET /api/v1/stations/{id}/status

Live counts and the wait estimate for one station. This is US 3.2, and this file
used to say it did not exist. It does.

No token, like the other `/stations` endpoints. An unknown id gives `404`.

Unlike the rest of this file, the body below is illustrative rather than
captured: the shape is settled and shipping, and the numbers are picked to show
every case at once.

```json
{
  "station_id": "pln_spklu-6",
  "station_status": 1,
  "available": 3,
  "total": 8,
  "in_use": 4,
  "out_of_service": 1,
  "waiting_time": 0,
  "connectors": [
    { "type": "CCS2", "speed_tier": "fast", "power_kw": 50.0,
      "available": 0, "total": 3, "in_use": 3, "out_of_service": 0, "waiting_time": 12.4 },
    { "type": "CCS2", "speed_tier": "fast", "power_kw": 25.0,
      "available": 0, "total": 2, "in_use": 1, "out_of_service": 1, "waiting_time": null },
    { "type": "AC Type 2", "speed_tier": "medium", "power_kw": 22.0,
      "available": 3, "total": 3, "in_use": 0, "out_of_service": 0, "waiting_time": 0 }
  ]
}
```

The station block and each `connectors` entry carry the same six fields with the
same meanings. The entries are one per `(type, speed_tier, power_kw)` group, and
the station block is their sum.

Worth knowing:

- **Every count is an integer.** `available`, `total`, `in_use` and
  `out_of_service` are numbers at both levels, never quoted strings. Sorting and
  arithmetic work without parsing.
- **`total` is `available + in_use + out_of_service`.** Do not compute occupancy
  as `total - available`. That folds the broken plugs into the busy ones, and a
  charger that is never going to free up gets shown to the driver as in use with
  a short wait. `out_of_service` is sent so you can say "out of service" instead.
- **`waiting_time` is minutes, and null is a value.** `0` means at least one plug
  in this group, or anywhere at the station, is free right now. A positive number
  means none is free and this is when the session finishing soonest ends. `null`
  means none is free *and* no estimate exists: no active session on record, no
  power to divide by. The second CCS2 group above is that case. Say the wait is
  unknown; do not print it as zero and do not fill it in with an average.
- **The type is the same at both levels.** A float or null in `connectors`, a
  float or null on the station. The station value is the soonest wait across the
  groups, so it is `0` whenever `available > 0`.
- **`power_kw` is part of a group's identity.** The two CCS2 fast rows above are
  not duplicates: they are 50 kW plugs and 25 kW plugs, and that is the field
  telling them apart. Show it. It is null only when the source data never
  reported a power.
- **`station_status`** is `1` when at least one plug at the station is free and
  `0` when none is, which is exactly `available > 0`. It is the map pin colour,
  nothing more.
- A station with no connectors on record answers `200` with zeroes, `connectors`
  empty, `station_status` `0` and `waiting_time` null, by the same rule as above.

`GET /api/v1/stations/{id}/availability` still returns the same four counts
without the wait estimate or the per-group breakdown. Nothing about it changed,
so keep calling it where that is all you need.

---

## 12. GET /api/v1/stations/{id}/occupancy

Historical hourly occupancy for one station, which is the peak-hours chart in
US 3.3. Also live, also previously described here as having neither an endpoint
nor any data. It has both.

No token. An unknown id gives `404`.

Illustrative again, and trimmed to three hours of one day:

```json
{
  "station_id": "pln_spklu-6",
  "days": [
    {
      "day_of_week": 1,
      "day_name": "Monday",
      "hours": [
        { "hour_of_day": 0,  "avg_occupancy": 4.2,  "occupancy_level": "LOW" },
        { "hour_of_day": 8,  "avg_occupancy": 46.0, "occupancy_level": "MODERATE" },
        { "hour_of_day": 18, "avg_occupancy": 87.5, "occupancy_level": "PEAK" }
      ]
    }
  ]
}
```

Worth knowing:

- **`day_of_week` is ISO: 1 is Monday, 7 is Sunday.** JavaScript's
  `Date.getDay()` is 0 for Sunday through 6 for Saturday, so the two do not line
  up anywhere. `days[today.getDay()]` is wrong for every day of the week. Match
  on the `day_of_week` value, or use `day_name`, which the server sends so you do
  not have to keep a label array in sync.
- **`avg_occupancy` is a percentage, 0 to 100.** It is the average share of the
  station's connectors busy in that hour, not a plug count and not a 0-to-1
  fraction.
- **`occupancy_level` is classified server-side** at 20, 50 and 80 percent into
  `LOW`, `MODERATE`, `BUSY`, `PEAK`. Render it rather than re-deriving the
  buckets, otherwise the thresholds live in two places and drift apart.
- **You get the hours that are on record, not a full grid.** Days and hours are
  both sparse. Key off `day_of_week` and `hour_of_day` instead of array position,
  or an absent 3am shifts the whole evening.
- Rows arrive sorted by day then hour, so plotting in order needs no sort.
- A station with no history returns `days: []`. Render that as "not enough data
  yet". A chart flat at zero reads as "always empty", which is a different claim.

This is aggregated history and says nothing about right now. "How busy is it at
6pm on a Friday" is this endpoint; "can I plug in when I arrive" is section 11.

---

## Epic 3 backend status

One gap left, not three. If you planned around an earlier version of this file
that said none of this existed, this is the part to re-read.

| User story | State |
|------------|-------|
| US 3.1 Real-time availability | Live: `GET /api/v1/stations/{id}/availability` and `GET /api/v1/stations/{id}/connectors` |
| US 3.2 Estimated wait time | Live: `GET /api/v1/stations/{id}/status`, section 11 |
| US 3.3 Peak hours chart | Live: `GET /api/v1/stations/{id}/occupancy`, section 12 |
| US 3.4 Alternative station suggestion | Not built. Alternatives exist inside a route plan, but there is still no standalone endpoint |
