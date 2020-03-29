from operator  import itemgetter, attrgetter
from functools import reduce
from argparse  import Namespace

import itertools as it

from pytest import mark, raises
xfail = mark.xfail
TODO = mark.xfail(reason='TODO')
GETITEM_FUNDAMENTALLY_BROKEN = xfail(reason="__getitem__ can't distinguish x[a,b] from x[(a,b)]")
parametrize = mark.parametrize

from hypothesis            import given
from hypothesis            import assume
from hypothesis.strategies import tuples
from hypothesis.strategies import integers
from hypothesis.strategies import none
from hypothesis.strategies import one_of, sampled_from


def test_trivial():
    from reboot import flow
    data = list(range(10))
    result = []
    flow(result.append)(data)
    assert result == data


def test_map():
    from reboot import flow
    data = list(range(10))
    f, = symbolic_functions('f')
    result = []
    flow(f, result.append)(data)
    assert result == list(map(f, data))


def test_filter():
    from reboot import flow
    data = list(range(10))
    result = []
    flow({odd}, result.append)(data)
    assert result == list(filter(odd, data))


def test_filter_with_key():
    from reboot import flow, arg as _
    data = list(range(10))
    result = []
    flow({odd : _+1}, result.append)(data)
    assert result == list(filter(even, data))


def test_branch():
    from reboot import flow
    data = list(range(10))
    branch, main = [], []
    flow([branch.append], main.append)(data)
    assert main   == data
    assert branch == data


def test_integration_1():
    from reboot import flow, arg as _
    data = range(20)
    f, g, h = square, (_ +  1), (_ +   2)
    a, b, c = odd   , (_ > 50), (_ < 100)
    s, t    = [], []
    flow(f,
         {a},
         [g, {b}, s.append],
         h,
         {c},
         t.append)(data)
    assert s == list(filter(b, map(g, filter(a, map(f, data)))))
    assert t == list(filter(c, map(h, filter(a, map(f, data)))))


def test_fold_and_return():
    from reboot import flow, out
    data = range(3)
    assert flow(out(sym_add))(data) == reduce(sym_add, data)


def test_fold_and_named_return():
    from reboot import flow, out
    data = range(3)
    assert flow(out.total(sym_add))(data).total == reduce(sym_add, data)


def test_fold_with_initial_value():
    from reboot import flow, out
    data = range(3)
    assert flow(out(sym_add, 99))(data) == reduce(sym_add, data, 99)


def test_fold_with_initial_value_named():
    from reboot import flow, out
    data = range(3)
    net = flow(out.total(sym_add, 99))
    assert net(data).total == reduce(sym_add, data, 99)


def test_return_value_from_branch():
    from reboot import flow, out
    data = range(3)
    result = flow([out.branch(sym_add)],
                   out.main  (sym_mul))(data)
    assert result.main   == reduce(sym_mul, data)
    assert result.branch == reduce(sym_add, data)


def test_implicit_collect_into_list_named():
    from reboot import flow, out
    data = range(3)
    assert flow(out.everything)(data).everything == list(data)


def test_implicit_collect_into_list_nameless_with_call():
    from reboot import flow, out
    data = range(3)
    assert flow(out())(data) == list(data)


def test_implicit_collect_into_list_nameless_without_call():
    from reboot import flow, out
    data = range(3)
    assert flow(out)(data) == list(data)


def test_more_than_one_anonymous_out():
    from reboot import flow, out
    f,g = symbolic_functions('fg')
    data = range(3)
    res = flow([f, out], g, out)(data)
    returns = getattr(res, 'return')
    assert returns[0] == list(map(f, data))
    assert returns[1] == list(map(g, data))


def test_anonymous_and_named_outs():
    from reboot import flow, out
    f,g = symbolic_functions('fg')
    data = range(3)
    res = flow([f, out.branch], g, out)(data)
    assert res.branch == list(map(f, data))
    assert vars(res)['return'][0] == list(map(g, data))


def test_nested_branches():
    from reboot import flow, out
    f,g,h,i = symbolic_functions('fghi')
    data = range(3)
    res = flow([[f, out.BB], g, out.BM],
                [h, out.MB], i, out.MM )(data)
    assert res.BB == list(map(f, data))
    assert res.BM == list(map(g, data))
    assert res.MB == list(map(h, data))
    assert res.MM == list(map(i, data))


def test_flat_map():
    from reboot import flow, FlatMap, out
    data = range(4)
    f = range
    assert flow(FlatMap(f), out)(data) == list(it.chain(*map(f, data)))


def test_pipe_as_function():
    from reboot import pipe
    f,g = symbolic_functions('fg')
    pipe_fn = pipe(f,g).fn()
    assert pipe_fn(6) == (g(f(6)),)


def test_pipe_as_multi_arg_function():
    from reboot import pipe
    f, = symbolic_functions('f')
    pipe_fn = pipe(sym_add, f).fn()
    assert pipe_fn(6,7) == (f(sym_add(6,7)),)


def test_pipe_on_filter():
    from reboot import pipe
    f = odd
    pipe_fn = pipe({f}).fn()
    assert pipe_fn(3) == (3,)
    assert pipe_fn(4) == ()


def test_pipe_on_flatmap():
    from reboot import pipe, FlatMap
    f = range
    pipe_fn = pipe(FlatMap(f)).fn()
    assert pipe_fn(3) == (0,1,2)
    assert pipe_fn(5) == (0,1,2,3,4)


def test_pipe_as_component():
    from reboot import pipe, flow, out
    data = range(3,6)
    a,b,f,g = symbolic_functions('abfg')
    pipe = pipe(f, g)
    assert flow(a, pipe, b, out)(data) == list(map(b, map(g, map(f, map(a, data)))))


def test_pick_item():
    from reboot import flow, pick, out
    names = 'abc'
    values = range(3)
    f, = symbolic_functions('f')
    data = [dict((name, value) for name in names) for value in values]
    assert flow(pick.a, f, out)(data) == list(map(f, values))


def test_pick_multiple_items():
    from reboot import flow, pick, out
    names = 'abc'
    ops = tuple(symbolic_functions(names))
    values = range(3)
    data = [{name:op(N) for (name, op) in zip(names, ops)} for N in values]
    assert flow(pick.a.b, out)(data) == list(map(itemgetter('a', 'b'), data))
    assert flow(pick.a  , out)(data) == list(map(itemgetter('a'     ), data))


def test_on_item():
    from reboot import flow, on, out
    names = 'abc'
    f, = symbolic_functions('f')
    values = range(3)
    data = [{name:N for name in names} for N in values]
    net = flow(on.a(f), out)
    expected = [d.copy() for d in data]
    for d in expected:
        d['a'] = f(d['a'])
    assert net(data) == expected


def test_get_single_attr():
    from reboot import get
    it = Namespace(a=1, b=2)
    assert get.a(it) == attrgetter('a')(it)


def test_get_single_item():
    from reboot import get
    it = dict(a=1, b=2)
    assert get['a'](it) == itemgetter('a')(it)


def test_get_multilpe_attr():
    from reboot import get
    it = Namespace(a=1, b=2, c=9, d=4)
    assert get.d.b.c(it) == attrgetter('d', 'b', 'c')(it)


@GETITEM_FUNDAMENTALLY_BROKEN
def test_get_multilpe_item():
    from reboot import get
    it = dict(a=1, b=2, c=9, d=4)
    assert get['d', 'b', 'c'](it) == attrgetter('d', 'b', 'c')(it)


def namespace_source(keys='abc', length=3):
    indices = range(length)
    return [{key:f'{key}{i}' for key in keys} for i in indices]


def test_args_single():
    from reboot import flow, args, out
    data = namespace_source()
    f, = symbolic_functions('f')
    assert flow((args.c, f), out)(data) == list(map(f, map(itemgetter('c'), data)))


def test_args_many():
    from reboot import flow, args, out
    data = namespace_source()
    net = flow((args.a.b, sym_add), out)
    expected = list(map(sym_add, map(itemgetter('a'), data),
                                 map(itemgetter('b'), data)))
    assert net(data) == expected

def test_put_single():
    from reboot import flow, put, out
    data = namespace_source()
    f, = symbolic_functions('f')
    net = flow((itemgetter('b'), f, put.xxx), out)
    expected = [d.copy() for d in data]
    for d in expected:
        d['xxx'] = f(d['b'])
    assert net(data) == expected


def test_put_many():
    from reboot import flow, put, out
    data = namespace_source()
    l,r = symbolic_functions('lr')
    def f(x):
        return l(x), r(x)
    net = flow((f, put.left.right), out)
    expected = [d.copy() for d in data]
    for d in expected:
        d['left' ], d['right'] = f(d)
    assert net(data) == expected


def test_args_single_put_single():
    from reboot import flow, args, put, out
    data = namespace_source()
    f, = symbolic_functions('f')
    net = flow((args.b, f, put.result), out)
    expected = [d.copy() for d in data]
    for d in expected:
        d['result'] = f(d['b'])
    assert net(data) == expected


def test_args_single_put_many():
    from reboot import flow, args, put, out
    l,r = symbolic_functions('lr')
    def f(x):
        return l(x), r(x)
    data = namespace_source()
    net = flow((args.c, f, put.l.r), out)
    expected = [d.copy() for d in data]
    for d in expected:
        result = f(d['c'])
        d['l'], d['r'] = result
    assert net(data) == expected


def test_args_single_filter():
    from reboot import flow, args, out, arg as _
    data = (dict(a=1, b=2),
            dict(a=3, b=3),
            dict(a=2, b=1),
            dict(a=8, b=9))
    net = flow((args.b, {_ > 2}), out)
    expected = list(filter(_ > 2, map(itemgetter('b'), data)))
    assert net(data) == expected


@TODO
def test_args_many_filter():
    from reboot import flow, args, out
    data = (dict(a=1, b=2),
            dict(a=3, b=3),
            dict(a=2, b=1),
            dict(a=8, b=9))
    net = flow((args.a.b, {lt}), out)
    expected = (dict(a=1, b=2),
                dict(a=8, b=9))
    assert net(data) == expected


def test_args_single_flatmap():
    from reboot import flow, FlatMap, args, out
    data = (dict(a=1, b=2),
            dict(a=0, b=3),
            dict(a=3, b=1))
    net = flow((args.a, FlatMap(lambda n:n*[n])), out)
    assert net(data) == [1,3,3,3]


def test_args_many_flatmap():
    from reboot import flow, FlatMap, args, out
    data = (dict(a=1, b=9),
            dict(a=0, b=8),
            dict(a=3, b=7))
    net = flow((args.a.b, FlatMap(lambda a,b:a*[b])), out)
    assert net(data) == [9,7,7,7]



small_ints         = integers(min_value=0, max_value=15)
small_ints_nonzero = integers(min_value=1, max_value=15)
slice_arg          = one_of(none(), small_ints)
slice_arg_nonzero  = one_of(none(), small_ints_nonzero)

@given(one_of(tuples(small_ints),
              tuples(small_ints, small_ints),
              tuples(slice_arg,  slice_arg, slice_arg_nonzero)))
def test_slice_downstream(spec):

    from reboot import flow, Slice, out
    data = list('abcdefghij')
    result = flow(Slice(*spec), out)(data)
    specslice = slice(*spec)
    assert result == data[specslice]
    assert result == data[specslice.start : specslice.stop : specslice.step]


# slice takes an optional argument close_all. If this argument
# is False (default), slice will close the innermost branch in
# which the component is plugged in after the component iterates
# over all its entries. However, when set to True, the behaviour
# is to close the outermost pipeline, resulting in a full stop of
# the data flow.
@parametrize("close_all", (False, True))
def test_slice_close_all(close_all):
    from reboot import Slice, flow, out

    data = list(range(20))
    n_elements = 5
    the_slice = Slice(n_elements, close_all=close_all)

    result = flow([the_slice, out.branch], out.main)(data)

    if close_all:
        assert result.branch == data[:n_elements]
        assert result.main   == data[:n_elements]
    else:
        assert result.branch == data[:n_elements]
        assert result.main   == data


@parametrize('args',
             ((      -1,),
              (None, -1),
              (-1, None),
              (None, None, -1),
              (None, None,  0),
             ))
def test_slice_raises_ValueError(args):
    from reboot import Slice
    with raises(ValueError):
        Slice(*args)


from operator import   eq, ne, lt, gt, le, ge, add, sub, mul, floordiv, truediv
binops = sampled_from((eq, ne, lt, gt, le, ge, add, sub, mul, floordiv, truediv))

@given(binops, integers(), integers())
def test_arg_as_lambda_binary(op, lhs, rhs):
    assume(op not in (truediv, floordiv) or rhs != 0)
    from reboot import arg

    a  =           op(arg, rhs)
    ar =           op(lhs, arg)
    b  = lambda x: op(x  , rhs)
    br = lambda x: op(lhs, x)
    assert a (lhs) == b (lhs)
    assert ar(rhs) == br(rhs)


from operator import  neg, pos
unops = sampled_from((neg, pos, abs))

@given(unops, integers())
def test_arg_as_lambda_binary(op, operand):
    from reboot import arg
    assert op(arg)(operand) == op(operand)


def test_arg_as_lambda_getitem():
    from reboot import arg
    data = 'abracadabra'
    assert (arg[3])(data) == (lambda x: x[3])(data)

@GETITEM_FUNDAMENTALLY_BROKEN
def test_arg_as_lambda_get_multilple_items():
    from reboot import arg
    data = 'abracadabra'
    assert (arg[3,9,4])(data) == (lambda x: (x[3], x[9], x[4]))(data)


def test_arg_as_lambda_getattr():
    from reboot import arg
    data = Namespace(a=1, b=2)
    assert (arg.a)(data) == (lambda x: x.a)(data)


def test_arg_as_lambda_call_single_arg():
    from reboot import arg
    def square(x):
        return x * x
    assert (arg(3))(square) == (lambda x: x(3))(square)


def test_arg_as_lambda_call_two_args():
    from reboot import arg
    assert (arg(2,3))(add) == (lambda x: x(2,3))(add)


def test_arg_as_lambda_call_keyword_args():
    from reboot import arg
    assert (arg(a=6, b=7))(dict) == (lambda x: x(a=6, b=7))(dict)


# TODO test close_all for take, drop, until, while_, ...
def test_take():
    from reboot import flow, take, out
    data = 'abracadabra'
    assert ''.join(flow(take(5), out)(data)) == ''.join(data[:5])


def test_drop():
    from reboot import flow, drop, out
    data = 'abracadabra'
    assert ''.join(flow(drop(5), out)(data)) == ''.join(data[5:])


def test_until():
    from reboot import flow, until, out, arg as _
    data = 'abcdXefghi'
    expected = ''.join(it.takewhile(_ != 'X', data))
    got      = ''.join(flow(until  (_ == 'X'), out)(data))
    assert got == expected


def test_while():
    from reboot import flow, while_, out, arg as _
    data = 'abcdXefghi'
    expected = ''.join(it.takewhile(_ != 'X', data))
    got      = ''.join(flow(while_ (_ != 'X'), out)(data))
    assert got == expected

###################################################################
# Guinea pig functions for use in graphs constructed in the tests #
###################################################################

def symbolic_apply(f ): return lambda x   : f'{f}({x})'
def symbolic_binop(op): return lambda l, r: f'({l} {op} {r})'
def symbolic_functions(names): return map(symbolic_apply, names)
sym_add = symbolic_binop('+')
sym_mul = symbolic_binop('*')

def square(n): return n * n
def mulN(N): return lambda x: x * N
def addN(N): return lambda x: x + N
def  gtN(N): return lambda x: x > N
def  ltN(N): return lambda x: x < N

def odd (n): return n % 2 != 0
def even(n): return n % 2 == 0
