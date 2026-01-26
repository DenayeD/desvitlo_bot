from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import sqlite3
from datetime import datetime, timedelta

from formatting.keyboard_builder import get_queue_keyboard, get_main_menu
from config.settings import ADMIN_USER_ID
from core.states import BroadcastStates

router = Router()

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 <b>Вітаю!</b> Оберіть свою підчергу:", reply_markup=get_queue_keyboard(), parse_mode="HTML")
    await message.answer("Керування ботом 👇", reply_markup=get_main_menu())

@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_USER_ID:  
        await message.answer("❌ Доступ заборонено.")
        return
    
    await state.set_state(BroadcastStates.waiting_for_message)
    await message.answer("📝 Надішліть повідомлення для розсилки всім користувачам.")

@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_USER_ID:
        await message.answer("❌ Доступ заборонено.")
        return
    
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # Загальна статистика
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM addresses')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM addresses')
    total_addresses = cursor.fetchone()[0]
    
    # Статистика по чергах
    cursor.execute('SELECT subqueue, COUNT(*) FROM addresses GROUP BY subqueue ORDER BY subqueue')
    subqueue_stats = cursor.fetchall()
    
    # Користувачі з налаштованими сповіщеннями
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM user_notifications')
    users_with_config = cursor.fetchone()[0]
    
    # Користувачі з увімкненими сповіщеннями
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM user_notifications WHERE notifications_enabled = 1')
    users_with_notifications = cursor.fetchone()[0]
    
    # Загальна кількість відправлених сповіщень
    cursor.execute('SELECT COUNT(*) FROM sent_alerts')
    total_alerts = cursor.fetchone()[0]
    
    # Сповіщення за останні 7 днів
    cursor.execute('SELECT COUNT(*) FROM sent_alerts WHERE event_date >= ?', 
                   ((datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),))
    recent_alerts = cursor.fetchone()[0]
    
    conn.close()
    
    # Формуємо повідомлення
    stats_text = f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
    stats_text += f"👥 <b>Користувачі:</b> {total_users}\n"
    stats_text += f"🏠 <b>Адрес:</b> {total_addresses}\n"
    stats_text += f"⚙️ <b>З налаштованими сповіщеннями:</b> {users_with_config}\n"
    stats_text += f"🔔 <b>З увімкненими сповіщеннями:</b> {users_with_notifications}\n\n"
    
    stats_text += f"📋 <b>Розподіл по чергах:</b>\n"
    for subq, count in subqueue_stats:
        stats_text += f"  {subq}: {count} адрес\n"
    
    stats_text += f"\n📨 <b>Сповіщення:</b>\n"
    stats_text += f"  Загалом: {total_alerts}\n"
    stats_text += f"  За 7 днів: {recent_alerts}\n"
    
    await message.answer(stats_text, parse_mode="HTML")

@router.message(Command("manual_schedule"))
async def cmd_manual_schedule(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_USER_ID:
        await message.answer("❌ Доступ заборонено.")
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Додати графік", callback_data="manual_add")],
        [InlineKeyboardButton(text="📝 Редагувати графік", callback_data="manual_edit")],
        [InlineKeyboardButton(text="🗑️ Видалити графік", callback_data="manual_delete")],
        [InlineKeyboardButton(text="👁️ Переглянути графіки", callback_data="manual_view")]
    ])
    
    await message.answer("🔧 <b>УПРАВЛІННЯ РУЧНИМИ ГРАФІКАМИ</b>\n\nОберіть дію:", reply_markup=kb, parse_mode="HTML")