"""Invoice generation and tax calculation."""

from typing import Dict, Any, List
from ..services.account_service import AccountService

class InvoiceService:
    """Manages invoice lifecycle and calls AccountService."""
    def __init__(self):
        self.account_service = AccountService()

    def generate_invoice(self, user_id: str, amount: float) -> Dict[str, Any]:
        account = self.account_service.get_account(user_id)
        return {"invoice_id": "INV-100", "user_id": user_id, "amount": amount, "account": account}
