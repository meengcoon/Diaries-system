from __future__ import annotations

from block_analyze import _parse_or_raise


def test_parse_or_raise_repairs_missing_commas_between_members():
    raw = (
        '{"summary_1_3":"工作冲突带来持续压力"'
        '"open_insight":"他在冲突和自我保护之间摇摆"'
        '"signals":{"mood":3,"stress":8,"sleep":null,"exercise":null,"social":4,"work":9}'
        '"facts":["和同事大吵一架"]'
        '"todos":[]'
        '"topics":["工作冲突","英语 loop"]'
        '"evidence_spans":["受够了","大吵一架"]'
        '"psychological_themes":["压迫感"]'
        '"tensions":["想离开又被试探挽回"]'
        '"needs":["稳定和尊重"]'
        '"patterns":["在高压环境下迅速耗竭"]'
        '"memory_candidates":["英语 loop 新功能"]'
        '"reflection_depth":2}'
    )

    obj = _parse_or_raise(raw)

    assert obj["summary_1_3"] == "工作冲突带来持续压力"
    assert obj["open_insight"] == "他在冲突和自我保护之间摇摆"
    assert obj["signals"]["work"] == 9
    assert obj["reflection_depth"] == 2
