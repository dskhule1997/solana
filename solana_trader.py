import logging
import asyncio
import json
import time
import base58
import secrets
from solana.rpc.async_api import AsyncClient
from solana.keypair import Keypair
from solana.publickey import PublicKey
from solana.transaction import Transaction
from solana.system_program import transfer, TransferParams
import httpx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SolanaTrader:
    def __init__(self, wallet_info=None, trading_settings=None):
        """
        Initialize the Solana trader.
        
        Args:
            wallet_info: Dictionary with wallet information (public_key, private_key)
            trading_settings: Dictionary with trading settings
        """
        self.wallet_info = wallet_info
        self.trading_settings = trading_settings or {}
        
        # Initialize RPC client (uses Solana mainnet by default)
        self.client = AsyncClient("https://api.mainnet-beta.solana.com")
        
        # Jupiter API URL
        self.jupiter_api_url = "https://quote-api.jup.ag/v6"
        
        # HTTP client for Jupiter API
        self.http_client = httpx.AsyncClient(timeout=30.0)
        
        # Load keypair if wallet info is provided
        self.keypair = None
        if wallet_info and 'private_key' in wallet_info:
            try:
                self.keypair = Keypair.from_secret_key(
                    base58.b58decode(wallet_info['private_key'])
                )
            except Exception as e:
                logger.error(f"Error loading keypair: {str(e)}")

    def create_new_wallet(self):
        """Create a new Solana wallet."""
        try:
            # Generate a new keypair
            self.keypair = Keypair()
            
            # Get private key as bytes and encode to base58
            private_key = base58.b58encode(self.keypair.secret_key).decode('utf-8')
            
            # Get public key as string
            public_key = str(self.keypair.public_key)
            
            # Update wallet info
            self.wallet_info = {
                'public_key': public_key,
                'private_key': private_key
            }
            
            logger.info(f"Created new wallet with address: {public_key}")
            
            return self.wallet_info
            
        except Exception as e:
            logger.error(f"Error creating wallet: {str(e)}")
            return None

    async def get_balance(self):
        """Get the wallet balance in SOL."""
        if not self.wallet_info or 'public_key' not in self.wallet_info:
            logger.error("No wallet configured")
            return 0
        
        try:
            response = await self.client.get_balance(
                PublicKey(self.wallet_info['public_key'])
            )
            
            # Convert lamports to SOL (1 SOL = 10^9 lamports)
            balance_sol = response['result']['value'] / 10**9
            
            return balance_sol
            
        except Exception as e:
            logger.error(f"Error getting balance: {str(e)}")
            return 0

    async def withdraw(self, amount, destination):
        """
        Withdraw SOL to another wallet.
        
        Args:
            amount: Amount of SOL to withdraw
            destination: Destination wallet address
            
        Returns:
            dict: Result of the withdrawal
        """
        if not self.keypair:
            return {'success': False, 'error': 'No wallet configured'}
        
        try:
            # Convert SOL to lamports
            lamports = int(amount * 10**9)
            
            # Create transfer instruction
            transfer_ix = transfer(
                TransferParams(
                    from_pubkey=self.keypair.public_key,
                    to_pubkey=PublicKey(destination),
                    lamports=lamports
                )
            )
            
            # Create and sign transaction
            transaction = Transaction().add(transfer_ix)
            transaction.recent_blockhash = (await self.client.get_recent_blockhash())['result']['value']['blockhash']
            transaction.sign(self.keypair)
            
            # Send transaction
            result = await self.client.send_raw_transaction(transaction.serialize())
            
            if 'result' in result:
                signature = result['result']
                logger.info(f"Withdrawal successful, signature: {signature}")
                return {
                    'success': True,
                    'signature': signature
                }
            else:
                logger.error(f"Withdrawal failed: {result}")
                return {
                    'success': False,
                    'error': str(result.get('error', 'Unknown error'))
                }
                
        except Exception as e:
            logger.error(f"Error during withdrawal: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_token_price(self, token_address):
        """
        Get the current price of a token in SOL.
        
        Args:
            token_address: Token mint address
            
        Returns:
            float: Token price in SOL
        """
        try:
            # Use Jupiter API to get a quote for 1 token to SOL
            params = {
                'inputMint': token_address,
                'outputMint': 'So11111111111111111111111111111111111111112',  # Wrapped SOL
                'amount': '1000000',  # 1 token with 6 decimals
                'slippageBps': 50  # 0.5% slippage
            }
            
            response = await self.http_client.get(
                f"{self.jupiter_api_url}/quote",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                # Extract the price in SOL
                price_in_lamports = int(data['outAmount'])
                price_in_sol = price_in_lamports / 10**9
                return price_in_sol
            else:
                logger.error(f"Error getting token price: {response.text}")
                return 0
                
        except Exception as e:
            logger.error(f"Error getting token price: {str(e)}")
            return 0

    async def buy_token(self, token_address, sol_amount, slippage=1):
        """
        Buy a token using the Jupiter API.
        
        Args:
            token_address: Token mint address
            sol_amount: Amount of SOL to spend
            slippage: Maximum slippage percentage
            
        Returns:
            dict: Result of the purchase
        """
        if not self.keypair:
            return {'success': False, 'error': 'No wallet configured'}
        
        try:
            # Convert SOL to lamports
            lamports = int(sol_amount * 10**9)
            
            # Get quote from Jupiter
            params = {
                'inputMint': 'So11111111111111111111111111111111111111112',  # Wrapped SOL
                'outputMint': token_address,
                'amount': str(lamports),
                'slippageBps': int(slippage * 100),  # Convert percentage to basis points
                'platformFeeBps': 0,  # No platform fee
                'onlyDirectRoutes': False
            }
            
            quote_response = await self.http_client.get(
                f"{self.jupiter_api_url}/quote",
                params=params
            )
            
            if quote_response.status_code != 200:
                return {
                    'success': False,
                    'error': f"Quote error: {quote_response.text}"
                }
            
            quote_data = quote_response.json()
            
            # Get the swap instructions from Jupiter
            swap_params = {
                'quoteResponse': quote_data,
                'userPublicKey': str(self.keypair.public_key),
                'wrapUnwrapSOL': True
            }
            
            swap_response = await self.http_client.post(
                f"{self.jupiter_api_url}/swap-instructions",
                json=swap_params
            )
            
            if swap_response.status_code != 200:
                return {
                    'success': False,
                    'error': f"Swap instructions error: {swap_response.text}"
                }
            
            swap_data = swap_response.json()
            
            # Now we'd execute the transaction using the swap instructions
            # This is a simplified version; in a real implementation, you'd need to:
            # 1. Deserialize and execute the transaction instructions
            # 2. Sign the transaction
            # 3. Send the transaction
            # 4. Wait for confirmation
            
            # For now, we'll simulate a successful trade
            logger.info(f"Simulating purchase of token {token_address} with {sol_amount} SOL")
            
            # Calculate token amount received (from quote)
            token_amount = int(quote_data['outAmount']) / 10**6  # Assuming 6 decimals
            
            # Calculate price per token
            price_per_token = sol_amount / token_amount
            
            return {
                'success': True,
                'amount': token_amount,
                'price': price_per_token,
                'transaction_id': f"sim_{secrets.token_hex(16)}"
            }
            
        except Exception as e:
            logger.error(f"Error buying token: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def sell_token(self, token_address, token_amount, slippage=1):
        """
        Sell a token using the Jupiter API.
        
        Args:
            token_address: Token mint address
            token_amount: Amount of tokens to sell
            slippage: Maximum slippage percentage
            
        Returns:
            dict: Result of the sale
        """
        if not self.keypair:
            return {'success': False, 'error': 'No wallet configured'}
        
        try:
            # Convert token_amount to token units with 6 decimals (common for SPL tokens)
            token_units = int(token_amount * 10**6)
            
            # Get quote from Jupiter
            params = {
                'inputMint': token_address,
                'outputMint': 'So11111111111111111111111111111111111111112',  # Wrapped SOL
                'amount': str(token_units),
                'slippageBps': int(slippage * 100),  # Convert percentage to basis points
                'platformFeeBps': 0  # No platform fee
            }
            
            quote_response = await self.http_client.get(
                f"{self.jupiter_api_url}/quote",
                params=params
            )
            
            if quote_response.status_code != 200:
                return {
                    'success': False,
                    'error': f"Quote error: {quote_response.text}"
                }
            
            quote_data = quote_response.json()
            
            # Get the swap instructions from Jupiter
            swap_params = {
                'quoteResponse': quote_data,
                'userPublicKey': str(self.keypair.public_key),
                'wrapUnwrapSOL': True
            }
            
            swap_response = await self.http_client.post(
                f"{self.jupiter_api_url}/swap-instructions",
                json=swap_params
            )
            
            if swap_response.status_code != 200:
                return {
                    'success': False,
                    'error': f"Swap instructions error: {swap_response.text}"
                }
            
            swap_data = swap_response.json()
            
            # Now we'd execute the transaction using the swap instructions
            # This is a simplified version; in a real implementation, you'd need to:
            # 1. Deserialize and execute the transaction instructions
            # 2. Sign the transaction
            # 3. Send the transaction
            # 4. Wait for confirmation
            
            # For now, we'll simulate a successful trade
            logger.info(f"Simulating sale of {token_amount} tokens of {token_address}")
            
            # Calculate SOL received (from quote)
            sol_received = int(quote_data['outAmount']) / 10**9
            
            # Calculate price per token
            price_per_token = sol_received / token_amount
            
            return {
                'success': True,
                'amount_sold': token_amount,
                'sol_received': sol_received,
                'price': price_per_token,
                'transaction_id': f"sim_{secrets.token_hex(16)}"
            }
            
        except Exception as e:
            logger.error(f"Error selling token: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }