import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import stickers


class StickerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="fish-stickers-"); self.addCleanup(directory.cleanup)
        self.data = Path(directory.name)
        self.directory = patch.object(stickers, "DATA", self.data); self.directory.start(); self.addCleanup(self.directory.stop)
        self.gif = b"GIF89a" + struct.pack("<HH", 100, 100) + b"fixture"
        self.item = {"id": "0123456789abcdef", "name": "开心", "url": "https://kiriyuki.com/fixture.gif", "hash": hashlib.sha1(self.gif).hexdigest()[:12]}

    def test_verified_local_sticker_is_saved_once(self):
        with patch.object(stickers, "fetch", return_value=self.gif) as fetch:
            first = stickers.collect(self.item); second = stickers.collect(self.item)
            self.assertEqual(first, second); fetch.assert_called_once()
        self.assertEqual((self.data / "assets/0123456789abcdef.gif").read_bytes(), self.gif)
        self.assertEqual(len(stickers.load("library.json", {})["items"]), 1)

    def test_non_images_and_hash_mismatches_do_not_enter_the_library(self):
        for content in [b"<html>not an image</html>", self.gif + b"changed"]:
            with patch.object(stickers, "fetch", return_value=content):
                with self.assertRaises(ValueError): stickers.collect(self.item)
        self.assertEqual(stickers.load("library.json", {"items": []})["items"], [])

    def test_unrecognized_sources_are_rejected_without_network_access(self):
        with self.assertRaises(ValueError): stickers.fetch("https://example.org/image.gif", 1000)


if __name__ == "__main__": unittest.main()
