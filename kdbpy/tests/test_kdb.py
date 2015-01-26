from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

import os
import datetime
import sys

import pytest
import pandas as pd
import pandas.util.testing as tm
import numpy as np
import kdbpy

from blaze import CSV, Data, discover, Expr

from qpython.qwriter import QWriterException

from kdbpy import kdb as k
from kdbpy.kdb import which
from kdbpy.exampleutils import example_data

try:
    from cStringIO import StringIO
except ImportError:  # pragma: no cover
    from io import StringIO


def test_super_basic():
    with k.KQ() as kq:
        assert kq.eval('2 + 2') == 4


def test_basic():
    kq = k.KQ()
    assert not kq.is_started

    kq.start()
    assert kq.is_started

    kq.stop()
    assert not kq.is_started

    kq.start(start='restart')
    assert kq.is_started

    # real restart
    kq.start(start='restart')
    assert kq.is_started

    kq.stop()

    # context
    with k.KQ() as kq:
        assert kq.is_started


def test_kq_repr():
    with k.KQ() as kq:
        result = repr(kq)
        assert 'connected: True' in result

    assert 'connected: False' in repr(kq)


def test_credentials():
    cred = k.Credentials(host='foo', port=1000)
    assert cred.host == 'foo'
    assert cred.port == 1000


def test_q_process(creds):
    q = k.Q(creds).start()

    assert q is not None
    assert q.pid
    assert q.process is not None

    # other instance
    q2 = k.Q(creds).start()
    assert q is q2

    # invalid instance
    c = k.Credentials(host='foo', port=1000)
    with pytest.raises(ValueError):
        k.Q(c)

    # restart
    prev = q.pid
    q = k.Q(creds).start(start=True)
    assert q.pid == prev

    q2 = k.Q().start(start='restart')
    assert q2.pid != prev

    with pytest.raises(ValueError):
        k.Q(creds).start(start=False)


def test_q_process_detached(qproc):
    # check our q process attributes
    assert qproc is not None
    assert qproc.pid
    assert qproc.process is not None


@pytest.yield_fixture(scope='session')
def qproc(creds):
    q = k.Q(creds).start()
    yield q
    q.stop()


def test_construction(qproc, creds):
    # the qproc fixture must be here because it must start before KDB
    kdb = k.KDB(credentials=creds)
    kdb.start()
    assert kdb.is_started

    result = repr(kdb)

    assert "password=''" in result
    assert "host='localhost'" in result

    kdb.stop()
    assert not kdb.is_started
    assert kdb.q is None


def test_init():
    # require initilization
    cred = k.Credentials(port=0)
    kdb = k.KDB(credentials=cred)
    with pytest.raises(ValueError):
        kdb.start()


def test_eval(kdb):
    # test function API
    assert kdb.eval('42') == 42
    f = lambda: kdb.eval('42') + 1
    assert kdb.eval(f) == 43
    assert kdb.eval(lambda x: x + 5, 42) == 47


def test_get_set_timestamp(kdb, gensym):
    ts = pd.Timestamp('2001-01-01 09:30:00.123')
    kdb.set(gensym, ts)
    assert kdb.get(gensym) == ts
    kdb[gensym] = ts
    result = kdb[gensym]
    assert result == ts


def test_get_set(kdb, gensym):
    for v in [42, 'foo']:
        kdb.set(gensym, v)
        assert kdb.get(gensym) == v


def test_get_set_mixed_frame(kdb, gensym):
    gensym = tm.makeMixedDataFrame()
    kdb.set('df', gensym)
    tm.assert_frame_equal(gensym, kdb.get('df'))


def test_scalar_datetime_like_conversions(kdb):

    # datetimes
    # only parses to ms resolutions
    result = kdb.eval('2001.01.01T09:30:00.123')
    assert result == pd.Timestamp('2001-01-01 09:30:00.123')

    result = kdb.eval('2006.07.04T09:04:59:000')
    assert result == pd.Timestamp('2006-07-04 09:04:59')

    result = kdb.eval('2001.01.01')
    assert result == pd.Timestamp('2001-01-01')

    # timedeltas
    result = kdb.eval('00:01')
    assert result == pd.Timedelta('1 min')
    result = kdb.eval('00:00:01')
    assert result == pd.Timedelta('1 sec')


def test_print_versions():
    file = StringIO()
    kdbpy.print_versions(file=file)


def test_cannot_find_program():
    with pytest.raises(OSError):
        which('xasdlkjasdga0sd9g8as0dg9@s0d98)(*)#(%*@)*')


def test_set_data_frame(gensym, kdb, df):
    kdb.set(gensym, df)
    result = kdb.eval(gensym)
    tm.assert_frame_equal(result, df)


@pytest.mark.parametrize('obj', (1, 1.0, 'a'))
def test_set_objects(gensym, kdb, obj):
    kdb.set(gensym, obj)
    assert kdb.eval(gensym) == obj


@pytest.mark.xfail(raises=QWriterException,
                   reason='qpython does not implement deserialization of '
                   'complex numbers')
def test_set_complex(gensym, kdb):
    kdb.set(gensym, 1.0j)
    result = kdb.eval(gensym)  # pragma: no cover
    assert result == 1.0j  # pragma: no cover


def test_date(kdb, gensym):
    csvdata = """name,date
a,2010-10-01
b,2010-10-02
c,2010-10-03
d,2010-10-04
e,2010-10-05"""
    with tm.ensure_clean('tmp.csv') as fname:
        with open(fname, 'wb') as f:
            f.write(csvdata)

        dshape = discover(CSV(fname, header=0))
        kdb.read_csv(fname, table=gensym, dshape=dshape)

        expected = pd.read_csv(fname, header=0, parse_dates=['date'])
    result = kdb.eval(gensym)
    tm.assert_frame_equal(expected, result)


def test_timestamp(kdb, gensym):
    csvdata = """name,date
a,2010-10-01 00:00:05
b,2010-10-02 00:00:04
c,2010-10-03 00:00:03
d,2010-10-04 00:00:02
e,2010-10-05 00:00:01"""
    with tm.ensure_clean('tmp.csv') as fname:
        with open(fname, 'wb') as f:
            f.write(csvdata)

        dshape = discover(CSV(fname, header=0))
        kdb.read_csv(fname, table=gensym, dshape=dshape)

        expected = pd.read_csv(fname, header=0, parse_dates=['date'])
    result = kdb.eval(gensym)
    tm.assert_frame_equal(expected, result)


def test_write_timestamp_from_q(kdb, gensym):
    csvdata = """name,date
a,2010-10-01D00:00:05
b,2010-10-02D00:00:04
c,2010-10-03D00:00:03
d,2010-10-04D00:00:02
e,2010-10-05D00:00:01"""
    with tm.ensure_clean('tmp.csv') as fname:
        with open(fname, 'wb') as f:
            f.write(csvdata)

        dshape = discover(CSV(fname, header=0))
        kdb.read_csv(fname, table=gensym, dshape=dshape)

        date_parser = lambda x: datetime.datetime.strptime(x,
                                                           '%Y-%m-%dD%H:%M:%S')
        expected = pd.read_csv(fname, header=0, parse_dates=['date'],
                               date_parser=date_parser)
    result = kdb.eval(gensym)
    tm.assert_frame_equal(expected, result)
    assert expected.date.dtype == np.dtype('datetime64[ns]')


def test_tables(kdb):
    tb = kdb.tables

    # we have at least our baked in names
    assert set(tb.name)
    assert set(['t', 'rt', 'st']).issubset(set(tb.name))

    # and they have non-empty kind that are well defined
    assert set(tb.kind)
    assert set(tb.kind).issubset(set(['binary', 'partitioned', 'splayed']))


def test_memory(kdb):
    mem = kdb.memory
    assert isinstance(mem, pd.Series)
    assert not mem.empty
    assert mem.name == 'memory'
    assert set(mem.index) == set(['used', 'heap', 'peak', 'wmax', 'mmap',
                                  'mphy', 'syms', 'symw'])


@pytest.mark.xfail(reason='Need to fix qpython to return nan instead of empty '
                   'string')
def test_csv_types(kdb, gensym):
    csvdata = """name,date,count,amount,sym
a,2010-10-01 00:00:05,1,1.0,`a
b,2010-10-02 00:00:04,2,,`b
,2010-10-03 00:00:03,3,3.0,`c
d,2010-10-04 00:00:02,4,4.0,
e,2010-10-05 00:00:01,5,5.0,`e"""  # note the whitespace here
    with tm.ensure_clean('tmp.csv') as fname:
        with open(fname, 'wb') as f:
            f.write(csvdata)
        dshape = CSV(fname, header=0).dshape
        kdb.read_csv(fname, table=gensym, dshape=dshape)
        expected = pd.read_csv(fname, header=0, parse_dates=['date'])
    result = kdb.eval(gensym)
    tm.assert_frame_equal(expected, result, check_dtype=False)
    assert result.name.dtype == np.dtype(object)
    assert result['count'].dtype == np.dtype('int16')
    assert result.amount.dtype == np.dtype('float32')
    assert result.sym.dtype == np.dtype(object)
    assert result.date.dtype == np.dtype('datetime64[ns]')


def test_data_getter(kdb):
    data = kdb['t']
    assert isinstance(data, Expr)
    assert repr(data)
    assert isinstance(kdb['n'], np.integer)


def test_data_getter_fails(kdb):
    with pytest.raises(AssertionError):
        kdb[object()]


def test_setitem(kdb):
    kdb['xyz'] = 1
    assert isinstance(kdb['xyz'], np.integer)


def test_setitem_table(kdb):
    kdb['mydf'] = pd.DataFrame({'a': [1, 2, 3], 'b': [3.0, 4.0, 5.0]})
    assert isinstance(kdb['mydf'], Expr)


def test_can_load_twice(kdbpar):
    path = example_data(os.path.join('start', 'db'))
    kdbpar.read_kdb(path)
    kdbpar.read_kdb(path)


def test_verbose_mode(kdb):
    oldstdout = sys.stdout
    sys.stdout = StringIO()
    kdb.verbose = True
    try:
        kdb.eval('2 + 2')
        expected = "(('2 + 2',), {})\n"
        result = sys.stdout.getvalue()
        assert expected == result
    finally:
        sys.stdout = oldstdout
        kdb.verbose = False