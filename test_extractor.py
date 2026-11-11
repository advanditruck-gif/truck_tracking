import json
import sys
import unittest
from unittest.mock import patch

import extractor


class GeoExtractionTests(unittest.TestCase):
    def run_empty_response(self, kind):
        response = json.dumps({key: None for key in extractor.SCHEMAS[kind]})
        with patch.dict(sys.modules, {"google": None}):
            with patch.object(extractor, "_get_api_key", return_value="test-key"):
                with patch.object(extractor, "_call_gemini_rest", return_value=response):
                    with patch.object(extractor, "MODEL", "test-model"):
                        return extractor.extract_gemini(kind, b"image")

    def test_empty_geo_result_is_recoverable_by_phone_gps(self):
        result = self.run_empty_response("geo")

        self.assertNotIn("_error", result)
        self.assertTrue(all(value is None for value in result.values()))

    def test_empty_non_geo_result_remains_an_error(self):
        result = self.run_empty_response("fuel")

        self.assertIn("_error", result)
        self.assertIn("no values returned", result["_error"])


if __name__ == "__main__":
    unittest.main()
