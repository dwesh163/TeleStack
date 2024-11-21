import os
import re
import logging
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import openstack
from openstack.connection import Connection

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_ALLOWED_CHAT_IDS = os.getenv('TELEGRAM_ALLOWED_CHAT_IDS').split(',')

OS_CLOUD = os.getenv('OS_CLOUD')
OS_ALLOWED_PROJECTS = os.getenv('OS_ALLOWED_PROJECTS').split(',')

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
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_main_menu(update, context)

# Command handler for the /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "🤖 OpenStack Bot Help:\n\n"
        "/start - Start the bot and show main menu\n"
        "/help - Show this help message\n"
        "/status - Show overall system status\n"
        "Use the buttons to navigate and control your OpenStack machines."
    )
    await update.message.reply_text(help_text, reply_markup=get_back_to_main_keyboard())

# Command handler for the /status command
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = connect_to_openstack()
    machines = conn.compute.servers()
    allowed_machines = [machine for machine in machines if machine.name in OS_ALLOWED_PROJECTS]
    
    total = len(allowed_machines)
    active = sum(1 for m in allowed_machines if m.status.lower() == 'active')
    shutoff = sum(1 for m in allowed_machines if m.status.lower() == 'shutoff')
    other = total - active - shutoff

    status_text = (
        "📊 System Status:\n\n"
        f"Total Machines: {total}\n"
        f"🟢 Active: {active}\n"
        f"🔴 Shutoff: {shutoff}\n"
        f"⚪ Other: {other}\n"
    )
    await update.message.reply_text(status_text, reply_markup=get_back_to_main_keyboard())

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🖥️ View Machines", callback_data='view_machines')],
        [InlineKeyboardButton("▶️ Start All", callback_data='start_all'),
         InlineKeyboardButton("⏹️ Stop All", callback_data='stop_all')],
        [InlineKeyboardButton("📊 System Status", callback_data='system_status')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = 'Welcome to OpenStack Bot! 👋 Choose an action:'
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)

# Callback query handler
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    if str(chat_id) not in TELEGRAM_ALLOWED_CHAT_IDS:
        await query.edit_message_text(text="⛔ Access Denied.")
        return

    conn = connect_to_openstack()

    try:
        if query.data == 'start_all':
            logging.warn(f"[{chat_id}] Starting all machines.")
            await handle_start_all(query, conn)
        elif query.data == 'stop_all':
            logging.warn(f"[{chat_id}] Stopping all machines.")
            await handle_stop_all(query, conn)
        elif query.data == 'view_machines':
            logging.warn(f"[{chat_id}] Viewing machines.")
            await handle_view_machines(query, conn)
        elif query.data.startswith("details_"):
            await handle_details(query, conn, chat_id)
        elif query.data.startswith("start_"):
            await handle_start(query, conn, chat_id)
        elif query.data.startswith("stop_"):
            await handle_stop(query, conn, chat_id)
        elif query.data.startswith("reboot_"):
            await handle_reboot(query, conn, chat_id)
        elif query.data == 'system_status':
            await handle_system_status(query, conn)
        elif query.data == 'back_to_main':
            await show_main_menu(update, context)
    
    except Exception as e:
        logging.error(f"Error in button handler: {str(e)}")
        error_text = "An unexpected error occurred. Please try again later."
        await query.edit_message_text(text=f"❌ {error_text}", reply_markup=get_back_to_main_keyboard())

# Helper functions
async def handle_start_all(query: Update.callback_query, conn: Connection) -> None:
    machines = conn.compute.servers()
    started_count = 0
    for machine in machines:
        if machine.name in OS_ALLOWED_PROJECTS and machine.status.lower() != 'active':
            conn.compute.start_server(machine.id)
            started_count += 1
    await query.edit_message_text(text=f"▶️ Started {started_count} machine(s).", reply_markup=get_back_to_main_keyboard())

async def handle_stop_all(query: Update.callback_query, conn: Connection) -> None:
    machines = conn.compute.servers()
    stopped_count = 0
    for machine in machines:
        if machine.name in OS_ALLOWED_PROJECTS and machine.status.lower() != 'shutoff':
            conn.compute.stop_server(machine.id)
            stopped_count += 1
    await query.edit_message_text(text=f"⏹️ Stopped {stopped_count} machine(s).", reply_markup=get_back_to_main_keyboard())

async def handle_view_machines(query: Update.callback_query, conn: Connection) -> None:
    machines = conn.compute.servers()
    allowed_machines = [
        machine for machine in machines
        if machine.name in OS_ALLOWED_PROJECTS
    ]
    
    if not allowed_machines:
        await query.edit_message_text(text="No machines available.", reply_markup=get_back_to_main_keyboard())
        return
    
    keyboard = [
        [InlineKeyboardButton(f"{machine.name} : {get_status_emoji(machine.status)}", callback_data=f"details_{machine.id}")]
        for machine in allowed_machines
    ]
    keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data='back_to_main')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text="Select a machine:", reply_markup=reply_markup)

async def handle_details(query: Update.callback_query, conn: Connection, chat_id) -> None:
    machine_id = query.data.split("_")[1]
    machine = conn.compute.get_server(machine_id)
    flavor = conn.compute.find_flavor(machine.flavor.id)
    logging.warn(f"[{chat_id}] Viewing {machine.name} details.")
    
    details = (f"🖥️ Machine: {machine.name}\n"
               f"Status: {get_status_emoji(machine.status)} {machine.status}\n"
               f"Flavor: {flavor.name}\n"
               f"RAM: {flavor.ram} MB\n"
               f"vCPUs: {flavor.vcpus}\n"
               f"Disk: {flavor.disk} GB")
    
    keyboard = [
        [InlineKeyboardButton("▶️ Start", callback_data=f"start_{machine_id}"),
         InlineKeyboardButton("⏹️ Stop", callback_data=f"stop_{machine_id}"),
         InlineKeyboardButton("🔄 Reboot", callback_data=f"reboot_{machine_id}")],
        [InlineKeyboardButton("🔙 Back to Machine List", callback_data='view_machines')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=details, reply_markup=reply_markup)

async def handle_start(query: Update.callback_query, conn: Connection, chat_id) -> None:
    machine_id = query.data.split("_")[1]
    machine = conn.compute.get_server(machine_id)
    logging.warn(f"[{chat_id}] Starting {machine.name}.")
    if machine.name not in OS_ALLOWED_PROJECTS:
        await query.edit_message_text(text="⛔ Access Denied: This machine is not in your allowed projects.", reply_markup=get_back_to_main_keyboard())
        return
    conn.compute.start_server(machine_id)
    await query.edit_message_text(text=f"▶️ Starting machine: {machine.name}", reply_markup=get_back_to_main_keyboard())

async def handle_stop(query: Update.callback_query, conn: Connection, chat_id) -> None:
    machine_id = query.data.split("_")[1]
    machine = conn.compute.get_server(machine_id)
    logging.warn(f"[{chat_id}] Stopping {machine.name}.")
    if machine.name not in OS_ALLOWED_PROJECTS:
        await query.edit_message_text(text="⛔ Access Denied: This machine is not in your allowed projects.", reply_markup=get_back_to_main_keyboard())
        return
    conn.compute.stop_server(machine_id)
    await query.edit_message_text(text=f"⏹️ Stopping machine: {machine.name}", reply_markup=get_back_to_main_keyboard())

async def handle_reboot(query: Update.callback_query, conn: Connection, chat_id) -> None:
    machine_id = query.data.split("_")[1]
    machine = conn.compute.get_server(machine_id)
    logging.warn(f"[{chat_id}] Rebooting {machine.name}.")
    if machine.name not in OS_ALLOWED_PROJECTS:
        await query.edit_message_text(text="⛔ Access Denied: This machine is not in your allowed projects.", reply_markup=get_back_to_main_keyboard())
        return
    conn.compute.reboot_server(machine_id, reboot_type='SOFT')
    await query.edit_message_text(text=f"🔄 Rebooting machine: {machine.name}", reply_markup=get_back_to_main_keyboard())

async def handle_system_status(query: Update.callback_query, conn: Connection) -> None:
    machines = conn.compute.servers()
    allowed_machines = [machine for machine in machines if machine.name in OS_ALLOWED_PROJECTS]
    
    total = len(allowed_machines)
    active = sum(1 for m in allowed_machines if m.status.lower() == 'active')
    shutoff = sum(1 for m in allowed_machines if m.status.lower() == 'shutoff')
    other = total - active - shutoff

    status_text = (
        "📊 System Status:\n\n"
        f"Total Machines: {total}\n"
        f"🟢 Active: {active}\n"
        f"🔴 Shutoff: {shutoff}\n"
        f"⚪ Other: {other}\n"
    )
    await query.edit_message_text(text=status_text, reply_markup=get_back_to_main_keyboard())

def get_status_emoji(status: str) -> str:
    status = status.lower()
    if status == 'active':
        return '🟢'
    elif status == 'shutoff':
        return '🔴'
    elif status in ['build', 'rebuild']:
        return '🟡'
    else:
        return '⚪'

def get_back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data='back_to_main')]])

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CallbackQueryHandler(button))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING)
    
    main()
