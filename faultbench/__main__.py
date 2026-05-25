"""Enable ``python -m faultbench`` execution.

Delegates directly to the Click CLI entry point defined in
:mod:`faultbench.cli`.
"""

from faultbench.cli import main

if __name__ == "__main__":
    main()
