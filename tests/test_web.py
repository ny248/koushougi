from html.parser import HTMLParser
from pathlib import Path
import unittest
from unittest.mock import patch

from koushougi import web
from koushougi.position import position


class OpponentOptions(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_opponent = False
        self.values = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "select":
            self.in_opponent = attributes.get("id") == "opponent"
        if tag == "option" and self.in_opponent:
            self.values.append(attributes["value"])

    def handle_endtag(self, tag):
        if tag == "select":
            self.in_opponent = False


class WebTest(unittest.TestCase):
    def test_ai_option_keeps_the_search_protocol_for_existing_servers(self):
        parser = OpponentOptions()
        parser.feed(Path(web.__file__).with_name("board.html").read_text())
        self.assertEqual(parser.values, ["human", "search"])

    def test_both_ai_protocol_values_call_the_search_player(self):
        for value in ("ai", "search"):
            with self.subTest(value=value), patch("koushougi.position.choose_search_move", return_value=None) as choose:
                position([], ai=value, human_side="white")
                choose.assert_called_once()
