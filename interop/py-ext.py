"""Python-side interop extension: serves echo/add/session/fail over NATS so a
Go/TS agent can drive it. Mirrors interop/go-ext and interop/ts-ext."""
import asyncio, os, signal, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from easybus.transport.nats import connect
from easybus.extension import Config, Extension, ToolSpec, ToolResultData, TypedError


async def _echo(args, cid, sess, ten):
    return ToolResultData(content='py-ext echo: ' + str(args.get('msg', '')))


async def _add(args, cid, sess, ten):
    return ToolResultData(data={'sum': float(args.get('a', 0)) + float(args.get('b', 0))})


async def _session(args, cid, sess, ten):
    return ToolResultData(content='session=' + sess)


async def _fail(args, cid, sess, ten):
    raise TypedError('CODE_BUSINESS', 'deliberate failure')


async def _ts_var(sess, ten):
    return 'from-py-ext/' + sess


async def main():
    url = os.environ.get('NATS_URL', 'nats://127.0.0.1:4222')
    bus = await connect(url)
    cfg = Config(
        id='py-ext', version='1.0',
        tools={
            'echo': ToolSpec(execute=_echo, description='echo content back'),
            'add': ToolSpec(execute=_add),
            'session': ToolSpec(execute=_session),
            'fail': ToolSpec(execute=_fail),
        },
        variables={'py-var': __import__('easybus.extension', fromlist=['VariableSpec']).VariableSpec(resolve=_ts_var)},
        config={'poll-interval': __import__('easybus.extension', fromlist=['ConfigSpec']).ConfigSpec(type='number', default=30)},
        on_config_change=lambda name, value, sess, get: print(f'[py-ext] config applied: {name}={value}', flush=True),
        call_hooks=['interop.before'],
        on_call_hook=lambda hook, sess, args, ten: asyncio.sleep(0, result={'ok': True, 'data': {'session': sess, 'hook': hook}}),
        event_hooks=['interop.event'],
        on_event_hook=lambda hook, sess, payload, ten: asyncio.sleep(0, result=print(f'[py-ext] event hook={hook} session={sess} payload={payload}', flush=True)),
    )
    ext = Extension(bus, cfg)
    await ext.serve()
    print(f'[py-ext] serving py-ext over {url}', flush=True)
    stop = asyncio.Event()
    loop = asyncio.get_event_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, stop.set)
    await stop.wait()
    await ext.close()
    print('[py-ext] shutting down', flush=True)


asyncio.run(main())
