from decimal import Decimal
from aimigrate.crossdb import compare_rows

def test_equal_unordered():
    assert compare_rows([(1,), (2,)], [(2,), (Decimal('1.0'),)])

def test_order_matters_when_requested():
    assert not compare_rows([(1,), (2,)], [(2,), (1,)], ordered=True)

def test_duplicate_counts_matter():
    assert not compare_rows([(1,), (1,)], [(1,)])

def test_null_differs_from_string():
    assert not compare_rows([(None,)], [('None',)])
