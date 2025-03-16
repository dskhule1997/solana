import logging
import asyncio
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telethon import TelegramClient, events
from telethon.tl.types import Channel
import nest_asyncio
nest_asyncio.apply()

# Local imports
from telegram_listener import TelegramListener
from solana_trader import SolanaTrader

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
SETUP, ADDING_GROUP, REMOVING_GROUP, SETTING_INVESTMENT, SETTING_TAKE_PROFIT = range(5)

class TradingBot:
    def __init__(self):
        # Load credentials
        self.credentials = self._load_credentials()
        self.wallet_info = self._load_wallet_info()
        self.monitored_groups = self._load_monitored_groups()
        self.trading_settings = self._load_trading_settings()
        
        self.wallets = self._load_wallets()
            # If we have a wallet_info but no wallets yet, migrate it
        if self.wallet_info and not self.wallets['wallets']:
            self.wallet_info['name'] = "Wallet 1"
            self.wallets['wallets'].append(self.wallet_info)
            self.wallets['active_wallet_index'] = 0
            self._save_wallets()
        # Initialize components
        self.solana_trader = SolanaTrader(self.wallet_info, self.trading_settings)
        
        # Create the telegram listener
        self.telegram_listener = TelegramListener(
            api_id=self.credentials['api_id'],
            api_hash=self.credentials['api_hash'],
            bot_token=self.credentials['bot_token'],
            callback=self.process_new_ca
        )
        
        # Initialize the telegram bot
        self.telegram_bot = Application.builder().token(self.credentials['bot_token']).build()
        self._setup_handlers()

    def _load_credentials(self):
        try:
            with open('credentials.txt', 'r') as f:
                creds = {}
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        creds[key.strip()] = value.strip().strip("'").strip('"')
                return creds
        except FileNotFoundError:
            logger.error("Credentials file not found. Please create a credentials.txt file.")
            return {
                'api_id': '',
                'api_hash': '',
                'bot_token': ''
            }

    def _load_wallet_info(self):
        try:
            with open('wallet_credentials.txt', 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _save_wallet_info(self, wallet_info):
        with open('wallet_credentials.txt', 'w') as f:
            json.dump(wallet_info, f)
        self.wallet_info = wallet_info

    def _load_monitored_groups(self):
        try:
            with open('monitored_groups.txt', 'r') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            return []

    def _save_monitored_groups(self):
        with open('monitored_groups.txt', 'w') as f:
            for group in self.monitored_groups:
                f.write(f"{group}\n")

    def _load_trading_settings(self):
        try:
            with open('trading_settings.json', 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Default settings
            default_settings = {
                'initial_investment': 0.1,  # SOL
                'take_profit_percentage': 30,  # %
                'sell_percentage': 50,  # %
                'max_slippage': 1,  # %
                'traded_tokens': []  # List of already traded token addresses
            }
            with open('trading_settings.json', 'w') as f:
                json.dump(default_settings, f)
            return default_settings

    def _load_wallets(self):
        """Load all saved wallets."""
        try:
            with open('wallets.json', 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Initialize with empty list
            wallets = {'wallets': [], 'active_wallet_index': -1}
            with open('wallets.json', 'w') as f:
                json.dump(wallets, f)
            return wallets

    def _save_wallets(self):
        """Save all wallets to file."""
        with open('wallets.json', 'w') as f:
            json.dump(self.wallets, f)

    def _get_active_wallet(self):
        """Get the currently active wallet."""
        if self.wallets['active_wallet_index'] >= 0 and len(self.wallets['wallets']) > self.wallets['active_wallet_index']:
            return self.wallets['wallets'][self.wallets['active_wallet_index']]
        return None

    def _save_trading_settings(self):
        with open('trading_settings.json', 'w') as f:
            json.dump(self.trading_settings, f)

    def _setup_handlers(self):
        # Command handlers
        self.telegram_bot.add_handler(CommandHandler("start", self.start))
        self.telegram_bot.add_handler(CommandHandler("help", self.help_command))
        self.telegram_bot.add_handler(CommandHandler("create_wallet", self.create_wallet))
        self.telegram_bot.add_handler(CommandHandler("wallet_info", self.wallet_info_command))
        self.telegram_bot.add_handler(CommandHandler("withdraw", self.withdraw))
        self.telegram_bot.add_handler(CommandHandler("add_group", self.add_group))
        self.telegram_bot.add_handler(CommandHandler("remove_group", self.remove_group))
        self.telegram_bot.add_handler(CommandHandler("list_groups", self.list_groups))
        self.telegram_bot.add_handler(CommandHandler("settings", self.show_settings))
        self.telegram_bot.add_handler(CommandHandler("set_investment", self.set_investment))
        self.telegram_bot.add_handler(CommandHandler("set_take_profit", self.set_take_profit))
        self.telegram_bot.add_handler(CommandHandler("manage_wallets", self.manage_wallets))
        self.telegram_bot.add_handler(CommandHandler("manage_wallets", self.manage_wallets_command))
        # Callback query handler
        self.telegram_bot.add_handler(CallbackQueryHandler(self.button_handler))
        
        # Conversation handlers for more complex flows
        self.telegram_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_handler))
        
        # Error handler
        self.telegram_bot.add_error_handler(self.error_handler)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /start is issued."""
        user = update.effective_user
        # Store the chat ID for notifications
        self.user_chat_id = update.effective_chat.id
        
        welcome_text = (
            f"Hi {user.first_name}! I'm your Solana Trading Bot.\n\n"
            "I can monitor Telegram groups for new Solana tokens and trade them automatically."
        )
        
        keyboard = [
            [InlineKeyboardButton("Manage Wallets", callback_data='manage_wallets')],
            [InlineKeyboardButton("Create Wallet", callback_data='create_wallet')],
            [InlineKeyboardButton("Wallet Info", callback_data='wallet_info')],
            [InlineKeyboardButton("Manage Groups", callback_data='manage_groups')],
            [InlineKeyboardButton("Trading Settings", callback_data='trading_settings')],
            [InlineKeyboardButton("Help", callback_data='help')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /help is issued."""
        help_text = (
            "🤖 *Solana Trading Bot Commands* 🤖\n\n"
            "*Wallet Commands:*\n"
            "/create_wallet - Generate a new Solana wallet\n"
            "/wallet_info - Display your current wallet info\n"
            "/withdraw <amount> <address> - Withdraw funds to another wallet\n\n"
            
            "*Group Management:*\n"
            "/add_group <group_link> - Add a Telegram group to monitor\n"
            "/remove_group - Shows a list of groups to remove\n"
            "/list_groups - List all monitored groups\n\n"
            
            "*Trading Settings:*\n"
            "/settings - View current trading settings\n"
            "/set_investment <amount> - Set initial investment amount in SOL\n"
            "/set_take_profit <profit_percentage> <sell_percentage> - Set take profit conditions\n"
            "Example: /set_take_profit 30 50 - Sell 50% when profit reaches 30%\n\n"
            
            "*Other Commands:*\n"
            "/start - Show the main menu\n"
            "/help - Display this help message"
        )
        
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def create_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Create a new Solana wallet."""
        # Generate a new wallet using the SolanaTrader
        new_wallet = self.solana_trader.create_new_wallet()
        
        if new_wallet:
            # Add name to wallet info
            new_wallet['name'] = f"Wallet {len(self.wallets['wallets']) + 1}"
                        
            # Add to wallets list
            self.wallets['wallets'].append(new_wallet)
                        
            # Set as active wallet
            self.wallets['active_wallet_index'] = len(self.wallets['wallets']) - 1
                        
            # Save wallets
            self._save_wallets()
            
            # Update trader's wallet info
            self.solana_trader.wallet_info = new_wallet
            self.wallet_info = new_wallet  # For backward compatibility
            
            # Only show part of the private key for security
            private_key = new_wallet['private_key']
            safe_private_key = f"{private_key[:5]}...{private_key[-5:]}"
            
            response = (
                "✅ New wallet created successfully!\n\n"
                f"🔑 Public Address: `{new_wallet['public_key']}`\n\n"
                f"🔐 Private Key: `{safe_private_key}`\n\n"
                "⚠️ *IMPORTANT:* Your wallet has been saved and set as active."
            )
        else:
            response = "❌ Failed to create a new wallet. Please try again later."
        
        await update.message.reply_text(response, parse_mode='Markdown')

    async def manage_wallets(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        keyboard = []
        
        # Add button for each wallet
        for i, wallet in enumerate(self.wallets['wallets']):
            wallet_name = wallet.get('name', f"Wallet {i+1}")
            active_marker = "✅ " if i == self.wallets['active_wallet_index'] else ""
            keyboard.append([InlineKeyboardButton(
                f"{active_marker}{wallet_name} ({wallet['public_key'][:6]}...)", 
                callback_data=f"select_wallet_{i}"
            )])
        
        # Add button to create new wallet
        keyboard.append([InlineKeyboardButton("➕ Create New Wallet", callback_data="create_wallet")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔑 *Wallet Management*\n\n"
            f"Total Wallets: {len(self.wallets['wallets'])}\n"
            "Select a wallet to make it active:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
    )
    
    async def manage_wallets_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show wallet management options from command."""
        keyboard = []
        
        # Add button for each wallet
        for i, wallet in enumerate(self.wallets['wallets']):
            wallet_name = wallet.get('name', f"Wallet {i+1}")
            active_marker = "✅ " if i == self.wallets['active_wallet_index'] else ""
            keyboard.append([InlineKeyboardButton(
                f"{active_marker}{wallet_name}", 
                callback_data=f"select_wallet_{i}"
            )])
        
        # Add button to create new wallet
        keyboard.append([InlineKeyboardButton("➕ Create New Wallet", callback_data="create_wallet")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔑 *Wallet Management*\n\nSelect a wallet to use or create a new one:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
    )
      
    async def wallet_info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Display wallet information."""
        if not self.wallet_info:
            await update.message.reply_text(
                "❌ No wallet configured. Use /create_wallet to create a new one."
            )
            return
        
        # Get current balance
        balance = await self.solana_trader.get_balance()
        
        # Only show part of the private key for security
        private_key = self.wallet_info['private_key']
        safe_private_key = f"{private_key[:5]}...{private_key[-5:]}"
        
        response = (
            "🔑 *Wallet Information*\n\n"
            f"Public Address: `{self.wallet_info['public_key']}`\n\n"
            f"Private Key: `{safe_private_key}`\n\n"
            f"Balance: {balance} SOL"
        )
        
        await update.message.reply_text(response, parse_mode='Markdown')

    async def withdraw(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Withdraw funds to another wallet."""
        if not self.wallet_info:
            await update.message.reply_text(
                "❌ No wallet configured. Use /create_wallet to create a new one."
            )
            return
        
        if len(context.args) != 2:
            await update.message.reply_text(
                "❌ Please use the format: /withdraw <amount> <destination_address>"
            )
            return
        
        try:
            amount = float(context.args[0])
            destination = context.args[1]
            
            # Validate the amount and destination
            if amount <= 0:
                await update.message.reply_text("❌ Amount must be greater than 0.")
                return
            
            # Send the transaction
            result = await self.solana_trader.withdraw(amount, destination)
            
            if result['success']:
                response = (
                    "✅ Withdrawal successful!\n\n"
                    f"Amount: {amount} SOL\n"
                    f"Destination: {destination}\n"
                    f"Transaction signature: {result['signature']}"
                )
            else:
                response = f"❌ Withdrawal failed: {result['error']}"
                
            await update.message.reply_text(response)
            
        except ValueError:
            await update.message.reply_text("❌ Invalid amount. Please provide a valid number.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def add_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Add a Telegram group to monitor."""
        if len(context.args) != 1:
            await update.message.reply_text(
                "❌ Please provide the group link.\n"
                "Example: /add_group https://t.me/groupname"
            )
            return
        
        group_link = context.args[0]
        
        # Validate the group link
        if not group_link.startswith("https://t.me/"):
            await update.message.reply_text(
                "❌ Invalid group link. It should start with https://t.me/"
            )
            return
        
        # Add to the list if not already there
        if group_link not in self.monitored_groups:
            self.monitored_groups.append(group_link)
            self._save_monitored_groups()
            
            # Add the listener for this group
            await self.telegram_listener.add_group(group_link)
            
            response = f"✅ Successfully added {group_link} to monitored groups."
        else:
            response = f"⚠️ {group_link} is already being monitored."
        
        await update.message.reply_text(response)

    async def remove_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show groups to remove with inline buttons."""
        if not self.monitored_groups:
            await update.message.reply_text("❌ No groups are currently being monitored.")
            return
        
        keyboard = []
        for group in self.monitored_groups:
            keyboard.append([InlineKeyboardButton(group, callback_data=f"remove_{group}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Select a group to remove:",
            reply_markup=reply_markup
        )

    async def list_groups(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """List all monitored groups."""
        if not self.monitored_groups:
            await update.message.reply_text("⚠️ No groups are currently being monitored.")
            return
        
        response = "📋 *Monitored Groups:*\n\n"
        for i, group in enumerate(self.monitored_groups, 1):
            response += f"{i}. {group}\n"
        
        await update.message.reply_text(response, parse_mode='Markdown')

    async def show_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show current trading settings."""
        settings = self.trading_settings
        
        response = (
            "⚙️ *Trading Settings*\n\n"
            f"Initial Investment: {settings['initial_investment']} SOL\n"
            f"Take Profit: {settings['take_profit_percentage']}%\n"
            f"Sell Percentage: {settings['sell_percentage']}%\n"
            f"Max Slippage: {settings['max_slippage']}%\n\n"
            f"Tokens Traded: {len(settings['traded_tokens'])}"
        )
        
        keyboard = [
            [InlineKeyboardButton("Set Investment", callback_data='set_investment')],
            [InlineKeyboardButton("Set Take Profit", callback_data='set_take_profit')],
            [InlineKeyboardButton("Main Menu", callback_data='main_menu')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')

    async def set_investment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Set the initial investment amount."""
        if len(context.args) != 1:
            await update.message.reply_text(
                "❌ Please provide the investment amount in SOL.\n"
                "Example: /set_investment 0.5"
            )
            return
        
        try:
            amount = float(context.args[0])
            
            if amount <= 0:
                await update.message.reply_text("❌ Amount must be greater than 0.")
                return
            
            self.trading_settings['initial_investment'] = amount
            self._save_trading_settings()
            
            await update.message.reply_text(f"✅ Initial investment amount set to {amount} SOL.")
            
        except ValueError:
            await update.message.reply_text("❌ Invalid amount. Please provide a valid number.")

    async def set_take_profit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Set the take profit conditions."""
        if len(context.args) != 2:
            await update.message.reply_text(
                "❌ Please provide both profit percentage and sell percentage.\n"
                "Example: /set_take_profit 30 50"
            )
            return
        
        try:
            profit_percentage = float(context.args[0])
            sell_percentage = float(context.args[1])
            
            if profit_percentage <= 0 or sell_percentage <= 0 or sell_percentage > 100:
                await update.message.reply_text(
                    "❌ Invalid values. Profit percentage must be greater than 0, "
                    "and sell percentage must be between 0 and 100."
                )
                return
            
            self.trading_settings['take_profit_percentage'] = profit_percentage
            self.trading_settings['sell_percentage'] = sell_percentage
            self._save_trading_settings()
            
            await update.message.reply_text(
                f"✅ Take profit settings updated:\n"
                f"- Sell {sell_percentage}% of tokens when profit reaches {profit_percentage}%"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Invalid values. Please provide valid numbers.")

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
    
        callback_data = query.data
    
                # In button_handler method
            # In button_handler method
        if callback_data == 'create_wallet':
            # Create new wallet
            wallet_info = self.solana_trader.create_new_wallet()
            
            if wallet_info:
                # Add name to wallet info
                wallet_info['name'] = f"Wallet {len(self.wallets['wallets']) + 1}"
                
                # Add to wallets list
                self.wallets['wallets'].append(wallet_info)
                
                # Set as active wallet if this is the first wallet
                if len(self.wallets['wallets']) == 1:
                    self.wallets['active_wallet_index'] = 0
                
                # Save wallets
                self._save_wallets()
                
                # Update trader's wallet info to use the active wallet
                self.solana_trader.wallet_info = self._get_active_wallet()
                
                # Only show part of the private key for security
                private_key = wallet_info['private_key']
                safe_private_key = f"{private_key[:5]}...{private_key[-5:]}"
                
                response = (
                    "✅ New wallet created successfully!\n\n"
                    f"🔑 Public Address: {wallet_info['public_key']}\n\n"
                    f"🔐 Private Key: {safe_private_key}\n\n"
                    f"Total Wallets: {len(self.wallets['wallets'])}\n"
                    "Use 'Manage Wallets' to switch between wallets."
                )
        
                await query.edit_message_text(response)
            else:
                await query.edit_message_text("❌ Failed to create a new wallet. Please try again later.")
                
            
        elif callback_data == 'wallet_info':
            # Direct handling in button_handler instead of calling wallet_info_command
            if not self.wallet_info:
                await query.edit_message_text(
                    "❌ No wallet configured. Use /create_wallet to create a new one."
                )
                return
            
            # Get current balance
            try:
                balance = await self.solana_trader.get_balance()
            except Exception as e:
                logger.error(f"Error getting balance: {str(e)}")
                balance = 0
            
            # Only show part of the private key for security
            private_key = self.wallet_info['private_key']
            safe_private_key = f"{private_key[:5]}...{private_key[-5:]}"
            
            response = (
                "🔑 Wallet Information\n\n"
                f"Public Address: {self.wallet_info['public_key']}\n\n"
                f"Private Key: {safe_private_key}\n\n"
                f"Balance: {balance} SOL"
            )
            
            await query.edit_message_text(response)
        elif callback_data == 'manage_wallets':
            await self.manage_wallets(update, context)

        elif callback_data.startswith('select_wallet_'):
            # Extract wallet index from callback data
            wallet_index = int(callback_data[14:])
            
            if wallet_index >= 0 and wallet_index < len(self.wallets['wallets']):
                # Set as active wallet
                self.wallets['active_wallet_index'] = wallet_index
                selected_wallet = self.wallets['wallets'][wallet_index]
                
                # Update trader's wallet info
                self.solana_trader.wallet_info = selected_wallet
                self.wallet_info = selected_wallet  # For backward compatibility
                
                # Save wallets
                self._save_wallets()
                
                wallet_name = selected_wallet.get('name', f"Wallet {wallet_index+1}")
                await query.edit_message_text(f"✅ Wallet '{wallet_name}' is now active.")
            else:
                await query.edit_message_text("❌ Invalid wallet selection.")

        elif callback_data == 'manage_groups':
            keyboard = [
                [InlineKeyboardButton("Add Group", callback_data='add_group')],
                [InlineKeyboardButton("Remove Group", callback_data='remove_group')],
                [InlineKeyboardButton("List Groups", callback_data='list_groups')],
                [InlineKeyboardButton("Back to Main Menu", callback_data='main_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("📋 Group Management", reply_markup=reply_markup)
        
        elif callback_data == 'trading_settings':
            settings = self.trading_settings
            text = (
                "⚙️ *Trading Settings*\n\n"
                f"Initial Investment: {settings['initial_investment']} SOL\n"
                f"Take Profit: {settings['take_profit_percentage']}%\n"
                f"Sell Percentage at Take Profit: {settings['sell_percentage']}%\n"
                f"Max Slippage: {settings['max_slippage']}%"
            )
            
            keyboard = [
                [InlineKeyboardButton("Set Investment", callback_data='set_investment_prompt')],
                [InlineKeyboardButton("Set Take Profit", callback_data='set_take_profit_prompt')],
                [InlineKeyboardButton("Back to Main Menu", callback_data='main_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        elif callback_data == 'help':
            help_text = (
                "🤖 *Solana Trading Bot Help* 🤖\n\n"
                "*How it works:*\n"
                "1. Create a wallet or import an existing one\n"
                "2. Add Telegram groups to monitor\n"
                "3. Configure your trading settings\n"
                "4. The bot will automatically trade when new tokens are posted\n\n"
                
                "*Commands:*\n"
                "/start - Show main menu\n"
                "/help - Show this help\n"
                "/create_wallet - Create a new wallet\n"
                "/add_group - Add a group to monitor\n"
                "/settings - Configure trading parameters"
            )
            
            keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
        
        elif callback_data == 'main_menu':
            # Return to main menu
            keyboard = [
                [InlineKeyboardButton("Manage Wallets", callback_data='manage_wallets')],
                [InlineKeyboardButton("Create Wallet", callback_data='create_wallet')],
                [InlineKeyboardButton("Wallet Info", callback_data='wallet_info')],
                [InlineKeyboardButton("Manage Groups", callback_data='manage_groups')],
                [InlineKeyboardButton("Trading Settings", callback_data='trading_settings')],
                [InlineKeyboardButton("Help", callback_data='help')]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text("Main Menu", reply_markup=reply_markup)
        
        elif callback_data.startswith('remove_'):
            # Extract group link from callback data
            group_to_remove = callback_data[7:]  # Remove 'remove_' prefix
            
            if group_to_remove in self.monitored_groups:
                self.monitored_groups.remove(group_to_remove)
                self._save_monitored_groups()
                
                # Remove the listener for this group
                await self.telegram_listener.remove_group(group_to_remove)
                
                await query.edit_message_text(f"✅ Removed {group_to_remove} from monitored groups.")
            else:
                await query.edit_message_text(f"❌ Group not found in the monitored list.")
        
        elif callback_data == 'add_group':
            await query.edit_message_text(
                "Please send the Telegram group link using the /add_group command.\n"
                "Example: /add_group https://t.me/groupname"
            )
        
        elif callback_data == 'remove_group':
            if not self.monitored_groups:
                await query.edit_message_text("❌ No groups are currently being monitored.")
                return
            
            keyboard = []
            for group in self.monitored_groups:
                keyboard.append([InlineKeyboardButton(group, callback_data=f"remove_{group}")])
            
            keyboard.append([InlineKeyboardButton("Back", callback_data='manage_groups')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text("Select a group to remove:", reply_markup=reply_markup)
        
        elif callback_data == 'list_groups':
            if not self.monitored_groups:
                text = "⚠️ No groups are currently being monitored."
            else:
                text = "📋 *Monitored Groups:*\n\n"
                for i, group in enumerate(self.monitored_groups, 1):
                    text += f"{i}. {group}\n"
            
            keyboard = [[InlineKeyboardButton("Back", callback_data='manage_groups')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        elif callback_data == 'set_investment_prompt':
            await query.edit_message_text(
                "Please enter the initial investment amount using the /set_investment command.\n"
                "Example: /set_investment 0.5"
            )
        
        elif callback_data == 'set_take_profit_prompt':
            await query.edit_message_text(
                "Please set the take profit conditions using the /set_take_profit command.\n"
                "Format: /set_take_profit <profit_percentage> <sell_percentage>\n"
                "Example: /set_take_profit 30 50 - Sell 50% when profit reaches 30%"
            )

    async def text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages that aren't commands."""
        await update.message.reply_text(
            "I don't understand that message. Use /help to see available commands."
        )

    async def error_handler(self, update, context):
        """Handle errors."""
        # Log the error
        logger.error(f"Update {update} caused error {context.error}")
    
        # Check if the update has a message or a callback query
        if update and update.message:
            # If the update is a message, reply to the user via the message
            await update.message.reply_text(
                "❌ An error occurred. Please try again later."
            )
        elif update and update.callback_query:
            # If the update is a callback query, reply via the callback query
            await update.callback_query.answer(
                "❌ An error occurred. Please try again later.", show_alert=True
            )
        else:
            # If there's no clear way to respond, log it
            logger.warning("Error occurred, but no valid update object to reply to.")

    async def process_new_ca(self, ca_address, group_name):
        """Process a new crypto address found in a monitored group."""
        logger.info(f"New CA detected: {ca_address} from {group_name}")
        
        # First, notify about the new CA detection regardless of trading
        await self.notify_user(
            f"🔍 *New Token Detected*\n\n"
            f"Token Address: `{ca_address}`\n"
            f"Found in: {group_name}\n"
        )
        
        # Check if this token has already been traded
        if ca_address in self.trading_settings['traded_tokens']:
            await self.notify_user(
                f"ℹ️ *Trading Skipped*\n\n"
                f"Token: `{ca_address}`\n"
                f"Reason: Already traded previously"
            )
            return
        
        # Execute trade
        trade_result = await self.solana_trader.buy_token(
            ca_address, 
            self.trading_settings['initial_investment'],
            self.trading_settings['max_slippage']
        )
        
        if trade_result['success']:
            # Add to traded tokens list
            self.trading_settings['traded_tokens'].append(ca_address)
            self._save_trading_settings()
            
            # Start monitoring for take profit
            asyncio.create_task(self.monitor_token_price(
                ca_address,
                trade_result['price'],
                trade_result['amount']
            ))
            
            # Notify user about successful trade
            await self.notify_user(
                f"🚀 *New Token Trade*\n\n"
                f"Token: `{ca_address}`\n"
                f"Group: {group_name}\n"
                f"Amount: {self.trading_settings['initial_investment']} SOL\n"
                f"Tokens purchased: {trade_result['amount']}\n"
                f"Entry price: {trade_result['price']} SOL per token\n\n"
                f"Now monitoring for take profit at {self.trading_settings['take_profit_percentage']}%"
            )
        else:
            # Notify about failed trade
            await self.notify_user(
                f"⚠️ *Trade Failed*\n\n"
                f"Token: `{ca_address}`\n"
                f"Group: {group_name}\n"
                f"Error: {trade_result['error']}"
            )

    async def monitor_token_price(self, token_address, entry_price, token_amount):
        """Monitor token price and execute take profit if conditions are met."""
        take_profit_price = entry_price * (1 + self.trading_settings['take_profit_percentage'] / 100)
        sell_amount = token_amount * (self.trading_settings['sell_percentage'] / 100)
        
        logger.info(f"Starting price monitoring for {token_address}")
        logger.info(f"Entry price: {entry_price}, Take profit price: {take_profit_price}")
        
        # Keep monitoring until take profit is reached or max monitoring time passed
        max_monitoring_time = 60 * 60 * 24  # 24 hours
        monitoring_interval = 60  # Check every 60 seconds
        elapsed_time = 0
        
        while elapsed_time < max_monitoring_time:
            # Get current price
            current_price = await self.solana_trader.get_token_price(token_address)
            
            if current_price >= take_profit_price:
                # Execute take profit
                sell_result = await self.solana_trader.sell_token(
                    token_address,
                    sell_amount,
                    self.trading_settings['max_slippage']
                )
                
                if sell_result['success']:
                    # Calculate profit
                    profit = (sell_result['price'] - entry_price) * sell_amount
                    profit_percentage = ((sell_result['price'] / entry_price) - 1) * 100
                    
                    # Notify user
                    await self.notify_user(
                        f"💰 *Take Profit Executed*\n\n"
                        f"Token: `{token_address}`\n"
                        f"Sold: {sell_amount} tokens ({self.trading_settings['sell_percentage']}% of position)\n"
                        f"Entry price: {entry_price} SOL\n"
                        f"Exit price: {sell_result['price']} SOL\n"
                        f"Profit: {profit:.4f} SOL ({profit_percentage:.2f}%)"
                    )
                    
                    # If we sold 100%, stop monitoring
                    if self.trading_settings['sell_percentage'] >= 100:
                        return
                    
                    # Update monitoring parameters for the remaining position
                    token_amount -= sell_amount
                    take_profit_price = sell_result['price'] * 1.1  # New take profit at +10% from current
                else:
                    # Notify about failed sell
                    await self.notify_user(
                        f"⚠️ *Take Profit Failed*\n\n"
                        f"Token: `{token_address}`\n"
                        f"Error: {sell_result['error']}"
                    )
            
            # Wait before next check
            await asyncio.sleep(monitoring_interval)
            elapsed_time += monitoring_interval

    async def notify_user(self, message):
        """Notify the user about important events."""
        try:
            # Get the most recent chat ID from context or configuration
            # You should store this when the user first interacts with the bot (/start command)
            if hasattr(self, 'user_chat_id'):
                await self.telegram_bot.bot.send_message(
                    chat_id=self.user_chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}")

    async def run(self):
        """Run the bot."""
        # Start the Telegram listener
        await self.telegram_listener.start(self.monitored_groups)

        # Start polling and block until stopped
        await self.telegram_bot.run_polling()

        logger.info("Bot started!")


async def main():
    """Main function."""
    bot = TradingBot()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
