from operator   import itemgetter
from functools  import reduce, wraps
from contextlib import contextmanager
from itertools  import chain
from argparse   import Namespace
from asyncio    import Future


# TODO: fill slots in OpenPipe.fn at call time: OpenPipe.fn(not only here)(data, but also here)

# TODO: count-filter: implicit {} in out: out.NAME({predicate}) -> .passed & .stopped

# TODO: string as implicit pick

# TODO: get inside out

# TODO: call


class _Pipe:

    def __init__(self, components):
        self._components = tuple(map(decode_implicits, components))
        last = self._components[-1]
        if isinstance(last, Map):
            last.__class__ = Sink

    def coroutine_and_outputs(self, bindings):
        cor_out_pairs = tuple(c.coroutine_and_outputs(bindings) for c in self._components)
        coroutines = map(itemgetter(0), cor_out_pairs)
        out_groups = map(itemgetter(1), cor_out_pairs)
        return combine_coroutines(coroutines), chain(*out_groups)


class Flow:

    def __init__(self, *components):
        self._pipe = _Pipe(components)

    def __call__(self, source, **bindings):
        coroutine, outputs = self._pipe.coroutine_and_outputs(bindings)
        push(source, coroutine)
        outputs = tuple(outputs)
        print(outputs)
        return Namespace(**{name: future.result() for name, future in outputs})


# components:
#
# map
# filter
# sink:   fold, side-effect, side-effect with result
# branch
# get
# out
# call

######################################################################
#    Component types                                                 #
######################################################################

class Component:
    pass

class Sink(Component):

    def __init__(self, fn):
        self._fn = fn

    def coroutine_and_outputs(self, bindings):
        @coroutine
        def sink_loop():
            while True:
                self._fn(*(yield))
        return sink_loop(), ()


class Map(Component):

    def __init__(self, fn):
        self._fn = fn

    def coroutine_and_outputs(self, bindings):
        @coroutine
        def map_loop(target):
                with closing(target):
                    while True:
                        target.send((self._fn(*(yield)),))
        return map_loop, ()


class FlatMap(Component):

    def __init__(self, fn):
        self._fn = fn

    def coroutine_and_outputs(self, bindings):
        @coroutine
        def flatmap_loop(target):
                with closing(target):
                    while True:
                        for item in self._fn(*(yield)):
                            target.send((item,))
        return flatmap_loop, ()


class Filter(Component):

    def __init__(self, predicate):
        self._predicate = predicate

    def coroutine_and_outputs(self, bindings):
        predicate = self._predicate
        @coroutine
        def filter_loop(target):
            with closing(target):
                while True:
                    args = yield
                    if predicate(*args):
                        target.send(args)
        return filter_loop, ()


class Branch(Component):

    def __init__(self, *components):
        self._pipe = _Pipe(components)

    def coroutine_and_outputs(self, bindings):
        sideways, outputs = self._pipe.coroutine_and_outputs(bindings)
        @coroutine
        def branch_loop(downstream):
            with closing(sideways), closing(downstream):
                while True:
                    args = yield
                    sideways  .send(args)
                    downstream.send(args)
        return branch_loop, outputs


class Output(Component):

    def __init__(self, name, sink=None):
        self._name = name
        self._sink = sink

    def coroutine_and_outputs(self, bindings):
        future = Future()
        coroutine = self._sink.make_coroutine(future)
        return coroutine, ((self._name, future),)

    class Name(Component):

        def __init__(self, name):
            self.name = name

        def __call__(self, sink, initial=None):
            if not isinstance(sink, Component):
                # TODO: issue warning/error if initial is not None
                sink = Fold(sink, initial=initial)
            # TODO: set as implicit count filter?
            return Output(self.name, sink)

        def coroutine_and_outputs(self, bindings):
            def append(the_list, element):
                the_list.append(element)
                return the_list
            collect_into_list = Fold(append, [])
            return Output(self.name, collect_into_list).coroutine_and_outputs(bindings)


class Input(Component):

    def __init__(self, name):
        self.name = name

    def coroutine_and_outputs(self, bindings):
        return decode_implicits(bindings[self.name]).coroutine_and_outputs(bindings)

class MultipleNames:

    def __init__(self, *names):
        self.names = names

    def __getattr__(self, name):
        return type(self)(*self.names, name)

class Pick(MultipleNames, Component):

    def coroutine_and_outputs(self, bindings):
        return Map(itemgetter(*self.names)).coroutine_and_outputs(bindings)


class On(Component):

    def __init__(self, name):
        self.name = name

    def __call__(self, *components):
        # TODO: shoudn't really mutate self
        self.process_one_item = OpenPipe(*components).fn()
        return self

    def coroutine_and_outputs(self, bindings):
        @coroutine
        def on_loop(downstream):
            with closing(downstream):
                while True:
                    namespace, = (yield)
                    for returned in self.process_one_item(namespace[self.name]):
                        updated_namespace = namespace.copy()
                        updated_namespace[self.name] = returned
                        downstream.send((updated_namespace,))
        return on_loop, ()


class Args(MultipleNames, Component):

    def __call__(self, fn):
        # TODO: shoudn't really mutate self
        #self.process_one_item = OpenPipe(*components).fn()
        self.fn = fn
        return self

    def coroutine_and_outputs(self, bindings):
        get_args = itemgetter(*self.names)
        @coroutine
        def args_loop(downstream):
            with closing(downstream):
                while True:
                    namespace = (yield)
                    args = get_args(namespace)
                    returned = self.fn(*args)
                    downstream.send(returned)
        return args_loop, ()


class Name:

    def __init__(self, callable):
        self.callable = callable

    def __getattr__(self, name):
        return self.callable(name)


out  = Name(Output.Name)
get  = Name(Input)
pick = Name(Pick)
on   = Name(On)
args = Name(Args)


class Fold(Component):

    # TODO: future-sinks should not appear at toplevel, as they must be wrapped
    # in an output. Detect and report error at conversion from implicit

    def __init__(self, fn, initial=None):
        self._fn = fn
        self._initial = initial

    def make_coroutine(self, future):
        binary_function = self._fn
        @coroutine
        def reduce_loop(future):
            if self._initial is None:
                try:
                    accumulator, = (yield)
                except StopIteration:
                    # TODO: message about not being able to run on an empty stream.
                    # Try to link it to variable names in the network?
                    pass
            else:
                accumulator = self._initial
            try:
                while True:
                    accumulator = binary_function(accumulator, *(yield))
            finally:
                future.set_result(accumulator)
        return reduce_loop(future)


class OpenPipe:

    def __init__(self, *components):
        # TODO: should disallow branches (unless we implement joins)
        self._components = components

    def fn  (self, **bindings): return OpenPipe._Fn(self._components, bindings)
    def pipe(self, **bindings): return FlatMap     (self.fn(        **bindings))

    class _Fn:

        def __init__(self, components, bindings):
            self._pipe = _Pipe(chain(components, [Sink(self.accept_result)]))
            self._coroutine, _ = self._pipe.coroutine_and_outputs(bindings)

        def __call__(self, *args):
            self._returns = []
            self._coroutine.send(args)
            return tuple(self._returns)

        def accept_result(self, item):
            self._returns.append(item)



######################################################################

# Most component names don't have to be used explicitly, because plain python
# types have implicit interpretations as components
def decode_implicits(it):
    if isinstance(it, Component): return it
    if isinstance(it, list     ): return Branch(*it)
    if isinstance(it, tuple    ): return Sink  (*it)
    if isinstance(it, set      ): return Filter(next(iter(it)))
    else                        : return Map(it)


def push(source, pipe):
    for item in source:
        pipe.send((item,))
    pipe.close()


def combine_coroutines(coroutines):
    coroutines = tuple(coroutines)
    if not coroutines:
        raise Exception('Need at least one coroutine')
    if not hasattr(coroutines[-1], 'close'):
        raise Exception(f'No sink at end of {coroutines}')
    def apply(arg, fn):
        return fn(arg)
    return reduce(apply, reversed(coroutines))


def coroutine(generator_function):
    @wraps(generator_function)
    def proxy(*args, **kwds):
        the_coroutine = generator_function(*args, **kwds)
        next(the_coroutine)
        return the_coroutine
    return proxy


@contextmanager
def closing(target):
    try:     yield
    finally: target.close()
