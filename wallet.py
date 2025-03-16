import solana

class Wallet:
    def __init__(self):
        self.public_key = None
        self.private_key = None

    def create_wallet(self):
        # Create a new wallet
        self.public_key, self.private_key = solana.account.create_account()
        return self.public_key

    def get_balance(self, address=None):
        # Get the wallet balance
        if address:
            return solana.rpc.api.get_balance(address)
        else:
            return solana.rpc.api.get_balance(self.public_key)

    def withdraw(self, amount):
        # Withdraw funds from the wallet
        solana.rpc.api.transfer_sol(self.public_key, amount)

    def get_transaction_history(self):
        # Get the transaction history
        return solana.rpc.api.get_transaction_history(self.public_key)