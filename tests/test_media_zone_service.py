from src.media_zone_service import MediaRoute, media_route_plan


def test_plan_uses_cname_and_keeps_zone_lookup_before_record_write():
    plan = media_route_plan(MediaRoute("media.example.com", "stream.media.example.com", "edge.example.net"))

    assert plan["zone_lookup"]["method"] == "GET"
    assert plan["record"]["body"]["zone_id"] == "<from zone_lookup>"
    assert plan["record"]["body"]["record_type"] == "CNAME"
    assert plan["mail_check"]["path"] == "/v1/email/domain/verify"
    assert plan["dkim_rotation"]["path"] == "/v1/email/domain/rotate_dkim/media.example.com"
