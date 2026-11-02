import unittest
from unittest.mock import patch

import supabase_storage


class SupabaseStorageUploadTests(unittest.TestCase):
    def test_upload_sends_jpeg_bytes_without_json_encoding(self):
        image_bytes = b"\xff\xd8\xfftest-image"
        with patch.object(supabase_storage, "_settings", return_value=("https://example.supabase.co", "test-key")), \
                patch.object(supabase_storage, "urlopen") as urlopen:
            response = urlopen.return_value.__enter__.return_value
            response.read.return_value = b""

            supabase_storage.upload_image("events/test.jpg", image_bytes, "image/jpeg")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.data, image_bytes)
        self.assertEqual(request.get_header("Content-type"), "image/jpeg")
        self.assertEqual(request.get_header("Cache-control"), "max-age=86400")


if __name__ == "__main__":
    unittest.main()
