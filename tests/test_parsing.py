import os
import tempfile

from connect2mp4.model import ContentEvent, ShapeAdded, ShapeRemoved, SlideEvent
from connect2mp4.parsing import parse_ftcontent, parse_mainstream

MAINSTREAM = """<?xml version="1.0"?><root>
<Message time="100"><Object></Object><String><![CDATA[streamAdded]]></String>
  <streamName><![CDATA[/cameraVoip_12_100]]></streamName><streamType><![CDATA[audio]]></streamType></Message>
<Message time="200"><Object></Object><String><![CDATA[setContentSo]]></String>
  <newValue><ctID><![CDATA[7]]></ctID><theName><![CDATA[Learning Theory.pdf]]></theName>
  <contentW><![CDATA[960]]></contentW><contentH><![CDATA[720]]></contentH>
  <playbackFileName><![CDATA[/_a123/pabc123/output/x.swf]]></playbackFileName>
  <playbackFileNameHTMLClient><![CDATA[/_a123/pzzz999/output/x.html]]></playbackFileNameHTMLClient>
  <theUrl><![CDATA[/psrc777/]]></theUrl></newValue></Message>
<Message time="5000"><Object></Object><String><![CDATA[streamRemoved]]></String>
  <streamName><![CDATA[/cameraVoip_12_100]]></streamName><streamType><![CDATA[audio]]></streamType></Message>
</root>"""

FTCONTENT = """<root>
<Message time="50"><Object></Object><String><![CDATA[setContentSo]]></String>
  <name><![CDATA[ctID]]></name><newValue><![CDATA[7]]></newValue></Message>
<Message time="60"><Object></Object><String><![CDATA[setPptLoaderSo]]></String>
  <name><![CDATA[slideIndex]]></name><newValue><![CDATA[3]]></newValue></Message>
<Message time="40"><Object></Object><String><![CDATA[setWBSo]]></String>
  <name><![CDATA[currentPage]]></name><newValue><![CDATA[1]]></newValue></Message>
<Message time="70"><Object></Object><String><![CDATA[set_WB_So_3]]></String>
  <Object><code><![CDATA[change]]></code><name><![CDATA[tID]]></name><newValue><![CDATA[9]]></newValue></Object>
  <Object><code><![CDATA[change]]></code><name><![CDATA[15]]></name><newValue>
    <type><![CDATA[pencil]]></type><x><![CDATA[10]]></x><y><![CDATA[20]]></y>
    <width><![CDATA[100]]></width><height><![CDATA[50]]></height>
    <strokeCol><![CDATA[16711680]]></strokeCol><strokeWeight><![CDATA[3]]></strokeWeight>
    <pts><x><![CDATA[0]]></x><y><![CDATA[0]]></y><x><![CDATA[1]]></x><y><![CDATA[0.5]]></y></pts>
  </newValue></Object></Message>
<Message time="80"><Object></Object><String><![CDATA[set_WB_So_3]]></String>
  <Object><code><![CDATA[delete]]></code><name><![CDATA[15]]></name><newValue><![CDATA[]]></newValue></Object></Message>
</root>"""


def _write(text):
    fd, path = tempfile.mkstemp(suffix=".xml")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return path


def test_parse_mainstream():
    streams, contents, last_ms = parse_mainstream(_write(MAINSTREAM))
    assert last_ms == 5000
    assert len(streams) == 1
    s = streams[0]
    assert (s.name, s.type, s.start_ms, s.end_ms) == ("cameraVoip_12_100", "audio", 100, 5000)
    c = contents["7"]
    assert c.name == "Learning Theory.pdf"
    assert (c.width, c.height) == (960.0, 720.0)
    assert c.sco == "pabc123"        # first playbackFileName wins
    assert c.sco_src == "psrc777"
    assert c.sco_ids == ["pabc123", "psrc777"]


def test_parse_ftcontent():
    events = parse_ftcontent(_write(FTCONTENT))
    assert [type(e) for e in events] == [SlideEvent, ContentEvent, SlideEvent, ShapeAdded, ShapeRemoved]
    assert [e.time_ms for e in events] == [40, 50, 60, 70, 80]
    assert events[1].ct_id == "7"
    assert events[2].index == 3
    added = events[3]
    assert (added.page, added.shape_id) == (3, "15")
    assert added.shape.kind == "pencil"
    assert added.shape.box == (10.0, 20.0, 100.0, 50.0)
    assert added.shape.color == 0xFF0000
    assert added.shape.weight == 3.0
    assert added.shape.points == [(0.0, 0.0), (1.0, 0.5)]
    assert (events[4].page, events[4].shape_id) == (3, "15")
