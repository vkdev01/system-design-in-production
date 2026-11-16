#!/usr/bin/env bash
# Chapter 08: the hot path. Positions update every few seconds per driver; that
# write rate should not hit the relational database.
set -euo pipefail

CITY=ap-south-1

# Latest position per available driver, as a geo set (radius queries)
redis-cli GEOADD "drivers:${CITY}:available" 72.8680 19.0670 driver-abc

# Nearest 10 within 3 km, closest first
redis-cli GEOSEARCH "drivers:${CITY}:available" \
  FROMLONLAT 72.8680 19.0670 BYRADIUS 3 km ASC COUNT 10

# Or per-cell sets, if you want exact ring semantics and cheap sharding
CELL=$(python3 -c "import h3; print(h3.latlng_to_cell(19.0670, 72.8680, 9))")
redis-cli SADD "cell:${CELL}" driver-abc
redis-cli SMEMBERS "cell:${CELL}"

# When a driver moves cells, remove from the old set and add to the new one in a
# single MULTI, or the driver is briefly in two cells and can be double-offered.
