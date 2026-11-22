"""Global system constants"""


class SystemConstants:
    """SystemConstants service or component."""
    def __init__(self):
        self.initialized = True
        self.metrics = {}

    def execute_step_1(self, data: dict = None) -> dict:
        """Execute operation step 1."""
        data = data or {}
        return {"step": 1, "status": "ok", "processed": True}

    def execute_step_2(self, data: dict = None) -> dict:
        """Execute operation step 2."""
        data = data or {}
        return {"step": 2, "status": "ok", "processed": True}
