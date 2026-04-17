"""
Unit tests for Agent 1: FAA Airspace Analysis Agent
====================================================
Tests three specified coordinates plus edge cases.

Run with:
    cd backend && python3 -m pytest tests/test_agent_airspace.py -v
"""
import sys
import asyncio
import pytest

sys.path.insert(0, ".")

from app.agents.agent_airspace import (
    run_airspace_agent,
    haversine_nm,
    bearing_degrees,
    classify_airspace,
    compute_airspace_score,
    load_us_airports,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(coro):
    """Run async coroutine in tests (Python 3.10+ compatible)."""
    return asyncio.run(coro)


# ── Geometry unit tests ───────────────────────────────────────────────────────

class TestHaversine:
    def test_zero_distance(self):
        assert haversine_nm(40.0, -74.0, 40.0, -74.0) == 0.0

    def test_known_distance_jfk_to_ewr(self):
        # JFK (40.6413, -73.7781) to EWR (40.6895, -74.1745) ≈ 16 nm
        dist = haversine_nm(40.6413, -73.7781, 40.6895, -74.1745)
        assert 14 <= dist <= 20, f"JFK→EWR expected ~16-18 nm, got {dist:.1f}"

    def test_symmetry(self):
        d1 = haversine_nm(25.79, -80.29, 32.78, -96.80)
        d2 = haversine_nm(32.78, -96.80, 25.79, -80.29)
        assert abs(d1 - d2) < 0.001

    def test_cross_country(self):
        # LAX to JFK ≈ 2,147 nm
        dist = haversine_nm(33.9425, -118.4081, 40.6413, -73.7781)
        assert 2100 <= dist <= 2200, f"LAX→JFK expected ~2147 nm, got {dist:.1f}"


class TestBearing:
    def test_north(self):
        b = bearing_degrees(0.0, 0.0, 1.0, 0.0)
        assert abs(b - 0.0) < 1.0

    def test_east(self):
        b = bearing_degrees(0.0, 0.0, 0.0, 1.0)
        assert abs(b - 90.0) < 1.0

    def test_south(self):
        b = bearing_degrees(1.0, 0.0, 0.0, 0.0)
        assert abs(b - 180.0) < 1.0


# ── Airport loader ────────────────────────────────────────────────────────────

class TestAirportLoader:
    def test_loads_without_error(self):
        airports = load_us_airports()
        assert isinstance(airports, list)
        assert len(airports) > 10000, "Expected 20K+ US airports"

    def test_all_have_lat_lon(self):
        airports = load_us_airports()
        for ap in airports[:500]:
            assert isinstance(ap["lat"], float)
            assert isinstance(ap["lon"], float)
            assert -90 <= ap["lat"] <= 90
            assert -180 <= ap["lon"] <= 180

    def test_includes_heliports(self):
        airports = load_us_airports()
        heliports = [a for a in airports if a["type"] == "heliport"]
        assert len(heliports) > 1000, "Expected 1000+ US heliports"

    def test_excludes_closed(self):
        airports = load_us_airports()
        closed = [a for a in airports if a["type"] == "closed"]
        assert len(closed) == 0

    def test_us_only(self):
        airports = load_us_airports()
        # All should be US — check first 1000
        for ap in airports[:1000]:
            assert ap["state"] != "", "Non-US airport slipped through"


# ── Airspace classification ───────────────────────────────────────────────────

class TestAirspaceClassification:
    def test_empty_airports_returns_class_g(self):
        result = classify_airspace(35.0, -100.0, [])
        assert result["class"] == "G"
        assert result["faa_form_required"] is False

    def test_class_b_major_hub(self):
        # Simulate being 2 nm from JFK (KJFK) — within Class B surface
        fake_nearby = [{
            "ident": "JFK", "icao": "KJFK", "type": "large_airport",
            "name": "JFK International", "state": "NY",
            "distance_nm": 2.0, "bearing_deg": 45.0,
        }]
        result = classify_airspace(40.65, -73.78, fake_nearby)
        assert result["class"] == "B"
        assert result["faa_form_required"] is True
        assert result["part_107_waiver_needed"] is True

    def test_class_b_shelf(self):
        # 12 nm from JFK — inside 20 nm shelf
        fake_nearby = [{
            "ident": "JFK", "icao": "KJFK", "type": "large_airport",
            "name": "JFK International", "state": "NY",
            "distance_nm": 12.0, "bearing_deg": 45.0,
        }]
        result = classify_airspace(40.75, -73.95, fake_nearby)
        assert result["class"] == "B"
        assert result["faa_form_required"] is True
        assert result["part_107_waiver_needed"] is False

    def test_class_c_medium_airport(self):
        fake_nearby = [{
            "ident": "MKE", "icao": "KMKE", "type": "medium_airport",
            "name": "Milwaukee Mitchell", "state": "WI",
            "distance_nm": 3.0, "bearing_deg": 90.0,
        }]
        result = classify_airspace(42.95, -87.90, fake_nearby)
        assert result["class"] == "C"

    def test_class_d_towered_small(self):
        fake_nearby = [{
            "ident": "PDK", "icao": "KPDK", "type": "small_airport",
            "name": "Dekalb-Peachtree Airport", "state": "GA",
            "distance_nm": 2.0, "bearing_deg": 180.0,
        }]
        result = classify_airspace(33.88, -84.30, fake_nearby)
        assert result["class"] == "D"
        assert result["faa_form_required"] is True

    def test_class_d_untowered_no_icao(self):
        """Private strip with no ICAO = no Class D, should be Class E or G."""
        fake_nearby = [{
            "ident": "TX42", "icao": "", "type": "small_airport",
            "name": "Smith Ranch Strip", "state": "TX",
            "distance_nm": 2.0, "bearing_deg": 270.0,
        }]
        result = classify_airspace(29.9, -101.5, fake_nearby)
        assert result["class"] != "D", "Untowered strip should not create Class D"

    def test_class_e_near_airport(self):
        fake_nearby = [{
            "ident": "SFB", "icao": "KSFB", "type": "medium_airport",
            "name": "Orlando Sanford", "state": "FL",
            "distance_nm": 8.0, "bearing_deg": 10.0,
        }]
        result = classify_airspace(28.75, -81.24, fake_nearby)
        assert result["class"] == "E"


# ── Scoring ───────────────────────────────────────────────────────────────────

class TestScoring:
    def test_class_g_rural_max_score(self):
        score = compute_airspace_score("G", nearest_airport_nm=50, heliport_count=0, obstructions_count=0)
        assert score >= 90

    def test_class_b_low_score(self):
        score = compute_airspace_score("B", nearest_airport_nm=1, heliport_count=0, obstructions_count=0)
        assert score <= 20

    def test_heliport_nearby_adds_points(self):
        base = compute_airspace_score("E", 8.0, 0, 0)
        with_heli = compute_airspace_score("E", 8.0, 1, 0)
        assert with_heli > base

    def test_score_bounds(self):
        for cls in ["B", "C", "D", "E", "G"]:
            for dist in [0.5, 3.0, 10.0, 50.0]:
                score = compute_airspace_score(cls, dist, 0, 0)
                assert 0 <= score <= 100, f"Score {score} out of bounds for class {cls} dist {dist}"


# ── Full agent integration tests ──────────────────────────────────────────────

class TestAirspaceAgentIntegration:
    """
    Full end-to-end tests against the three required coordinates.
    These run the complete agent including airport database lookups.
    """

    def test_miami_executive_airport(self):
        """
        Miami Executive Airport (KTMB): 25.6479° N, 80.4298° W
        Expected: Low score (right on top of a towered airport), Class C or D,
        FAA Form 7480-1 required, multiple nearby airports.
        """
        result = run(run_airspace_agent(25.6479, -80.4298))

        assert isinstance(result["score"], int)
        assert isinstance(result["summary"], str)
        assert isinstance(result["warnings"], list)
        assert isinstance(result["raw_data"], dict)

        rd = result["raw_data"]

        # Should detect Miami Executive Airport itself nearby
        assert rd["counts"]["airports_within_5nm"] >= 1, \
            "Should detect Miami Executive Airport within 5nm"

        # Score should be low — sitting on top of a towered airport
        assert result["score"] <= 60, \
            f"Expected low score at Miami Executive, got {result['score']}"

        # FAA coordination definitely required
        assert rd["airspace"]["faa_form_required"] is True, \
            "FAA Form 7480-1 must be required at a towered airport"

        # Should have warnings
        assert len(result["warnings"]) >= 1

        # Airspace should be C, D, or E (definitely controlled)
        assert rd["airspace"]["class"] in ("B", "C", "D", "E"), \
            f"Expected controlled airspace at Miami Executive, got Class {rd['airspace']['class']}"

        print(f"\n  Miami Executive: score={result['score']}/100  class={rd['airspace']['class']}  "
              f"nearest={rd['nearest_airport']['name']} @ {rd['nearest_airport']['distance_nm']} nm")

    def test_manhattan_heliport(self):
        """
        Manhattan Heliport area: 40.7012° N, 74.0072° W
        Expected: Moderate score, Class E (near Newark/JFK/LGA but not in Class B surface),
        multiple heliports nearby, FAA Form 7480-1 required.
        """
        result = run(run_airspace_agent(40.7012, -74.0072))

        rd = result["raw_data"]

        # NYC has dense heliport network
        assert rd["counts"]["heliports_within_10nm"] >= 5, \
            f"Expected 5+ heliports within 10nm of Manhattan, got {rd['counts']['heliports_within_10nm']}"

        # Should detect major airports within 20nm (EWR, JFK, LGA)
        assert rd["counts"]["airports_within_20nm"] >= 3, \
            f"Expected EWR/JFK/LGA within 20nm, got {rd['counts']['airports_within_20nm']}"

        # FAA coordination required in NYC
        assert rd["airspace"]["faa_form_required"] is True

        # Should have at least 2 warnings (dense airspace)
        assert len(result["warnings"]) >= 2

        # Score should reflect moderate complexity
        assert result["score"] <= 90

        # Nearest airport is EWR, JFK, or LGA
        nearest = rd["nearest_airport"]
        assert nearest is not None
        assert nearest["distance_nm"] > 0

        print(f"\n  Manhattan Heliport: score={result['score']}/100  class={rd['airspace']['class']}  "
              f"heliports_10nm={rd['counts']['heliports_within_10nm']}  "
              f"airports_20nm={rd['counts']['airports_within_20nm']}")

    def test_rural_texas_uncontrolled(self):
        """
        Rural Texas (Val Verde County): 29.8970° N, 101.5220° W
        Expected: High score (80+), Class G or E, only untowered private strips nearby,
        minimal regulatory burden.
        """
        result = run(run_airspace_agent(29.8970, -101.5220))

        rd = result["raw_data"]

        # Should be Class G or E (no towered airports nearby)
        assert rd["airspace"]["class"] in ("G", "E"), \
            f"Expected Class G or E in rural Texas, got Class {rd['airspace']['class']}"

        # No Class B/C/D in rural Texas
        assert rd["airspace"]["class"] not in ("B", "C", "D"), \
            "Should not have Class B/C/D airspace in Val Verde County"

        # Score should be HIGH — uncontrolled, ideal for vertiport
        assert result["score"] >= 60, \
            f"Expected high readiness score in rural Texas, got {result['score']}"

        # Part 107 waiver should NOT be required
        assert rd["airspace"]["part_107_waiver_needed"] is False

        # No large/medium airports within 20nm
        assert rd["counts"]["airports_within_10nm"] == 0 or \
               all(a.get("type") == "small_airport" for a in rd["nearby_airports"] if a.get("distance_nm", 99) <= 10), \
            "Expected only small uncontrolled airports in rural Texas"

        print(f"\n  Rural Texas: score={result['score']}/100  class={rd['airspace']['class']}  "
              f"airports_20nm={rd['counts']['airports_within_20nm']}  "
              f"part107_waiver={rd['airspace']['part_107_waiver_needed']}")

    def test_result_schema(self):
        """Verify the agent always returns the expected schema."""
        result = run(run_airspace_agent(32.7767, -96.7970))  # Dallas

        assert "score" in result
        assert "summary" in result
        assert "warnings" in result
        assert "raw_data" in result

        rd = result["raw_data"]
        assert "input" in rd
        assert "airspace" in rd
        assert "nearby_airports" in rd
        assert "nearby_heliports" in rd
        assert "counts" in rd
        assert "analysis_timestamp" in rd

        airspace = rd["airspace"]
        assert "class" in airspace
        assert "faa_form_required" in airspace
        assert "part_107_waiver_needed" in airspace
        assert "notes" in airspace

        assert airspace["class"] in ("B", "C", "D", "E", "G")
        assert 0 <= result["score"] <= 100

        counts = rd["counts"]
        assert all(k in counts for k in [
            "airports_within_5nm", "airports_within_10nm", "airports_within_20nm",
            "heliports_within_5nm", "heliports_within_10nm"
        ])
