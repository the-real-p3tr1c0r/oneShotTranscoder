from pgsrip.api import Pgs
from pgsrip.options import Options
from pathlib import Path

# Test with a dummy file first
options = Options()
p = Pgs('test', options, lambda: b'', '/tmp')

print("Pgs attributes:", [m for m in dir(p) if not m.startswith('_')])
print("items type:", type(p.items))
print("items:", p.items)

# Try to use as context manager
try:
    with p as pg:
        print("Context manager works")
        print("pg type:", type(pg))
        print("pg attributes:", [m for m in dir(pg) if not m.startswith('_')][:15])
        if hasattr(pg, 'items'):
            print("pg.items:", pg.items)
except Exception as e:
    print("Error:", e)

