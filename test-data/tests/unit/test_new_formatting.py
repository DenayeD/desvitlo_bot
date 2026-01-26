# Тестуємо нову функціональність з періодами електропостачання
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

def format_outages_compact(intervals):
    """Форматує відключення в компактному вигляді"""
    guaranteed = merge_consecutive_intervals(intervals['guaranteed'])
    possible = merge_consecutive_intervals(intervals['possible'])

    all_intervals = []
    for start, end in guaranteed:
        all_intervals.append((start, end, 'guaranteed'))
    for start, end in possible:
        all_intervals.append((start, end, 'possible'))

    all_intervals.sort(key=lambda x: x[0])

    formatted = []
    for start, end, outage_type in all_intervals:
        time_str = f"{start:02d}:00-{end:02d}:00"
        if outage_type == 'guaranteed':
            formatted.append(f"🔴 {time_str}")
        else:
            formatted.append(f"🟡 {time_str}")

    return formatted

def format_power_periods(intervals):
    """Форматує періоди електропостачання"""
    all_outages = []
    for start, end in intervals['guaranteed']:
        all_outages.append((start, end, 'guaranteed'))
    for start, end in intervals['possible']:
        all_outages.append((start, end, 'possible'))

    all_outages.sort(key=lambda x: x[0])

    power_periods = []
    current_time = 0

    for start, end, outage_type in all_outages:
        if current_time < start:
            power_periods.append((current_time, start))
        current_time = max(current_time, end)

    if current_time < 24:
        power_periods.append((current_time, 24))

    formatted = []
    for start, end in power_periods:
        time_str = f"{start:02d}:00-{end:02d}:00"
        formatted.append(f"🟢 {time_str}")

    return formatted

# Тестові дані
intervals = {
    'guaranteed': [(3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (11, 12), (12, 13), (13, 14), (14, 15), (15, 16), (16, 17), (19, 20), (20, 21), (21, 22), (22, 23), (23, 24)],
    'possible': [(0, 1)]
}

print("Тестові дані для черги 3.1:")
print(f"Гарантовані відключення: {intervals['guaranteed']}")
print(f"Можливі відключення: {intervals['possible']}")
print()

formatted_outages = format_outages_compact(intervals)
formatted_power = format_power_periods(intervals)

print("ПЕРІОДИ ВІДКЛЮЧЕНЬ:")
print(" | ".join(formatted_outages))
print()
print("🔴 - електропостачання вимкнене | 🟡 - електропостачання можливе")
print()

print("ПЕРІОДИ ЕЛЕКТРОПОСТАЧАННЯ:")
print(" | ".join(formatted_power))
print()
print("🟢 - електропостачання увімкнене")