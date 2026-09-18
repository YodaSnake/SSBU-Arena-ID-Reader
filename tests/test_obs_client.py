from ssbu_arena_id_reader.obs_client import build_authentication


def test_build_authentication_matches_obs_protocol_example() -> None:
    assert build_authentication(
        "supersecretpassword",
        "lM1GncleQOaCu9lT1yeUZhFYnqhsLLP1G5lAGo3ixaI=",
        "+IxH4CnCiqpX1rM9scsNynZzbOe4KhDeYcTNS3PDaeY=",
    ) == "1Ct943GAT+6YQUUX47Ia/ncufilbe6+oD6lY+5kaCu4="
