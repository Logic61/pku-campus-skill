import json
import unittest
from server import parse_pkuknow, read_feed


class FeedTests(unittest.TestCase):
    def test_public_payload_deduplicates_and_rejects_unsafe_urls(self):
        items = [
            {'id':'a', 'title':'讲座', 'url':'https://pku.edu.cn/a', 'source_name':'院系'},
            {'id':'a', 'title':'重复', 'url':'https://pku.edu.cn/a'},
            {'id':'b', 'title':'不安全链接', 'url':'javascript:alert(1)'},
        ]
        payload = json.dumps({'items':items}, ensure_ascii=False)
        # Next.js can split a JSON value across multiple streamed chunks.
        chunks = [payload[:30], payload[30:]]
        html = ''.join(f'<script>self.__next_f.push({json.dumps([1, part])})</script>' for part in chunks)
        actual = parse_pkuknow(html)
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0]['source'], '院系')

    def test_changed_source_fails_explicitly(self):
        with self.assertRaises(ValueError):
            parse_pkuknow('<html>source changed</html>')

    def test_shipped_snapshot_contains_real_source_links(self):
        feed = read_feed()
        self.assertGreater(len(feed['items']), 0)
        self.assertEqual(feed['source'], 'https://pkuknow.cn/')
        self.assertTrue(all(item['url'].startswith(('https://','http://')) for item in feed['items']))


if __name__ == '__main__':
    unittest.main()
