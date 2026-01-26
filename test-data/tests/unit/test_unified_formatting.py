# Тестуємо нову функцію format_all_periods
def merge_consecutive_intervals(intervals):
    """Об'єднує інтервали, які йдуть підряд"""
    if not intervals:
        return intervals

    # Сортуємо інтервали за початковим часом
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_intervals[0]]

    for start, end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        # Якщо поточний інтервал починається відразу після попереднього
        if start == last_end:
            # Об'єднуємо інтервали
            merged[-1] = (last_start, end)
        else:
            # Додаємо новий інтервал
            merged.append((start, end))

    return merged

def format_all_periods(intervals):
    """
    Форматує всі періоди (відключення + електропостачання) в одному блоці
    Кожен період на окремому рядку, відсортовані за часом
    """
    # Об'єднуємо гарантовані інтервали
    guaranteed = merge_consecutive_intervals(intervals['guaranteed'])
    possible = merge_consecutive_intervals(intervals['possible'])
    
    # Збираємо всі періоди відключень
    all_outages = []
    for start, end in guaranteed:
        all_outages.append((start, end, '🔴', 'guaranteed'))
    for start, end in possible:
        all_outages.append((start, end, '🟡', 'possible'))
    
    # Сортуємо відключення за часом
    all_outages.sort(key=lambda x: x[0])
    
    # Збираємо всі періоди електропостачання
    power_periods = []
    current_time = 0
    
    for start, end, emoji, outage_type in all_outages:
        if current_time < start:
            power_periods.append((current_time, start, '🟢', 'power'))
        current_time = max(current_time, end)
    
    if current_time < 24:
        power_periods.append((current_time, 24, '🟢', 'power'))
    
    # Об'єднуємо всі періоди
    all_periods = all_outages + power_periods
    
    # Сортуємо за часом початку
    all_periods.sort(key=lambda x: x[0])
    
    # Форматуємо кожен період на окремому рядку
    formatted_lines = []
    for start, end, emoji, period_type in all_periods:
        time_str = f"{start:02d}:00-{end:02d}:00"
        formatted_lines.append(f"{emoji} {time_str}")
    
    return formatted_lines

# Тестові дані
intervals = {
    'guaranteed': [(3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (11, 12), (12, 13), (13, 14), (14, 15), (15, 16), (16, 17), (19, 20), (20, 21), (21, 22), (22, 23), (23, 24)],
    'possible': [(0, 1)]
}

print("Тестові дані для черги 3.1:")
print(f"Гарантовані відключення: {intervals['guaranteed']}")
print(f"Можливі відключення: {intervals['possible']}")
print()

formatted_periods = format_all_periods(intervals)

print("Новий формат ПЕРІОДИ:")
for line in formatted_periods:
    print(line)
print()

print("Пояснення:")
print("🟡 - електропостачання можливе")
print("🔴 - електропостачання вимкнене")
print("🟢 - електропостачання увімкнене")