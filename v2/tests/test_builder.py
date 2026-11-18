import gzip, os, subprocess, sys, tempfile, unittest
from pathlib import Path
import xml.etree.ElementTree as ET

SCRIPT=Path(__file__).resolve().parents[1]/'build.py'

class RosterFirstTests(unittest.TestCase):
    def test_only_playlist_channels_and_safe_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp)
            strong='''<tv><channel id="CFPL.ca"><display-name>CTV 2 London</display-name></channel><programme channel="CFPL.ca" start="20261118120000 +0000" stop="20261118130000 +0000"><title>Strong News</title></programme></tv>'''
            extra='''<tv><channel id="ctv2london.ca"><display-name>CTV 2 London</display-name></channel><channel id="phantom.us"><display-name>Imaginary Extra Channel</display-name></channel><channel id="dummy-777"><display-name>Live Game @ Nov 18 12:00 :TSN+ 01</display-name></channel><programme channel="ctv2london.ca" start="20261118130000 +0000" stop="20261118150000 +0000"><title>CTV London</title></programme><programme channel="phantom.us" start="20261118120000 +0000" stop="20261118130000 +0000"><title>Phantom</title></programme><programme channel="dummy-777" start="20261118160000 +0000" stop="20261118180000 +0000"><title>Live Game @ Nov 18 12:00 :TSN+ 01</title></programme></tv>'''
            playlist='''#EXTM3U\n#EXTINF:-1 tvg-id="CFPL.ca" tvg-name="CTV 2 London" group-title="CA | Locals",CTV 2 London\nhttp://provider.example/live/SECRETUSER/SECRETPASS/1001.ts\n#EXTINF:-1 tvg-id="NBC.us" tvg-name="NBC Local US" group-title="US",NBC Local US\nhttp://provider.example/live/SECRETUSER/SECRETPASS/1002.ts\n#EXTINF:-1 tvg-id="" tvg-name="TSN+ 01" group-title="CA | TSN+ PPV",TSN+ 01 - LIVE NCAA\nhttp://provider.example/live/SECRETUSER/SECRETPASS/1003.ts\n'''
            for name,body in [('strong.xml',strong),('extra.xml',extra),('channels.m3u',playlist)]: (tmp/name).write_text(body)
            output=tmp/'preview.xml.gz'
            p=subprocess.run([sys.executable,str(SCRIPT),'--strong',str(tmp/'strong.xml'),'--m3u',str(tmp/'channels.m3u'),'--ganjarelease',str(tmp/'extra.xml'),'--canada','','--us-local','','--uk','','--portugal','','--brazil','','--now','2026-11-18T11:00:00+00:00','--output',str(output),'--audit',str(tmp/'audit.csv'),'--streams',str(tmp/'streams.csv'),'--require-m3u'],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+'\n'+p.stderr)
            raw=gzip.decompress(output.read_bytes())
            root=ET.fromstring(raw)
            ids={e.get('id') for e in root.findall('channel')}
            self.assertEqual(len(ids),3)
            self.assertIn('CFPL.ca',ids)
            self.assertIn('NBC.us',ids)
            self.assertTrue(any(x.startswith('strong-unmapped-') for x in ids))
            self.assertNotIn('phantom.us',ids)
            self.assertNotIn('ctv2london.ca',ids)
            self.assertNotIn('dummy-777',ids)
            self.assertNotIn(b'SECRETUSER',raw)
            self.assertNotIn(b'SECRETPASS',raw)
            self.assertIn(b'Live Game',raw)
            self.assertIn(b'CTV London',raw)
            self.assertIn(b'Channel-name fallback',raw)
            self.assertIn('manual_epg_assignment_needed',(tmp/'streams.csv').read_text())
            self.assertIn('streams_sharing_epg_id',(tmp/'streams.csv').read_text())

if __name__=='__main__':unittest.main()
