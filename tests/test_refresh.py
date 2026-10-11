import unittest
from unittest.mock import patch
from api import refresh
from scripts import update

class RefreshTests(unittest.TestCase):
    def test_place_boundaries(self):
        self.assertIsNone(update.place_for('Ambulance Assendelft'))
        self.assertEqual(update.place_for('Ambulance Delft'), 'Delft')
        self.assertEqual(update.place_for('a1 rivierenlaan pijnak : 15121'), 'Pijnacker')

    def test_all_sources_failed(self):
        with patch.object(refresh, 'fetch_feed', return_value=([], 'failed')):
            with self.assertRaises(RuntimeError):
                refresh.collect_live()

    def test_partial_success_is_explicit(self):
        def mocked(feed, now):
            return ([], 'failed') if feed == refresh.FEEDS[0] else ([], None)
        with patch.object(refresh, 'fetch_feed', side_effect=mocked):
            data = refresh.collect_live()
        self.assertTrue(data['partial'])
        self.assertEqual(data['failed_sources'], 1)
        self.assertEqual(data['incidents'], [])

if __name__ == '__main__':
    unittest.main()
