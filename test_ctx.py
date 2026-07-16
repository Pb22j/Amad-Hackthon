import asyncio
import contextvars
import langchain_core.tools

c = contextvars.ContextVar('c', default=None)

async def t() -> str:
    return str(c.get())

tool = langchain_core.tools.StructuredTool.from_function(
    coroutine=t, name='t', description='t'
)

async def m():
    c.set('hi')
    res = await tool.ainvoke({})
    print("Result:", res)

asyncio.run(m())
