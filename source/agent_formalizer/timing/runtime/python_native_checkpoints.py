"""Version-checked, named Python cancellation sites for external-call escrow.

Only timeout calculations that can enclose model/solver calls are replaced.
Output text, physical timing metadata, yield sleeps, process cleanup and the
native choice of sequential/concurrent tools are deliberately untouched.
"""
import ast

TARGETS = {
    'generic': {'ga', 'llmcore'},
    'hermes': {'tools.environments.base', 'tools.process_registry', 'agent.tool_executor'},
    'nanobot': {'nanobot.agent.tools.shell', 'nanobot.agent.tools.exec_session',
                'nanobot.agent.tools.registry', 'nanobot.agent.runner'},
}


def transform(source, module, filename):
    tree = ast.parse(source, filename)
    counts = {}

    def change(key):
        counts[key] = counts.get(key, 0) + 1

    def expression(value):
        return ast.parse(value, mode='eval').body

    def wrap(node, context):
        body = ast.parse('with ' + context + ':\n    pass').body[0]
        body.body = node.body
        node.body = [body]

    class Rewrite(ast.NodeTransformer):
        def __init__(self):
            self.functions = []

        def function(self, node):
            self.functions.append(node.name)
            node = self.generic_visit(node)
            self.functions.pop()
            selected = (module, node.name)
            timed = {
                ('ga', 'code_run'), ('tools.environments.base', '_wait_for_process'),
                ('tools.process_registry', 'wait'),
                ('agent.tool_executor', 'execute_tool_calls_concurrent'),
                ('nanobot.agent.tools.exec_session', '_wait_for_output'),
            }
            if selected in timed:
                wrap(node, "__import__('contextlib').ExitStack() as _benchmark_deadlines")
            watched = {
                ('llmcore', '_stream_with_retry'): 'payload',
                ('agent.tool_executor', 'execute_tool_calls_concurrent'): 'messages',
                ('agent.tool_executor', 'execute_tool_calls_sequential'): 'messages',
                ('nanobot.agent.runner', '_run_core'): 'messages',
            }
            if selected in watched:
                wrap(node, "__import__('python_checkpoints').watch_context(" + watched[selected] + ')')
                change('context')
            if selected in {('ga', 'code_run'),
                            ('agent.tool_executor', '_run_agent_tool_execution_middleware'),
                            ('nanobot.agent.tools.registry', 'execute')}:
                wrap(node, "__import__('python_checkpoints').tool_activity()")
                change('activity')
            return node

        visit_FunctionDef = function
        visit_AsyncFunctionDef = function

        def visit_Assign(self, node):
            fn = self.functions[-1] if self.functions else None
            value = ast.unparse(node.value)
            target = ast.unparse(node.targets[0])
            duration = None
            if (module, fn, target, value) == ('ga', 'code_run', 'start_t', 'time.time()'):
                # Start at precisely the native initialization point, not before
                # command creation, imports or process startup.
                new = ast.parse("_benchmark_deadline = _benchmark_deadlines.enter_context(__import__('benchmark_logical_time').Deadline(timeout))").body[0]
                change('deadline')
                return [node, ast.copy_location(new, node)]
            if (module, fn, target) == ('tools.environments.base', '_wait_for_process', 'deadline') and value == 'time.monotonic() + timeout':
                duration = 'timeout'
            if (module, fn, target) == ('tools.process_registry', 'wait', 'deadline') and value == 'time.monotonic() + effective_timeout':
                duration = 'effective_timeout'
            if (module, fn, target) == ('agent.tool_executor', 'execute_tool_calls_concurrent', 'deadline') and value == 'time.monotonic() + timeout_s if timeout_s is not None else None':
                duration = 'timeout_s'
            if (module, fn, target, value) == ('nanobot.agent.tools.exec_session', '_wait_for_output', 'deadline', 'time.monotonic() + wait_timeout_ms / 1000'):
                duration = 'wait_timeout_ms / 1000'
            if duration:
                value = "_benchmark_deadlines.enter_context(__import__('benchmark_logical_time').Deadline(" + duration + ')).target'
                if duration == 'timeout_s':
                    value += ' if timeout_s is not None else None'
                node.value = expression(value)
                change('deadline')
                return node
            if module == 'nanobot.agent.tools.exec_session' and target == 'self.deadline' and value == "time.monotonic() + timeout if timeout else float('inf')":
                # Native session expiry is checked ONLY when polled. Do not
                # create an active lease or introduce an eager timeout callback.
                node.value = expression("__import__('benchmark_logical_time').logical_now() + timeout if timeout else float('inf')")
                change('session_deadline')
                return node
            return self.generic_visit(node)

        def visit_Compare(self, node):
            fn = self.functions[-1] if self.functions else None
            if (module, fn) == ('ga', 'code_run') and ast.unparse(node) == 'time.time() - start_t > timeout':
                change('expiry')
                return ast.copy_location(expression('_benchmark_deadline.expired()'), node)
            if module == 'nanobot.agent.tools.exec_session' and ast.unparse(node) == 'time.monotonic() >= self.deadline':
                node.left = expression("__import__('benchmark_logical_time').logical_now()")
                change('session_expiry')
                return node
            if (module, fn) in {('tools.environments.base', '_wait_for_process'),
                                 ('tools.process_registry', 'wait'),
                                 ('agent.tool_executor', 'execute_tool_calls_concurrent')} and ast.unparse(node) in {
                                     'time.monotonic() > deadline', 'time.monotonic() < deadline',
                                     'time.monotonic() >= deadline'}:
                node.left = expression("__import__('benchmark_logical_time').logical_now()")
                change('clock_read')
                return node
            return self.generic_visit(node)

        def visit_BinOp(self, node):
            fn = self.functions[-1] if self.functions else None
            if (module, fn) in {('tools.process_registry', 'wait'),
                                 ('agent.tool_executor', 'execute_tool_calls_concurrent'),
                                 ('nanobot.agent.tools.exec_session', '_wait_for_output')} and ast.unparse(node) == 'deadline - time.monotonic()':
                node.right = expression("__import__('benchmark_logical_time').logical_now()")
                change('clock_read')
                return node
            if module == 'nanobot.agent.tools.exec_session' and ast.unparse(node) == 'session.deadline - now':
                node.right = expression("__import__('benchmark_logical_time').logical_now()")
                change('session_remaining')
                return node
            return self.generic_visit(node)

        def visit_Call(self, node):
            fn = self.functions[-1] if self.functions else None
            if ast.unparse(node.func) == 'asyncio.wait_for' and node.args and (
                (module == 'nanobot.agent.tools.shell' and ast.unparse(node.args[0]) == 'process.communicate()') or
                (module == 'nanobot.agent.runner' and ast.unparse(node.args[0]) == 'coro')
            ):
                node.func = expression("__import__('benchmark_logical_time').wait_for")
                change('wait_for')
            return self.generic_visit(node)

    tree = Rewrite().visit(tree)
    expected = {
        'ga': {'deadline': 1, 'expiry': 1, 'activity': 1},
        'llmcore': {'context': 1},
        'tools.environments.base': {'deadline': 1, 'clock_read': 1},
        'tools.process_registry': {'deadline': 1, 'clock_read': 2},
        'agent.tool_executor': {'deadline': 1, 'clock_read': 2, 'context': 2, 'activity': 1},
        'nanobot.agent.tools.shell': {'wait_for': 1},
        'nanobot.agent.tools.exec_session': {'session_deadline': 1, 'session_expiry': 1, 'session_remaining': 1, 'deadline': 1, 'clock_read': 1},
        'nanobot.agent.tools.registry': {'activity': 1},
        'nanobot.agent.runner': {'context': 1, 'wait_for': 1},
    }
    if counts != expected.get(module):
        raise RuntimeError(f'checkpoint native source mismatch: {module}: {counts}, expected {expected.get(module)}')
    return compile(ast.fix_missing_locations(tree), filename, 'exec')
