"""在线地名搜索的缓存、限速和响应校验。"""

import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import URLError, HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from geocoding import Geocoder


class GeocodingTests(unittest.TestCase):
    def test_query_encoding_and_cache(self):
        payload = b'[{"lat":"35", "lon":"139", "display_name":"Tokyo", "boundingbox":["34","36","138","140"]}]'
        with patch('geocoding.urlopen', return_value=io.BytesIO(payload)) as request:
            geo = Geocoder()
            first = geo.search('Tokyo & station')
            self.assertEqual(geo.search('Tokyo & station'), first)
            request.assert_called_once()
            self.assertIn('q=Tokyo+%26+station', request.call_args.args[0].full_url)
            self.assertEqual(first[0]['bounds'], [[34, 138], [36, 140]])

    def test_consecutive_requests_are_rate_limited(self):
        with patch('geocoding.urlopen', side_effect=lambda *a, **k: io.BytesIO(b'[]')) as request, \
                patch('geocoding.time.monotonic', return_value=10), \
                patch('geocoding.time.sleep') as sleep:
            geo = Geocoder()
            geo.search('Tokyo')
            geo.search('Osaka')
            self.assertEqual(request.call_count, 2)
            sleep.assert_called_once_with(1.05)

    def test_invalid_coordinates_are_not_returned(self):
        with patch('geocoding.urlopen', return_value=io.BytesIO(b'[{"lat":"nan", "lon":"139"}]')):
            self.assertEqual(Geocoder().search('test'), [])

    def test_transient_connection_failure_retries_once(self):
        with patch('geocoding.urlopen', side_effect=[URLError(TimeoutError('timed out')), io.BytesIO(b'[]')]) as request, \
                patch('geocoding.time.sleep'), self.assertLogs('geocoding', level='WARNING'):
            self.assertEqual(Geocoder().search('test'), [])
            self.assertEqual(request.call_count, 2)

    def test_rate_limit_is_not_retried(self):
        error = HTTPError('https://example.test', 429, 'Too Many Requests', {}, None)
        with patch('geocoding.urlopen', side_effect=error) as request:
            with self.assertRaises(HTTPError):
                Geocoder().search('test')
            request.assert_called_once()


if __name__ == '__main__':
    unittest.main()
