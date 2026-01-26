# Тестуємо логіку форматування без імпорту
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
    """
    Форматує відключення в компактному вигляді з об'єднанням інтервалів
    Повертає список рядків для відображення
    """
    # Об'єднуємо гарантовані інтервали
    guaranteed = merge_consecutive_intervals(intervals['guaranteed'])
    possible = merge_consecutive_intervals(intervals['possible'])

    # Створюємо список всіх інтервалів з типом
    all_intervals = []
    for start, end in guaranteed:
        all_intervals.append((start, end, 'guaranteed'))
    for start, end in possible:
        all_intervals.append((start, end, 'possible'))

    # Сортуємо за часом
    all_intervals.sort(key=lambda x: x[0])

    # Форматуємо
    formatted = []
    for start, end, outage_type in all_intervals:
        time_str = f"{start:02d}:00-{end:02d}:00"
        if outage_type == 'guaranteed':
            formatted.append(f"🔴 {time_str}")
        else:  # possible
            formatted.append(f"🟡 {time_str}")

    return formatted

# Тестові дані
intervals = {
    'guaranteed': [(3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (11, 12), (12, 13), (13, 14), (14, 15), (15, 16), (16, 17), (19, 20), (20, 21), (21, 22), (22, 23), (23, 24)],
    'possible': [(0, 1)]
}

print("Оригінальні інтервали:")
print(f"Гарантовані: {intervals['guaranteed']}")
print(f"Можливі: {intervals['possible']}")
print()

formatted = format_outages_compact(intervals)
print("Форматований вивід:")
print(" | ".join(formatted))
print()
print("🔴 - гарантовано немає світла | 🟡 - можливо немає світла")