"""Patch Phase 3 runner in-place; keeps a .phase3_backup copy."""
from pathlib import Path
import shutil
p = Path('src/aimigrate/gemini_experiment.py')
s = p.read_text()
if 'from .retry import call_with_retries' in s:
    raise SystemExit('Already patched; no changes made')
checks = [
    'from .validator import validate_sql',
    '             temperature: float = 0.0) -> Observation:',
    '    def request(prompt: str) -> str:',
    '        api_calls += 1  # count attempted calls, including errors',
    '        answer, input_count, output_count = caller(prompt, model, temperature)',
    "    parser.add_argument('--max-calls', type=int, default=20,",
    "    # Each case/method can request at most one API call in this version.",
    "            result = evaluate(case, method, args.model, temperature=args.temperature)",
    '                    total_api_calls=sum(r.api_calls for r in observations),',
]
missing = [x for x in checks if x not in s]
if missing:
    raise SystemExit('Source differs from expected version; no changes made. Missing: ' + repr(missing))
s = s.replace('from .validator import validate_sql', 'from .validator import validate_sql\nfrom .retry import call_with_retries')
s = s.replace('             temperature: float = 0.0) -> Observation:',
              '             temperature: float = 0.0, max_attempts: int = 1,\n'
              '             before_api_call: Callable[[], None] | None = None) -> Observation:')
s = s.replace('''        api_calls += 1  # count attempted calls, including errors
        answer, input_count, output_count = caller(prompt, model, temperature)''', '''        def attempt() -> tuple[str, int | None, int | None]:
            return caller(prompt, model, temperature)

        def count_attempt() -> None:
            nonlocal api_calls
            if before_api_call is not None:
                before_api_call()
            api_calls += 1

        answer, input_count, output_count = call_with_retries(
            attempt, max_attempts=max_attempts, on_attempt=count_attempt)''')
s = s.replace("    args = parser.parse_args()", "    parser.add_argument('--max-attempts', type=int, default=3,\n                        help='Maximum attempts per Gemini request, including first call')\n    args = parser.parse_args()")
s = s.replace("    if args.max_calls < 0:\n        parser.error('max-calls must be nonnegative')", "    if args.max_calls < 0:\n        parser.error('max-calls must be nonnegative')\n    if args.max_attempts < 1:\n        parser.error('max-attempts must be >= 1')")
s = s.replace('    # Each case/method can request at most one API call in this version.\n',
              '    # Reserve at least one attempt for each LLM-only case.\n')
s = s.replace('''    observations = []
    for case in cases:''', '''    observations = []
    attempted_calls = 0

    def enforce_budget() -> None:
        nonlocal attempted_calls
        if attempted_calls >= args.max_calls:
            raise RuntimeError('API call budget exhausted')
        attempted_calls += 1

    for case in cases:''')
s = s.replace('''            result = evaluate(case, method, args.model, temperature=args.temperature)''', '''            result = evaluate(case, method, args.model, temperature=args.temperature,
                              max_attempts=args.max_attempts,
                              before_api_call=enforce_budget)''')
s = s.replace('                    total_api_calls=sum(r.api_calls for r in observations),',
              '                    total_api_calls=sum(r.api_calls for r in observations),\n                    max_attempts=args.max_attempts, max_calls=args.max_calls,')
backup = p.with_suffix('.py.phase3_backup')
shutil.copy2(p, backup)
p.write_text(s)
print('Patched:', p)
print('Backup:', backup)
