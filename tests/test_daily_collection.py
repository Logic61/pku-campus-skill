import unittest
from unittest.mock import Mock
from scripts.collect_daily_treehole import day_window,in_window,batch_text,retrieve_comments


class DailyCollectionTests(unittest.TestCase):
    def test_shanghai_day_boundaries(self):
        start,end=day_window('2026-10-25')
        self.assertEqual(end-start,86400)
        self.assertTrue(in_window({'timestamp':start},start,end))
        self.assertFalse(in_window({'timestamp':end},start,end))
        self.assertFalse(in_window({'timestamp':None},start,end))

    def test_all_comment_pages_not_only_preview(self):
        client=Mock()
        client._json.side_effect=[{'success':True,'data':{'data':[{'cid':1,'text':'一'}],'total':2}},
                                  {'success':True,'data':{'data':[{'cid':2,'text':'二'}],'total':2}}]
        comments,complete,total=retrieve_comments(client,{'pid':123,'reply':2},3)
        self.assertTrue(complete)
        self.assertEqual(len(comments),2)
        self.assertEqual(total,2)

    def test_packet_keeps_full_text_and_filters_next_day_comments(self):
        start,end=day_window('2026-10-25')
        thread={'post':{'pid':1,'text':'测试'*100},'comments':[{'cid':1,'text':'当天评论','timestamp':start+5},
               {'cid':2,'text':'次日评论不纳入','timestamp':end+5}]}
        packets=batch_text([thread],start,end,size=60)
        text=''.join(packets)
        self.assertIn('测试'*100,text)
        self.assertIn('当天评论',text)
        self.assertNotIn('次日评论不纳入',text)
        self.assertTrue(all(len(p)<=60 for p in packets))
