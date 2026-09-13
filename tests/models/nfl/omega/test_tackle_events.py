import unittest
from tackle_events import extract_credit_events, aggregate_player_games, duplicate_credit_anomalies, validate_tackle_schema

class TackleEventsTest(unittest.TestCase):
    def base(self):
        return {'game_id':'2019_01_A_B','play_id':10,'season':2019,'week':1,'posteam':'A','defteam':'B','play_type':'run','rush_attempt':1,'special_teams_play':0}

    def test_credit_classes_preserved(self):
        r=self.base();r.update({
            'tackle_with_assist_1_player_id':'P1','tackle_with_assist_1_player_name':'One','tackle_with_assist_1_team':'B',
            'assist_tackle_1_player_id':'P2','assist_tackle_1_player_name':'Two','assist_tackle_1_team':'B'})
        ev=extract_credit_events(r)
        self.assertEqual([e['credit_role'] for e in ev],['PRIMARY_WITH_ASSIST','ASSIST'])
        self.assertEqual(sum(e['combined_credit_unit'] for e in ev),2)
        self.assertTrue(all(e['is_standard_def_scrimmage_credit']==1 for e in ev))

    def test_equal_assist_play_can_create_two_combined_credits(self):
        r=self.base();r.update({'assist_tackle_1_player_id':'P1','assist_tackle_1_team':'B','assist_tackle_2_player_id':'P2','assist_tackle_2_team':'B'})
        ev=extract_credit_events(r)
        self.assertEqual(len(ev),2)
        self.assertEqual(sum(e['assist_credit'] for e in ev),2)

    def test_special_teams_is_not_standard_def_scrimmage(self):
        r=self.base();r.update({'play_type':'punt','special_teams_play':1,'solo_tackle_1_player_id':'P1','solo_tackle_1_team':'B'})
        ev=extract_credit_events(r)
        self.assertEqual(ev[0]['is_special_teams'],1)
        self.assertEqual(ev[0]['is_standard_def_scrimmage_credit'],0)

    def test_original_offense_credit_on_turnover_is_flagged(self):
        r=self.base();r.update({'play_type':'pass','interception':1,'solo_tackle_1_player_id':'P1','solo_tackle_1_team':'A'})
        ev=extract_credit_events(r)
        self.assertEqual(ev[0]['credit_team_role'],'ORIGINAL_OFFENSE')
        self.assertEqual(ev[0]['is_original_defense_credit'],0)

    def test_aggregate_keeps_market_semantics_separate(self):
        r=self.base();r.update({'solo_tackle_1_player_id':'P1','solo_tackle_1_team':'B'})
        ev=extract_credit_events(r)
        rows=aggregate_player_games(ev,player_meta={'P1':{'display_name':'Player','position':'LB','position_group':'LB','pfr_id':'x'}},game_meta={'2019_01_A_B':{'season':'2019','week':'1','game_type':'REG'}},snap_meta={('2019_01_A_B','P1'):{'defense_snaps':50,'defense_pct':0.9}})
        self.assertEqual(rows[0]['solo'],1)
        self.assertEqual(rows[0]['primary_with_assist'],0)
        self.assertEqual(rows[0]['assists'],0)
        self.assertAlmostEqual(rows[0]['combined_standard_per_def_snap'],0.02)

    def test_duplicate_is_audit_not_silent_dedupe(self):
        r=self.base();r.update({'solo_tackle_1_player_id':'P1','solo_tackle_1_team':'B','solo_tackle_2_player_id':'P1','solo_tackle_2_team':'B'})
        ev=extract_credit_events(r)
        self.assertEqual(len(ev),2)
        self.assertEqual(duplicate_credit_anomalies(ev)[0]['count'],2)

    def test_schema_fails_closed_without_credit_columns(self):
        with self.assertRaises(ValueError): validate_tackle_schema({'game_id','play_id'})

if __name__=='__main__':unittest.main()
