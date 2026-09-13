import unittest
from exposure_universe import aggregate_event_player_games, build_expanded_rows

class ExposureUniverseTests(unittest.TestCase):
    def test_zero_credit_defender_is_retained(self):
        events = [{
            "game_id":"g1","player_id":"gsis1","credit_team":"A",
            "solo_tackle_credit":1,"tackle_with_assist_credit":0,"assist_credit":0,
            "combined_credit_unit":1,"is_original_defense_credit":1,
            "is_standard_def_scrimmage_credit":1,"is_special_teams":0,
        }]
        groups = aggregate_event_player_games(events)
        snaps = [
            {"game_id":"g1","season":2024,"week":1,"game_type":"REG","team":"A","opponent":"B","player":"One","pfr_player_id":"p1","position":"LB","defense_snaps":60,"defense_pct":1.0},
            {"game_id":"g1","season":2024,"week":1,"game_type":"REG","team":"A","opponent":"B","player":"Two","pfr_player_id":"p2","position":"S","defense_snaps":40,"defense_pct":.67},
        ]
        rows, audit = build_expanded_rows(snaps, groups, pfr_to_gsis={"p1":"gsis1","p2":"gsis2"}, allowed_game_ids={"g1"})
        by = {r["player_id"]: r for r in rows}
        self.assertEqual(by["gsis1"]["combined_standard_def_scrimmage"], 1)
        self.assertEqual(by["gsis2"]["combined_standard_def_scrimmage"], 0)
        self.assertEqual(audit["zeroStandardCreditSnapRows"], 1)

    def test_event_positive_without_snap_is_audit_only(self):
        events = [{
            "game_id":"g1","player_id":"gsis3","credit_team":"A",
            "solo_tackle_credit":0,"tackle_with_assist_credit":0,"assist_credit":1,
            "combined_credit_unit":1,"is_original_defense_credit":1,
            "is_standard_def_scrimmage_credit":1,"is_special_teams":0,
        }]
        rows, audit = build_expanded_rows([], aggregate_event_player_games(events), pfr_to_gsis={}, allowed_game_ids={"g1"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["exposure_source"], "EVENT_ONLY_NO_SNAP")
        self.assertEqual(rows[0]["eligible_standard_rate_fit"], 0)
        self.assertEqual(audit["eventOnlyPositiveRows"], 1)

    def test_nonstandard_credit_does_not_enter_standard_target(self):
        events = [{
            "game_id":"g1","player_id":"gsis1","credit_team":"A",
            "solo_tackle_credit":1,"tackle_with_assist_credit":0,"assist_credit":0,
            "combined_credit_unit":1,"is_original_defense_credit":1,
            "is_standard_def_scrimmage_credit":0,"is_special_teams":1,
        }]
        g = aggregate_event_player_games(events)[("g1","gsis1")]
        self.assertEqual(g["combined_standard_def_scrimmage"], 0)
        self.assertEqual(g["combined_special_teams"], 1)

if __name__ == "__main__":
    unittest.main()
