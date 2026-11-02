import unittest
from io import BytesIO

from PIL import Image

from image_utils import normalize_jpeg, rotate_jpeg


class NormalizeJpegTests(unittest.TestCase):
    def test_rotated_exif_image_is_transposed_and_orientation_removed(self):
        source = Image.new("RGB", (40, 20), "red")
        exif = Image.Exif()
        exif[274] = 6
        encoded = BytesIO()
        source.save(encoded, format="JPEG", exif=exif)

        normalized, orientation = normalize_jpeg(encoded.getvalue())

        with Image.open(BytesIO(normalized)) as result:
            self.assertEqual(orientation, 6)
            self.assertEqual(result.size, (20, 40))
            self.assertEqual(result.getexif().get(274), None)

    def test_upright_image_keeps_its_dimensions(self):
        source = Image.new("RGB", (40, 20), "blue")
        encoded = BytesIO()
        source.save(encoded, format="JPEG")

        normalized, orientation = normalize_jpeg(encoded.getvalue())

        with Image.open(BytesIO(normalized)) as result:
            self.assertEqual(orientation, 1)
            self.assertEqual(result.size, (40, 20))

    def test_manual_rotation_changes_portrait_to_landscape(self):
        source = Image.new("RGB", (20, 40), "green")
        encoded = BytesIO()
        source.save(encoded, format="JPEG")

        rotated = rotate_jpeg(encoded.getvalue(), "counterclockwise")

        with Image.open(BytesIO(rotated)) as result:
            self.assertEqual(result.size, (40, 20))
            self.assertIsNone(result.getexif().get(274))


if __name__ == "__main__":
    unittest.main()
