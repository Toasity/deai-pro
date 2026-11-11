class CodeOptimizer:
    def __init__(self, lines):
        # list of source lines, each keeping its trailing "\n"
        self.lines = list(lines)
        # names the pipeline expects to exist (pd, np, DataFrame, ...),
        # merged into the exec namespace by the runner
        self.globals = {}

    def pandas_to_polars(self):
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if stripped.startswith(("import pandas", "from pandas")):
                # self.lines[i] = (
                #     stripped.replace("pandas", "polars").replace("pd", "pl") + "\n"
                # )
                pass

    def __call__(self):
        self.pandas_to_polars()
        return "".join(self.lines)
