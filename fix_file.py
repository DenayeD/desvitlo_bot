with open('handlers/callbacks.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the corruption
lines = content.split('\n')
for i, line in enumerate(lines):
    if '2♦' in line or '♦' in line:
        print(f'Corruption starts at line {i}')
        # Keep only good lines
        good_content = '\n'.join(lines[:i])
        good_content += '''
    await send_schedule_logic(callback.from_user.id, addr_data, "today")
    await callback.message.edit_text(f"📊 Графік для адреси <b>{addr_name}</b> надіслано в особисті повідомлення.", parse_mode="HTML")
    await callback.answer()
'''
        with open('handlers/callbacks.py', 'w', encoding='utf-8') as f:
            f.write(good_content)
        print('Fixed successfully')
        break