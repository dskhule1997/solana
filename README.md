# Solana Trading Bot

A Telegram bot that monitors specified groups for new Solana token addresses and automatically trades them based on user-defined rules.

## Features

- **Telegram Group Monitoring**: Watches specified Telegram groups for new Solana token addresses
- **Automatic Trading**: Executes trades when new tokens are detected using Jupiter API
- **Take Profit**: Automatically sells tokens when they reach specified profit targets
- **Wallet Management**: Create and manage Solana wallets directly from the bot
- **User-friendly Interface**: Interact with the bot using commands and buttons in Telegram

## Setup Instructions

### Prerequisites

- Python 3.9+
- Telegram account
- Telegram bot token (created via BotFather)
- Telegram API credentials (api_id and api_hash)

### Installation

1. Clone this repository or download the files:

```bash
git clone https://github.com/yourusername/solana-trading-bot.git
cd solana-trading-bot
```

2. Install the required packages:

```bash
pip install -r requirements.txt
```

### Configuration

1. Create a `credentials.txt` file with the following content:

```
api_id=
api_hash=
bot_token=
```

Replace the values with your actual credentials if they differ.

2. Create an initial `monitored_groups.txt` file (optional):

```
https://t.me/
https://t.me/
```

### Running the Bot

Start the bot by running:

```bash
python main.py
```

## Usage

Once the bot is running, you can interact with it using the following commands in Telegram:

### Wallet Commands

- `/start` - Display the main menu
- `/create_wallet` - Create a new Solana wallet
- `/wallet_info` - Display your current wallet info
- `/withdraw <amount> <address>` - Withdraw funds to another wallet

### Group Management

- `/add_group <group_link>` - Add a Telegram group to monitor
- `/remove_group` - Shows a list of groups to remove
- `/list_groups` - List all monitored groups

### Trading Settings

- `/settings` - View current trading settings
- `/set_investment <amount>` - Set initial investment amount in SOL
- `/set_take_profit <profit_percentage> <sell_percentage>` - Set take profit conditions
  - Example: `/set_take_profit 30 50` - Sell 50% when profit reaches 30%

### Other Commands

- `/help` - Display the help message

## Project Structure

- `main.py` - Main bot file that ties everything together
- `telegram_listener.py` - Module for monitoring Telegram groups
- `solana_trader.py` - Module for interacting with Solana blockchain and Jupiter API
- `credentials.txt` - Contains Telegram API credentials
- `wallet_credentials.txt` - Contains wallet information (created when you generate a wallet)
- `monitored_groups.txt` - List of Telegram groups to monitor
- `trading_settings.json` - Trading parameters and configuration

## Security Considerations

This bot stores sensitive information like private keys in plain text files. For production use, consider:

1. Using encrypted storage for private keys
2. Running the bot on a secure, dedicated server
3. Implementing additional security measures

## Disclaimer

This bot is provided for educational purposes only. Trading cryptocurrencies involves significant risk. Use at your own risk.
