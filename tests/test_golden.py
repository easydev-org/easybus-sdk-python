from easybus.protocol.golden import GOLDEN_VECTORS


def test_golden_vectors():
    for name, (got, want) in GOLDEN_VECTORS.items():
        assert got == want, f"{name}: {got!r} != {want!r}"
