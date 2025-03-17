import logging
import re
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import Channel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramListener:
    def __init__(self, api_id, api_hash, bot_token, callback):
        """
        Initialize the Telegram listener.
        
        Args:
            api_id: Telegram API ID
            api_hash: Telegram API hash
            bot_token: Telegram bot token
            callback: Function to call when a new CA is found
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.bot_token = bot_token
        self.callback = callback
        self.client = None
        self.running = False
        self.monitored_groups = set()
        self.processed_cas = set()  # To avoid processing duplicates
        
        # Regex pattern for Solana addresses (base58 encoded, 32-44 chars)
        self.solana_address_pattern = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')

    async def start(self, initial_groups=None):
        """Start monitoring Telegram groups."""
        if not self.api_id or not self.api_hash or not self.bot_token:
            logger.error("API credentials or bot token not provided")
            return False
        
        # Create a new client
        self.client = TelegramClient('solana_bot_session', self.api_id, self.api_hash)
        await self.client.start(bot_token=self.bot_token)
        
        logger.info("Telegram client started")
        self.running = True
        
        # Add initial groups if provided
        if initial_groups:
            for group in initial_groups:
                await self.add_group(group)
        
        # Register the message handler
        self.client.add_event_handler(
            self.message_handler,
            events.NewMessage()
        )
        # In telegram_listener.py, modify the message_handler function:
    async def message_handler(self, event):
        # Skip messages from non-monitored groups
        chat = await event.get_chat()
        if chat not in self.monitored_groups:
            return
        
        # Skip edits, forwards, and replies
        if event.message.forward or event.message.reply_to:
            return
            
        # Get message text
        message_text = event.message.text
        
        # Find Solana addresses in the message
        addresses = self.solana_address_pattern.findall(message_text)
        
        if addresses:
            group_entity = await event.get_chat()
            group_name = getattr(group_entity, 'title', str(group_entity.id))
            
            for address in addresses:
                logger.info(f"Found new CA: {address} in {group_name}")
                
                # Call the callback function for each address found
                if self.callback:
                    await self.callback(address, group_name)

    async def add_group(self, group_url):
        """Add a group to monitor."""
        if not self.running:
            logger.error("Telegram client not running")
            return False
        
        try:
            # Convert group URL to username
            if group_url.startswith("https://t.me/"):
                group_username = group_url.split("https://t.me/")[1]
            else:
                group_username = group_url
            
            # Try to join the group
            entity = await self.client.get_entity(group_username)
            
            # Add to monitored groups
            self.monitored_groups.add(entity)
            
            logger.info(f"Added group {group_username} to monitoring")
            return True
            
        except Exception as e:
            logger.error(f"Error adding group {group_url}: {str(e)}")
            return False

    async def remove_group(self, group_url):
        """Remove a group from monitoring."""
        if not self.running:
            logger.error("Telegram client not running")
            return False
        
        try:
            # Convert group URL to username
            if group_url.startswith("https://t.me/"):
                group_username = group_url.split("https://t.me/")[1]
            else:
                group_username = group_url
            
            # Find and remove the group
            group_to_remove = None
            for group in self.monitored_groups:
                if isinstance(group, Channel):
                    if group.username == group_username:
                        group_to_remove = group
                        break
                elif str(group) == group_username:
                    group_to_remove = group
                    break

            if group_to_remove:
                self.monitored_groups.remove(group_to_remove)
                logger.info(f"Removed group {group_username} from monitoring")
                return True
            else:
                logger.warning(f"Group {group_username} not found in monitored groups")
                return False
                
        except Exception as e:
            logger.error(f"Error removing group {group_url}: {str(e)}")
            return False

    async def stop(self):
        """Stop the listener."""
        if self.client:
            await self.client.disconnect()
            self.client = None
        self.running = False
        logger.info("Telegram listener stopped")
