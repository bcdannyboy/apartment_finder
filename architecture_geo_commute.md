# Geo and Commute (Authoritative)

## Providers
- Geocoding: Pelias (primary), Nominatim (optional fallback), local-only.
- Transit routing: OpenTripPlanner (OTP), local-only.
- Walk/bike/drive routing: Valhalla (primary), OSRM (secondary option), local-only.

## Provider enums
- GeoProvider: pelias | nominatim
- RoutingProvider: otp | valhalla | osrm
- CommuteMode: transit | walk | bike | drive

## 511 GTFS
- 511 GTFS is desired and stored locally.
- No redistribution of GTFS files or derived artifacts.

## Cache keys
- Commute cache key: (origin_h3, anchor_id, mode, time_bucket)

## Constraints
- No paid geocoding or routing APIs.
- All geo/routing services bind to localhost or local container network.
