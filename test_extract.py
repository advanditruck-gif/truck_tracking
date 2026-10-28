"""Check image reading without the web page:  py test_extract.py photo.jpg cluster   (cluster | geo | fuel)"""
import sys
from extractor import extract
print(extract(sys.argv[2] if len(sys.argv) > 2 else "cluster", open(sys.argv[1], "rb").read()))
