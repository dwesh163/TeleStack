import os
import logging
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
import openstack
from openstack.connection import Connection

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OS_CLOUD = os.getenv('OS_CLOUD')
TELEGRAM_ALLOWED_CHAT_IDS = os.getenv('TELEGRAM_ALLOWED_CHAT_IDS').split(',')


# Check for necessary environment variables
if not all([TELEGRAM_TOKEN, OS_CLOUD]):
    logging.error("Missing required environment variables.")
    raise EnvironmentError("Please set TELEGRAM_BOT_TOKEN, OS_CLOUD, OS_USERNAME, and OS_PASSWORD.")


# Function to connect to OpenStack
def connect_to_openstack() -> Connection:
    try:
        return openstack.connect(cloud=OS_CLOUD)
    except Exception as e:
        logging.error(f"Failed to connect to OpenStack: {e}")
        raise

# Command handler for the /start command
async def start(update: Update, context) -> None:
    keyboard = [
        [InlineKeyboardButton("Start All", callback_data='start_all')],
        [InlineKeyboardButton("Stop All", callback_data='stop_all')],
        [InlineKeyboardButton("View Machines", callback_data='view_machines')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Choose an action:', reply_markup=reply_markup)

# Callback query handler
async def button(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    if str(chat_id) not in TELEGRAM_ALLOWED_CHAT_IDS:
        await query.edit_message_text(text="Access Denied.")
        return

    conn = connect_to_openstack()

    try:
        if query.data == 'start_all':
            await handle_start_all(query, conn)
        elif query.data == 'stop_all':
            await handle_stop_all(query, conn)
        elif query.data == 'view_machines':
            await handle_view_machines(query, conn)
        elif query.data.startswith("details_"):
            await handle_details(query, conn)
        elif query.data.startswith("start_"):
            await handle_start(query, conn)
        elif query.data.startswith("stop_"):
            await handle_stop(query, conn)
        elif query.data.startswith("reboot_"):
            await handle_reboot(query, conn)
    
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        query.edit_message_text(text="An error occurred while processing your request.")

# Helper functions
async def handle_start_all(query, conn) -> None:
    machines = conn.compute.servers()
    for machine in machines:
        conn.compute.start_server(machine.id)
    await query.edit_message_text(text="All machines started.")

async def handle_stop_all(query, conn) -> None:
    machines = conn.compute.servers()
    for machine in machines:
        conn.compute.stop_server(machine.id)
    await query.edit_message_text(text="All machines stopped.")

async def handle_view_machines(query, conn) -> None:
    machines = conn.compute.servers()
    keyboard = [[InlineKeyboardButton(f"{machine.name}", callback_data=f"details_{machine.id}")] for machine in machines]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text="Select a machine:", reply_markup=reply_markup)

async def handle_details(query, conn) -> None:
    machine_id = query.data.split("_")[1]
    machine = conn.compute.get_server(machine_id)
    keyboard = [
        [InlineKeyboardButton("Start", callback_data=f"start_{machine_id}")],
        [InlineKeyboardButton("Stop", callback_data=f"stop_{machine_id}")],
        [InlineKeyboardButton("Reboot", callback_data=f"reboot_{machine_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=f"Machine: {machine.name}\nStatus: {machine.status}", reply_markup=reply_markup)

async def handle_start(query, conn) -> None:
    machine_id = query.data.split("_")[1]
    conn.compute.start_server(machine_id)
    await query.edit_message_text(text="Machine started.")

async def handle_stop(query, conn) -> None:
    machine_id = query.data.split("_")[1]
    conn.compute.stop_server(machine_id)
    await query.edit_message_text(text="Machine stopped.")

async def handle_reboot(query, conn) -> None:
    machine_id = query.data.split("_")[1]
    conn.compute.reboot_server(machine_id, reboot_type='SOFT')
    await query.edit_message_text(text="Machine rebooted.")

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    
    main()
