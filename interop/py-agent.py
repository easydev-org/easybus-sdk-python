"""Python-side interop agent: discovers a Go extension (go-ext) and asserts the
cross-language wire contract. Mirrors interop/go-agent and interop/ts-agent."""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from easybus.transport.nats import connect
from easybus.agent import Agent


def expect(cond, msg):
    if not cond:
        print('[py-agent] FAIL:', msg, flush=True)
        sys.exit(1)
    print('[py-agent] ok:', msg, flush=True)


async def main():
    url = os.environ.get('NATS_URL', 'nats://127.0.0.1:4222')
    bus = await connect(url)
    a = Agent(bus)
    print('[py-agent] connected to', url, flush=True)

    ms = await a.discover(1000)
    expect(any(m.id == 'go-ext' for m in ms), 'discover sees go-ext')

    tr = await a.call_tool('i1', 'sess-x', 'go-ext', 'echo', 'c1', {'msg': 'hello-from-py'})
    expect(tr.content == 'go-ext echo: hello-from-py', 'tool echo content')

    s = await a.call_tool('i1', 'sess-x', 'go-ext', 'session', 'c2', {})
    expect(s.content == 'session=sess-x', 'session name')

    e = await a.call_tool('i1', 'sess-x', 'go-ext', 'fail', 'c3', {})
    expect(e.error and e.error['code'] == 'CODE_BUSINESS' and e.error['message'] == 'deliberate failure', 'business error mapping')

    await a.publish_event_hook('i1', 'interop.event', 'sess-py', {'from': 'py-agent'})
    print('[py-agent] ok: event hook published (check go-ext stdout)', flush=True)
    print('[py-agent] ALL INTEROP CHECKS PASSED', flush=True)
    await a.close()


asyncio.run(main())
